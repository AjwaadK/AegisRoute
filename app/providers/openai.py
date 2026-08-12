"""Single-attempt OpenAI Responses API adapter."""

import asyncio
from typing import Any, Protocol

import openai

from app.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderInternalError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.base import ProviderAdapter
from app.schemas.generation import GenerateRequest, ProviderResult, TokenUsage


class ResponsesResource(Protocol):
    async def create(self, **kwargs: Any) -> Any:
        """Create one OpenAI response."""


class AsyncOpenAIClient(Protocol):
    responses: ResponsesResource


class OpenAIProviderAdapter(ProviderAdapter):
    """Translate one AegisRoute request into one OpenAI Responses API call."""

    provider_name = "openai"

    def __init__(
        self,
        client: AsyncOpenAIClient,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(timeout_seconds)
        self._client = client

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        return await self._with_timeout(self._generate(request, request_id))

    async def _generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        try:
            response = await self._client.responses.create(
                model=request.model,
                input=[
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                max_output_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except asyncio.CancelledError:
            raise
        except openai.APITimeoutError as exc:
            raise self._translated_error(ProviderTimeoutError, exc) from exc
        except openai.RateLimitError as exc:
            raise self._translated_error(ProviderRateLimitError, exc) from exc
        except openai.AuthenticationError as exc:
            raise self._translated_error(ProviderAuthenticationError, exc) from exc
        except openai.BadRequestError as exc:
            raise self._translated_error(ProviderInvalidRequestError, exc) from exc
        except openai.InternalServerError as exc:
            raise self._translated_error(ProviderInternalError, exc) from exc
        except openai.APIConnectionError as exc:
            raise self._translated_error(ProviderUnavailableError, exc) from exc
        except openai.APIStatusError as exc:
            error_type = self._status_error_type(exc.status_code)
            raise self._translated_error(error_type, exc) from exc

        usage = getattr(response, "usage", None)
        return ProviderResult(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output=response.output_text,
            usage=(
                TokenUsage(
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                )
                if usage is not None
                else None
            ),
        )

    @classmethod
    def _translated_error(
        cls,
        error_type: type[ProviderError],
        error: openai.APIError,
    ) -> ProviderError:
        provider_code = cls._provider_code(error)
        return error_type(
            cls.provider_name,
            provider_code=provider_code,
            message=f"Provider '{cls.provider_name}' request failed"
            + (f" ({provider_code})" if provider_code else ""),
        )

    @staticmethod
    def _provider_code(error: openai.APIError) -> str | None:
        code = getattr(error, "code", None)
        if isinstance(code, str) and code:
            return code[:128]
        body = getattr(error, "body", None)
        if isinstance(body, dict):
            error_details = body.get("error")
            if isinstance(error_details, dict):
                code = error_details.get("code")
                if isinstance(code, str) and code:
                    return code[:128]
        status_code = getattr(error, "status_code", None)
        return str(status_code) if isinstance(status_code, int) else None

    @staticmethod
    def _status_error_type(status_code: int) -> type[ProviderError]:
        if status_code in (401, 403):
            return ProviderAuthenticationError
        if status_code in (400, 404, 409, 422):
            return ProviderInvalidRequestError
        if status_code == 408:
            return ProviderTimeoutError
        if status_code == 429:
            return ProviderRateLimitError
        if status_code >= 500:
            return ProviderInternalError
        return ProviderUnavailableError


# Concise public name; the suffix remains consistent with the existing mock.
OpenAIProvider = OpenAIProviderAdapter

__all__ = ("AsyncOpenAIClient", "OpenAIProvider", "OpenAIProviderAdapter")
