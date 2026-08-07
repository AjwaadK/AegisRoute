import math

import pytest

from app.config import ProviderRetrySettings
from app.errors import (
    ProviderAuthenticationError,
    ProviderInternalError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.executor import RetryPolicy


def settings(**changes: object) -> ProviderRetrySettings:
    defaults = {
        "max_attempts": 3,
        "base_delay_seconds": 0.25,
        "max_delay_seconds": 2.0,
        "request_deadline_seconds": 10.0,
        "min_attempt_budget_seconds": 0.1,
    }
    defaults.update(changes)
    return ProviderRetrySettings(**defaults)


@pytest.mark.parametrize(
    "error_type",
    (
        ProviderTimeoutError,
        ProviderRateLimitError,
        ProviderUnavailableError,
        ProviderInternalError,
    ),
)
def test_selected_transient_errors_are_retryable(error_type) -> None:
    assert RetryPolicy(settings()).is_retryable(error_type("mock"))


@pytest.mark.parametrize(
    "error_type", (ProviderAuthenticationError, ProviderInvalidRequestError)
)
def test_client_and_authentication_errors_are_not_retryable(error_type) -> None:
    assert not RetryPolicy(settings()).is_retryable(error_type("mock"))


def test_max_attempts_one_and_exhausted_budget_never_retry() -> None:
    error = ProviderTimeoutError("mock")
    one_attempt = RetryPolicy(settings(max_attempts=1))
    exhausted = RetryPolicy(settings(max_attempts=2))

    assert not one_attempt.permits_retry(
        error,
        attempts_made=1,
        remaining_deadline_seconds=10,
        delay_seconds=0,
    )
    assert not exhausted.permits_retry(
        error,
        attempts_made=2,
        remaining_deadline_seconds=10,
        delay_seconds=0,
    )


def test_deadline_requires_sleep_plus_minimum_useful_attempt_budget() -> None:
    policy = RetryPolicy(settings(min_attempt_budget_seconds=0.5))
    error = ProviderTimeoutError("mock")

    assert not policy.permits_retry(
        error,
        attempts_made=1,
        remaining_deadline_seconds=0.74,
        delay_seconds=0.25,
    )
    assert policy.permits_retry(
        error,
        attempts_made=1,
        remaining_deadline_seconds=0.75,
        delay_seconds=0.25,
    )


def test_zero_based_exponential_caps_and_maximum_cap() -> None:
    policy = RetryPolicy(settings(base_delay_seconds=0.25, max_delay_seconds=1.0))

    assert [policy.backoff_cap(number) for number in range(5)] == [
        0.25,
        0.5,
        1.0,
        1.0,
        1.0,
    ]


def test_full_jitter_uses_zero_and_the_exponential_cap() -> None:
    calls = []

    def jitter(lower: float, upper: float) -> float:
        calls.append((lower, upper))
        return upper * 0.4

    policy = RetryPolicy(settings(), jitter=jitter)

    assert policy.retry_delay(1) == 0.2
    assert calls == [(0.0, 0.5)]
    assert 0 <= policy.retry_delay(0) <= policy.backoff_cap(0)


@pytest.mark.parametrize(
    "changes",
    (
        {"max_attempts": 0},
        {"max_attempts": 1.5},
        {"base_delay_seconds": -1},
        {"base_delay_seconds": math.inf},
        {"max_delay_seconds": math.nan},
        {"base_delay_seconds": 2, "max_delay_seconds": 1},
        {"request_deadline_seconds": 0},
        {"min_attempt_budget_seconds": -0.1},
    ),
)
def test_invalid_retry_settings_are_rejected(changes) -> None:
    with pytest.raises(ValueError):
        settings(**changes)


def test_retry_settings_load_explicit_environment(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("PROVIDER_RETRY_BASE_DELAY_SECONDS", "0.5")
    monkeypatch.setenv("PROVIDER_RETRY_MAX_DELAY_SECONDS", "3")
    monkeypatch.setenv("GATEWAY_REQUEST_DEADLINE_SECONDS", "12")
    monkeypatch.setenv("PROVIDER_MIN_RETRY_ATTEMPT_BUDGET_SECONDS", "0.2")

    configured = ProviderRetrySettings.from_environment()

    assert configured == ProviderRetrySettings(4, 0.5, 3, 12, 0.2)
