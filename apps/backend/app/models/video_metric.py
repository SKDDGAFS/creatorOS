import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.video import Video


class VideoMetric(Base):
    __tablename__ = "video_metrics"
    __table_args__ = (
        CheckConstraint("views >= 0", name="views_nonnegative"),
        CheckConstraint("likes >= 0", name="likes_nonnegative"),
        CheckConstraint("comments >= 0", name="comments_nonnegative"),
        CheckConstraint("shares >= 0", name="shares_nonnegative"),
        CheckConstraint(
            "watch_time_seconds >= 0",
            name="watch_time_seconds_nonnegative",
        ),
        CheckConstraint(
            "average_view_duration_seconds >= 0",
            name="average_view_duration_seconds_nonnegative",
        ),
        CheckConstraint("impressions >= 0", name="impressions_nonnegative"),
        CheckConstraint(
            "click_through_rate >= 0 AND click_through_rate <= 1",
            name="click_through_rate_ratio",
        ),
        Index(
            "ix_video_metrics_video_id_captured_at",
            "video_id",
            "captured_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="RESTRICT"),
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    views: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    likes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    comments: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    shares: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    watch_time_seconds: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
    )
    average_view_duration_seconds: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default="0",
    )
    impressions: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    click_through_rate: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        default=Decimal("0"),
        server_default="0",
    )

    video: Mapped["Video"] = relationship(
        back_populates="metrics",
        cascade="save-update, merge",
    )
