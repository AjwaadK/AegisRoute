import asyncio

import pytest

from app.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderInternalError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.mock import MockProviderAdapter
from app.schemas.generation import GenerateRequest

PROVIDER_ERROR_TYPES = (
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderAuthenticationError,
    ProviderUnavailableError,
    ProviderInvalidRequestError,
    ProviderInternalError,
)


@pytest.mark.parametrize("error_type", PROVIDER_ERROR_TYPES)
def test_typed_provider_errors_preserve_metadata(
    error_type: type[ProviderError],
) -> None:
    error = error_type(
        "example-provider",
        provider_code="provider-code-123",
        message="human-readable provider failure",
    )

    assert isinstance(error, ProviderError)
    assert error.provider_name == "example-provider"
    assert error.provider_code == "provider-code-123"
    assert error.message == "human-readable provider failure"
    assert str(error) == "human-readable provider failure"


def test_provider_error_supports_optional_metadata() -> None:
    error = ProviderError("example-provider")

    assert error.provider_name == "example-provider"
    assert error.provider_code is None
    assert error.message is None
    assert str(error) == "Provider 'example-provider' request failed"


def test_provider_error_supports_exception_chaining() -> None:
    upstream_error = TimeoutError("socket timed out")

    try:
        raise upstream_error
    except TimeoutError as exc:
        try:
            raise ProviderTimeoutError(
                "example-provider",
                provider_code="timeout",
                message="provider timed out",
            ) from exc
        except ProviderTimeoutError as error:
            assert error.__cause__ is upstream_error
            assert error.__suppress_context__ is True


@pytest.mark.parametrize("error_type", PROVIDER_ERROR_TYPES)
def test_mock_provider_typed_failures_are_caught_as_provider_errors(
    error_type: type[ProviderError],
) -> None:
    failure = error_type("mock", provider_code="test-failure")
    provider = MockProviderAdapter(failure=failure)
    request = GenerateRequest(
        model="mock-model-v1",
        messages=[{"role": "user", "content": "Hello router"}],
        max_tokens=64,
        temperature=0.5,
    )

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.generate(request, "request-123"))

    assert exc_info.value is failure
