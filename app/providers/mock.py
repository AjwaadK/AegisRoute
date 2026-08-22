import asyncio
from collections.abc import AsyncIterator

from app.providers.base import ProviderAdapter
from app.schemas.generation import (
    GenerateRequest,
    ProviderResult,
    ProviderStreamEvent,
    StreamCompleted,
    StreamTextDelta,
    TokenUsage,
)


class MockProviderAdapter(ProviderAdapter):
    provider_name = "mock"

    def __init__(
        self,
        failure: Exception | None = None,
        *,
        timeout_seconds: float = 30.0,
        response_delay_seconds: float = 0.0,
        stream_chunks: tuple[str, ...] | None = None,
        stream_failure: Exception | None = None,
        stream_failure_after_chunks: int = 0,
        stream_usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(timeout_seconds)
        self.failure = failure
        self.response_delay_seconds = response_delay_seconds
        self.stream_chunks = stream_chunks
        self.stream_failure = stream_failure
        self.stream_failure_after_chunks = stream_failure_after_chunks
        self.stream_usage = stream_usage

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        return await self._with_timeout(self._generate(request, request_id))

    async def _generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        if self.response_delay_seconds:
            await asyncio.sleep(self.response_delay_seconds)
        if self.failure is not None:
            raise self.failure

        last_user_message = next(
            (
                message.content
                for message in reversed(request.messages)
                if message.role == "user"
            ),
            request.messages[-1].content,
        )
        output = f"mock_response:{last_user_message}"
        input_tokens = sum(len(message.content.split()) for message in request.messages)
        output_tokens = len(output.split())
        return ProviderResult(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output=output,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    async def stream(
        self, request: GenerateRequest, request_id: str
    ) -> AsyncIterator[ProviderStreamEvent]:
        if self.response_delay_seconds:
            await asyncio.sleep(self.response_delay_seconds)
        chunks = self.stream_chunks
        if chunks is None:
            last_user_message = next(
                (
                    message.content
                    for message in reversed(request.messages)
                    if message.role == "user"
                ),
                request.messages[-1].content,
            )
            chunks = (f"mock_response:{last_user_message}",)
        if self.stream_failure is not None and self.stream_failure_after_chunks == 0:
            raise self.stream_failure
        for emitted, chunk in enumerate(chunks, start=1):
            yield StreamTextDelta(text=chunk)
            if (
                self.stream_failure is not None
                and emitted >= self.stream_failure_after_chunks
            ):
                raise self.stream_failure
        yield StreamCompleted(
            provider=self.provider_name,
            model=request.model,
            usage=self.stream_usage,
        )
