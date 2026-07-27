import pytest

from app.providers.base import ProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.routing.contracts import RoutingDecision, RoutingPolicy, RoutingRequest
from app.routing.errors import ModelNotFoundError, ProviderNotFoundError
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy
from app.routing.provider_registry import ProviderRegistry


def make_policy(
    *,
    providers: tuple[str, ...] = ("mock",),
    registered_providers: tuple[ProviderAdapter, ...] | None = None,
) -> DeterministicRoutingPolicy:
    model_registry = ModelRegistry(
        [ModelDefinition(name="public-model", providers=providers)]
    )
    provider_registry = ProviderRegistry(
        registered_providers
        if registered_providers is not None
        else (MockProviderAdapter(),)
    )
    return DeterministicRoutingPolicy(model_registry, provider_registry)


def test_known_model_routes_successfully() -> None:
    decision = make_policy().route(RoutingRequest(requested_model="public-model"))

    assert decision == RoutingDecision(
        requested_model="public-model",
        selected_model="public-model",
        provider_name="mock",
        reason="selected first configured provider",
    )


def test_first_configured_provider_is_selected() -> None:
    first_provider = MockProviderAdapter()

    class OtherProvider(MockProviderAdapter):
        provider_name = "other"

    policy = make_policy(
        providers=("other", "mock"),
        registered_providers=(first_provider, OtherProvider()),
    )

    decision = policy.route(RoutingRequest(requested_model="public-model"))

    assert decision.provider_name == "other"


def test_unknown_model_raises_model_not_found() -> None:
    with pytest.raises(ModelNotFoundError):
        make_policy().route(RoutingRequest(requested_model="unknown-model"))


def test_missing_provider_raises_provider_not_found() -> None:
    policy = make_policy(providers=("missing",))

    with pytest.raises(ProviderNotFoundError):
        policy.route(RoutingRequest(requested_model="public-model"))


def test_route_returns_routing_decision() -> None:
    decision = make_policy().route(RoutingRequest(requested_model="public-model"))

    assert isinstance(decision, RoutingDecision)


def test_deterministic_policy_satisfies_routing_policy_contract() -> None:
    policy: RoutingPolicy = make_policy()

    assert policy.route(RoutingRequest(requested_model="public-model")).provider_name == "mock"
