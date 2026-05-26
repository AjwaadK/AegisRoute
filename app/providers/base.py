from abc import ABC, abstractmethod

from app.schemas.generation import GenerateRequest, GenerateResponse


class ProviderAdapter(ABC):
    @abstractmethod
    async def generate(self, request: GenerateRequest, request_id: str) -> GenerateResponse:
        """Generate text response for the input request."""
