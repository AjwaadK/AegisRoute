import asyncio
import json
import logging
from typing import Any

import pytest

from app.core.logging import LOGGER_NAME
from app.errors import ModelNotFoundError, ProviderError, ProviderNotFoundError
from app.providers.base import ProviderAdapter
from app.repositories.request_log import InMemoryRequestLogRepository, NoopRequestLogRepository
from app.routing.contracts import RoutingDecision, RoutingRequest
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy, RoutingPolicy
from app.routing.provider_registry import ProviderRegistry
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


class FailingRequestLogRepository:
    async def create_started_request(self, **fields: Any) -> None:
        raise RuntimeError("request log unavailable")

    async def mark_completed(self, **fields: Any) -> None:
        raise RuntimeError("request log unavailable")

    async def mark_failed(self, **fields: Any) -> None:
        raise RuntimeError("request log unavailable")

    async def add_event(self, **fields: Any) -> None:
        raise RuntimeError("request log unavailable")


def make_service(
    provider: ProviderAdapter | None = None,
    *,
    routing_policy: RoutingPolicy | None = None,
    provider_registry: ProviderRegistry | None = None,
    request_log_repository: Any = None,
) -> GatewayService:
    configured_provider = provider or CapturingProviderAdapter()
    registry = provider_registry or ProviderRegistry([configured_provider])
    policy = routing_policy or DeterministicRoutingPolicy(
        ModelRegistry(
            [
                ModelDefinition(
                    name="mock-model-v1",
                    providers=(configured_provider.provider_name,),
                )
            ]
        ),
        registry,
    )
    return GatewayService(
        routing_policy=policy,
        provider_registry=registry,
        request_log_repository=request_log_repository,
    )


def make_request(model: str = "mock-model-v1") -> GenerateRequest:
    return GenerateRequest(
        model=model,
        messages=[{"role": "user", "content": "Hello router"}],
        max_tokens=64,
        temperature=0.5,
    )


def logged_payloads(caplog) -> list[dict[str, Any]]:
    return [json.loads(record.message) for record in caplog.records if record.name == LOGGER_NAME]


def test_gateway_service_defaults_to_noop_request_log_repository() -> None:
    service = make_service()

    assert isinstance(service.request_log_repository, NoopRequestLogRepository)


def test_noop_request_log_repository_methods_complete_without_raising() -> None:
    repository = NoopRequestLogRepository()

    async def call_methods() -> None:
        await repository.create_started_request(
            request_id="request-123",
            provider="capturing",
            model="mock-model-v1",
            prompt_hash="abc",
            message_count=1,
            input_chars=12,
        )
        await repository.add_event(
            request_id="request-123",
            event_type="generation_started",
            status="started",
            provider="capturing",
            model="mock-model-v1",
        )
        await repository.mark_completed(
            request_id="request-123",
            provider="capturing",
            model="mock-model-v1",
            latency_ms=1,
            input_tokens=1,
            output_tokens=2,
        )
        await repository.mark_failed(
            request_id="request-123",
            error_type="ProviderError",
            latency_ms=1,
        )

    asyncio.run(call_methods())


def test_in_memory_events_store_explicit_fields() -> None:
    repository = InMemoryRequestLogRepository()

    asyncio.run(
        repository.add_event(
            request_id="request-123",
            event_type="generation_failed",
            status="failed",
            provider="capturing",
            model="mock-model-v1",
            error_type="ProviderError",
            message="provider failed",
            latency_ms=7,
        )
    )

    assert repository.events == [
        {
            "request_id": "request-123",
            "event_type": "generation_failed",
            "status": "failed",
            "provider": "capturing",
            "model": "mock-model-v1",
            "error_type": "ProviderError",
            "message": "provider failed",
            "latency_ms": 7,
        }
    ]


def test_generate_returns_public_response() -> None:
    request_id = "request-123"
    service = make_service()

    response = asyncio.run(service.generate(request=make_request(), request_id=request_id))

    assert response.request_id == request_id
    assert response.model == "mock-model-v1"
    assert response.output
    assert response.latency_ms >= 0
    assert response.input_tokens >= 0
    assert response.output_tokens >= 0


