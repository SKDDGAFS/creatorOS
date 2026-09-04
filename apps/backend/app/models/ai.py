from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun
    from app.models.user import User
    from app.models.workspace import Workspace


class AIProviderKind(str, Enum):
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


class AICapabilityTier(str, Enum):
    LIGHTWEIGHT = "lightweight"
    STANDARD = "standard"
    ADVANCED = "advanced"


class AIInvocationStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AIProviderConfiguration(Base):
    __tablename__ = "ai_provider_configurations"
    __table_args__ = (
        CheckConstraint(
            "provider_kind IN ('ollama', 'openai_compatible')",
            name="provider_kind_allowed",
        ),
        CheckConstraint(
            "capability_tier IN ('lightweight', 'standard', 'advanced')",
            name="capability_tier_allowed",
        ),
        CheckConstraint("priority >= 0 AND priority <= 100", name="priority_range"),
        CheckConstraint(
            "timeout_seconds > 0 AND timeout_seconds <= 300",
            name="timeout_seconds_range",
        ),
        CheckConstraint(
            "max_attempts >= 1 AND max_attempts <= 5",
            name="max_attempts_range",
        ),
        CheckConstraint(
            "input_cost_per_million >= 0",
            name="input_cost_nonnegative",
        ),
        CheckConstraint(
            "output_cost_per_million >= 0",
            name="output_cost_nonnegative",
        ),
        UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_ai_provider_configurations_workspace_name",
        ),
        Index(
            "ix_ai_provider_configurations_selection",
            "workspace_id",
            "is_enabled",
            "priority",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100))
    provider_kind: Mapped[str] = mapped_column(String(30), index=True)
    base_url: Mapped[str] = mapped_column(String(2048))
    model_name: Mapped[str] = mapped_column(String(255))
    credential_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    capability_tier: Mapped[str] = mapped_column(
        String(30),
        default=AICapabilityTier.LIGHTWEIGHT.value,
        server_default=AICapabilityTier.LIGHTWEIGHT.value,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    timeout_seconds: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    max_attempts: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    input_cost_per_million: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        default=Decimal("0"),
        server_default="0",
    )
    output_cost_per_million: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        default=Decimal("0"),
        server_default="0",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="ai_providers")
    created_by: Mapped[User] = relationship(back_populates="ai_providers_created")
    invocations: Mapped[list[AIInvocation]] = relationship(
        back_populates="provider_configuration",
        cascade="save-update, merge",
        passive_deletes=True,
    )

    @property
    def requires_api_key(self) -> bool:
        return self.credential_reference is not None


class AIPromptVersion(Base):
    __tablename__ = "ai_prompt_versions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        UniqueConstraint(
            "workspace_id",
            "name",
            "version",
            name="uq_ai_prompt_versions_workspace_name_version",
        ),
        Index(
            "ix_ai_prompt_versions_lookup",
            "workspace_id",
            "name",
            "is_active",
            "version",
        ),
        Index(
            "uq_ai_prompt_versions_active_name",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer)
    system_template: Mapped[str] = mapped_column(Text)
    user_template: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )

    workspace: Mapped[Workspace] = relationship(back_populates="ai_prompt_versions")
    created_by: Mapped[User] = relationship(back_populates="ai_prompt_versions_created")
    invocations: Mapped[list[AIInvocation]] = relationship(
        back_populates="prompt_version",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="prompt_version",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class AIUsageBudget(Base):
    __tablename__ = "ai_usage_budgets"
    __table_args__ = (
        CheckConstraint(
            "monthly_token_limit IS NULL OR monthly_token_limit > 0",
            name="monthly_token_limit_positive",
        ),
        CheckConstraint(
            "monthly_cost_limit_usd IS NULL OR monthly_cost_limit_usd > 0",
            name="monthly_cost_limit_positive",
        ),
        CheckConstraint(
            "default_max_output_tokens >= 1 AND default_max_output_tokens <= 32768",
            name="default_max_output_tokens_range",
        ),
        UniqueConstraint("workspace_id", name="uq_ai_usage_budgets_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    monthly_token_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    monthly_cost_limit_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
    )
    default_max_output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=2048,
        server_default="2048",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="ai_usage_budget")


class AIInvocation(Base):
    __tablename__ = "ai_invocations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint("attempts >= 1", name="attempts_positive"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_nonnegative"),
        CheckConstraint("estimated_cost_usd >= 0", name="cost_nonnegative"),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key_hash",
            name="uq_ai_invocations_workspace_idempotency",
        ),
        Index(
            "ix_ai_invocations_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    provider_configuration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "ai_provider_configurations.id",
            name="fk_ai_invocations_provider_config_ai_providers",
            ondelete="RESTRICT",
        ),
        index=True,
    )
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_prompt_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    provider_kind: Mapped[str] = mapped_column(String(30))
    model_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), index=True)
    attempts: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        default=Decimal("0"),
        server_default="0",
    )
    output: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )

    workspace: Mapped[Workspace] = relationship(back_populates="ai_invocations")
    provider_configuration: Mapped[AIProviderConfiguration] = relationship(
        back_populates="invocations"
    )
    prompt_version: Mapped[AIPromptVersion] = relationship(back_populates="invocations")
    requested_by: Mapped[User] = relationship(back_populates="ai_invocations")
    agent_run: Mapped[AgentRun | None] = relationship(
        back_populates="ai_invocation",
        uselist=False,
    )
