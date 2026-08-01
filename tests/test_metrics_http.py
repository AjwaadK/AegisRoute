from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry
from sqlalchemy import create_engine

from app.composition import ApplicationContainer
from app.main import create_app
from app.observability.prometheus import PrometheusApplicationMetrics
from app.providers.mock import MockProviderAdapter
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.services.gateway import GatewayService


def build_metrics_container() -> ApplicationContainer:
    registry = CollectorRegistry()
    metrics = PrometheusApplicationMetrics(registry)
    provider = MockProviderAdapter()
    providers = ProviderRegistry([provider])
    models = ModelRegistry([ModelDefinition("mock-model-v1", ("mock",))])
    policy = DeterministicRoutingPolicy(models, providers)
    gateway = GatewayService(
        routing_policy=policy,
        provider_registry=providers,
        metrics=metrics,
    )
    return ApplicationContainer(
        engine=create_engine("sqlite://"),
        gateway_service=gateway,
        metrics_registry=registry,
        metrics=metrics,
        model_registry=models,
        provider_registry=providers,
        routing_policy=policy,
    )


def test_metrics_endpoint_exposes_isolated_live_metrics_without_postgres() -> None:
    application = create_app(build_metrics_container)

    with TestClient(application) as client:
        generated = client.post(
            "/generate",
            json={
                "model": "mock-model-v1",
                "messages": [{"role": "user", "content": "top secret prompt"}],
            },
        )
        response = client.get("/metrics")

    assert generated.status_code == 200
    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
    assert "aegisroute_generation_requests_total 1.0" in response.text
    assert "aegisroute_generation_completed_total 1.0" in response.text
    assert 'aegisroute_provider_calls_total{provider="mock",selected_model="mock-model-v1"} 1.0' in response.text
    assert "top secret prompt" not in response.text
    assert "DATABASE_URL" not in response.text


def test_multiple_test_apps_use_distinct_registries() -> None:
    first = build_metrics_container()
    second = build_metrics_container()

    assert first.metrics_registry is not second.metrics_registry
    assert first.metrics is not second.metrics

    with TestClient(create_app(lambda: first)) as first_client:
        assert first_client.get("/metrics").status_code == 200
    with TestClient(create_app(lambda: second)) as second_client:
        assert second_client.get("/metrics").status_code == 200
