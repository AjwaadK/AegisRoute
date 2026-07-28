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
class RoutingDecision:
    """A provider-agnostic record of a completed routing choice."""

    requested_model: str
    selected_model: str
    provider_name: str
    reason: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.requested_model, "requested_model")
        _validate_non_empty(self.selected_model, "selected_model")
        _validate_non_empty(self.provider_name, "provider_name")
        _validate_non_empty(self.reason, "reason")
        if self.provider_name != self.provider_name.lower():
            raise ValueError("provider_name must be lowercase")


class RoutingPolicy(Protocol):
    """Select a provider and concrete model for a routing request."""

    def route(self, request: RoutingRequest) -> RoutingDecision:
        """Return the routing decision for the request."""
