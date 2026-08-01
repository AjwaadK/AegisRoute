from collections.abc import Awaitable, Callable
from hashlib import sha256
from time import perf_counter
from typing import Any

from app.core.logging import log_event
from app.errors import ModelNotFoundError, ProviderError, ProviderNotFoundError
from app.observability.metrics import ApplicationMetrics, NoopApplicationMetrics
from app.repositories.request_log import NoopRequestLogRepository, RequestLogRepository
from app.routing.contracts import RoutingDecision, RoutingRequest
from app.routing.policy import RoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.schemas.generation import GenerateRequest, GenerateResponse


class GatewayService:
    """Orchestrate routing, provider invocation, persistence, and responses."""

    def __init__(
        self,
        routing_policy: RoutingPolicy | None = None,
        provider_registry: ProviderRegistry | None = None,
        request_log_repository: RequestLogRepository | None = None,
        metrics: ApplicationMetrics | None = None,
    ) -> None:
        self.routing_policy = routing_policy
        self.provider_registry = provider_registry
        self.request_log_repository = request_log_repository or NoopRequestLogRepository()
        self.metrics = metrics or NoopApplicationMetrics()

    async def generate(self, request: GenerateRequest, request_id: str) -> GenerateResponse:
        metrics_lifecycle_start = perf_counter()
        self._record_metric("record_request_started", self.metrics.record_request_started)
        if self.routing_policy is None or self.provider_registry is None:
            self._record_metric(
                "record_request_failed",
                lambda: self.metrics.record_request_failed("RuntimeError", "internal"),
            )
            raise RuntimeError("GatewayService routing dependencies are not configured")

        lifecycle_start = perf_counter()
        request_metadata = self._request_metadata(request)
        await self._persist_request_log_insert(
            request_id=request_id,
            operation="create_started_request",
            action=self.request_log_repository.create_started_request(
                request_id=request_id,
                requested_model=request.model,
                **request_metadata,
            ),
        )

        routing_request = RoutingRequest(requested_model=request.model)
        decision: RoutingDecision | None = None
        try:
            decision = self.routing_policy.route(routing_request)
        except (ModelNotFoundError, ProviderNotFoundError) as exc:
            error_type = type(exc).__name__
            self._record_metric(
                "record_routing_failure",
                lambda: self.metrics.record_routing_failure(error_type),
            )
            self._record_metric(
                "record_request_failed",
                lambda: self.metrics.record_request_failed(error_type, "routing"),
            )
            latency_ms = int((perf_counter() - lifecycle_start) * 1000)
            await self._persist_request_log_update(
                request_id=request_id,
                operation="mark_failed",
                action=self.request_log_repository.mark_failed(
                    request_id=request_id,
                    error_type=type(exc).__name__,
                    latency_ms=latency_ms,
                ),
            )
            log_event(
                "routing_failed",
                request_id=request_id,
                requested_model=request.model,
                selected_model=None,
                provider_name=None,
                routing_reason=None,
                lifecycle_stage="routing",
                error_type=type(exc).__name__,
            )
            if isinstance(exc, ProviderNotFoundError):
                self._log_routing_invariant_violation(
                    request_id=request_id,
                    requested_model=request.model,
                    error=exc,
                    decision=None,
                )
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            self._record_metric(
                "record_routing_failure",
                lambda: self.metrics.record_routing_failure(error_type),
            )
            self._record_metric(
                "record_request_failed",
                lambda: self.metrics.record_request_failed(error_type, "internal"),
            )
            raise

        log_event(
            "routing_decision",
            request_id=request_id,
            requested_model=decision.requested_model,
            selected_model=decision.selected_model,
            provider_name=decision.provider_name,
            routing_reason=decision.reason,
            lifecycle_stage="routed",
        )
        await self._persist_request_log_update(
            request_id=request_id,
            operation="mark_routed",
            action=self.request_log_repository.mark_routed(
                request_id=request_id,
                selected_model=decision.selected_model,
                provider_name=decision.provider_name,
                routing_reason=decision.reason,
            ),
        )

        try:
            provider_adapter = self.provider_registry.get(decision.provider_name)
        except ProviderNotFoundError as exc:
            error_type = type(exc).__name__
            self._record_metric(
                "record_routing_failure",
                lambda: self.metrics.record_routing_failure(error_type),
            )
            self._record_metric(
                "record_request_failed",
                lambda: self.metrics.record_request_failed(error_type, "routing"),
            )
            latency_ms = int((perf_counter() - lifecycle_start) * 1000)
            await self._persist_request_log_update(
                request_id=request_id,
                operation="mark_failed",
                action=self.request_log_repository.mark_failed(
                    request_id=request_id,
                    error_type=type(exc).__name__,
                    latency_ms=latency_ms,
                ),
            )
            self._log_routing_invariant_violation(
                request_id=request_id,
                requested_model=request.model,
                error=exc,
                decision=decision,
            )
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            self._record_metric(
                "record_routing_failure",
                lambda: self.metrics.record_routing_failure(error_type),
            )
            self._record_metric(
                "record_request_failed",
                lambda: self.metrics.record_request_failed(error_type, "internal"),
            )
            raise

        provider_name = decision.provider_name
        selected_request = request.model_copy(
            update={"model": decision.selected_model}
        )
        log_event(
            "generation_started",
            request_id=request_id,
            provider=provider_name,
            model=decision.selected_model,
            status="started",
            lifecycle_stage="provider_invocation",
        )
        start = perf_counter()
        self._record_metric(
            "record_provider_call",
            lambda: self.metrics.record_provider_call(
                provider_name,
                decision.selected_model,
            ),
        )
        try:
            provider_result = await provider_adapter.generate(
                request=selected_request,
                request_id=request_id,
            )
        except ProviderError as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            metrics_latency_seconds = perf_counter() - metrics_lifecycle_start
            error_type = type(exc).__name__
            self._record_metric(
                "record_provider_failure",
                lambda: self.metrics.record_provider_failure(
                    provider_name,
                    decision.selected_model,
                    error_type,
                    metrics_latency_seconds,
                ),
            )
            self._record_metric(
                "record_request_failed",
                lambda: self.metrics.record_request_failed(error_type, "provider"),
            )
            await self._persist_request_log_update(
                request_id=request_id,
                operation="mark_failed",
                action=self.request_log_repository.mark_failed(
                    request_id=request_id,
                    error_type="ProviderError",
                    latency_ms=latency_ms,
                ),
            )
            log_event(
                "generation_failed",
                request_id=request_id,
                provider=provider_name,
                model=decision.selected_model,
                status="failed",
                error_type="ProviderError",
                latency_ms=latency_ms,
                lifecycle_stage="provider_invocation",
            )
            raise
        except Exception as exc:
            metrics_latency_seconds = perf_counter() - metrics_lifecycle_start
            error_type = type(exc).__name__
            self._record_metric(
                "record_provider_failure",
                lambda: self.metrics.record_provider_failure(
                    provider_name,
                    decision.selected_model,
                    error_type,
                    metrics_latency_seconds,
                ),
            )
            self._record_metric(
                "record_request_failed",
                lambda: self.metrics.record_request_failed(error_type, "provider"),
            )
            raise
        latency_ms = int((perf_counter() - start) * 1000)
        await self._persist_request_log_update(
            request_id=request_id,
            operation="mark_completed",
            action=self.request_log_repository.mark_completed(
                request_id=request_id,
                latency_ms=latency_ms,
                input_tokens=provider_result.input_tokens,
                output_tokens=provider_result.output_tokens,
            ),
        )
        log_event(
            "generation_completed",
            request_id=request_id,
            provider=provider_result.provider,
            model=provider_result.model,
            status="completed",
            latency_ms=latency_ms,
            lifecycle_stage="completed",
        )
        self._record_metric(
            "record_request_completed",
            lambda: self.metrics.record_request_completed(
                provider_name,
                decision.selected_model,
                perf_counter() - metrics_lifecycle_start,
            ),
        )
        return GenerateResponse(
            request_id=request_id,
            model=provider_result.model,
            output=provider_result.output,
            latency_ms=latency_ms,
            input_tokens=provider_result.input_tokens,
            output_tokens=provider_result.output_tokens,
        )

    def _request_metadata(self, request: GenerateRequest) -> dict[str, int | str]:
        prompt_hash = sha256()
        input_chars = 0
        for message in request.messages:
            prompt_hash.update(message.role.encode())
            prompt_hash.update(b"\0")
            prompt_hash.update(message.content.encode())
            prompt_hash.update(b"\0")
            input_chars += len(message.content)
        return {
            "prompt_hash": prompt_hash.hexdigest(),
            "message_count": len(request.messages),
            "input_chars": input_chars,
        }

    def _log_routing_invariant_violation(
        self,
        *,
        request_id: str,
        requested_model: str,
        error: ProviderNotFoundError,
        decision: RoutingDecision | None,
    ) -> None:
        if self.provider_registry is None:
            return
        log_event(
            "routing_invariant_violation",
            request_id=request_id,
            requested_model=requested_model,
            selected_model=decision.selected_model if decision else None,
            missing_provider=error.provider_name,
            routing_reason=decision.reason if decision else None,
            registered_providers=self.provider_registry.names(),
            lifecycle_stage=(
                "provider_resolution" if decision is not None else "routing"
            ),
            error_type=type(error).__name__,
        )

    async def _persist_request_log_insert(
        self,
        *,
        request_id: str,
        operation: str,
        action: Awaitable[Any],
    ) -> None:
        try:
            await action
        except Exception as exc:
            # Persistence is non-blocking in v1. Record the failure without
            # changing the generation result.
            log_event(
                "request_log_insert_failed",
                request_id=request_id,
                operation=operation,
                error_type=type(exc).__name__,
            )

    async def _persist_request_log_update(
        self,
        *,
        request_id: str,
        operation: str,
        action: Awaitable[Any],
    ) -> None:
        try:
            await action
        except Exception as exc:
            # Persistence is non-blocking in v1. Record the failure without
            # changing the generation result.
            log_event(
                "request_log_update_failed",
                request_id=request_id,
                operation=operation,
                error_type=type(exc).__name__,
            )

    def _record_metric(self, operation: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            log_event(
                "metrics_recording_failed",
                operation=operation,
                error_type=type(exc).__name__,
            )
