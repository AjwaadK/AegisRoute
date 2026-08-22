import asyncio
from collections.abc import AsyncIterator

import pytest

from app.config import ProviderRetrySettings, ProviderRouteSettings
from app.errors import ProviderTimeoutError, ProviderUnavailableError
from app.observability.metrics import NoopApplicationMetrics
from app.providers.base import ProviderAdapter
from app.providers.executor import ProviderExecutor, RetryPolicy
from app.routing.contracts import RouteCandidate, RoutingDecision
from app.routing.executor import RouteExecutor
from app.routing.provider_registry import ProviderRegistry
from app.schemas.generation import (
    GenerateRequest,
    ProviderResult,
    ProviderStreamEvent,
    StreamCompleted,
    StreamTextDelta,
)


class MutableClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ScriptedStreamingProvider(ProviderAdapter):
    def __init__(
        self,
        provider_name: str,
        attempts: list[list[ProviderStreamEvent | BaseException]],
        *,
        clock: MutableClock | None = None,
        advance_per_attempt: float = 0,
    ) -> None:
        super().__init__()
        self.provider_name = provider_name
        self.scripts = attempts
        self.attempts = 0
        self.closed = 0
        self.clock = clock
        self.advance_per_attempt = advance_per_attempt

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        raise AssertionError("non-streaming path used")

    async def stream(
        self, request: GenerateRequest, request_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        script = self.scripts[self.attempts]
        self.attempts += 1
        if self.clock is not None:
            self.clock.advance(self.advance_per_attempt)
        try:
            for outcome in script:
                if isinstance(outcome, BaseException):
                    raise outcome
                yield outcome
        finally:
            self.closed += 1


class RecordingMetrics(NoopApplicationMetrics):
    def __init__(self) -> None:
        self.retries: list[tuple[str, str]] = []
        self.fallbacks: list[tuple[str, str, str]] = []
        self.ttft: list[tuple[str, str, float]] = []

    def record_provider_retry(self, provider: str, error_type: str) -> None:
        self.retries.append((provider, error_type))

    def record_provider_fallback(
        self, from_provider: str, to_provider: str, reason: str
    ) -> None:
        self.fallbacks.append((from_provider, to_provider, reason))

    def record_stream_time_to_first_token(
        self, provider: str, model: str, latency_seconds: float
    ) -> None:
        self.ttft.append((provider, model, latency_seconds))


def request() -> GenerateRequest:
    return GenerateRequest(
        model="model-v1", messages=[{"role": "user", "content": "hello"}]
    )


def completed(provider: str) -> StreamCompleted:
    return StreamCompleted(provider=provider, model="model-v1")


def decision(*providers: str) -> RoutingDecision:
    return RoutingDecision(
        requested_model="model-v1",
        selected_model="model-v1",
        provider_name=providers[0],
        reason="tests",
        fallback_candidates=tuple(
            RouteCandidate(provider, "model-v1") for provider in providers[1:]
        ),
    )


def route_executor(
    providers: list[ScriptedStreamingProvider],
    *,
    max_provider_attempts: int = 2,
    max_route_attempts: int = 3,
    deadline: float = 10,
    minimum_budget: float = 0,
    clock: MutableClock | None = None,
) -> RouteExecutor:
    configured_clock = clock or MutableClock()
    provider_executor = ProviderExecutor(
        RetryPolicy(
            ProviderRetrySettings(
                max_attempts=max_provider_attempts,
                base_delay_seconds=0,
                max_delay_seconds=0,
                request_deadline_seconds=deadline,
                min_attempt_budget_seconds=minimum_budget,
            ),
            jitter=lambda _lower, _upper: 0,
        ),
        clock=configured_clock,
        sleep=lambda _delay: asyncio.sleep(0),
    )
    return RouteExecutor(
        ProviderRegistry(providers),
        provider_executor,
        ProviderRouteSettings(max_route_attempts=max_route_attempts),
        clock=configured_clock,
    )


async def collect(
    executor: RouteExecutor,
    route: RoutingDecision,
    metrics: RecordingMetrics,
) -> list[ProviderStreamEvent]:
    return [
        event async for event in executor.stream(route, request(), "request-1", metrics)
    ]


def test_failure_before_first_delta_retries_and_then_succeeds() -> None:
    provider = ScriptedStreamingProvider(
        "primary",
        [
            [ProviderTimeoutError("primary")],
            [StreamTextDelta(text="ok"), completed("primary")],
        ],
    )
    metrics = RecordingMetrics()

    events = asyncio.run(
        collect(route_executor([provider]), decision("primary"), metrics)
    )

    assert events == [StreamTextDelta(text="ok"), completed("primary")]
    assert provider.attempts == 2
    assert metrics.retries == [("primary", "ProviderTimeoutError")]
    assert len(metrics.ttft) == 1


def test_retry_exhaustion_before_commit_falls_back() -> None:
    primary = ScriptedStreamingProvider(
        "primary",
        [
            [ProviderTimeoutError("primary")],
            [ProviderTimeoutError("primary")],
        ],
    )
    fallback = ScriptedStreamingProvider(
        "fallback", [[StreamTextDelta(text="fallback"), completed("fallback")]]
    )
    metrics = RecordingMetrics()

    events = asyncio.run(
        collect(
            route_executor([primary, fallback]),
            decision("primary", "fallback"),
            metrics,
        )
    )

    assert events == [StreamTextDelta(text="fallback"), completed("fallback")]
    assert [primary.attempts, fallback.attempts] == [2, 1]
    assert metrics.fallbacks == [("primary", "fallback", "ProviderTimeoutError")]


def test_failure_after_first_delta_never_retries_falls_back_or_restarts() -> None:
    error = ProviderUnavailableError("primary")
    primary = ScriptedStreamingProvider(
        "primary", [[StreamTextDelta(text="visible"), error]]
    )
    fallback = ScriptedStreamingProvider(
        "fallback", [[StreamTextDelta(text="must-not-appear"), completed("fallback")]]
    )
    third = ScriptedStreamingProvider(
        "third", [[StreamTextDelta(text="also-unused"), completed("third")]]
    )
    metrics = RecordingMetrics()
    seen: list[ProviderStreamEvent] = []

    async def consume() -> None:
        async for event in route_executor([primary, fallback, third]).stream(
            decision("primary", "fallback", "third"),
            request(),
            "request-1",
            metrics,
        ):
            seen.append(event)

    with pytest.raises(ProviderUnavailableError) as captured:
        asyncio.run(consume())

    assert captured.value is error
    assert seen == [StreamTextDelta(text="visible")]
    assert [primary.attempts, fallback.attempts, third.attempts] == [1, 0, 0]
    assert metrics.retries == []
    assert metrics.fallbacks == []
    assert primary.closed == 1


def test_shared_deadline_prevents_precommit_fallback() -> None:
    clock = MutableClock()
    primary = ScriptedStreamingProvider(
        "primary",
        [[ProviderTimeoutError("primary")]],
        clock=clock,
        advance_per_attempt=0.8,
    )
    fallback = ScriptedStreamingProvider(
        "fallback", [[StreamTextDelta(text="unused"), completed("fallback")]]
    )

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(
            collect(
                route_executor(
                    [primary, fallback],
                    max_provider_attempts=1,
                    deadline=1,
                    minimum_budget=0.3,
                    clock=clock,
                ),
                decision("primary", "fallback"),
                RecordingMetrics(),
            )
        )

    assert fallback.attempts == 0


def test_cancellation_propagates_without_retry_or_fallback() -> None:
    cancellation = asyncio.CancelledError()
    primary = ScriptedStreamingProvider("primary", [[cancellation]])
    fallback = ScriptedStreamingProvider(
        "fallback", [[StreamTextDelta(text="unused"), completed("fallback")]]
    )
    metrics = RecordingMetrics()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            collect(
                route_executor([primary, fallback]),
                decision("primary", "fallback"),
                metrics,
            )
        )

    assert [primary.attempts, fallback.attempts] == [1, 0]
    assert metrics.retries == []
    assert metrics.fallbacks == []
    assert primary.closed == 1


