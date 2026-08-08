"""Immutable, infrastructure-independent routing value objects."""

from dataclasses import dataclass
from typing import Protocol


def _validate_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    """The model requested by a caller before routing is performed."""

    requested_model: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.requested_model, "requested_model")


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """One bounded provider/model choice in routing preference order."""

    provider_name: str
    selected_model: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.provider_name, "provider_name")
        _validate_non_empty(self.selected_model, "selected_model")
        if self.provider_name != self.provider_name.lower():
            raise ValueError("provider_name must be lowercase")

    @property
    def identity(self) -> tuple[str, str]:
        return (self.provider_name, self.selected_model)


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """A provider-agnostic record of a completed routing choice."""

    requested_model: str
    selected_model: str
    provider_name: str
    reason: str
    fallback_candidates: tuple[RouteCandidate, ...] = ()

    def __post_init__(self) -> None:
        _validate_non_empty(self.requested_model, "requested_model")
        _validate_non_empty(self.selected_model, "selected_model")
        _validate_non_empty(self.provider_name, "provider_name")
        _validate_non_empty(self.reason, "reason")
        if self.provider_name != self.provider_name.lower():
            raise ValueError("provider_name must be lowercase")
        if not isinstance(self.fallback_candidates, tuple):
            raise TypeError("fallback_candidates must be a tuple")

    @property
    def candidates(self) -> tuple[RouteCandidate, ...]:
        """Return the primary route followed by ordered fallback candidates."""

        return (
            RouteCandidate(self.provider_name, self.selected_model),
            *self.fallback_candidates,
        )


class RoutingPolicy(Protocol):
    """Select an ordered provider/model route for a routing request."""

    def route(self, request: RoutingRequest) -> RoutingDecision:
        """Return a primary decision with optional ordered fallbacks."""
