from abc import ABC, abstractmethod

from app.schemas.generation import GenerateRequest, ProviderResult


class AIProvider(ABC):
    """Contract implemented by AI provider integrations."""

    provider_name: str

    @abstractmethod
    async def generate(self, request: GenerateRequest, request_id: str) -> ProviderResult:
        """Generate text response for the input request."""


# Backwards-compatible name for existing provider implementations and callers.
ProviderAdapter = AIProvider
