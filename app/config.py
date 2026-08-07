"""Project environment configuration."""

import math
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_environment() -> None:
    """Load .env defaults without replacing explicitly supplied configuration."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True, slots=True)
class ProviderTimeoutSettings:
    """Timeout policy applied to provider calls, expressed in seconds."""

    default_timeout_seconds: float = 30.0
    mock_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        _validate_positive_seconds(
            "default_timeout_seconds", self.default_timeout_seconds
        )
        if self.mock_timeout_seconds is not None:
            _validate_positive_seconds(
                "mock_timeout_seconds", self.mock_timeout_seconds
            )

    @classmethod
    def from_environment(cls) -> "ProviderTimeoutSettings":
        """Build settings from environment variables after loading `.env`."""

        load_project_environment()
        return cls(
            default_timeout_seconds=_positive_seconds(
                "PROVIDER_TIMEOUT_SECONDS",
                os.environ.get("PROVIDER_TIMEOUT_SECONDS", "30"),
            ),
            mock_timeout_seconds=_optional_positive_seconds(
                "MOCK_PROVIDER_TIMEOUT_SECONDS",
                os.environ.get("MOCK_PROVIDER_TIMEOUT_SECONDS"),
            ),
        )

    def for_provider(self, provider_name: str) -> float:
        """Return the configured deadline for a provider."""

        if provider_name == "mock" and self.mock_timeout_seconds is not None:
            return self.mock_timeout_seconds
        return self.default_timeout_seconds


@dataclass(frozen=True, slots=True)
class ProviderRetrySettings:
    """Bounded retry and gateway deadline settings, expressed in seconds."""

    max_attempts: int = 2
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    request_deadline_seconds: float = 30.0
    min_attempt_budget_seconds: float = 0.1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or self.max_attempts < 1
        ):
            raise ValueError("max_attempts must be at least 1")
        _validate_non_negative_seconds("base_delay_seconds", self.base_delay_seconds)
        _validate_non_negative_seconds("max_delay_seconds", self.max_delay_seconds)
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                "max_delay_seconds must be greater than or equal to "
                "base_delay_seconds"
            )
        _validate_positive_seconds(
            "request_deadline_seconds", self.request_deadline_seconds
        )
        _validate_non_negative_seconds(
            "min_attempt_budget_seconds", self.min_attempt_budget_seconds
        )

    @classmethod
    def from_environment(cls) -> "ProviderRetrySettings":
        """Build retry settings from environment variables and `.env` defaults."""

        load_project_environment()
        return cls(
            max_attempts=_positive_integer(
                "PROVIDER_MAX_ATTEMPTS",
                os.environ.get("PROVIDER_MAX_ATTEMPTS", "2"),
            ),
            base_delay_seconds=_non_negative_seconds(
                "PROVIDER_RETRY_BASE_DELAY_SECONDS",
                os.environ.get("PROVIDER_RETRY_BASE_DELAY_SECONDS", "0.25"),
            ),
            max_delay_seconds=_non_negative_seconds(
                "PROVIDER_RETRY_MAX_DELAY_SECONDS",
                os.environ.get("PROVIDER_RETRY_MAX_DELAY_SECONDS", "2"),
            ),
            request_deadline_seconds=_positive_seconds(
                "GATEWAY_REQUEST_DEADLINE_SECONDS",
                os.environ.get("GATEWAY_REQUEST_DEADLINE_SECONDS", "30"),
            ),
            min_attempt_budget_seconds=_non_negative_seconds(
                "PROVIDER_MIN_RETRY_ATTEMPT_BUDGET_SECONDS",
                os.environ.get("PROVIDER_MIN_RETRY_ATTEMPT_BUDGET_SECONDS", "0.1"),
            ),
        )


def _optional_positive_seconds(name: str, value: str | None) -> float | None:
    return None if value is None else _positive_seconds(name, value)


def _positive_seconds(name: str, value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    _validate_positive_seconds(name, seconds)
    return seconds


def _non_negative_seconds(name: str, value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative number") from exc
    _validate_non_negative_seconds(name, seconds)
    return seconds


def _positive_integer(name: str, value: str) -> int:
    try:
        integer = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer of at least 1") from exc
    if integer < 1:
        raise ValueError(f"{name} must be an integer of at least 1")
    return integer


def _validate_positive_seconds(name: str, seconds: float) -> None:
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f"{name} must be a positive number")


def _validate_non_negative_seconds(name: str, seconds: float) -> None:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"{name} must be a non-negative number")
