"""Immutable registry of configured AI providers."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.errors import ProviderNotFoundError
from app.providers.base import AIProvider


@dataclass(frozen=True, slots=True)
class ProviderRegistry:
    """Provide name-based access to a fixed set of provider instances.

    The constructor accepts a mapping. Duplicate provider names therefore
    cannot reach the registry: mappings contain at most one value per key.
    """

    _providers: dict[str, AIProvider] = field(init=False, repr=False)

    def __init__(self, providers: Mapping[str, AIProvider]) -> None:
        copied_providers = dict(providers)
        if not copied_providers:
            raise ValueError("Provider registry cannot be empty")
        invalid_names = tuple(name for name in copied_providers if name != name.lower())
        if invalid_names:
            raise ValueError("Provider names must be lowercase")
        object.__setattr__(self, "_providers", copied_providers)

    def get(self, provider_name: str) -> AIProvider:
        """Return a registered provider by name."""

        try:
            return self._providers[provider_name]
        except KeyError:
            raise ProviderNotFoundError(provider_name) from None

    def names(self) -> tuple[str, ...]:
        """Return provider names in their mapping iteration order."""

        return tuple(self._providers)
