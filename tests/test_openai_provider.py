import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.errors import (
    ProviderAuthenticationError,
    ProviderInternalError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.openai import OpenAIProviderAdapter
from app.schemas.generation import (
    ChatMessage,
    GenerateRequest,
    ProviderResult,
    TokenUsage,
)


class FakeResponses:
    def __init__(self, result=None, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def request() -> GenerateRequest:
    return GenerateRequest(
        model="gpt-test",
        messages=[
            ChatMessage(role="system", content="Be concise"),
            ChatMessage(role="user", content="Hello"),
        ],
        max_tokens=17,
        temperature=0.25,
    )


@pytest.mark.anyio
async def test_openai_provider_translates_one_responses_call() -> None:
    responses = FakeResponses(
        SimpleNamespace(
            output_text="Hi",
            usage=SimpleNamespace(input_tokens=4, output_tokens=2, total_tokens=6),
        )
    )
    provider = OpenAIProviderAdapter(FakeClient(responses), timeout_seconds=2)

    result = await provider.generate(request(), "request-1")

    assert result == ProviderResult(
        request_id="request-1",
        provider="openai",
        model="gpt-test",
        output="Hi",
        usage=TokenUsage(input_tokens=4, output_tokens=2, total_tokens=6),
    )
    assert responses.calls == [
        {
            "model": "gpt-test",
            "input": [
                {"role": "system", "content": "Be concise"},
                {"role": "user", "content": "Hello"},
            ],
            "max_output_tokens": 17,
            "temperature": 0.25,
        }
    ]
    assert type(result) is ProviderResult


@pytest.mark.anyio
async def test_openai_provider_handles_absent_usage() -> None:
    responses = FakeResponses(SimpleNamespace(output_text="Hi", usage=None))

    result = await OpenAIProviderAdapter(FakeClient(responses)).generate(
        request(), "request-1"
    )

    assert result.usage is None


@pytest.mark.anyio
async def test_openai_provider_preserves_partially_absent_usage() -> None:
    responses = FakeResponses(
        SimpleNamespace(
            output_text="Hi",
            usage=SimpleNamespace(input_tokens=4, output_tokens=None),
        )
    )

    result = await OpenAIProviderAdapter(FakeClient(responses)).generate(
        request(), "request-1"
    )

    assert result.usage == TokenUsage(input_tokens=4)


def sdk_status_error(error_type, status: int, code: str = "stable_code"):
    sdk_request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses",
        headers={"authorization": "Bearer secret-value"},
        content=b'{"input":"private prompt"}',
    )
    response = httpx.Response(status, request=sdk_request)
    return error_type(
        "unsafe private prompt secret-value",
        response=response,
        body={"error": {"code": code, "message": "unsafe private prompt"}},
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sdk_error", "expected_type"),
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
        (sdk_status_error(openai.BadRequestError, 400), ProviderInvalidRequestError),
        (sdk_status_error(openai.InternalServerError, 500), ProviderInternalError),
        (
            openai.APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com")
            ),
            ProviderUnavailableError,
        ),
    ],
)
async def test_openai_provider_maps_sdk_errors(sdk_error, expected_type) -> None:
    provider = OpenAIProviderAdapter(FakeClient(FakeResponses(error=sdk_error)))

    with pytest.raises(expected_type) as captured:
        await provider.generate(request(), "request-1")

    assert captured.value.provider_name == "openai"
    assert captured.value.__cause__ is sdk_error
    assert "private prompt" not in str(captured.value)
    assert "secret-value" not in str(captured.value)


@pytest.mark.anyio
async def test_openai_provider_preserves_stable_provider_code() -> None:
    sdk_error = sdk_status_error(openai.RateLimitError, 429, "rate_limit_exceeded")

    with pytest.raises(ProviderRateLimitError) as captured:
        await OpenAIProviderAdapter(
            FakeClient(FakeResponses(error=sdk_error))
        ).generate(request(), "request-1")

    assert captured.value.provider_code == "rate_limit_exceeded"


@pytest.mark.anyio
async def test_openai_provider_propagates_cancellation() -> None:
    provider = OpenAIProviderAdapter(
        FakeClient(FakeResponses(error=asyncio.CancelledError()))
    )

    with pytest.raises(asyncio.CancelledError):
        await provider.generate(request(), "request-1")


@pytest.mark.anyio
async def test_openai_provider_does_not_translate_programming_errors() -> None:
    error = TypeError("adapter bug")
    provider = OpenAIProviderAdapter(FakeClient(FakeResponses(error=error)))

    with pytest.raises(TypeError) as captured:
        await provider.generate(request(), "request-1")

    assert captured.value is error


@pytest.mark.anyio
async def test_provider_executor_owns_retry_across_single_openai_attempts() -> None:
    from app.config import ProviderRetrySettings
    from app.observability.metrics import NoopApplicationMetrics
    from app.providers.executor import ProviderExecutor, RetryPolicy

    first_error = sdk_status_error(openai.RateLimitError, 429)

    class SequencedResponses(FakeResponses):
        async def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise first_error
            return SimpleNamespace(output_text="recovered", usage=None)

    responses = SequencedResponses()
    provider = OpenAIProviderAdapter(FakeClient(responses))
    settings = ProviderRetrySettings(
        max_attempts=2,
        base_delay_seconds=0,
        max_delay_seconds=0,
        request_deadline_seconds=5,
        min_attempt_budget_seconds=0,
    )
    executor = ProviderExecutor(
        RetryPolicy(settings, jitter=lambda _low, _high: 0),
        sleep=lambda _delay: asyncio.sleep(0),
    )

    result = await executor.execute(
        provider,
        request(),
        "request-1",
        "gpt-test",
        NoopApplicationMetrics(),
    )

    assert result.output == "recovered"
    assert len(responses.calls) == 2


@pytest.mark.anyio
async def test_provider_executor_does_not_retry_openai_authentication_error() -> None:
    from app.config import ProviderRetrySettings
    from app.observability.metrics import NoopApplicationMetrics
    from app.providers.executor import ProviderExecutor, RetryPolicy

    responses = FakeResponses(error=sdk_status_error(openai.AuthenticationError, 401))
    settings = ProviderRetrySettings(
        max_attempts=3,
        base_delay_seconds=0,
        max_delay_seconds=0,
        request_deadline_seconds=5,
        min_attempt_budget_seconds=0,
    )

    with pytest.raises(ProviderAuthenticationError):
        await ProviderExecutor(RetryPolicy(settings)).execute(
            OpenAIProviderAdapter(FakeClient(responses)),
            request(),
            "request-1",
            "gpt-test",
            NoopApplicationMetrics(),
        )

    assert len(responses.calls) == 1
