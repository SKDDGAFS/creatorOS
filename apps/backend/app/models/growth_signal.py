from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class GrowthSignal(str, Enum):
    RETENTION_CURVE = "retention_curve"
    COMPLETION_RATE = "completion_rate"
    AVERAGE_PERCENTAGE_VIEWED = "average_percentage_viewed"
    FIRST_HOUR_PERFORMANCE = "first_hour_performance"
    SHARE_RATE = "share_rate"
    FOLLOWER_CONVERSION_RATE = "follower_conversion_rate"
    RECOMMENDATION_TRAFFIC = "recommendation_traffic"
    NEW_VIEWER_REACH = "new_viewer_reach"
    IMPRESSIONS_TO_VIEW_RATE = "impressions_to_view_rate"
    RETURNING_VIEWER_TREND = "returning_viewer_trend"
    SAVE_RATE = "save_rate"
    NORMALIZED_ENGAGEMENT_RATE = "normalized_engagement_rate"
    SEARCH_TRAFFIC = "search_traffic"
    HASHTAG_REACH = "hashtag_reach"
    SOUND_REACH = "sound_reach"
    POSTING_TIME_PERFORMANCE = "posting_time_performance"
    GEOGRAPHIC_FIT = "geographic_fit"
    RAW_LIKES = "raw_likes"
    RAW_COMMENTS = "raw_comments"
    RAW_VIEWS = "raw_views"
    RAW_IMPRESSIONS = "raw_impressions"
    DEMOGRAPHIC_BREAKDOWN = "demographic_breakdown"


class SignalTier(str, Enum):
    STRONG = "strong"
    MEDIUM = "medium"
    CONTEXTUAL = "contextual"


SIGNAL_VALUES = ", ".join(f"'{signal.value}'" for signal in GrowthSignal)


class GrowthSignalProfile(Base):
    __tablename__ = "growth_signal_profiles"
    __table_args__ = (
        CheckConstraint(
            "platform IS NULL OR "
            "platform IN ('youtube', 'tiktok', 'instagram')",
            name="platform_allowed",
        ),
        CheckConstraint(
            "account_size_min IS NULL OR account_size_min >= 0",
            name="account_size_min_nonnegative",
        ),
        CheckConstraint(
            "account_size_max IS NULL OR account_size_max >= 0",
            name="account_size_max_nonnegative",
        ),
        CheckConstraint(
            "account_size_min IS NULL OR account_size_max IS NULL "
            "OR account_size_min <= account_size_max",
            name="account_size_range",
        ),
        CheckConstraint(
            "video_duration_min_seconds IS NULL "
            "OR video_duration_min_seconds > 0",
            name="video_duration_min_positive",
        ),
        CheckConstraint(
            "video_duration_max_seconds IS NULL "
            "OR video_duration_max_seconds > 0",
            name="video_duration_max_positive",
        ),
        CheckConstraint(
            "video_duration_min_seconds IS NULL "
            "OR video_duration_max_seconds IS NULL "
            "OR video_duration_min_seconds <= video_duration_max_seconds",
            name="video_duration_range",
        ),
        CheckConstraint("evidence_min >= 0", name="evidence_min_nonnegative"),
        CheckConstraint(
            "evidence_max IS NULL OR evidence_max >= evidence_min",
            name="evidence_range",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        UniqueConstraint(
            "workspace_id",
            "name",
            "version",
            name="uq_growth_signal_profiles_workspace_name_version",
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
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)
    platform: Mapped[str | None] = mapped_column(String(20), nullable=True)
    content_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    account_size_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_size_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_duration_min_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    video_duration_max_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    goal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence_min: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    evidence_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )

    workspace: Mapped[Workspace] = relationship(
        back_populates="growth_signal_profiles"
    )
    created_by: Mapped[User] = relationship(
        back_populates="growth_signal_profiles_created"
    )
    weights: Mapped[list[GrowthSignalWeight]] = relationship(
        back_populates="profile",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by="GrowthSignalWeight.signal",
    )


class GrowthSignalWeight(Base):
    __tablename__ = "growth_signal_weights"
    __table_args__ = (
        CheckConstraint(
            f"signal IN ({SIGNAL_VALUES})",
            name="signal_allowed",
        ),
        CheckConstraint(
            "tier IN ('strong', 'medium', 'contextual')",
            name="tier_allowed",
        ),
        CheckConstraint(
            "weight > 0 AND weight <= 100",
            name="weight_range",
        ),
        CheckConstraint(
            "minimum_sample_size >= 1",
            name="minimum_sample_size_positive",
        ),
        CheckConstraint(
            "full_confidence_sample_size >= minimum_sample_size",
            name="confidence_sample_range",
        ),
        UniqueConstraint(
            "profile_id",
            "signal",
            name="uq_growth_signal_weights_profile_signal",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("growth_signal_profiles.id", ondelete="RESTRICT"),
        index=True,
    )
    signal: Mapped[str] = mapped_column(String(60))
    tier: Mapped[str] = mapped_column(String(20))
    weight: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    minimum_sample_size: Mapped[int] = mapped_column(Integer, default=1)
    full_confidence_sample_size: Mapped[int] = mapped_column(Integer)

    profile: Mapped[GrowthSignalProfile] = relationship(back_populates="weights")
