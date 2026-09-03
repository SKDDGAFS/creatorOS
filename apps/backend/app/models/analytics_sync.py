from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.durable_job import DurableJob
    from app.models.platform_integration import PlatformConnection
    from app.models.workspace import Workspace


class AnalyticsSyncStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class AnalyticsSyncRun(Base):
    __tablename__ = "analytics_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'skipped')",
            name="status_allowed",
        ),
        CheckConstraint("channels_synced >= 0", name="channels_synced_nonnegative"),
        CheckConstraint("videos_synced >= 0", name="videos_synced_nonnegative"),
        CheckConstraint("metrics_synced >= 0", name="metrics_synced_nonnegative"),
        CheckConstraint(
            "account_metrics_synced >= 0",
            name="account_metrics_synced_nonnegative",
        ),
        UniqueConstraint(
            "durable_job_id",
            name="uq_analytics_sync_runs_durable_job_id",
        ),
        Index(
            "ix_analytics_sync_runs_workspace_status_created",
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
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_connections.id", ondelete="RESTRICT"),
        index=True,
    )
    durable_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("durable_jobs.id", ondelete="RESTRICT"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=AnalyticsSyncStatus.QUEUED.value,
        server_default=AnalyticsSyncStatus.QUEUED.value,
        index=True,
    )
    channels_synced: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    videos_synced: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    metrics_synced: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    account_metrics_synced: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
        server_default="{}",
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    workspace: Mapped[Workspace] = relationship(back_populates="analytics_sync_runs")
    connection: Mapped[PlatformConnection] = relationship(
        back_populates="analytics_sync_runs"
    )
    durable_job: Mapped[DurableJob] = relationship(back_populates="analytics_sync_run")