def test_generate_unknown_model_propagates_model_not_found_error() -> None:
    request = make_request(model="unknown-model")
    service = make_service()

    with pytest.raises(ModelNotFoundError) as exc_info:
        asyncio.run(service.generate(request=request, request_id="request-123"))

    assert exc_info.value.model_name == "unknown-model"


def test_generate_response_does_not_expose_provider() -> None:
    service = make_service()

    response = asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    assert "provider" not in response.model_dump()


def test_generate_passes_request_id_to_provider() -> None:
    provider_adapter = CapturingProviderAdapter()
    service = make_service(provider_adapter)

    asyncio.run(service.generate(request=make_request(), request_id="request-abc"))

    assert provider_adapter.request_id == "request-abc"


def test_generate_provider_error_logs_failure(caplog) -> None:
    service = make_service(FailingProviderAdapter())

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME), pytest.raises(ProviderError):
        asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    failure_logs = [payload for payload in logged_payloads(caplog) if payload.get("event") == "generation_failed"]
    assert len(failure_logs) == 1
    failure_log = failure_logs[0]
    assert failure_log["request_id"] == "request-123"
    assert failure_log["model"] == "mock-model-v1"
    assert failure_log["provider"] == "failing"
    assert failure_log["status"] == "failed"
    assert failure_log["error_type"] == "ProviderError"
    assert isinstance(failure_log["latency_ms"], int)


def test_generate_creates_started_request_log_and_completion_event() -> None:
    repository = InMemoryRequestLogRepository()
    service = make_service(
        CapturingProviderAdapter(),
        request_log_repository=repository,
    )

    asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    started_request = repository.requests["request-123"]
    assert started_request["status"] == "completed"
    assert started_request["provider"] == "capturing"
    assert started_request["model"] == "mock-model-v1"
    assert len(str(started_request["prompt_hash"])) == 64
    assert started_request["message_count"] == 1
    assert started_request["input_chars"] == len("Hello router")
    assert "Hello router" not in started_request.values()
    assert repository.events[0] == {
        "request_id": "request-123",
        "event_type": "generation_started",
        "status": "started",
        "provider": "capturing",
        "model": "mock-model-v1",
        "error_type": None,
        "message": None,
        "latency_ms": None,
    }
    assert repository.events[-1]["event_type"] == "generation_completed"
    assert repository.events[-1]["status"] == "completed"


def test_generate_marks_completed_on_success() -> None:
    repository = InMemoryRequestLogRepository()
    service = make_service(
        CapturingProviderAdapter(),
        request_log_repository=repository,
    )

    response = asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    completed_request = repository.requests["request-123"]
    assert completed_request["status"] == "completed"
    assert completed_request["latency_ms"] == response.latency_ms
    assert completed_request["input_tokens"] == 1
    assert completed_request["output_tokens"] == 2
    assert repository.events[-1]["latency_ms"] == response.latency_ms


def test_generate_marks_failed_on_provider_error() -> None:
    repository = InMemoryRequestLogRepository()
    service = make_service(
        FailingProviderAdapter(),
        request_log_repository=repository,
    )

    with pytest.raises(ProviderError):
        asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    failed_request = repository.requests["request-123"]
    assert failed_request["status"] == "failed"
    assert failed_request["error_type"] == "ProviderError"
    assert isinstance(failed_request["latency_ms"], int)
    assert repository.events[-1]["event_type"] == "generation_failed"
    assert repository.events[-1]["provider"] == "failing"
    assert repository.events[-1]["model"] == "mock-model-v1"
    assert repository.events[-1]["status"] == "failed"
    assert repository.events[-1]["error_type"] == "ProviderError"
    assert repository.events[-1]["latency_ms"] == failed_request["latency_ms"]


