from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.ai import AIInvocation, AIPromptVersion
    from app.models.durable_job import DurableJob
    from app.models.publishing import ActivityEvent
    from app.models.user import User
    from app.models.workspace import Workspace


class AgentType(str, Enum):
    CONTENT_STRATEGIST = "content_strategist"
    COPYWRITER = "copywriter"
    SOCIAL_PLANNER = "social_planner"
    VIDEO_ANALYST = "video_analyst"
    TOKEN_OPTIMIZER = "token_optimizer"


class AgentRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


AGENT_TYPES = ", ".join(f"'{value.value}'" for value in AgentType)
AGENT_RUN_STATUSES = ", ".join(f"'{value.value}'" for value in AgentRunStatus)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(f"agent_type IN ({AGENT_TYPES})", name="agent_type_allowed"),
        CheckConstraint(
            f"status IN ({AGENT_RUN_STATUSES})",
            name="status_allowed",
        ),
        CheckConstraint(
            "estimated_cost_usd >= 0",
            name="estimated_cost_nonnegative",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        UniqueConstraint(
            "durable_job_id",
            name="uq_agent_runs_durable_job_id",
        ),
        UniqueConstraint(
            "ai_invocation_id",
            name="uq_agent_runs_ai_invocation_id",
        ),
        Index(
            "ix_agent_runs_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_prompt_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    durable_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("durable_jobs.id", ondelete="RESTRICT"),
        index=True,
    )
    ai_invocation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_invocations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    agent_type: Mapped[str] = mapped_column(String(40), index=True)
    objective: Mapped[str] = mapped_column(Text)
    input_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=AgentRunStatus.QUEUED.value,
        server_default=AgentRunStatus.QUEUED.value,
        index=True,
    )
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        default=Decimal("0"),
        server_default="0",
    )
    output: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    workspace: Mapped[Workspace] = relationship(back_populates="agent_runs")
    requested_by: Mapped[User] = relationship(back_populates="agent_runs_requested")
    prompt_version: Mapped[AIPromptVersion] = relationship(back_populates="agent_runs")
    durable_job: Mapped[DurableJob] = relationship(back_populates="agent_run")
    ai_invocation: Mapped[AIInvocation | None] = relationship(
        back_populates="agent_run"
    )
    activity_events: Mapped[list[ActivityEvent]] = relationship(
        back_populates="agent_run",
        cascade="save-update, merge",
        passive_deletes=True,
    )
