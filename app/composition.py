"""Application composition for process-scoped runtime dependencies."""

from dataclasses import dataclass, field

from sqlalchemy.engine import Engine

from app.db.session import create_database_engine, create_session_factory
from app.models.model_registry import ModelDefinition, ModelRegistry
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
    model_registry: ModelRegistry = field(
        default_factory=lambda: ModelRegistry(
            {"mock-model-v1": ModelDefinition("mock-model-v1", ("mock",))}
        )
    )

    def dispose(self) -> None:
        """Release resources owned by the application process."""

        self.engine.dispose()


def build_application_container(
    provider: ProviderAdapter | None = None,
    *,
    model_registry: ModelRegistry | None = None,
) -> ApplicationContainer:
    """Assemble the production dependency graph without opening a session."""

    engine = create_database_engine()
    try:
        session_factory = create_session_factory(engine)
        request_log_repository = SQLAlchemyRequestLogRepository(session_factory)
        configured_provider = provider or MockProviderAdapter()
        provider_registry = ProviderRegistry(
            {configured_provider.provider_name: configured_provider}
        )
        configured_model_registry = model_registry or ModelRegistry(
            {
                "mock-model-v1": ModelDefinition(
                    "mock-model-v1",
                    (configured_provider.provider_name,),
                )
            }
        )
        _validate_model_provider_references(
            model_registry=configured_model_registry,
            provider_registry=provider_registry,
        )
        gateway_service = GatewayService(
            provider_registry=provider_registry,
            provider_name=configured_provider.provider_name,
            request_log_repository=request_log_repository,
        )
        return ApplicationContainer(
            engine=engine,
            gateway_service=gateway_service,
            model_registry=configured_model_registry,
        )
    except Exception:
        engine.dispose()
        raise


def _validate_model_provider_references(
    *,
    model_registry: ModelRegistry,
    provider_registry: ProviderRegistry,
) -> None:
    """Fail composition when a model references an unknown provider."""

    for model_name in model_registry.names():
        for provider_name in model_registry.get(model_name).providers:
            provider_registry.get(provider_name)
