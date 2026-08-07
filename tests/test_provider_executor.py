import asyncio
from collections.abc import Sequence

import pytest

from app.config import ProviderRetrySettings
from app.errors import (
    ProviderAuthenticationError,
    ProviderInvalidRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.observability.metrics import NoopApplicationMetrics
from app.providers.base import ProviderAdapter
from app.providers.executor import ProviderExecutor, RetryPolicy
from app.schemas.generation import GenerateRequest, ProviderResult


class SequenceProvider(ProviderAdapter):
    provider_name = "sequence"

    def __init__(self, outcomes: Sequence[ProviderResult | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.attempts = 0

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        outcome = self.outcomes[self.attempts]
        self.attempts += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class RecordingMetrics(NoopApplicationMetrics):
    def __init__(self) -> None:
        self.calls = 0
        self.failures: list[str] = []
        self.retries: list[str] = []

    def record_provider_call(self, provider: str, selected_model: str) -> None:
        self.calls += 1

    def record_provider_failure(
        self,
        provider: str,
        selected_model: str,
        error_type: str,
        latency_seconds: float,
    ) -> None:
        self.failures.append(error_type)

    def record_provider_retry(self, provider: str, error_type: str) -> None:
        self.retries.append(error_type)


def request() -> GenerateRequest:
    return GenerateRequest(
        model="model-v1",
        messages=[{"role": "user", "content": "hello"}],
    )


def result() -> ProviderResult:
    return ProviderResult(
        request_id="request-1",
        provider="sequence",
        model="model-v1",
        output="ok",
        input_tokens=1,
        output_tokens=1,
    )


def executor(
    *,
    max_attempts: int = 2,
    deadline: float = 10,
    minimum_budget: float = 0.1,
    delay: float = 0.25,
    sleep=None,
) -> ProviderExecutor:
    policy = RetryPolicy(
        ProviderRetrySettings(
            max_attempts=max_attempts,
            base_delay_seconds=delay,
            max_delay_seconds=delay,
            request_deadline_seconds=deadline,
            min_attempt_budget_seconds=minimum_budget,
        ),
        jitter=lambda _lower, upper: upper,
    )
    return ProviderExecutor(policy, sleep=sleep or asyncio.sleep)


async def execute(
    configured_executor: ProviderExecutor,
    provider: SequenceProvider,
    metrics: RecordingMetrics | None = None,
) -> tuple[ProviderResult, RecordingMetrics]:
    recorded = metrics or RecordingMetrics()
    response = await configured_executor.execute(
        provider,
        request(),
        "request-1",
        "model-v1",
        recorded,
    )
    return response, recorded


def test_first_attempt_success_does_not_retry_or_sleep() -> None:
    sleeps = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = SequenceProvider([result()])
    response, metrics = asyncio.run(execute(executor(sleep=sleep), provider))

    assert response == result()
    assert provider.attempts == 1
    assert sleeps == []
    assert metrics.calls == 1
    assert metrics.failures == []
    assert metrics.retries == []


@pytest.mark.parametrize(
    "error",
    (ProviderTimeoutError("sequence"), ProviderUnavailableError("sequence")),
)
def test_retryable_failure_then_success_performs_two_attempts(error) -> None:
    sleeps = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = SequenceProvider([error, result()])
    response, metrics = asyncio.run(execute(executor(sleep=sleep), provider))

    assert response == result()
    assert provider.attempts == 2
    assert sleeps == [0.25]
    assert metrics.calls == 2
    assert metrics.failures == [type(error).__name__]
    assert metrics.retries == [type(error).__name__]


@pytest.mark.parametrize(
    "error",
    (
        ProviderAuthenticationError("sequence"),
        ProviderInvalidRequestError("sequence"),
    ),
)
def test_non_retryable_failure_performs_one_attempt(error) -> None:
    provider = SequenceProvider([error])
    metrics = RecordingMetrics()

    with pytest.raises(type(error)) as caught:
        asyncio.run(execute(executor(), provider, metrics))

    assert caught.value is error
    assert provider.attempts == 1
    assert metrics.calls == 1
    assert metrics.retries == []


def test_exhausted_attempts_reraise_final_error_with_metadata_and_chain() -> None:
    first = ProviderTimeoutError("sequence", provider_code="first")
    cause = TimeoutError("socket deadline")
    final = ProviderTimeoutError(
        "sequence", provider_code="final", message="final timeout"
    )
    final.__cause__ = cause
    provider = SequenceProvider([first, final])

    with pytest.raises(ProviderTimeoutError) as caught:
        asyncio.run(execute(executor(), provider))

    assert caught.value is final
    assert caught.value.provider_name == "sequence"
    assert caught.value.provider_code == "final"
    assert caught.value.__cause__ is cause
    assert provider.attempts == 2


def test_insufficient_deadline_prevents_sleep_retry_and_retry_metric() -> None:
    sleeps = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    error = ProviderTimeoutError("sequence")
    provider = SequenceProvider([error, result()])
    metrics = RecordingMetrics()

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(
            execute(
                executor(
                    deadline=0.3,
                    minimum_budget=0.1,
                    delay=0.25,
                    sleep=sleep,
                ),
                provider,
                metrics,
            )
        )

    assert provider.attempts == 1
    assert sleeps == []
    assert metrics.retries == []


def test_jittered_delay_is_passed_to_sleep_only_before_retry() -> None:
    sleeps = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    provider = SequenceProvider([ProviderUnavailableError("sequence"), result()])
    asyncio.run(execute(executor(delay=0.4, sleep=sleep), provider))

    assert sleeps == [0.4]


def test_cancelled_error_propagates_immediately_without_retry() -> None:
    provider = SequenceProvider([asyncio.CancelledError()])
    metrics = RecordingMetrics()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(execute(executor(), provider, metrics))

    assert provider.attempts == 1
    assert metrics.calls == 1
    assert metrics.failures == []
    assert metrics.retries == []
