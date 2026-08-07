"""Deadline-aware, bounded execution above single-attempt provider adapters."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import TypeVar

from app.config import ProviderRetrySettings
from app.core.logging import log_event
from app.errors import (
    ProviderError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.observability.metrics import ApplicationMetrics
from app.providers.base import ProviderAdapter
from app.schemas.generation import GenerateRequest, ProviderResult

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]
Jitter = Callable[[float, float], float]
T = TypeVar("T")


class RetryPolicy:
    """Classify failures and calculate bounded, full-jitter retry delays."""

    retryable_error_types = (
        ProviderTimeoutError,
        ProviderRateLimitError,
        ProviderUnavailableError,
        ProviderInternalError,
    )

    def __init__(
        self,
        settings: ProviderRetrySettings | None = None,
        *,
        jitter: Jitter = random.uniform,
    ) -> None:
        self.settings = settings or ProviderRetrySettings()
        self._jitter = jitter

    def is_retryable(self, error: ProviderError) -> bool:
        return isinstance(error, self.retryable_error_types)

    def backoff_cap(self, retry_number: int) -> float:
        """Return the cap for a zero-based retry number.

        Retry zero is the first retry after the original provider attempt.
        """

        if retry_number < 0:
            raise ValueError("retry_number must be non-negative")
        return min(
            self.settings.max_delay_seconds,
            self.settings.base_delay_seconds * (2**retry_number),
        )

    def retry_delay(self, retry_number: int) -> float:
        return self._jitter(0.0, self.backoff_cap(retry_number))

    def permits_retry(
        self,
        error: ProviderError,
        *,
        attempts_made: int,
        remaining_deadline_seconds: float,
        delay_seconds: float,
    ) -> bool:
        return (
            self.is_retryable(error)
            and attempts_made < self.settings.max_attempts
            and remaining_deadline_seconds
            >= delay_seconds + self.settings.min_attempt_budget_seconds
        )


class ProviderExecutor:
    """Execute one selected provider within retry and deadline budgets."""

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        *,
        clock: Clock = monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self._clock = clock
        self._sleep = sleep

    async def execute(
        self,
        provider: ProviderAdapter,
        request: GenerateRequest,
        request_id: str,
        selected_model: str,
        metrics: ApplicationMetrics,
        *,
        elapsed_request_seconds: float = 0.0,
    ) -> ProviderResult:
        remaining_budget = max(
            0.0,
            self.policy.settings.request_deadline_seconds - elapsed_request_seconds,
        )
        deadline = self._clock() + remaining_budget
        attempts_made = 0

        while True:
            attempts_made += 1
            attempt_started = self._clock()
            self._record_metric(
                "record_provider_call",
                lambda: metrics.record_provider_call(
                    provider.provider_name, selected_model
                ),
            )
            try:
                result = await self._invoke_before_deadline(
                    provider.generate(request=request, request_id=request_id),
                    provider.provider_name,
                    max(0.0, deadline - self._clock()),
                )
            except ProviderError as error:
                error_type = type(error).__name__
                self._record_metric(
                    "record_provider_failure",
                    lambda error_type=error_type, attempt_started=attempt_started: metrics.record_provider_failure(
                        provider.provider_name,
                        selected_model,
                        error_type,
                        max(0.0, self._clock() - attempt_started),
                    ),
                )
                if (
                    not self.policy.is_retryable(error)
                    or attempts_made >= self.policy.settings.max_attempts
                ):
                    raise
                retry_number = attempts_made - 1
                delay = self.policy.retry_delay(retry_number)
                remaining = max(0.0, deadline - self._clock())
                if not self.policy.permits_retry(
                    error,
                    attempts_made=attempts_made,
                    remaining_deadline_seconds=remaining,
                    delay_seconds=delay,
                ):
                    raise
                self._record_metric(
                    "record_provider_retry",
                    lambda error_type=error_type: metrics.record_provider_retry(
                        provider.provider_name, error_type
                    ),
                )
                log_event(
                    "provider_retry_scheduled",
                    request_id=request_id,
                    provider=provider.provider_name,
                    attempt=attempts_made,
                    error_type=error_type,
                    delay_seconds=delay,
                    remaining_deadline_seconds=remaining,
                )
                await self._sleep(delay)
                continue
            except Exception as error:
                error_type = type(error).__name__
                self._record_metric(
                    "record_provider_failure",
                    lambda error_type=error_type, attempt_started=attempt_started: metrics.record_provider_failure(
                        provider.provider_name,
                        selected_model,
                        error_type,
                        max(0.0, self._clock() - attempt_started),
                    ),
                )
                raise
            return result

    async def _invoke_before_deadline(
        self,
        operation: Awaitable[T],
        provider_name: str,
        remaining_deadline_seconds: float,
    ) -> T:
        try:
            return await asyncio.wait_for(
                operation,
                timeout=remaining_deadline_seconds,
            )
        except TimeoutError as exc:
            raise ProviderTimeoutError(
                provider_name,
                provider_code="gateway_deadline",
                message=f"Provider '{provider_name}' request timed out",
            ) from exc

    @staticmethod
    def _record_metric(operation: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:  # noqa: BLE001 -- metrics are intentionally fail-open
            log_event(
                "metrics_recording_failed",
                operation=operation,
                error_type=type(exc).__name__,
            )
