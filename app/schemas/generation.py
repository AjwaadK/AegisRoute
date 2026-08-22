from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content cannot be empty")
        return value


class GenerateRequest(BaseModel):
    model: str

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model cannot be empty")
        return value

    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int = Field(default=64, ge=1, le=4096)
    temperature: float = Field(default=0.5, ge=0, le=2)


class TokenUsage(BaseModel):
    """Provider-neutral token usage facts reported by an upstream provider."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class StreamTextDelta(BaseModel):
    """One provider-neutral user-visible text fragment."""

    model_config = ConfigDict(frozen=True)

    text: str


class StreamCompleted(BaseModel):
    """Successful provider stream completion and any observed usage."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    usage: TokenUsage | None = None


ProviderStreamEvent = StreamTextDelta | StreamCompleted


class ProviderResult(BaseModel):
    request_id: str
    provider: str
    model: str
    output: str
    usage: TokenUsage | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_token_fields(cls, value: object) -> object:
        """Keep existing provider fixtures/callers compatible during migration."""

        if not isinstance(value, dict) or "usage" in value:
            return value
        legacy_fields = ("input_tokens", "output_tokens", "total_tokens")
        if not any(field in value for field in legacy_fields):
            return value
        migrated = dict(value)
        migrated["usage"] = {
            field: migrated.pop(field, None) for field in legacy_fields
        }
        return migrated

    @property
    def input_tokens(self) -> int | None:
        return self.usage.input_tokens if self.usage is not None else None

    @property
    def output_tokens(self) -> int | None:
        return self.usage.output_tokens if self.usage is not None else None

    @property
    def total_tokens(self) -> int | None:
        return self.usage.total_tokens if self.usage is not None else None


class GenerateResponse(BaseModel):
    request_id: str
    model: str
    output: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
