import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.composition import ApplicationContainer
from app.providers.mock import MockProviderAdapter
from app.main import create_app
from app.routing.contracts import RoutingDecision, RoutingRequest
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy, RoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.services.gateway import GatewayService


def build_test_container(
    routing_policy: RoutingPolicy | None = None,
) -> ApplicationContainer:
    provider = MockProviderAdapter()
    provider_registry = ProviderRegistry([provider])
    model_registry = ModelRegistry(
        [ModelDefinition("mock-model-v1", ("mock",))]
    )
    policy = routing_policy or DeterministicRoutingPolicy(
        model_registry,
        provider_registry,
    )
    gateway_service = GatewayService(
        routing_policy=policy,
        provider_registry=provider_registry,
    )
    return ApplicationContainer(
        engine=create_engine("sqlite://"),
        gateway_service=gateway_service,
        model_registry=model_registry,
        provider_registry=provider_registry,
        routing_policy=policy,
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app(build_test_container)) as test_client:
        yield test_client


def test_generate_success(client: TestClient) -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hello router"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "provider" not in body
    assert body["model"] == payload["model"]
    assert body["output"].startswith("mock_response:")
    assert isinstance(body["request_id"], str)
    assert isinstance(body["latency_ms"], int)
    assert body["input_tokens"] >= 1
    assert body["output_tokens"] >= 1


def test_generate_success_with_default_options(client: TestClient) -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hello router"}],
    }
    response = client.post("/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == payload["model"]
    assert body["output"].startswith("mock_response:")


def test_generate_unknown_model_returns_unprocessable_entity(client: TestClient) -> None:
    payload = {
        "model": "unknown-model",
        "messages": [{"role": "user", "content": "Hello router"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "error": "model_not_found",
        "requested_model": "unknown-model",
    }


def test_generate_invalid_schema_messages_required(client: TestClient) -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_invalid_schema_content_not_empty(client: TestClient) -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "   "}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_invalid_schema_max_tokens_bounds(client: TestClient) -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 0,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_invalid_schema_temperature_bounds(client: TestClient) -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 10,
        "temperature": 2.1,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_invalid_schema_model_not_whitespace(client: TestClient) -> None:
    payload = {
        "model": "   ",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_provider_error_returns_bad_gateway(client: TestClient, monkeypatch) -> None:
    from app.errors import ProviderError
    from app.providers.mock import MockProviderAdapter

    async def fail_generate(self, request, request_id):
        raise ProviderError("provider unavailable")

    monkeypatch.setattr(MockProviderAdapter, "generate", fail_generate)
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 502
    assert response.json()["detail"] == {
    "error": "provider_error",
    "message": "Upstream provider failed",
}


def test_generate_provider_error_logs_generation_failed(client: TestClient, monkeypatch, caplog) -> None:
    import logging

    from app.core.logging import LOGGER_NAME
    from app.errors import ProviderError
    from app.providers.mock import MockProviderAdapter

    async def fail_generate(self, request, request_id):
        raise ProviderError("provider unavailable")

    monkeypatch.setattr(MockProviderAdapter, "generate", fail_generate)
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = client.post("/generate", json=payload)

    assert response.status_code == 502
    assert any('"event": "generation_failed"' in record.message for record in caplog.records)
    assert any('"error_type": "ProviderError"' in record.message for record in caplog.records)


def test_missing_selected_provider_returns_generic_internal_error() -> None:
    class MissingProviderPolicy:
        def route(self, request: RoutingRequest) -> RoutingDecision:
            return RoutingDecision(
                requested_model=request.requested_model,
                selected_model="internal-model",
                provider_name="missing-provider",
                reason="internal configuration",
            )

    with TestClient(
        create_app(lambda: build_test_container(MissingProviderPolicy()))
    ) as test_client:
        response = test_client.post(
            "/generate",
            json={
                "model": "public-model",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "error": "internal_routing_error",
        "message": "An internal routing error occurred",
    }
    serialized_body = response.text
    assert "missing-provider" not in serialized_body
    assert "internal-model" not in serialized_body
    assert "internal configuration" not in serialized_body
    assert "mock" not in serialized_body
