from __future__ import annotations

import uuid
from datetime import UTC, datetime
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


class ResearchSourceType(str, Enum):
    OFFICIAL_API = "official_api"
    PUBLIC_WEB = "public_web"
    FIRST_PARTY = "first_party"
    MANUAL = "manual"


class ResearchRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchFindingType(str, Enum):
    TREND = "trend"
    CONTENT_PATTERN = "content_pattern"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"


class ResearchSource(Base):
    __tablename__ = "research_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('official_api', 'public_web', 'first_party', 'manual')",
            name="source_type_allowed",
        ),
        CheckConstraint(
            "stale_after_days >= 1 AND stale_after_days <= 3650",
            name="stale_after_days_range",
        ),
        UniqueConstraint(
            "workspace_id",
            "content_hash",
            name="uq_research_sources_workspace_content_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(500))
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    excerpt: Mapped[str] = mapped_column(Text)
    source_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    stale_after_days: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30"
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    workspace: Mapped[Workspace] = relationship(back_populates="research_sources")
    created_by: Mapped[User] = relationship(back_populates="research_sources_created")
    evidence_links: Mapped[list[ResearchFindingEvidence]] = relationship(
        back_populates="source", cascade="save-update, merge", passive_deletes=True
    )

    @property
    def freshness_status(self) -> str:
        source_date = (
            self.source_date.replace(tzinfo=UTC)
            if self.source_date.tzinfo is None
            else self.source_date.astimezone(UTC)
        )
        age = datetime.now(UTC) - source_date
        return (
            FreshnessStatus.STALE.value
            if age.days > self.stale_after_days
            else FreshnessStatus.CURRENT.value
        )


class Competitor(Base):
    __tablename__ = "competitors"
    __table_args__ = (
        CheckConstraint(
            "platform IN ('youtube', 'instagram', 'tiktok')",
            name="platform_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "platform",
            "handle",
            name="uq_competitors_workspace_platform_handle",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(20), index=True)
    handle: Mapped[str] = mapped_column(String(255))
    profile_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="competitors")
    created_by: Mapped[User] = relationship(back_populates="competitors_created")


class ResearchRun(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("fresh_source_count >= 0", name="fresh_sources_nonnegative"),
        CheckConstraint("stale_source_count >= 0", name="stale_sources_nonnegative"),
        CheckConstraint("estimated_cost_usd >= 0", name="cost_nonnegative"),
        UniqueConstraint("durable_job_id", name="uq_research_runs_durable_job_id"),
        UniqueConstraint("ai_invocation_id", name="uq_research_runs_ai_invocation_id"),
        Index(
            "ix_research_runs_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_prompt_versions.id", ondelete="RESTRICT"), index=True
    )
    durable_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("durable_jobs.id", ondelete="RESTRICT"), index=True
    )
    ai_invocation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_invocations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    objective: Mapped[str] = mapped_column(Text)
    source_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    competitor_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    include_stale_sources: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=ResearchRunStatus.QUEUED.value,
        server_default=ResearchRunStatus.QUEUED.value,
        index=True,
    )
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), server_default="0"
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    fresh_source_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    stale_source_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="research_runs")
    requested_by: Mapped[User] = relationship(back_populates="research_runs_requested")
    prompt_version: Mapped[AIPromptVersion] = relationship(
        back_populates="research_runs"
    )
    durable_job: Mapped[DurableJob] = relationship(back_populates="research_run")
    ai_invocation: Mapped[AIInvocation | None] = relationship(
        back_populates="research_run"
    )
    activity_events: Mapped[list[ActivityEvent]] = relationship(
        back_populates="research_run",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class ResearchFinding(Base):
    __tablename__ = "research_findings"
    __table_args__ = (
        CheckConstraint(
            "finding_type IN ('trend', 'content_pattern')",
            name="finding_type_allowed",
        ),
        CheckConstraint(
            "freshness_status IN ('current', 'stale')",
            name="freshness_status_allowed",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        UniqueConstraint(
            "workspace_id",
            "fingerprint",
            name="uq_research_findings_workspace_fingerprint",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    first_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="RESTRICT"), index=True
    )
    last_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="RESTRICT"), index=True
    )
    finding_type: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    source_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    freshness_status: Mapped[str] = mapped_column(String(20), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    evidence: Mapped[list[ResearchFindingEvidence]] = relationship(
        back_populates="finding", cascade="save-update, merge", passive_deletes=True
    )


class ResearchFindingEvidence(Base):
    __tablename__ = "research_finding_evidence"
    __table_args__ = (
        UniqueConstraint(
            "finding_id", "source_id", name="uq_research_finding_evidence_pair"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_findings.id", ondelete="RESTRICT"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_sources.id", ondelete="RESTRICT"), index=True
    )
    evidence_note: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    finding: Mapped[ResearchFinding] = relationship(back_populates="evidence")
    source: Mapped[ResearchSource] = relationship(back_populates="evidence_links")


class ResearchHook(Base):
    __tablename__ = "research_hooks"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        UniqueConstraint(
            "workspace_id",
            "fingerprint",
            name="uq_research_hooks_workspace_fingerprint",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    first_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="RESTRICT"), index=True
    )
    last_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="RESTRICT"), index=True
    )
    text: Mapped[str] = mapped_column(String(1000))
    rationale: Mapped[str] = mapped_column(String(2000))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    source_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class ContentIdea(Base):
    __tablename__ = "content_ideas"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        UniqueConstraint(
            "workspace_id", "fingerprint", name="uq_content_ideas_workspace_fingerprint"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    first_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="RESTRICT"), index=True
    )
    last_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    concept: Mapped[str] = mapped_column(Text)
    suggested_hook: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    platforms: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    source_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=list
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    fingerprint: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
