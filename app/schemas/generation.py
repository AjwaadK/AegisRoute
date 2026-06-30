from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    max_tokens: int = Field(ge=1, le=4096)
    temperature: float = Field(ge=0, le=2)


class ProviderResult(BaseModel):
    request_id: str
    provider: str
    model: str
    output: str
    input_tokens: int
    output_tokens: int


class GenerateResponse(BaseModel):
    request_id: str
    model: str
    output: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
