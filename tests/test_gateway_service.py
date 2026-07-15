import asyncio
import json
import logging
from typing import Any

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


class CapturingRequestLogRepository:
    def __init__(self) -> None:
        self.requests: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []

    async def create_started_request(self, **fields: Any) -> None:
        self.requests[fields["request_id"]] = {**fields, "status": "started"}

    async def mark_completed(self, **fields: Any) -> None:
        request_id = fields["request_id"]
        self.requests[request_id] = {
            **self.requests.get(request_id, {"request_id": request_id}),
            **fields,
            "status": "completed",
        }

    async def mark_failed(self, **fields: Any) -> None:
        request_id = fields["request_id"]
        self.requests[request_id] = {
            **self.requests.get(request_id, {"request_id": request_id}),
            **fields,
            "status": "failed",
        }

    async def add_event(self, **fields: Any) -> None:
        self.events.append(fields)


class FailingRequestLogRepository:
    async def create_started_request(self, **fields: Any) -> None:
        raise RuntimeError("request log unavailable")

    async def mark_completed(self, **fields: Any) -> None:
        raise RuntimeError("request log unavailable")

    async def mark_failed(self, **fields: Any) -> None:
        raise RuntimeError("request log unavailable")

    async def add_event(self, **fields: Any) -> None:
        raise RuntimeError("request log unavailable")


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


def test_generate_creates_started_request_log() -> None:
    repository = CapturingRequestLogRepository()
    service = GatewayService(
        provider_adapter=CapturingProviderAdapter(),
        request_log_repository=repository,
    )

    asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    started_request = repository.requests["request-123"]
    assert started_request["status"] == "completed"
    assert started_request["provider"] == "capturing"
    assert started_request["model"] == "mock-model-v1"
    assert len(started_request["prompt_hash"]) == 64
    assert started_request["message_count"] == 1
    assert started_request["input_chars"] == len("Hello router")
    assert "Hello router" not in started_request.values()
    assert repository.events[0]["event_type"] == "generation_started"


def test_generate_marks_completed_on_success() -> None:
    repository = CapturingRequestLogRepository()
    service = GatewayService(
        provider_adapter=CapturingProviderAdapter(),
        request_log_repository=repository,
    )

    response = asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    completed_request = repository.requests["request-123"]
    assert completed_request["status"] == "completed"
    assert completed_request["latency_ms"] == response.latency_ms
    assert completed_request["input_tokens"] == 1
    assert completed_request["output_tokens"] == 2
    assert repository.events[-1]["event_type"] == "generation_completed"


def test_generate_marks_failed_on_provider_error() -> None:
    repository = CapturingRequestLogRepository()
    service = GatewayService(
        provider_adapter=FailingProviderAdapter(),
        request_log_repository=repository,
    )

    with pytest.raises(ProviderError):
        asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    failed_request = repository.requests["request-123"]
    assert failed_request["status"] == "failed"
    assert failed_request["error_type"] == "ProviderError"
    assert repository.events[-1]["event_type"] == "generation_failed"


def test_request_log_failure_does_not_fail_successful_generation(caplog) -> None:
    service = GatewayService(
        provider_adapter=CapturingProviderAdapter(),
        request_log_repository=FailingRequestLogRepository(),
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    assert response.output == "captured response"
    payloads = [json.loads(record.message) for record in caplog.records if record.name == LOGGER_NAME]
    assert any(payload["event"] == "request_log_insert_failed" for payload in payloads)
    assert any(payload["event"] == "request_log_update_failed" for payload in payloads)


def test_request_log_failure_during_provider_failure_reraises_provider_error(caplog) -> None:
    service = GatewayService(
        provider_adapter=FailingProviderAdapter(),
        request_log_repository=FailingRequestLogRepository(),
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME), pytest.raises(ProviderError):
        asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    payloads = [json.loads(record.message) for record in caplog.records if record.name == LOGGER_NAME]
    assert any(payload["event"] == "request_log_insert_failed" for payload in payloads)
    assert any(payload["event"] == "request_log_update_failed" for payload in payloads)
    assert any(payload["event"] == "generation_failed" for payload in payloads)
