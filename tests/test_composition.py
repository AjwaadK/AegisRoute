import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from prometheus_client import CollectorRegistry

from app.api.routes import get_gateway_service
from app.composition import ApplicationContainer, build_application_container
from app.main import create_app
from app.observability.prometheus import PrometheusApplicationMetrics
from app.models.model_registry import ModelDefinition, ModelRegistry
from app.providers.mock import MockProviderAdapter
from app.routing.contracts import RoutingDecision, RoutingRequest
from app.schemas.generation import GenerateRequest, GenerateResponse
from app.services.gateway import GatewayService


class StubGatewayService:
    async def generate(self, request: GenerateRequest, request_id: str) -> GenerateResponse:
        return GenerateResponse(
            request_id=request_id,
            model=request.model,
            output="stubbed response",
            latency_ms=1,
            input_tokens=1,
            output_tokens=1,
        )


def build_test_container() -> ApplicationContainer:
    return ApplicationContainer(engine=create_engine("sqlite://"), gateway_service=GatewayService())


def test_route_dependency_override_replaces_composed_gateway() -> None:
    application = create_app(build_test_container)
    application.dependency_overrides[get_gateway_service] = lambda: StubGatewayService()
    try:
        with TestClient(application) as client:
            response = client.post(
                "/generate",
                json={"model": "mock-model-v1", "messages": [{"role": "user", "content": "Hello"}]},
            )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["output"] == "stubbed response"


def test_postgres_configuration_error_is_raised_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is required"):
        with TestClient(create_app()):
            pass


def test_composition_rejects_model_with_unregistered_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    models = ModelRegistry(
        {"mock-model-v1": ModelDefinition("mock-model-v1", ("unregistered",))}
    )

    with pytest.raises(LookupError, match="unregistered"):
        build_application_container(MockProviderAdapter(), model_registry=models)


def test_real_composition_routes_mock_model_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    container = build_application_container()
    try:
        assert container.routing_policy is not None
        assert container.routing_policy.route(
            RoutingRequest(requested_model="mock-model-v1")
        ) == RoutingDecision(
            requested_model="mock-model-v1",
            selected_model="mock-model-v1",
            provider_name="mock",
            reason="selected first configured provider",
        )
        assert container.provider_registry is not None
        assert container.gateway_service.routing_policy is container.routing_policy
        assert (
            container.gateway_service.provider_registry
            is container.provider_registry
        )
        assert isinstance(container.metrics_registry, CollectorRegistry)
        assert isinstance(container.metrics, PrometheusApplicationMetrics)
        assert container.metrics.registry is container.metrics_registry
        assert container.gateway_service.metrics is container.metrics
        assert container.routing_analytics_service is not None
        assert (
            container.routing_analytics_service._repository.__class__.__name__
            == "SQLAlchemyRoutingAnalyticsRepository"
        )
    finally:
        container.dispose()
