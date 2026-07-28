from __future__ import annotations

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
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
    from app.models.analytics import (
        InstagramMetricExtension,
        TikTokMetricExtension,
        VideoAudienceDemographic,
        VideoAudienceGeography,
        VideoDiscoveryAsset,
        VideoRetentionPoint,
        VideoTrafficSource,
        YouTubeMetricExtension,
    )
    from app.models.video import Video


SHARED_COUNT_FIELDS = (
    "views",
    "unique_viewers",
    "engaged_views",
    "completed_views",
    "likes",
    "comments",
    "shares",
    "saves",
    "impressions",
    "views_from_impressions",
    "watch_time_seconds",
    "average_view_duration_seconds",
    "followers_gained",
    "followers_lost",
    "new_viewers",
    "returning_viewers",
    "first_hour_views",
    "first_hour_likes",
    "first_hour_comments",
    "first_hour_shares",
    "first_hour_saves",
    "first_hour_watch_time_seconds",
    "first_hour_followers_gained",
    "first_hour_impressions",
)


def _safe_ratio(numerator: int | None, denominator: int | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.000001"),
        rounding=ROUND_HALF_UP,
    )


class VideoMetric(Base):
    __tablename__ = "video_metrics"
    __table_args__ = (
        *(
            CheckConstraint(
                f"{field_name} IS NULL OR {field_name} >= 0",
                name=f"{field_name}_nonnegative",
            )
            for field_name in SHARED_COUNT_FIELDS
        ),
        CheckConstraint(
            "click_through_rate IS NULL OR "
            "(click_through_rate >= 0 AND click_through_rate <= 1)",
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
    views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    unique_viewers: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    engaged_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completed_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    likes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comments: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    shares: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    saves: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    impressions: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    views_from_impressions: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    watch_time_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    average_view_duration_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    followers_gained: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    followers_lost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    new_viewers: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    returning_viewers: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_hour_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_hour_likes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_hour_comments: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_hour_shares: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_hour_saves: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_hour_watch_time_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    first_hour_followers_gained: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    first_hour_impressions: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    click_through_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    video: Mapped[Video] = relationship(
        back_populates="metrics",
        cascade="save-update, merge",
    )
    retention_points: Mapped[list[VideoRetentionPoint]] = relationship(
        back_populates="metric",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by="VideoRetentionPoint.position_ratio",
    )
    traffic_sources: Mapped[list[VideoTrafficSource]] = relationship(
        back_populates="metric",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by="VideoTrafficSource.source_type",
    )
    demographics: Mapped[list[VideoAudienceDemographic]] = relationship(
        back_populates="metric",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by=(
            "VideoAudienceDemographic.dimension, "
            "VideoAudienceDemographic.segment"
        ),
    )
    geography: Mapped[list[VideoAudienceGeography]] = relationship(
        back_populates="metric",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by="VideoAudienceGeography.country_code",
    )
    discovery_assets: Mapped[list[VideoDiscoveryAsset]] = relationship(
        back_populates="metric",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by=(
            "VideoDiscoveryAsset.asset_type, VideoDiscoveryAsset.asset_value"
        ),
    )
    tiktok_extension: Mapped[TikTokMetricExtension | None] = relationship(
        back_populates="metric",
        uselist=False,
        cascade="save-update, merge",
    )
    instagram_extension: Mapped[InstagramMetricExtension | None] = relationship(
        back_populates="metric",
        uselist=False,
        cascade="save-update, merge",
    )
    youtube_extension: Mapped[YouTubeMetricExtension | None] = relationship(
        back_populates="metric",
        uselist=False,
        cascade="save-update, merge",
    )

    @property
    def engagement_rate(self) -> Decimal | None:
        components = (self.likes, self.comments, self.shares, self.saves)
        if any(value is None for value in components):
            return None
        return _safe_ratio(
            sum(value for value in components if value is not None),
            self.views,
        )

    @property
    def follower_conversion_rate(self) -> Decimal | None:
        return _safe_ratio(self.followers_gained, self.views)

    @property
    def share_rate(self) -> Decimal | None:
        return _safe_ratio(self.shares, self.views)

    @property
    def save_rate(self) -> Decimal | None:
        return _safe_ratio(self.saves, self.views)

    @property
    def new_viewer_ratio(self) -> Decimal | None:
        if self.new_viewers is None or self.returning_viewers is None:
            return None
        return _safe_ratio(
            self.new_viewers,
            self.new_viewers + self.returning_viewers,
        )

    @property
    def returning_viewer_ratio(self) -> Decimal | None:
        if self.new_viewers is None or self.returning_viewers is None:
            return None
        return _safe_ratio(
            self.returning_viewers,
            self.new_viewers + self.returning_viewers,
        )

    @property
    def impressions_to_view_rate(self) -> Decimal | None:
        return _safe_ratio(self.views_from_impressions, self.impressions)

    @property
    def average_percentage_viewed(self) -> Decimal | None:
        duration = self.video.duration_seconds
        return _safe_ratio(self.average_view_duration_seconds, duration)

    @property
    def completion_rate(self) -> Decimal | None:
        return _safe_ratio(self.completed_views, self.views)
