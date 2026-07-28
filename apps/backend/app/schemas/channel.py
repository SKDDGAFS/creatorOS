from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.channel import Platform


class ChannelBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    platform: Platform
    platform_channel_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    handle: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    platform: Platform | None = None
    platform_channel_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    name: str | None = Field(default=None, min_length=1, max_length=255)
    handle: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> Self:
        required_fields = {
            "platform",
            "platform_channel_id",
            "name",
            "is_active",
        }

        for field_name in self.model_fields_set & required_fields:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")

        return self


class ChannelResponse(ChannelBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime
