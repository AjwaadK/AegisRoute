import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry
from sqlalchemy import create_engine

from app.api.routes import get_gateway_service
from app.composition import ApplicationContainer, build_application_container
from app.config import ProviderRetrySettings, ProviderTimeoutSettings
from app.main import create_app
from app.models.model_registry import ModelDefinition, ModelRegistry
from app.observability.prometheus import PrometheusApplicationMetrics
from app.providers.mock import MockProviderAdapter
from app.routing.contracts import RoutingDecision, RoutingRequest
from app.schemas.generation import GenerateRequest, GenerateResponse
from app.services.gateway import GatewayService


class StubGatewayService:
    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> GenerateResponse:
        return GenerateResponse(
            request_id=request_id,
            model=request.model,
            output="stubbed response",
            latency_ms=1,
            input_tokens=1,
            output_tokens=1,
        )


def build_test_container() -> ApplicationContainer:
    return ApplicationContainer(
        engine=create_engine("sqlite://"), gateway_service=GatewayService()
    )


def test_route_dependency_override_replaces_composed_gateway() -> None:
    application = create_app(build_test_container)
    application.dependency_overrides[get_gateway_service] = lambda: StubGatewayService()
    try:
        with TestClient(application) as client:
            response = client.post(
                "/generate",
                json={
                    "model": "mock-model-v1",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )
    finally:
        application.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["output"] == "stubbed response"


def test_postgres_configuration_error_is_raised_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(
        RuntimeError, match="DATABASE_URL environment variable is required"
    ):
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


def test_real_composition_routes_mock_model_to_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            container.gateway_service.provider_registry is container.provider_registry
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


def test_composition_applies_provider_timeout_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    settings = ProviderTimeoutSettings(
        default_timeout_seconds=10,
        mock_timeout_seconds=0.25,
    )

    container = build_application_container(provider_timeout_settings=settings)
    try:
        assert container.provider_registry is not None
        provider = container.provider_registry.get("mock")
        assert provider.timeout_seconds == 0.25
    finally:
        container.dispose()


def test_composition_wires_provider_retry_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    settings = ProviderRetrySettings(
        max_attempts=3,
        base_delay_seconds=0.1,
        max_delay_seconds=0.5,
        request_deadline_seconds=5,
        min_attempt_budget_seconds=0.2,
    )

    container = build_application_container(provider_retry_settings=settings)
    try:
        assert container.gateway_service.provider_executor.policy.settings is settings
    finally:
        container.dispose()


def test_provider_timeout_settings_load_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("MOCK_PROVIDER_TIMEOUT_SECONDS", "2.5")

    settings = ProviderTimeoutSettings.from_environment()

    assert settings.default_timeout_seconds == 12.5
    assert settings.for_provider("other") == 12.5
    assert settings.for_provider("mock") == 2.5


@pytest.mark.parametrize("value", ["0", "-1", "nan", "invalid"])
def test_provider_timeout_settings_reject_invalid_environment(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", value)
    monkeypatch.delenv("MOCK_PROVIDER_TIMEOUT_SECONDS", raising=False)

    with pytest.raises(ValueError, match="PROVIDER_TIMEOUT_SECONDS"):
        ProviderTimeoutSettings.from_environment()
