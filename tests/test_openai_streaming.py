import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.errors import (
    ProviderAuthenticationError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.openai import OpenAIProviderAdapter
from app.schemas.generation import (
    GenerateRequest,
    StreamCompleted,
    StreamTextDelta,
    TokenUsage,
)


class FakeStream:
    def __init__(self, events=(), error: BaseException | None = None) -> None:
        self.events = iter(events)
        self.error = error
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.error is not None:
            error, self.error = self.error, None
            raise error
        try:
            return next(self.events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def aclose(self) -> None:
        self.closed = True


class FakeResponses:
    def __init__(self, stream: FakeStream | None = None, error=None) -> None:
        self.stream = stream
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.stream


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def request() -> GenerateRequest:
    return GenerateRequest(
        model="gpt-test",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=17,
        temperature=0.25,
    )


async def collect(provider: OpenAIProviderAdapter):
    return [event async for event in provider.stream(request(), "request-1")]


def sdk_status_error(error_type, status: int):
    sdk_request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status, request=sdk_request)
    return error_type("unsafe", response=response, body={"error": {"code": "stable"}})


@pytest.mark.anyio
async def test_openai_stream_translates_deltas_and_final_usage_once() -> None:
    stream = FakeStream(
        [
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.output_text.delta", delta="hel"),
            SimpleNamespace(type="response.output_text.delta", delta="lo"),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    usage=SimpleNamespace(
                        input_tokens=4, output_tokens=2, total_tokens=6
                    )
                ),
            ),
        ]
    )
    responses = FakeResponses(stream)

    events = await collect(OpenAIProviderAdapter(FakeClient(responses)))

    assert events == [
        StreamTextDelta(text="hel"),
        StreamTextDelta(text="lo"),
        StreamCompleted(
            provider="openai",
            model="gpt-test",
            usage=TokenUsage(input_tokens=4, output_tokens=2, total_tokens=6),
        ),
    ]
    assert len(responses.calls) == 1
    assert responses.calls[0]["model"] == "gpt-test"
    assert responses.calls[0]["stream"] is True
    assert stream.closed


@pytest.mark.anyio
async def test_openai_stream_handles_absent_usage() -> None:
    stream = FakeStream(
        [
            SimpleNamespace(
                type="response.completed", response=SimpleNamespace(usage=None)
            )
        ]
    )

    events = await collect(OpenAIProviderAdapter(FakeClient(FakeResponses(stream))))

    assert events == [StreamCompleted(provider="openai", model="gpt-test")]


@pytest.mark.anyio
async def test_openai_stream_does_not_swallow_provider_failure_events() -> None:
    stream = FakeStream(
        [
            SimpleNamespace(
                type="response.failed",
                response=SimpleNamespace(
                    error=SimpleNamespace(code="server_error", message="unsafe")
                ),
            )
        ]
    )

    with pytest.raises(ProviderInternalError) as captured:
        await collect(OpenAIProviderAdapter(FakeClient(FakeResponses(stream))))

    assert captured.value.provider_code == "server_error"
    assert "unsafe" not in str(captured.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sdk_error", "expected"),
    [
        (
            openai.APITimeoutError(
                request=httpx.Request("POST", "https://api.openai.com")
            ),
            ProviderTimeoutError,
        ),
        (sdk_status_error(openai.RateLimitError, 429), ProviderRateLimitError),
        (
            sdk_status_error(openai.AuthenticationError, 401),
            ProviderAuthenticationError,
        ),
        (
            openai.APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com")
            ),
            ProviderUnavailableError,
        ),
    ],
)
async def test_openai_stream_maps_known_sdk_errors(sdk_error, expected) -> None:
    provider = OpenAIProviderAdapter(FakeClient(FakeResponses(error=sdk_error)))

    with pytest.raises(expected) as captured:
        await collect(provider)

    assert captured.value.__cause__ is sdk_error


@pytest.mark.anyio
@pytest.mark.parametrize("error", [asyncio.CancelledError(), TypeError("bug")])
async def test_openai_stream_propagates_cancellation_and_programming_errors(
    error,
) -> None:
    stream = FakeStream(error=error)
    provider = OpenAIProviderAdapter(FakeClient(FakeResponses(stream)))

    with pytest.raises(type(error)) as captured:
        await collect(provider)

    assert captured.value is error
    assert stream.closed
