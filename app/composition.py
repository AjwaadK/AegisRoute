"""Application composition for process-scoped runtime dependencies."""

from dataclasses import dataclass

from sqlalchemy.engine import Engine

from app.db.session import create_database_engine, create_session_factory
from app.providers.base import ProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.repositories.request_log import SQLAlchemyRequestLogRepository
from app.routing.contracts import RoutingPolicy
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.services.gateway import GatewayService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Process-scoped dependencies owned by the FastAPI application."""

    engine: Engine
    gateway_service: GatewayService
    routing_policy: RoutingPolicy | None = None

    def dispose(self) -> None:
        """Release resources owned by the application process."""

        self.engine.dispose()


def build_application_container(provider: ProviderAdapter | None = None) -> ApplicationContainer:
    """Assemble the production dependency graph without opening a session."""

    engine = create_database_engine()
    try:
        session_factory = create_session_factory(engine)
        request_log_repository = SQLAlchemyRequestLogRepository(session_factory)
        provider_adapter = provider or MockProviderAdapter()
        provider_registry = ProviderRegistry([provider_adapter])
        model_registry = ModelRegistry(
            [ModelDefinition(name="mock-model-v1", providers=(provider_adapter.provider_name,))]
        )
        routing_policy = DeterministicRoutingPolicy(model_registry, provider_registry)
        gateway_service = GatewayService(
            provider_adapter=provider_adapter,
            request_log_repository=request_log_repository,
        )
        return ApplicationContainer(
            engine=engine,
            gateway_service=gateway_service,
            routing_policy=routing_policy,
        )
    except Exception:
        engine.dispose()
        raise
