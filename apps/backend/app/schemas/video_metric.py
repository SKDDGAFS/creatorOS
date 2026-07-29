from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

Ratio = Decimal | None


class AnalyticsSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)


class RetentionPointCreate(AnalyticsSchema):
    position_ratio: Decimal = Field(ge=0, le=1, max_digits=7, decimal_places=6)
    audience_retention_ratio: Decimal = Field(
        ge=0,
        max_digits=7,
        decimal_places=6,
    )


class RetentionPointResponse(RetentionPointCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class TrafficSourceCreate(AnalyticsSchema):
    source_type: str = Field(min_length=1, max_length=100)
    views: int | None = Field(default=None, ge=0)
    watch_time_seconds: int | None = Field(default=None, ge=0)
    percentage: Ratio = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=7,
        decimal_places=6,
    )


class TrafficSourceResponse(TrafficSourceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class AudienceDemographicCreate(AnalyticsSchema):
    dimension: str = Field(min_length=1, max_length=50)
    segment: str = Field(min_length=1, max_length=100)
    viewers: int | None = Field(default=None, ge=0)
    percentage: Ratio = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=7,
        decimal_places=6,
    )


class AudienceDemographicResponse(AudienceDemographicCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class AudienceGeographyCreate(AnalyticsSchema):
    country_code: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    viewers: int | None = Field(default=None, ge=0)
    percentage: Ratio = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=7,
        decimal_places=6,
    )


class AudienceGeographyResponse(AudienceGeographyCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class DiscoveryAssetType(str, Enum):
    HASHTAG = "hashtag"
    SOUND = "sound"
    SEARCH_TERM = "search_term"
    EXTERNAL_REFERRER = "external_referrer"
    OTHER = "other"


class DiscoveryAssetCreate(AnalyticsSchema):
    asset_type: DiscoveryAssetType
    asset_value: str = Field(min_length=1, max_length=500)
    views: int | None = Field(default=None, ge=0)
    percentage: Ratio = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=7,
        decimal_places=6,
    )


class DiscoveryAssetResponse(DiscoveryAssetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class TikTokMetricExtensionCreate(AnalyticsSchema):
    for_you_views: int | None = Field(default=None, ge=0)
    following_feed_views: int | None = Field(default=None, ge=0)
    search_views: int | None = Field(default=None, ge=0)
    profile_views: int | None = Field(default=None, ge=0)
    sound_views: int | None = Field(default=None, ge=0)


class InstagramMetricExtensionCreate(AnalyticsSchema):
    reels_tab_reach: int | None = Field(default=None, ge=0)
    feed_reach: int | None = Field(default=None, ge=0)
    explore_reach: int | None = Field(default=None, ge=0)
    profile_reach: int | None = Field(default=None, ge=0)
    accounts_reached: int | None = Field(default=None, ge=0)
    accounts_engaged: int | None = Field(default=None, ge=0)


class YouTubeMetricExtensionCreate(AnalyticsSchema):
    suggested_video_views: int | None = Field(default=None, ge=0)
    browse_feature_views: int | None = Field(default=None, ge=0)
    subscriber_views: int | None = Field(default=None, ge=0)
    unsubscribed_views: int | None = Field(default=None, ge=0)
    search_views: int | None = Field(default=None, ge=0)
    external_views: int | None = Field(default=None, ge=0)
    end_screen_views: int | None = Field(default=None, ge=0)
    reported_impressions_ctr: Ratio = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=9,
        decimal_places=6,
    )


class VideoMetricBase(AnalyticsSchema):
    views: int | None = Field(default=None, ge=0)
    unique_viewers: int | None = Field(default=None, ge=0)
    engaged_views: int | None = Field(default=None, ge=0)
    completed_views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    views_from_impressions: int | None = Field(default=None, ge=0)
    watch_time_seconds: int | None = Field(default=None, ge=0)
    average_view_duration_seconds: int | None = Field(default=None, ge=0)
    followers_gained: int | None = Field(default=None, ge=0)
    followers_lost: int | None = Field(default=None, ge=0)
    new_viewers: int | None = Field(default=None, ge=0)
    returning_viewers: int | None = Field(default=None, ge=0)
    first_hour_views: int | None = Field(default=None, ge=0)
    first_hour_likes: int | None = Field(default=None, ge=0)
    first_hour_comments: int | None = Field(default=None, ge=0)
    first_hour_shares: int | None = Field(default=None, ge=0)
    first_hour_saves: int | None = Field(default=None, ge=0)
    first_hour_watch_time_seconds: int | None = Field(default=None, ge=0)
    first_hour_followers_gained: int | None = Field(default=None, ge=0)
    first_hour_impressions: int | None = Field(default=None, ge=0)
    click_through_rate: Ratio = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=9,
        decimal_places=6,
    )


class VideoMetricCreate(VideoMetricBase):
    captured_at: AwareDatetime | None = None
    retention_points: list[RetentionPointCreate] = Field(default_factory=list)
    traffic_sources: list[TrafficSourceCreate] = Field(default_factory=list)
    demographics: list[AudienceDemographicCreate] = Field(default_factory=list)
    geography: list[AudienceGeographyCreate] = Field(default_factory=list)
    discovery_assets: list[DiscoveryAssetCreate] = Field(default_factory=list)
    tiktok_extension: TikTokMetricExtensionCreate | None = None
    instagram_extension: InstagramMetricExtensionCreate | None = None
    youtube_extension: YouTubeMetricExtensionCreate | None = None

    @model_validator(mode="after")
    def validate_nested_uniqueness(self) -> Self:
        extensions = (
            self.tiktok_extension,
            self.instagram_extension,
            self.youtube_extension,
        )
        if sum(extension is not None for extension in extensions) > 1:
            raise ValueError("only one platform metric extension may be supplied")

        keys: tuple[tuple[object, ...], ...] = (
            tuple(point.position_ratio for point in self.retention_points),
            tuple(source.source_type.lower() for source in self.traffic_sources),
            tuple(
                (item.dimension.lower(), item.segment.lower())
                for item in self.demographics
            ),
            tuple(item.country_code.upper() for item in self.geography),
            tuple(
                (item.asset_type.value, item.asset_value.lower())
                for item in self.discovery_assets
            ),
        )
        if any(len(values) != len(set(values)) for values in keys):
            raise ValueError("nested analytics records must be unique per snapshot")
        return self


class VideoMetricResponse(VideoMetricBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: UUID
    captured_at: datetime
    retention_points: list[RetentionPointResponse]
    traffic_sources: list[TrafficSourceResponse]
    demographics: list[AudienceDemographicResponse]
    geography: list[AudienceGeographyResponse]
    discovery_assets: list[DiscoveryAssetResponse]
    tiktok_extension: TikTokMetricExtensionCreate | None
    instagram_extension: InstagramMetricExtensionCreate | None
    youtube_extension: YouTubeMetricExtensionCreate | None
    engagement_rate: Decimal | None
    follower_conversion_rate: Decimal | None
    share_rate: Decimal | None
    save_rate: Decimal | None
    new_viewer_ratio: Decimal | None
    returning_viewer_ratio: Decimal | None
    impressions_to_view_rate: Decimal | None
    average_percentage_viewed: Decimal | None
    completion_rate: Decimal | None
