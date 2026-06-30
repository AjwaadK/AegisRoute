from time import perf_counter

from app.core.logging import log_event
from app.errors import InvalidModelError
from app.providers.mock import MockProviderAdapter
from app.schemas.generation import GenerateRequest, GenerateResponse


class GatewayService:
    """Coordinates model validation, provider selection, and response mapping."""

    valid_models = ["mock-model-v1"]

    async def generate(self, request: GenerateRequest, request_id: str) -> GenerateResponse:
        if request.model not in self.valid_models:
            raise InvalidModelError(
                requested_model=request.model,
                valid_models=self.valid_models,
            )

        provider_adapter = MockProviderAdapter()
        provider_name = provider_adapter.provider_name
        log_event(
            "generation_started",
            request_id=request_id,
            provider=provider_name,
            model=request.model,
            status="started",
        )
        start = perf_counter()
        provider_result = await provider_adapter.generate(
            request=request,
            request_id=request_id,
        )
        latency_ms = int((perf_counter() - start) * 1000)
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
