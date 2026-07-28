import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.video_metric import VideoMetric


class VideoStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'published', 'failed')",
            name="status_allowed",
        ),
        UniqueConstraint(
            "channel_id",
            "platform_video_id",
            name="uq_videos_channel_id_platform_video_id",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds > 0",
            name="duration_seconds_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="RESTRICT"),
        index=True,
    )
    platform_video_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=VideoStatus.DRAFT.value,
        server_default=VideoStatus.DRAFT.value,
    )
    published_at: Mapped[datetime | None] = mapped_column(
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

    channel: Mapped[Channel] = relationship(
        back_populates="videos",
        cascade="save-update, merge",
    )
    metrics: Mapped[list[VideoMetric]] = relationship(
        back_populates="video",
        cascade="save-update, merge",
        passive_deletes=True,
    )
