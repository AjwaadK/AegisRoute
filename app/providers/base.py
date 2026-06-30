from abc import ABC, abstractmethod

from app.schemas.generation import GenerateRequest, ProviderResult


class ProviderAdapter(ABC):
    provider_name: str

    @abstractmethod
    async def generate(self, request: GenerateRequest, request_id: str) -> ProviderResult:
        """Generate text response for the input request."""
