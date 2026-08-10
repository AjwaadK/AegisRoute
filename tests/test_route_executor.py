import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from app.config import ProviderRetrySettings, ProviderRouteSettings
from app.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderInternalError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.observability.metrics import NoopApplicationMetrics
from app.providers.base import ProviderAdapter
from app.providers.executor import ProviderExecutor, RetryPolicy
from app.routing.contracts import RouteCandidate, RoutingDecision
from app.routing.executor import RouteExecutor
from app.routing.provider_registry import ProviderRegistry
from app.schemas.generation import ChatMessage, GenerateRequest, ProviderResult


class MutableClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ScriptedProvider(ProviderAdapter):
    def __init__(
        self,
        provider_name: str,
        outcomes: list[str | BaseException],
        *,
        before_outcome: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.provider_name = provider_name
        self.outcomes = outcomes
        self.before_outcome = before_outcome
        self.attempts = 0

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        self.attempts += 1
        if self.before_outcome is not None:
            self.before_outcome()
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return ProviderResult(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output=outcome,
            input_tokens=1,
            output_tokens=1,
        )


class RecordingMetrics(NoopApplicationMetrics):
    def __init__(self) -> None:
        self.fallbacks: list[tuple[str, str, str]] = []
        self.retries: list[tuple[str, str]] = []

    def record_provider_fallback(
        self, from_provider: str, to_provider: str, reason: str
    ) -> None:
        self.fallbacks.append((from_provider, to_provider, reason))

    def record_provider_retry(self, provider: str, error_type: str) -> None:
        self.retries.append((provider, error_type))


class CapturingProviderExecutor(ProviderExecutor):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.elapsed_budgets: list[float] = []

    async def execute(self, *args: object, **kwargs: object) -> ProviderResult:
        self.elapsed_budgets.append(float(kwargs["elapsed_request_seconds"]))
        return await super().execute(*args, **kwargs)  # type: ignore[arg-type]


def request() -> GenerateRequest:
    return GenerateRequest(
        model="model-v1",
        messages=[ChatMessage(role="user", content="hello")],
    )


def decision(*providers: str) -> RoutingDecision:
    return RoutingDecision(
        requested_model="model-v1",
        selected_model="model-v1",
        provider_name=providers[0],
        reason="test order",
        fallback_candidates=tuple(
            RouteCandidate(provider_name, "model-v1") for provider_name in providers[1:]
        ),
    )


def executor(
    providers: list[ScriptedProvider],
    *,
    max_route_attempts: int = 3,
    max_provider_attempts: int = 1,
    deadline: float = 10,
    minimum_budget: float = 0.1,
    clock: MutableClock | None = None,
    capturing: bool = False,
) -> RouteExecutor:
    configured_clock = clock or MutableClock()
    retry = RetryPolicy(
        ProviderRetrySettings(
            max_attempts=max_provider_attempts,
            base_delay_seconds=0,
            max_delay_seconds=0,
            request_deadline_seconds=deadline,
            min_attempt_budget_seconds=minimum_budget,
        ),
        jitter=lambda _lower, _upper: 0,
    )
    executor_type = CapturingProviderExecutor if capturing else ProviderExecutor
    provider_executor = executor_type(
        retry,
        clock=configured_clock,
        sleep=lambda _delay: asyncio.sleep(0),
    )
    return RouteExecutor(
        ProviderRegistry(providers),
        provider_executor,
        ProviderRouteSettings(max_route_attempts),
        clock=configured_clock,
    )


def run(
    route_executor: RouteExecutor,
    route_decision: RoutingDecision,
    metrics: RecordingMetrics | None = None,
) -> ProviderResult:
    return asyncio.run(
        route_executor.execute(
            route_decision,
            request(),
            "request-1",
            metrics or RecordingMetrics(),
        )
    )


def test_primary_success_returns_without_fallback() -> None:
    primary = ScriptedProvider("primary", ["ok"])
    fallback = ScriptedProvider("fallback", ["unused"])
    metrics = RecordingMetrics()

    result = run(
        executor([primary, fallback]), decision("primary", "fallback"), metrics
    )

    assert result.output == "ok"
    assert primary.attempts == 1
    assert fallback.attempts == 0
    assert metrics.fallbacks == []


@pytest.mark.parametrize(
    "error_type",
    [
        ProviderTimeoutError,
        ProviderRateLimitError,
        ProviderUnavailableError,
        ProviderInternalError,
    ],
)
def test_fallbackable_primary_failure_can_succeed_on_fallback(
    error_type: type[ProviderError],
) -> None:
    primary = ScriptedProvider("primary", [error_type("primary")])
    fallback = ScriptedProvider("fallback", ["ok"])
    metrics = RecordingMetrics()

    result = run(
        executor([primary, fallback]), decision("primary", "fallback"), metrics
    )

    assert result.provider == "fallback"
    assert metrics.fallbacks == [("primary", "fallback", error_type.__name__)]


def test_fallback_log_uses_bounded_structured_route_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged_events: list[tuple[str, dict[str, Any]]] = []

    def capture_event(event: str, **fields: Any) -> None:
        logged_events.append((event, fields))

    monkeypatch.setattr("app.routing.executor.log_event", capture_event)
    primary = ScriptedProvider(
        "primary",
        [ProviderTimeoutError("primary", message="unrestricted secret message")],
    )
    fallback = ScriptedProvider("fallback", ["ok"])

    run(executor([primary, fallback]), decision("primary", "fallback"))

    event_name, event_fields = next(
        logged_event
        for logged_event in logged_events
        if logged_event[0] == "provider_fallback_scheduled"
    )
    assert event_name == "provider_fallback_scheduled"
    assert event_fields == {
        "request_id": "request-1",
        "from_provider": "primary",
        "from_model": "model-v1",
        "to_provider": "fallback",
        "to_model": "model-v1",
        "reason": "ProviderTimeoutError",
        "route_attempt": 2,
        "remaining_deadline_seconds": 10.0,
    }
    assert "unrestricted secret message" not in repr(logged_events)


@pytest.mark.parametrize(
    "error_type", [ProviderAuthenticationError, ProviderInvalidRequestError]
)
def test_non_fallbackable_primary_failure_stops_immediately(
    error_type: type[ProviderError],
) -> None:
    error = error_type("primary", provider_code="stable-code")
    primary = ScriptedProvider("primary", [error])
    fallback = ScriptedProvider("fallback", ["unused"])
    metrics = RecordingMetrics()

    with pytest.raises(error_type) as exc_info:
        run(executor([primary, fallback]), decision("primary", "fallback"), metrics)

    assert exc_info.value is error
    assert fallback.attempts == 0
    assert metrics.fallbacks == []


@pytest.mark.parametrize(
    "error_type", [ProviderAuthenticationError, ProviderInvalidRequestError]
)
def test_non_fallbackable_failure_on_fallback_stops_remaining_chain(
    error_type: type[ProviderError],
) -> None:
    primary = ScriptedProvider("primary", [ProviderTimeoutError("primary")])
    second = ScriptedProvider("second", [error_type("second")])
    third = ScriptedProvider("third", ["unused"])
    metrics = RecordingMetrics()

    with pytest.raises(error_type):
        run(
            executor([primary, second, third]),
            decision("primary", "second", "third"),
            metrics,
        )

    assert third.attempts == 0
    assert metrics.fallbacks == [("primary", "second", "ProviderTimeoutError")]


def test_max_route_attempts_one_disables_fallback() -> None:
    error = ProviderTimeoutError("primary")
    primary = ScriptedProvider("primary", [error])
    fallback = ScriptedProvider("fallback", ["unused"])

    with pytest.raises(ProviderTimeoutError) as exc_info:
        run(
            executor([primary, fallback], max_route_attempts=1),
            decision("primary", "fallback"),
        )

    assert exc_info.value is error
    assert fallback.attempts == 0


def test_max_route_attempts_bound_is_respected() -> None:
    providers = [
        ScriptedProvider("primary", [ProviderTimeoutError("primary")]),
        ScriptedProvider("second", [ProviderUnavailableError("second")]),
        ScriptedProvider("third", ["unused"]),
    ]

    with pytest.raises(ProviderUnavailableError):
        run(
            executor(providers, max_route_attempts=2),
            decision("primary", "second", "third"),
        )

    assert [provider.attempts for provider in providers] == [1, 1, 0]


def test_no_remaining_candidate_reraises_original_error_with_metadata() -> None:
    cause = RuntimeError("upstream")
    error = ProviderTimeoutError(
        "primary", provider_code="timeout-code", message="bounded message"
    )
    error.__cause__ = cause
    primary = ScriptedProvider("primary", [error])

    with pytest.raises(ProviderTimeoutError) as exc_info:
        run(executor([primary]), decision("primary"))

    assert exc_info.value is error
    assert exc_info.value.provider_code == "timeout-code"
    assert exc_info.value.__cause__ is cause


def test_insufficient_deadline_prevents_fallback_and_metric() -> None:
    clock = MutableClock()
    primary = ScriptedProvider(
        "primary",
        [ProviderTimeoutError("primary")],
        before_outcome=lambda: clock.advance(0.8),
    )
    fallback = ScriptedProvider("fallback", ["unused"])
    metrics = RecordingMetrics()

    with pytest.raises(ProviderTimeoutError):
        run(
            executor(
                [primary, fallback],
                deadline=1,
                minimum_budget=0.3,
                clock=clock,
            ),
            decision("primary", "fallback"),
            metrics,
        )

    assert fallback.attempts == 0
    assert metrics.fallbacks == []


def test_shared_deadline_elapsed_time_is_passed_to_each_provider() -> None:
    clock = MutableClock()
    primary = ScriptedProvider(
        "primary",
        [ProviderTimeoutError("primary")],
        before_outcome=lambda: clock.advance(0.6),
    )
    fallback = ScriptedProvider("fallback", ["ok"])
    route_executor = executor(
        [primary, fallback], clock=clock, capturing=True, deadline=2
    )

    run(route_executor, decision("primary", "fallback"))

    assert isinstance(route_executor.provider_executor, CapturingProviderExecutor)
    assert route_executor.provider_executor.elapsed_budgets == [0.0, 0.6]


def test_duplicate_candidates_are_skipped_and_cannot_loop() -> None:
    primary = ScriptedProvider("primary", [ProviderTimeoutError("primary")])
    fallback = ScriptedProvider("fallback", [ProviderUnavailableError("fallback")])
    route_decision = RoutingDecision(
        requested_model="model-v1",
        selected_model="model-v1",
        provider_name="primary",
        reason="duplicates",
        fallback_candidates=(
            RouteCandidate("fallback", "model-v1"),
            RouteCandidate("primary", "model-v1"),
            RouteCandidate("fallback", "model-v1"),
        ),
    )

    with pytest.raises(ProviderUnavailableError):
        run(executor([primary, fallback]), route_decision)

    assert primary.attempts == 1
    assert fallback.attempts == 1


def test_cancellation_propagates_without_fallback() -> None:
    primary = ScriptedProvider("primary", [asyncio.CancelledError()])
    fallback = ScriptedProvider("fallback", ["unused"])
    metrics = RecordingMetrics()

    with pytest.raises(asyncio.CancelledError):
        run(executor([primary, fallback]), decision("primary", "fallback"), metrics)

    assert fallback.attempts == 0
    assert metrics.fallbacks == []


def test_provider_retries_are_exhausted_before_fallback() -> None:
    primary = ScriptedProvider(
        "primary",
        [ProviderTimeoutError("primary"), ProviderTimeoutError("primary")],
    )
    fallback = ScriptedProvider("fallback", ["ok"])
    metrics = RecordingMetrics()

    result = run(
        executor([primary, fallback], max_provider_attempts=2),
        decision("primary", "fallback"),
        metrics,
    )

    assert result.provider == "fallback"
    assert primary.attempts == 2
    assert fallback.attempts == 1
    assert metrics.retries == [("primary", "ProviderTimeoutError")]
    assert metrics.fallbacks == [("primary", "fallback", "ProviderTimeoutError")]


def test_successful_provider_retry_does_not_trigger_fallback() -> None:
    primary = ScriptedProvider(
        "primary", [ProviderTimeoutError("primary"), "retried-ok"]
    )
    fallback = ScriptedProvider("fallback", ["unused"])
    metrics = RecordingMetrics()

    result = run(
        executor([primary, fallback], max_provider_attempts=2),
        decision("primary", "fallback"),
        metrics,
    )

    assert result.output == "retried-ok"
    assert fallback.attempts == 0
    assert metrics.retries == [("primary", "ProviderTimeoutError")]
    assert metrics.fallbacks == []
