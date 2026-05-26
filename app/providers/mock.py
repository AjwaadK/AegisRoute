from app.providers.base import ProviderAdapter
from app.schemas.generation import GenerateRequest, GenerateResponse


class MockProviderAdapter(ProviderAdapter):
    provider_name = "mock"

    async def generate(self, request: GenerateRequest, request_id: str) -> GenerateResponse:
        last_user_message = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            request.messages[-1].content,
        )
        output = f"mock_response:{last_user_message}"
        input_tokens = sum(len(message.content.split()) for message in request.messages)
        output_tokens = len(output.split())
        return GenerateResponse(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output=output,
            latency_ms=0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
