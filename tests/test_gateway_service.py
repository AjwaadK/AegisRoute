import asyncio
import json
import logging

import pytest

from app.core.logging import LOGGER_NAME
from app.errors import InvalidModelError, ProviderError
from app.providers.base import ProviderAdapter
from app.schemas.generation import GenerateRequest, ProviderResult
from app.services.gateway import GatewayService


class CapturingProviderAdapter(ProviderAdapter):
    provider_name = "capturing"

    def __init__(self) -> None:
        self.request_id: str | None = None

    async def generate(self, request: GenerateRequest, request_id: str) -> ProviderResult:
        self.request_id = request_id
        return ProviderResult(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output="captured response",
            input_tokens=1,
            output_tokens=2,
        )


class FailingProviderAdapter(ProviderAdapter):
    provider_name = "failing"

    async def generate(self, request: GenerateRequest, request_id: str) -> ProviderResult:
        raise ProviderError("provider unavailable")


def make_request(model: str = "mock-model-v1") -> GenerateRequest:
    return GenerateRequest(
        model=model,
        messages=[{"role": "user", "content": "Hello router"}],
        max_tokens=64,
        temperature=0.5,
    )


def test_generate_returns_public_response() -> None:
    request_id = "request-123"
    service = GatewayService(provider_adapter=CapturingProviderAdapter())

    response = asyncio.run(service.generate(request=make_request(), request_id=request_id))

    assert response.request_id == request_id
    assert response.model == "mock-model-v1"
    assert response.output
    assert response.latency_ms >= 0
    assert response.input_tokens >= 0
    assert response.output_tokens >= 0


def test_generate_unsupported_model_raises_invalid_model_error() -> None:
    request = make_request(model="unknown-model")
    service = GatewayService(provider_adapter=CapturingProviderAdapter())

    with pytest.raises(InvalidModelError) as exc_info:
        asyncio.run(service.generate(request=request, request_id="request-123"))

    assert exc_info.value.requested_model == "unknown-model"
    assert exc_info.value.valid_models == ("mock-model-v1",)


def test_generate_response_does_not_expose_provider() -> None:
    service = GatewayService(provider_adapter=CapturingProviderAdapter())

    response = asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    assert "provider" not in response.model_dump()


def test_generate_passes_request_id_to_provider() -> None:
    provider_adapter = CapturingProviderAdapter()
    service = GatewayService(provider_adapter=provider_adapter)

    asyncio.run(service.generate(request=make_request(), request_id="request-abc"))

    assert provider_adapter.request_id == "request-abc"


def test_generate_provider_error_logs_failure(caplog) -> None:
    service = GatewayService(provider_adapter=FailingProviderAdapter())

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME), pytest.raises(ProviderError):
        asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    failure_logs = []
    for record in caplog.records:
        if record.name != LOGGER_NAME:
            continue
        payload = json.loads(record.message)
        if payload.get("event") == "generation_failed":
            failure_logs.append(payload)
    assert failure_logs == [
        {
            "event": "generation_failed",
            "request_id": "request-123",
            "model": "mock-model-v1",
            "provider": "failing",
            "status": "failed",
            "error_type": "ProviderError",
        }
    ]
