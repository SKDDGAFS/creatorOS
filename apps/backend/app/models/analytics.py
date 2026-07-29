from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.video_metric import VideoMetric


class VideoRetentionPoint(Base):
    __tablename__ = "video_retention_points"
    __table_args__ = (
        CheckConstraint(
            "position_ratio >= 0 AND position_ratio <= 1",
            name="position_ratio",
        ),
        CheckConstraint(
            "audience_retention_ratio >= 0",
            name="audience_retention_ratio",
        ),
        UniqueConstraint(
            "video_metric_id",
            "position_ratio",
            name="uq_video_retention_points_metric_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_metrics.id", ondelete="RESTRICT"),
        index=True,
    )
    position_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    audience_retention_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 6))

    metric: Mapped[VideoMetric] = relationship(back_populates="retention_points")


class VideoTrafficSource(Base):
    __tablename__ = "video_traffic_sources"
    __table_args__ = (
        CheckConstraint("views IS NULL OR views >= 0", name="views_nonnegative"),
        CheckConstraint(
            "watch_time_seconds IS NULL OR watch_time_seconds >= 0",
            name="watch_time_seconds_nonnegative",
        ),
        CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 1)",
            name="percentage_ratio",
        ),
        UniqueConstraint(
            "video_metric_id",
            "source_type",
            name="uq_video_traffic_sources_metric_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_metrics.id", ondelete="RESTRICT"),
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(100))
    views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    watch_time_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)

    metric: Mapped[VideoMetric] = relationship(back_populates="traffic_sources")


class VideoAudienceDemographic(Base):
    __tablename__ = "video_audience_demographics"
    __table_args__ = (
        CheckConstraint("viewers IS NULL OR viewers >= 0", name="viewers_nonnegative"),
        CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 1)",
            name="percentage_ratio",
        ),
        UniqueConstraint(
            "video_metric_id",
            "dimension",
            "segment",
            name="uq_video_audience_demographics_metric_segment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_metrics.id", ondelete="RESTRICT"),
        index=True,
    )
    dimension: Mapped[str] = mapped_column(String(50))
    segment: Mapped[str] = mapped_column(String(100))
    viewers: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)

    metric: Mapped[VideoMetric] = relationship(back_populates="demographics")


class VideoAudienceGeography(Base):
    __tablename__ = "video_audience_geography"
    __table_args__ = (
        CheckConstraint("viewers IS NULL OR viewers >= 0", name="viewers_nonnegative"),
        CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 1)",
            name="percentage_ratio",
        ),
        UniqueConstraint(
            "video_metric_id",
            "country_code",
            name="uq_video_audience_geography_metric_country",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_metrics.id", ondelete="RESTRICT"),
        index=True,
    )
    country_code: Mapped[str] = mapped_column(String(2))
    viewers: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)

    metric: Mapped[VideoMetric] = relationship(back_populates="geography")


class VideoDiscoveryAsset(Base):
    __tablename__ = "video_discovery_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN "
            "('hashtag', 'sound', 'search_term', 'external_referrer', 'other')",
            name="asset_type_allowed",
        ),
        CheckConstraint("views IS NULL OR views >= 0", name="views_nonnegative"),
        CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 1)",
            name="percentage_ratio",
        ),
        UniqueConstraint(
            "video_metric_id",
            "asset_type",
            "asset_value",
            name="uq_video_discovery_assets_metric_asset",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    video_metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_metrics.id", ondelete="RESTRICT"),
        index=True,
    )
    asset_type: Mapped[str] = mapped_column(String(30))
    asset_value: Mapped[str] = mapped_column(String(500))
    views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)

    metric: Mapped[VideoMetric] = relationship(back_populates="discovery_assets")


class TikTokMetricExtension(Base):
    __tablename__ = "tiktok_metric_extensions"
    __table_args__ = (
        CheckConstraint(
            "for_you_views IS NULL OR for_you_views >= 0",
            name="for_you_views_nonnegative",
        ),
        CheckConstraint(
            "following_feed_views IS NULL OR following_feed_views >= 0",
            name="following_feed_views_nonnegative",
        ),
        CheckConstraint(
            "search_views IS NULL OR search_views >= 0",
            name="search_views_nonnegative",
        ),
        CheckConstraint(
            "profile_views IS NULL OR profile_views >= 0",
            name="profile_views_nonnegative",
        ),
        CheckConstraint(
            "sound_views IS NULL OR sound_views >= 0",
            name="sound_views_nonnegative",
        ),
    )

    video_metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_metrics.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    for_you_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    following_feed_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    search_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    profile_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sound_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    metric: Mapped[VideoMetric] = relationship(back_populates="tiktok_extension")


class InstagramMetricExtension(Base):
    __tablename__ = "instagram_metric_extensions"
    __table_args__ = (
        CheckConstraint(
            "reels_tab_reach IS NULL OR reels_tab_reach >= 0",
            name="reels_tab_reach_nonnegative",
        ),
        CheckConstraint(
            "feed_reach IS NULL OR feed_reach >= 0",
            name="feed_reach_nonnegative",
        ),
        CheckConstraint(
            "explore_reach IS NULL OR explore_reach >= 0",
            name="explore_reach_nonnegative",
        ),
        CheckConstraint(
            "profile_reach IS NULL OR profile_reach >= 0",
            name="profile_reach_nonnegative",
        ),
        CheckConstraint(
            "accounts_reached IS NULL OR accounts_reached >= 0",
            name="accounts_reached_nonnegative",
        ),
        CheckConstraint(
            "accounts_engaged IS NULL OR accounts_engaged >= 0",
            name="accounts_engaged_nonnegative",
        ),
    )

    video_metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_metrics.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    reels_tab_reach: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    feed_reach: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    explore_reach: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    profile_reach: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    accounts_reached: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    accounts_engaged: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    metric: Mapped[VideoMetric] = relationship(back_populates="instagram_extension")


class YouTubeMetricExtension(Base):
    __tablename__ = "youtube_metric_extensions"
    __table_args__ = (
        CheckConstraint(
            "suggested_video_views IS NULL OR suggested_video_views >= 0",
            name="suggested_video_views_nonnegative",
        ),
        CheckConstraint(
            "browse_feature_views IS NULL OR browse_feature_views >= 0",
            name="browse_feature_views_nonnegative",
        ),
        CheckConstraint(
            "subscriber_views IS NULL OR subscriber_views >= 0",
            name="subscriber_views_nonnegative",
        ),
        CheckConstraint(
            "unsubscribed_views IS NULL OR unsubscribed_views >= 0",
            name="unsubscribed_views_nonnegative",
        ),
        CheckConstraint(
            "search_views IS NULL OR search_views >= 0",
            name="search_views_nonnegative",
        ),
        CheckConstraint(
            "external_views IS NULL OR external_views >= 0",
            name="external_views_nonnegative",
        ),
        CheckConstraint(
            "end_screen_views IS NULL OR end_screen_views >= 0",
            name="end_screen_views_nonnegative",
        ),
        CheckConstraint(
            "reported_impressions_ctr IS NULL OR "
            "(reported_impressions_ctr >= 0 AND reported_impressions_ctr <= 1)",
            name="reported_impressions_ctr_ratio",
        ),
    )

    video_metric_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_metrics.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    suggested_video_views: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    browse_feature_views: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    subscriber_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    unsubscribed_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    search_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    external_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_screen_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reported_impressions_ctr: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    metric: Mapped[VideoMetric] = relationship(back_populates="youtube_extension")
