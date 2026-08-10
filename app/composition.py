"""Application composition for process-scoped runtime dependencies."""

from collections.abc import Callable
from dataclasses import dataclass, field

from openai import AsyncOpenAI
from prometheus_client import CollectorRegistry
from sqlalchemy.engine import Engine

from app.analytics.service import RoutingAnalyticsService
from app.config import (
    OpenAISettings,
    ProviderRetrySettings,
    ProviderRouteSettings,
    ProviderTimeoutSettings,
)
from app.db.session import create_database_engine, create_session_factory
from app.observability.metrics import ApplicationMetrics, NoopApplicationMetrics
from app.observability.prometheus import PrometheusApplicationMetrics
from app.providers.base import ProviderAdapter
from app.providers.executor import ProviderExecutor, RetryPolicy
from app.providers.mock import MockProviderAdapter
from app.providers.openai import AsyncOpenAIClient, OpenAIProviderAdapter
from app.repositories.request_log import SQLAlchemyRequestLogRepository
from app.repositories.sqlalchemy_routing_analytics import (
    SQLAlchemyRoutingAnalyticsRepository,
)
from app.routing.executor import RouteExecutor
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
    provider_route_settings: ProviderRouteSettings | None = None,
    openai_settings: OpenAISettings | None = None,
    openai_client_factory: Callable[..., AsyncOpenAIClient] = AsyncOpenAI,
) -> ApplicationContainer:
    """Assemble and validate the production dependency graph."""

    engine = create_database_engine()
    try:
        session_factory = create_session_factory(engine)
        request_log_repository = SQLAlchemyRequestLogRepository(session_factory)
        routing_analytics_service = RoutingAnalyticsService(
            SQLAlchemyRoutingAnalyticsRepository(session_factory)
        )
        timeout_settings = (
            provider_timeout_settings or ProviderTimeoutSettings.from_environment()
        )
        if provider is None:
            configured_providers: list[ProviderAdapter] = [
                MockProviderAdapter(
                    timeout_seconds=timeout_settings.for_provider("mock")
                )
            ]
            configured_openai = openai_settings or OpenAISettings.from_environment()
            if configured_openai.api_key is not None:
                openai_timeout = timeout_settings.for_provider("openai")
                client = openai_client_factory(
                    api_key=configured_openai.api_key,
                    max_retries=0,
                    timeout=openai_timeout,
                )
                configured_providers.append(
                    OpenAIProviderAdapter(client, timeout_seconds=openai_timeout)
                )
        else:
            configured_providers = [provider]
        provider_registry = ProviderRegistry(configured_providers)
        if model_registry is None:
            default_provider_name = (
                "mock" if provider is None else configured_providers[0].provider_name
            )
            model_definitions = {
                "mock-model-v1": ModelDefinition(
                    "mock-model-v1", (default_provider_name,)
                )
            }
            if (
                provider is None
                and configured_openai.api_key is not None
                and configured_openai.model is not None
            ):
                model_definitions[configured_openai.model] = ModelDefinition(
                    configured_openai.model, ("openai",)
                )
            configured_models = ModelRegistry(model_definitions)
        else:
            configured_models = model_registry
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
        route_settings = (
            provider_route_settings or ProviderRouteSettings.from_environment()
        )
        route_executor = RouteExecutor(
            provider_registry,
            provider_executor,
            route_settings,
        )
        gateway_service = GatewayService(
            routing_policy=routing_policy,
            provider_registry=provider_registry,
            request_log_repository=request_log_repository,
            metrics=metrics,
            provider_executor=provider_executor,
            route_executor=route_executor,
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
