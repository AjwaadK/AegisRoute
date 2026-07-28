"""Provider implementation registry used by routing policies."""

from collections.abc import Iterable

from app.providers.base import ProviderAdapter
from app.routing.errors import ProviderNotFoundError


class ProviderRegistry:
    """Resolve provider implementations by their configured name."""

    def __init__(self, providers: Iterable[ProviderAdapter]) -> None:
        self._providers = {provider.provider_name: provider for provider in providers}

    def get(self, provider_name: str) -> ProviderAdapter:
        """Return a provider implementation or raise the routing-domain error."""

        try:
            return self._providers[provider_name]
        except KeyError:
            raise ProviderNotFoundError(provider_name) from None
