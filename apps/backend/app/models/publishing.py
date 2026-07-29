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
    from app.models.video import Video
    from app.models.workspace import Workspace


class PublishingState(str, Enum):
    DRAFT = "draft"
    PREPARING = "preparing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ActivityType(str, Enum):
    JOB_CREATED = "publishing_job_created"
    STATE_CHANGED = "publishing_state_changed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    SCHEDULED = "publishing_scheduled"
    CANCELLED = "publishing_cancelled"
    FAILED = "publishing_failed"
    PUBLISHED = "publishing_succeeded"


PUBLISHING_STATES = ", ".join(f"'{state.value}'" for state in PublishingState)


class PublishingJob(Base):
    __tablename__ = "publishing_jobs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({PUBLISHING_STATES})",
            name="status_allowed",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key_hash",
            name="uq_publishing_jobs_workspace_idempotency_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="RESTRICT"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(30),
        default=PublishingState.DRAFT.value,
        server_default=PublishingState.DRAFT.value,
        index=True,
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="publishing_jobs")
    video: Mapped[Video] = relationship(back_populates="publishing_jobs")
    created_by: Mapped[User] = relationship(
        back_populates="publishing_jobs_created"
    )
    approvals: Mapped[list[ApprovalRequest]] = relationship(
        back_populates="job",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by="ApprovalRequest.sequence",
    )
    transitions: Mapped[list[PublishingTransition]] = relationship(
        back_populates="job",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by="PublishingTransition.created_at, PublishingTransition.id",
    )
    activity_events: Mapped[list[ActivityEvent]] = relationship(
        back_populates="publishing_job",
        cascade="save-update, merge",
        passive_deletes=True,
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        UniqueConstraint(
            "publishing_job_id",
            "sequence",
            name="uq_approval_requests_job_sequence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    publishing_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publishing_jobs.id", ondelete="RESTRICT"),
        index=True,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20),
        default=ApprovalStatus.PENDING.value,
        server_default=ApprovalStatus.PENDING.value,
        index=True,
    )
    request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    job: Mapped[PublishingJob] = relationship(back_populates="approvals")
    requested_by: Mapped[User] = relationship(
        foreign_keys=[requested_by_user_id],
    )
    decided_by: Mapped[User | None] = relationship(
        foreign_keys=[decided_by_user_id],
    )


class PublishingTransition(Base):
    __tablename__ = "publishing_transitions"
    __table_args__ = (
        CheckConstraint(
            f"from_state IS NULL OR from_state IN ({PUBLISHING_STATES})",
            name="from_state_allowed",
        ),
        CheckConstraint(
            f"to_state IN ({PUBLISHING_STATES})",
            name="to_state_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    publishing_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publishing_jobs.id", ondelete="RESTRICT"),
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    from_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )

    job: Mapped[PublishingJob] = relationship(back_populates="transitions")
    actor: Mapped[User | None] = relationship()


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN "
            "('publishing_job_created', 'publishing_state_changed', "
            "'approval_requested', 'approval_approved', 'approval_rejected', "
            "'publishing_scheduled', 'publishing_cancelled', "
            "'publishing_failed', 'publishing_succeeded')",
            name="event_type_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    publishing_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("publishing_jobs.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        index=True,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="activity_events")
    actor: Mapped[User | None] = relationship()
    publishing_job: Mapped[PublishingJob | None] = relationship(
        back_populates="activity_events"
    )