def test_cancellation_after_commit_does_not_retry_or_fallback() -> None:
    cancellation = asyncio.CancelledError()
    primary = ScriptedStreamingProvider(
        "primary", [[StreamTextDelta(text="visible"), cancellation]]
    )
    fallback = ScriptedStreamingProvider(
        "fallback", [[StreamTextDelta(text="unused"), completed("fallback")]]
    )
    metrics = RecordingMetrics()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            collect(
                route_executor([primary, fallback]),
                decision("primary", "fallback"),
                metrics,
            )
        )

    assert [primary.attempts, fallback.attempts] == [1, 0]
    assert metrics.retries == []
    assert metrics.fallbacks == []


def test_deadline_expiry_after_commit_terminates_without_resilience() -> None:
    clock = MutableClock()

    class DeadlineProvider(ScriptedStreamingProvider):
        async def stream(
            self, request: GenerateRequest, request_id: str
        ) -> AsyncIterator[ProviderStreamEvent]:
            self.attempts += 1
            try:
                clock.advance(2)
                yield StreamTextDelta(text="visible")
                yield completed(self.provider_name)
            finally:
                self.closed += 1

    primary = DeadlineProvider("primary", [[]])
    fallback = ScriptedStreamingProvider(
        "fallback", [[StreamTextDelta(text="unused"), completed("fallback")]]
    )
    seen = []

    async def consume() -> None:
        async for event in route_executor(
            [primary, fallback], deadline=1, clock=clock
        ).stream(
            decision("primary", "fallback"),
            request(),
            "request-1",
            RecordingMetrics(),
        ):
            seen.append(event)

    with pytest.raises(ProviderTimeoutError) as captured:
        asyncio.run(consume())

    assert captured.value.provider_code == "gateway_deadline"
    assert seen == [StreamTextDelta(text="visible")]
    assert [primary.attempts, fallback.attempts] == [1, 0]
