"""Deterministic routing policy implementations."""

from typing import Protocol

from app.routing.contracts import RouteCandidate, RoutingDecision, RoutingRequest
from app.routing.model_registry import ModelRegistry
from app.routing.provider_registry import ProviderRegistry


class RoutingPolicy(Protocol):
    """Contract for selecting ordered provider/model route candidates."""

    def route(self, request: RoutingRequest) -> RoutingDecision:
        """Return a primary decision with optional ordered fallbacks."""


class DeterministicRoutingPolicy(RoutingPolicy):
    """Order a registered model's configured providers deterministically."""

    def __init__(
        self, model_registry: ModelRegistry, provider_registry: ProviderRegistry
    ) -> None:
        self._model_registry = model_registry
        self._provider_registry = provider_registry

    def route(self, request: RoutingRequest) -> RoutingDecision:
        model_definition = self._model_registry.get(request.requested_model)
        for provider_name in model_definition.providers:
            self._provider_registry.get(provider_name)
        provider_name = model_definition.providers[0]
        return RoutingDecision(
            requested_model=request.requested_model,
            selected_model=model_definition.name,
            provider_name=provider_name,
            reason="selected first configured provider",
            fallback_candidates=tuple(
                RouteCandidate(candidate_provider, model_definition.name)
                for candidate_provider in model_definition.providers[1:]
            ),
        )


__all__ = ("DeterministicRoutingPolicy", "RoutingPolicy")
