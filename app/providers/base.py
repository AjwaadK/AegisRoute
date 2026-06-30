from abc import ABC, abstractmethod

from app.schemas.generation import GenerateRequest, ProviderResult


class ProviderAdapter(ABC):
    @abstractmethod
    async def generate(self, request: GenerateRequest, request_id: str) -> ProviderResult:
        """Generate text response for the input request."""
