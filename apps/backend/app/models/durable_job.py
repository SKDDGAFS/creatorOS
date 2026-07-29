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
    from app.models.user import User
    from app.models.workspace import Workspace


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobAttemptStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"


class DurableJob(Base):
    __tablename__ = "durable_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint(
            "priority >= 0 AND priority <= 100",
            name="priority_range",
        ),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        CheckConstraint(
            "attempts <= max_attempts",
            name="attempts_within_maximum",
        ),
        CheckConstraint(
            "(lock_owner IS NULL AND lock_expires_at IS NULL) OR "
            "(lock_owner IS NOT NULL AND lock_expires_at IS NOT NULL)",
            name="lock_pair_consistent",
        ),
        UniqueConstraint(
            "workspace_id",
            "job_type",
            "idempotency_key_hash",
            name="uq_durable_jobs_workspace_type_idempotency",
        ),
        Index(
            "ix_durable_jobs_claim",
            "status",
            "scheduled_for",
            "priority",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=JobStatus.PENDING.value,
        server_default=JobStatus.PENDING.value,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        server_default="3",
    )
    idempotency_key_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    lock_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="durable_jobs")
    created_by: Mapped[User | None] = relationship(
        back_populates="durable_jobs_created"
    )
    attempt_history: Mapped[list[JobAttempt]] = relationship(
        back_populates="job",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by="JobAttempt.attempt_number",
    )


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'retry_scheduled', "
            "'failed', 'cancelled', 'abandoned')",
            name="status_allowed",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="attempt_number_positive",
        ),
        UniqueConstraint(
            "job_id",
            "attempt_number",
            name="uq_job_attempts_job_attempt_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("durable_jobs.id", ondelete="RESTRICT"),
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(
        String(30),
        default=JobAttemptStatus.RUNNING.value,
        server_default=JobAttemptStatus.RUNNING.value,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    job: Mapped[DurableJob] = relationship(back_populates="attempt_history")
