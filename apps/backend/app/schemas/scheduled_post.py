from datetime import UTC, datetime
from uuid import UUID

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
)

from app.models.channel import Platform
from app.models.scheduled_post import ScheduledPostStatus


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    caption: str | None = Field(default=None, max_length=2200)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    is_short: bool = False


class ScheduledPostCreate(BaseModel):
    video_id: UUID
    channel_id: UUID
    scheduled_at: AwareDatetime | None = None
    recommended_at: AwareDatetime | None = None
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    metadata: Metadata
    status: ScheduledPostStatus = ScheduledPostStatus.DRAFT


class ScheduledPostUpdate(BaseModel):
    scheduled_at: AwareDatetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: Metadata | None = None
    status: ScheduledPostStatus | None = None


class ScheduledPostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: UUID
    channel_id: UUID
    platform: Platform
    scheduled_at: datetime | None
    recommended_at: datetime | None
    timezone: str
    status: ScheduledPostStatus
    metadata: Metadata = Field(
        validation_alias=AliasChoices("metadata_json", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime

    @field_serializer("scheduled_at", "recommended_at")
    def serialize_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )
