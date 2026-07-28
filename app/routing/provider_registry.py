"""Immutable provider implementation registry used by routing policies."""

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from app.errors import ProviderNotFoundError
from app.providers.base import ProviderAdapter


class ProviderRegistry:
    """Resolve provider implementations by their configured name."""

    __slots__ = ("_providers",)

    def __init__(
        self,
        providers: Mapping[str, ProviderAdapter] | Iterable[ProviderAdapter],
    ) -> None:
        if isinstance(providers, Mapping):
            copied = dict(providers)
        else:
            copied = {provider.provider_name: provider for provider in providers}
        if not copied:
            raise ValueError("Provider registry cannot be empty")
        if any(name != name.lower() for name in copied):
            raise ValueError("Provider names must be lowercase")
        object.__setattr__(self, "_providers", MappingProxyType(copied))

    def __setattr__(self, name: str, value: object) -> None:
        if hasattr(self, name):
            raise AttributeError(f"{type(self).__name__} is immutable")
        object.__setattr__(self, name, value)

    def get(self, provider_name: str) -> ProviderAdapter:
        try:
            return self._providers[provider_name]
        except KeyError:
            raise ProviderNotFoundError(provider_name) from None

    def names(self) -> tuple[str, ...]:
        return tuple(self._providers)
