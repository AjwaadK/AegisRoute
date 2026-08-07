"""Application composition for process-scoped runtime dependencies."""

from dataclasses import dataclass, field

from prometheus_client import CollectorRegistry
from sqlalchemy.engine import Engine

from app.analytics.service import RoutingAnalyticsService
from app.config import ProviderRetrySettings, ProviderTimeoutSettings
from app.db.session import create_database_engine, create_session_factory
from app.observability.metrics import ApplicationMetrics, NoopApplicationMetrics
from app.observability.prometheus import PrometheusApplicationMetrics
from app.providers.base import ProviderAdapter
from app.providers.executor import ProviderExecutor, RetryPolicy
from app.providers.mock import MockProviderAdapter
from app.repositories.request_log import SQLAlchemyRequestLogRepository
from app.repositories.sqlalchemy_routing_analytics import (
    SQLAlchemyRoutingAnalyticsRepository,
)
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy, RoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.services.gateway import GatewayService


def _default_model_registry() -> ModelRegistry:
    return ModelRegistry({"mock-model-v1": ModelDefinition("mock-model-v1", ("mock",))})


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Process-scoped dependencies owned by the FastAPI application."""

    engine: Engine
    gateway_service: GatewayService
    metrics_registry: CollectorRegistry = field(default_factory=CollectorRegistry)
    metrics: ApplicationMetrics = field(default_factory=NoopApplicationMetrics)
    routing_analytics_service: RoutingAnalyticsService | None = None
    model_registry: ModelRegistry = field(default_factory=_default_model_registry)
    provider_registry: ProviderRegistry | None = None
    routing_policy: RoutingPolicy | None = None

    def dispose(self) -> None:
        self.engine.dispose()


def build_application_container(
    provider: ProviderAdapter | None = None,
    *,
    model_registry: ModelRegistry | None = None,
    provider_timeout_settings: ProviderTimeoutSettings | None = None,
    provider_retry_settings: ProviderRetrySettings | None = None,
) -> ApplicationContainer:
    """Assemble and validate the production dependency graph."""

    engine = create_database_engine()
    try:
        session_factory = create_session_factory(engine)
        request_log_repository = SQLAlchemyRequestLogRepository(session_factory)
        routing_analytics_service = RoutingAnalyticsService(
            SQLAlchemyRoutingAnalyticsRepository(session_factory)
        )
        if provider is None:
            timeout_settings = (
                provider_timeout_settings or ProviderTimeoutSettings.from_environment()
            )
            configured_provider = MockProviderAdapter(
                timeout_seconds=timeout_settings.for_provider("mock")
            )
        else:
            configured_provider = provider
        provider_registry = ProviderRegistry(
            {configured_provider.provider_name: configured_provider}
        )
        configured_models = model_registry or ModelRegistry(
            {
                "mock-model-v1": ModelDefinition(
                    "mock-model-v1",
                    (configured_provider.provider_name,),
                )
            }
        )
        _validate_model_provider_references(configured_models, provider_registry)
        routing_policy = DeterministicRoutingPolicy(
            configured_models,
            provider_registry,
        )
        metrics_registry = CollectorRegistry()
        metrics = PrometheusApplicationMetrics(metrics_registry)
        retry_settings = (
            provider_retry_settings or ProviderRetrySettings.from_environment()
        )
        provider_executor = ProviderExecutor(RetryPolicy(retry_settings))
        gateway_service = GatewayService(
            routing_policy=routing_policy,
            provider_registry=provider_registry,
            request_log_repository=request_log_repository,
            metrics=metrics,
            provider_executor=provider_executor,
        )
        return ApplicationContainer(
            engine=engine,
            gateway_service=gateway_service,
            metrics_registry=metrics_registry,
            metrics=metrics,
            routing_analytics_service=routing_analytics_service,
            model_registry=configured_models,
            provider_registry=provider_registry,
            routing_policy=routing_policy,
        )
    except Exception:
        engine.dispose()
        raise


def _validate_model_provider_references(
    model_registry: ModelRegistry,
    provider_registry: ProviderRegistry,
) -> None:
    for model_name in model_registry.names():
        for provider_name in model_registry.get(model_name).providers:
            provider_registry.get(provider_name)
