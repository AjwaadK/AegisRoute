from collections.abc import Awaitable
from hashlib import sha256
from time import perf_counter
from typing import Any

from app.core.logging import log_event
from app.errors import InvalidModelError, ProviderError
from app.providers.base import ProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.repositories.request_log import InMemoryRequestLogRepository, RequestLogRepository
from app.schemas.generation import GenerateRequest, GenerateResponse


class GatewayService:
    """Coordinates model validation, provider selection, and response mapping."""

    valid_models = ("mock-model-v1",)

    def __init__(
        self,
        provider_adapter: ProviderAdapter | None = None,
        request_log_repository: RequestLogRepository | None = None,
    ) -> None:
        self.provider_adapter = provider_adapter or MockProviderAdapter()
        self.request_log_repository = request_log_repository or InMemoryRequestLogRepository()

    async def generate(self, request: GenerateRequest, request_id: str) -> GenerateResponse:
        if request.model not in self.valid_models:
            raise InvalidModelError(
                requested_model=request.model,
                valid_models=self.valid_models,
            )

        provider_adapter = self.provider_adapter
        provider_name = provider_adapter.provider_name
        request_metadata = self._request_metadata(request)
        await self._persist_request_log_insert(
            request_id=request_id,
            operation="create_started_request",
            action=self.request_log_repository.create_started_request(
                request_id=request_id,
                provider=provider_name,
                model=request.model,
                **request_metadata,
            ),
        )
        await self._persist_request_log_insert(
            request_id=request_id,
            operation="add_generation_started_event",
            action=self.request_log_repository.add_event(
                request_id=request_id,
                event_type="generation_started",
                metadata={
                    "provider": provider_name,
                    "model": request.model,
                    "status": "started",
                },
            ),
        )
        log_event(
            "generation_started",
            request_id=request_id,
            provider=provider_name,
            model=request.model,
            status="started",
        )
        start = perf_counter()
        try:
            provider_result = await provider_adapter.generate(
                request=request,
                request_id=request_id,
            )
        except ProviderError:
            await self._persist_request_log_update(
                request_id=request_id,
                operation="mark_failed",
                action=self.request_log_repository.mark_failed(
                    request_id=request_id,
                    error_type="ProviderError",
                ),
            )
            await self._persist_request_log_insert(
                request_id=request_id,
                operation="add_generation_failed_event",
                action=self.request_log_repository.add_event(
                    request_id=request_id,
                    event_type="generation_failed",
                    metadata={
                        "provider": provider_name,
                        "model": request.model,
                        "status": "failed",
                        "error_type": "ProviderError",
                    },
                ),
            )
            log_event(
                "generation_failed",
                request_id=request_id,
                provider=provider_name,
                model=request.model,
                status="failed",
                error_type="ProviderError",
            )
            raise
        latency_ms = int((perf_counter() - start) * 1000)
        await self._persist_request_log_update(
            request_id=request_id,
            operation="mark_completed",
            action=self.request_log_repository.mark_completed(
                request_id=request_id,
                provider=provider_result.provider,
                model=provider_result.model,
                latency_ms=latency_ms,
                input_tokens=provider_result.input_tokens,
                output_tokens=provider_result.output_tokens,
            ),
        )
        await self._persist_request_log_insert(
            request_id=request_id,
            operation="add_generation_completed_event",
            action=self.request_log_repository.add_event(
                request_id=request_id,
                event_type="generation_completed",
                metadata={
                    "provider": provider_result.provider,
                    "model": provider_result.model,
                    "status": "completed",
                    "latency_ms": latency_ms,
                },
            ),
        )
        log_event(
            "generation_completed",
            request_id=request_id,
            provider=provider_result.provider,
            model=provider_result.model,
            status="completed",
            latency_ms=latency_ms,
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

    async def _persist_request_log_insert(
        self,
        *,
        request_id: str,
        operation: str,
        action: Awaitable[Any],
    ) -> None:
        try:
            await action
        except Exception:
            log_event(
                "request_log_insert_failed",
                request_id=request_id,
                operation=operation,
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
        except Exception:
            log_event(
                "request_log_update_failed",
                request_id=request_id,
                operation=operation,
            )
