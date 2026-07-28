from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.video import VideoStatus


class VideoBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    platform_video_id: str | None = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    status: VideoStatus = VideoStatus.DRAFT
    published_at: AwareDatetime | None = None


class VideoCreate(VideoBase):
    channel_id: UUID


class VideoUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    platform_video_id: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: VideoStatus | None = None
    published_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> Self:
        required_fields = {"title", "status"}

        for field_name in self.model_fields_set & required_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class VideoResponse(VideoBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_id: UUID
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
