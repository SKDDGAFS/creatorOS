from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent_run import AgentRunStatus, AgentType
from app.models.ai import AICapabilityTier


class AgentSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class AgentInputKind(str, Enum):
    CHANNEL = "channel"
    VIDEO = "video"
    PLATFORM_CONNECTION = "platform_connection"


class AgentInputReference(AgentSchema):
    kind: AgentInputKind
    resource_id: UUID
    label: str | None = Field(default=None, min_length=1, max_length=200)


class AgentRunCreate(AgentSchema):
    agent_type: AgentType
    objective: str = Field(min_length=1, max_length=10_000)
    input_references: tuple[AgentInputReference, ...] = Field(
        default=(),
        max_length=100,
    )
    priority: int = Field(default=50, ge=0, le=100)
    max_attempts: int = Field(default=3, ge=1, le=10)


class AgentRecommendation(AgentSchema):
    title: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=2_000)
    confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)


class AgentRunOutput(AgentSchema):
    summary: str = Field(min_length=1, max_length=5_000)
    recommendations: tuple[AgentRecommendation, ...] = Field(
        min_length=1,
        max_length=20,
    )
    assumptions: tuple[str, ...] = Field(default=(), max_length=20)
    next_steps: tuple[str, ...] = Field(default=(), max_length=20)
    overall_confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)


class AgentCapabilityResponse(AgentSchema):
    agent_type: AgentType
    prompt_name: str
    capability_tier: AICapabilityTier
    purpose: str
    output_mode: str
    can_publish: bool
    can_execute_shell: bool


class AgentRunResponse(AgentSchema):
    id: UUID
    workspace_id: UUID
    requested_by_user_id: UUID
    prompt_version_id: UUID
    durable_job_id: UUID
    ai_invocation_id: UUID | None
    agent_type: AgentType
    objective: str
    input_references: list[dict[str, object]]
    status: AgentRunStatus
    model_name: str | None
    estimated_cost_usd: Decimal
    output: dict[str, object] | None
    confidence: Decimal | None
    last_error_code: str | None
    last_error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
