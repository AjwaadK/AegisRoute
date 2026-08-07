import asyncio

from app.providers.base import ProviderAdapter
from app.schemas.generation import GenerateRequest, ProviderResult


class MockProviderAdapter(ProviderAdapter):
    provider_name = "mock"

    def __init__(
        self,
        failure: Exception | None = None,
        *,
        timeout_seconds: float = 30.0,
        response_delay_seconds: float = 0.0,
    ) -> None:
        super().__init__(timeout_seconds)
        self.failure = failure
        self.response_delay_seconds = response_delay_seconds

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
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
