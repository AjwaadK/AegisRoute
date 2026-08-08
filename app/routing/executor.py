"""Bounded execution across ordered provider route candidates."""

from collections.abc import Callable
from time import monotonic

from app.config import ProviderRouteSettings
from app.core.logging import log_event
from app.errors import (
    ProviderError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.observability.metrics import ApplicationMetrics
from app.providers.executor import ProviderExecutor
from app.routing.contracts import RouteCandidate, RoutingDecision
from app.routing.provider_registry import ProviderRegistry
from app.schemas.generation import GenerateRequest, ProviderResult

Clock = Callable[[], float]


class FallbackPolicy:
    """Classify typed provider failures eligible for cross-provider fallback."""

    fallbackable_error_types = (
        ProviderTimeoutError,
        ProviderRateLimitError,
        ProviderUnavailableError,
        ProviderInternalError,
    )

    def is_fallbackable(self, error: ProviderError) -> bool:
        return isinstance(error, self.fallbackable_error_types)


class RouteExecutor:
    """Execute unique ordered candidates within one shared request deadline."""

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        provider_executor: ProviderExecutor,
        settings: ProviderRouteSettings | None = None,
        policy: FallbackPolicy | None = None,
        *,
        clock: Clock = monotonic,
    ) -> None:
        self.provider_registry = provider_registry
        self.provider_executor = provider_executor
        self.settings = settings or ProviderRouteSettings()
        self.policy = policy or FallbackPolicy()
        self._clock = clock

    async def execute(
        self,
        decision: RoutingDecision,
        request: GenerateRequest,
        request_id: str,
        metrics: ApplicationMetrics,
        *,
        elapsed_request_seconds: float = 0.0,
    ) -> ProviderResult:
        route_started = self._clock()
        total_deadline = self.provider_executor.policy.settings.request_deadline_seconds
        deadline = route_started + max(0.0, total_deadline - elapsed_request_seconds)
        attempted: set[tuple[str, str]] = set()
        candidate_index = 0
        current = decision.candidates[0]

        while True:
            attempted.add(current.identity)
            provider = self.provider_registry.get(current.provider_name)
            selected_request = request.model_copy(
                update={"model": current.selected_model}
            )
            try:
                return await self.provider_executor.execute(
                    provider,
                    selected_request,
                    request_id,
                    current.selected_model,
                    metrics,
                    elapsed_request_seconds=(
                        elapsed_request_seconds + self._clock() - route_started
                    ),
                )
            except ProviderError as error:
                if not self.policy.is_fallbackable(error):
                    raise
                if len(attempted) >= self.settings.max_route_attempts:
                    raise

                next_candidate, candidate_index = self._next_unique_candidate(
                    decision.candidates,
                    candidate_index + 1,
                    attempted,
                )
                if next_candidate is None:
                    raise

                remaining = max(0.0, deadline - self._clock())
                minimum_budget = (
                    self.provider_executor.policy.settings.min_attempt_budget_seconds
                )
                if remaining < minimum_budget:
                    raise

                # Resolve before recording a transition so metrics describe an
                # executable, registry-bounded destination.
                self.provider_registry.get(next_candidate.provider_name)
                reason = type(error).__name__
                self._record_fallback_metric(
                    metrics,
                    current.provider_name,
                    next_candidate.provider_name,
                    reason,
                )
                log_event(
                    "provider_fallback_scheduled",
                    request_id=request_id,
                    from_provider=current.provider_name,
                    from_model=current.selected_model,
                    to_provider=next_candidate.provider_name,
                    to_model=next_candidate.selected_model,
                    reason=reason,
                    route_attempt=len(attempted) + 1,
                    remaining_deadline_seconds=remaining,
                )
                current = next_candidate

    @staticmethod
    def _next_unique_candidate(
        candidates: tuple[RouteCandidate, ...],
        start_index: int,
        attempted: set[tuple[str, str]],
    ) -> tuple[RouteCandidate | None, int]:
        for index in range(start_index, len(candidates)):
            candidate = candidates[index]
            if candidate.identity not in attempted:
                return candidate, index
        return None, len(candidates)

    @staticmethod
    def _record_fallback_metric(
        metrics: ApplicationMetrics,
        from_provider: str,
        to_provider: str,
        reason: str,
    ) -> None:
        try:
            metrics.record_provider_fallback(from_provider, to_provider, reason)
        except Exception as exc:  # noqa: BLE001 -- metrics are intentionally fail-open
            log_event(
                "metrics_recording_failed",
                operation="record_provider_fallback",
                error_type=type(exc).__name__,
            )


__all__ = ("FallbackPolicy", "RouteExecutor")
