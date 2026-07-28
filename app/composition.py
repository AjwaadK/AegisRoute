"""Application composition for process-scoped runtime dependencies."""

<<<<<<< ours
<<<<<<< ours
from dataclasses import dataclass, field
=======
from dataclasses import dataclass
>>>>>>> theirs
=======
from dataclasses import dataclass
>>>>>>> theirs

from sqlalchemy.engine import Engine

from app.db.session import create_database_engine, create_session_factory
<<<<<<< ours
<<<<<<< ours
from app.models.model_registry import ModelDefinition, ModelRegistry
from app.providers.base import ProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.providers.provider_registry import ProviderRegistry
from app.repositories.request_log import SQLAlchemyRequestLogRepository
=======
=======
>>>>>>> theirs
from app.providers.base import ProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.repositories.request_log import SQLAlchemyRequestLogRepository
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy, RoutingPolicy
from app.routing.provider_registry import ProviderRegistry
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
from app.services.gateway import GatewayService


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Process-scoped dependencies owned by the FastAPI application."""

    engine: Engine
    gateway_service: GatewayService
<<<<<<< ours
<<<<<<< ours
    model_registry: ModelRegistry = field(
        default_factory=lambda: ModelRegistry(
            {"mock-model-v1": ModelDefinition("mock-model-v1", ("mock",))}
        )
    )
=======
    routing_policy: RoutingPolicy | None = None
>>>>>>> theirs
=======
    routing_policy: RoutingPolicy | None = None
>>>>>>> theirs

    def dispose(self) -> None:
        """Release resources owned by the application process."""

        self.engine.dispose()


<<<<<<< ours
<<<<<<< ours
def build_application_container(
    provider: ProviderAdapter | None = None,
    *,
    model_registry: ModelRegistry | None = None,
) -> ApplicationContainer:
=======
def build_application_container(provider: ProviderAdapter | None = None) -> ApplicationContainer:
>>>>>>> theirs
=======
def build_application_container(provider: ProviderAdapter | None = None) -> ApplicationContainer:
>>>>>>> theirs
    """Assemble the production dependency graph without opening a session."""

    engine = create_database_engine()
    try:
        session_factory = create_session_factory(engine)
        request_log_repository = SQLAlchemyRequestLogRepository(session_factory)
<<<<<<< ours
<<<<<<< ours
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
=======
=======
>>>>>>> theirs
        provider_adapter = provider or MockProviderAdapter()
        provider_registry = ProviderRegistry([provider_adapter])
        model_registry = ModelRegistry(
            [ModelDefinition(name="mock-model-v1", providers=(provider_adapter.provider_name,))]
        )
        routing_policy = DeterministicRoutingPolicy(model_registry, provider_registry)
        gateway_service = GatewayService(
            provider_adapter=provider_adapter,
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
            request_log_repository=request_log_repository,
        )
        return ApplicationContainer(
            engine=engine,
            gateway_service=gateway_service,
<<<<<<< ours
<<<<<<< ours
            model_registry=configured_model_registry,
=======
            routing_policy=routing_policy,
>>>>>>> theirs
=======
            routing_policy=routing_policy,
>>>>>>> theirs
        )
    except Exception:
        engine.dispose()
        raise
<<<<<<< ours
<<<<<<< ours


def _validate_model_provider_references(
    *,
    model_registry: ModelRegistry,
    provider_registry: ProviderRegistry,
) -> None:
    """Fail composition when a model references an unknown provider."""

    for model_name in model_registry.names():
        for provider_name in model_registry.get(model_name).providers:
            provider_registry.get(provider_name)
=======
>>>>>>> theirs
=======
>>>>>>> theirs
