from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.channel import Platform
from app.models.platform_integration import ConnectionStatus
from app.schemas.video import VideoResponse


class IntegrationSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class YouTubeOAuthStartRequest(IntegrationSchema):
    publishing: bool = False


class InstagramOAuthStartRequest(IntegrationSchema):
    publishing: bool = False


class TikTokOAuthStartRequest(IntegrationSchema):
    publishing: bool = False


class PlatformConnectionResponse(IntegrationSchema):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    platform: Platform
    external_account_id: str
    display_name: str | None
    scopes: list[str]
    status: ConnectionStatus
    token_expires_at: datetime | None
    connected_at: datetime
    last_refreshed_at: datetime | None
    disconnected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VideoSyncResponse(IntegrationSchema):
    videos: list[VideoResponse]
    next_cursor: str | None


class PlatformQuotaUsageResponse(IntegrationSchema):
    id: UUID
    connection_id: UUID
    usage_date: date
    quota_bucket: str
    units: int
    request_count: int
    updated_at: datetime


class PlatformAccountMetricSnapshotResponse(IntegrationSchema):
    id: UUID
    connection_id: UUID
    captured_at: datetime
    period: str
    values: dict[str, int | float | str | bool | None]
    unavailable_fields: list[str]
    provider_metadata: dict[str, object]
    created_at: datetime


class InstagramPublishingLimitResponse(IntegrationSchema):
    quota_usage: int
    quota_total: int
    quota_duration_seconds: int
