"""Project environment configuration."""

from dataclasses import dataclass
import math
import os
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


def _optional_positive_seconds(name: str, value: str | None) -> float | None:
    return None if value is None else _positive_seconds(name, value)


def _positive_seconds(name: str, value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    _validate_positive_seconds(name, seconds)
    return seconds


def _validate_positive_seconds(name: str, seconds: float) -> None:
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f"{name} must be a positive number")