def test_request_log_insert_failure_does_not_fail_successful_generation(caplog) -> None:
    service = make_service(
        CapturingProviderAdapter(),
        request_log_repository=FailingRequestLogRepository(),
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    assert response.output == "captured response"
    payloads = logged_payloads(caplog)
    insert_failures = [payload for payload in payloads if payload["event"] == "request_log_insert_failed"]
    assert insert_failures
    assert all(payload["error_type"] == "RuntimeError" for payload in insert_failures)


def test_request_log_update_failure_during_provider_failure_reraises_provider_error(caplog) -> None:
    service = make_service(
        FailingProviderAdapter(),
        request_log_repository=FailingRequestLogRepository(),
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME), pytest.raises(ProviderError):
        asyncio.run(service.generate(request=make_request(), request_id="request-123"))

    payloads = logged_payloads(caplog)
    update_failures = [payload for payload in payloads if payload["event"] == "request_log_update_failed"]
    assert update_failures
    assert all(payload["error_type"] == "RuntimeError" for payload in update_failures)
    assert any(payload["event"] == "generation_failed" for payload in payloads)


def test_routing_policy_receives_requested_model_and_selected_provider_is_invoked() -> None:
    selected = CapturingProviderAdapter()

    class OtherProvider(CapturingProviderAdapter):
        provider_name = "other"

    other = OtherProvider()

    class CapturingPolicy:
        def __init__(self) -> None:
            self.request: RoutingRequest | None = None

        def route(self, request: RoutingRequest) -> RoutingDecision:
            self.request = request
            return RoutingDecision(
                requested_model=request.requested_model,
                selected_model="provider-model-v2",
                provider_name="capturing",
                reason="test selection",
            )

    policy = CapturingPolicy()
    service = make_service(
        routing_policy=policy,
        provider_registry=ProviderRegistry([selected, other]),
    )

    response = asyncio.run(
        service.generate(request=make_request(), request_id="request-routing")
    )

    assert policy.request == RoutingRequest(requested_model="mock-model-v1")
    assert selected.request_id == "request-routing"
    assert other.request_id is None
    assert response.model == "provider-model-v2"


def test_routing_decision_selected_model_is_passed_to_provider() -> None:
    provider = CapturingProviderAdapter()

    class SelectedModelPolicy:
        def route(self, request: RoutingRequest) -> RoutingDecision:
            return RoutingDecision(
                requested_model=request.requested_model,
                selected_model="provider-model-v2",
                provider_name="capturing",
                reason="model alias",
            )

    response = asyncio.run(
        make_service(
            routing_policy=SelectedModelPolicy(),
            provider_registry=ProviderRegistry([provider]),
        ).generate(request=make_request(), request_id="request-selected-model")
    )

    assert response.model == "provider-model-v2"


def test_missing_selected_provider_propagates_and_logs_invariant(caplog) -> None:
    class MissingProviderPolicy:
        def route(self, request: RoutingRequest) -> RoutingDecision:
            return RoutingDecision(
                requested_model=request.requested_model,
                selected_model="provider-model-v2",
                provider_name="missing",
                reason="misconfigured route",
            )

    registry = ProviderRegistry([CapturingProviderAdapter()])
    service = make_service(
        routing_policy=MissingProviderPolicy(),
        provider_registry=registry,
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME), pytest.raises(
        ProviderNotFoundError
    ):
        asyncio.run(service.generate(request=make_request(), request_id="request-missing"))

    invariant = next(
        payload
        for payload in logged_payloads(caplog)
        if payload["event"] == "routing_invariant_violation"
    )
    assert invariant == {
        "event": "routing_invariant_violation",
        "request_id": "request-missing",
        "requested_model": "mock-model-v1",
        "selected_model": "provider-model-v2",
        "missing_provider": "missing",
        "routing_reason": "misconfigured route",
        "registered_providers": ["capturing"],
    }


def test_routing_decision_is_logged(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        asyncio.run(
            make_service().generate(
                request=make_request(),
                request_id="request-decision",
            )
        )

    decision = next(
        payload
        for payload in logged_payloads(caplog)
        if payload["event"] == "routing_decision"
    )
    assert decision["request_id"] == "request-decision"
    assert decision["requested_model"] == "mock-model-v1"
    assert decision["selected_model"] == "mock-model-v1"
    assert decision["provider_name"] == "capturing"
    assert decision["routing_reason"] == "selected first configured provider"
