from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.ai import (
    AICapabilityTier,
    AIInvocationStatus,
    AIProviderKind,
)


class AISchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class AIProviderCreate(AISchema):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9 _.-]+$")
    provider_kind: AIProviderKind
    base_url: str = Field(min_length=1, max_length=2048)
    model_name: str = Field(min_length=1, max_length=255)
    credential_reference: str | None = Field(
        default=None,
        max_length=255,
        pattern=r"^env://[A-Z][A-Z0-9_]{1,127}$",
    )
    capability_tier: AICapabilityTier = AICapabilityTier.LIGHTWEIGHT
    priority: int = Field(default=50, ge=0, le=100)
    timeout_seconds: Decimal = Field(
        default=Decimal("60"),
        gt=0,
        le=300,
        max_digits=8,
        decimal_places=3,
    )
    max_attempts: int = Field(default=2, ge=1, le=5)
    input_cost_per_million: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=12,
        decimal_places=6,
    )
    output_cost_per_million: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=12,
        decimal_places=6,
    )

    @model_validator(mode="after")
    def validate_credential_boundary(self) -> Self:
        if self.provider_kind is AIProviderKind.OLLAMA and self.credential_reference:
            raise ValueError("Ollama configuration must not include credentials")
        return self


class AIProviderResponse(AISchema):
    id: UUID
    workspace_id: UUID
    name: str
    provider_kind: AIProviderKind
    base_url: str
    model_name: str
    capability_tier: AICapabilityTier
    priority: int
    timeout_seconds: Decimal
    max_attempts: int
    input_cost_per_million: Decimal
    output_cost_per_million: Decimal
    is_enabled: bool
    requires_api_key: bool
    created_at: datetime
    updated_at: datetime


class AIPromptVersionCreate(AISchema):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    system_template: str = Field(min_length=1, max_length=50_000)
    user_template: str = Field(min_length=1, max_length=50_000)


class AIPromptVersionResponse(AISchema):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    name: str
    version: int
    system_template: str
    user_template: str
    is_active: bool
    created_at: datetime


class AIUsageBudgetUpdate(AISchema):
    monthly_token_limit: int | None = Field(default=None, gt=0)
    monthly_cost_limit_usd: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=6,
    )
    default_max_output_tokens: int = Field(default=2048, ge=1, le=32_768)


class AIUsageBudgetResponse(AIUsageBudgetUpdate):
    id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime


class AIUsageSummary(AISchema):
    period_start: datetime
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: Decimal
    invocation_count: int
    monthly_token_limit: int | None
    monthly_cost_limit_usd: Decimal | None


class AIInvocationResponse(AISchema):
    id: UUID
    workspace_id: UUID
    provider_configuration_id: UUID
    prompt_version_id: UUID
    requested_by_user_id: UUID
    provider_kind: AIProviderKind
    model_name: str
    status: AIInvocationStatus
    attempts: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    output: dict[str, object] | None
    last_error_code: str | None
    last_error_message: str | None
    started_at: datetime
    completed_at: datetime
    created_at: datetime


class AIProviderHealthResponse(AISchema):
    provider_configuration_id: UUID
    provider_name: str
    provider_kind: AIProviderKind
    model_name: str
    healthy: bool
    safe_message: str
