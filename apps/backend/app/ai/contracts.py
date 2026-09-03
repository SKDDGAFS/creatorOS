from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AIMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class AIContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AIMessage(AIContract):
    role: AIMessageRole
    content: str = Field(min_length=1, max_length=100_000)


class AIStructuredRequest(AIContract):
    model: str = Field(min_length=1, max_length=255)
    messages: tuple[AIMessage, ...] = Field(min_length=1, max_length=20)
    output_schema_name: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    output_schema: dict[str, object]
    max_output_tokens: int = Field(ge=1, le=32_768)
    temperature: float = Field(default=0.2, ge=0, le=2)


class AIProviderResult(AIContract):
    output: dict[str, object]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    finish_reason: str | None = Field(default=None, max_length=100)
    provider_request_id: str | None = Field(default=None, max_length=255)


class AIProviderHealth(AIContract):
    healthy: bool
    safe_message: str = Field(min_length=1, max_length=255)


class AIAPIKeyStore(Protocol):
    def load(self, reference: str) -> SecretStr: ...


class AIProvider(Protocol):
    def generate_structured(
        self,
        request: AIStructuredRequest,
    ) -> AIProviderResult: ...

    def health_check(self) -> AIProviderHealth: ...
