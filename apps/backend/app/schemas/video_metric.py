from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class VideoMetricBase(BaseModel):
    views: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    watch_time_seconds: int = Field(default=0, ge=0)
    average_view_duration_seconds: int = Field(default=0, ge=0)
    impressions: int = Field(default=0, ge=0)
    click_through_rate: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=1,
        max_digits=7,
        decimal_places=4,
    )


class VideoMetricCreate(VideoMetricBase):
    captured_at: AwareDatetime | None = None


class VideoMetricResponse(VideoMetricBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    video_id: UUID
    captured_at: datetime