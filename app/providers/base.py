import asyncio
import math
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable
from typing import Protocol, TypeVar, runtime_checkable

from app.errors import ProviderTimeoutError
from app.schemas.generation import (
    GenerateRequest,
    ProviderResult,
    ProviderStreamEvent,
)


@runtime_checkable
class StreamingProvider(Protocol):
    """Optional capability for adapters that support provider-neutral text streams."""

    provider_name: str

    def stream(
        self, request: GenerateRequest, request_id: str
    ) -> AsyncIterator[ProviderStreamEvent]: ...


class AIProvider(ABC):
    """Contract implemented by AI provider integrations."""

    provider_name: str

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    async def _with_timeout(self, operation: Awaitable["T"]) -> "T":
        """Enforce the provider deadline and normalize timeout exceptions."""

        try:
            return await asyncio.wait_for(operation, timeout=self.timeout_seconds)
        except TimeoutError as exc:
            raise ProviderTimeoutError(
                self.provider_name,
                provider_code="timeout",
                message=f"Provider '{self.provider_name}' request timed out",
            ) from exc

    @abstractmethod
    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        """Generate text response for the input request."""


# Backwards-compatible name for existing provider implementations and callers.
ProviderAdapter = AIProvider

T = TypeVar("T")
