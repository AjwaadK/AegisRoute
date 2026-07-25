"""Application composition for process-scoped runtime dependencies."""

from dataclasses import dataclass

from sqlalchemy.engine import Engine

from app.db.session import create_database_engine, create_session_factory
from app.providers.base import ProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.providers.provider_registry import ProviderRegistry
from app.repositories.request_log import SQLAlchemyRequestLogRepository
from app.services.gateway import GatewayService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Process-scoped dependencies owned by the FastAPI application."""

    engine: Engine
    gateway_service: GatewayService

    def dispose(self) -> None:
        """Release resources owned by the application process."""

        self.engine.dispose()


def build_application_container(provider: ProviderAdapter | None = None) -> ApplicationContainer:
    """Assemble the production dependency graph without opening a session."""

    engine = create_database_engine()
    try:
        session_factory = create_session_factory(engine)
        request_log_repository = SQLAlchemyRequestLogRepository(session_factory)
        configured_provider = provider or MockProviderAdapter()
        provider_registry = ProviderRegistry(
            {configured_provider.provider_name: configured_provider}
        )
        gateway_service = GatewayService(
            provider_registry=provider_registry,
            provider_name=configured_provider.provider_name,
            request_log_repository=request_log_repository,
        )
        return ApplicationContainer(engine=engine, gateway_service=gateway_service)
    except Exception:
        engine.dispose()
        raise
