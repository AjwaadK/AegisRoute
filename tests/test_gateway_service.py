import asyncio
import json
import logging

import pytest

from app.core.logging import LOGGER_NAME
from app.errors import InvalidModelError, ProviderError
from app.providers.mock import MockProviderAdapter
from app.schemas.generation import GenerateRequest
from app.services.gateway import GatewayService


def make_request(model: str = "mock-model-v1") -> GenerateRequest:
    return GenerateRequest(
        model=model,
        messages=[{"role": "user", "content": "Hello router"}],
        max_tokens=64,
        temperature=0.5,
    )


def test_generate_returns_public_response() -> None:
    request_id = "request-123"

    response = asyncio.run(GatewayService().generate(request=make_request(), request_id=request_id))

    assert response.request_id == request_id
    assert response.model == "mock-model-v1"
    assert response.output
    assert response.latency_ms >= 0
    assert response.input_tokens is not None
    assert response.output_tokens is not None


def test_generate_unsupported_model_raises_invalid_model_error() -> None:
    request = make_request(model="unknown-model")

    with pytest.raises(InvalidModelError) as exc_info:
        asyncio.run(GatewayService().generate(request=request, request_id="request-123"))

    assert exc_info.value.requested_model == "unknown-model"
    assert exc_info.value.valid_models == ("mock-model-v1",)


def test_generate_response_does_not_expose_provider() -> None:
    response = asyncio.run(GatewayService().generate(request=make_request(), request_id="request-123"))

    assert "provider" not in response.model_dump()


def test_generate_passes_request_id_to_provider(monkeypatch) -> None:
    seen_request_id = None

    async def capture_generate(self, request, request_id):
        nonlocal seen_request_id
        seen_request_id = request_id
        return await original_generate(self, request=request, request_id=request_id)

    original_generate = MockProviderAdapter.generate
    monkeypatch.setattr(MockProviderAdapter, "generate", capture_generate)

    asyncio.run(GatewayService().generate(request=make_request(), request_id="request-abc"))

    assert seen_request_id == "request-abc"


def test_generate_provider_error_logs_failure(monkeypatch, caplog) -> None:
    async def fail_generate(self, request, request_id):
        raise ProviderError("provider unavailable")

    monkeypatch.setattr(MockProviderAdapter, "generate", fail_generate)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME), pytest.raises(ProviderError):
        asyncio.run(GatewayService().generate(request=make_request(), request_id="request-123"))

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
            "provider": "mock",
            "status": "failed",
            "error_type": "ProviderError",
        }
    ]
