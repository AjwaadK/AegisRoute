"""Deterministic routing policy implementations."""

from typing import Protocol

from app.routing.contracts import RoutingDecision, RoutingRequest
from app.routing.model_registry import ModelRegistry
from app.routing.provider_registry import ProviderRegistry


class RoutingPolicy(Protocol):
    """Contract for selecting a provider and model for a routing request."""

    def route(self, request: RoutingRequest) -> RoutingDecision:
        """Return the routing decision for the request."""


class DeterministicRoutingPolicy(RoutingPolicy):
    """Select the first configured provider for a registered model."""

    def __init__(self, model_registry: ModelRegistry, provider_registry: ProviderRegistry) -> None:
        self._model_registry = model_registry
        self._provider_registry = provider_registry

    def route(self, request: RoutingRequest) -> RoutingDecision:
        model_definition = self._model_registry.get(request.requested_model)
        provider_name = model_definition.providers[0]
        self._provider_registry.get(provider_name)
        return RoutingDecision(
            requested_model=request.requested_model,
            selected_model=model_definition.name,
            provider_name=provider_name,
            reason="selected first configured provider",
        )


__all__ = ("DeterministicRoutingPolicy", "RoutingPolicy")
