from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.publishing import (
    ActivityType,
    ApprovalStatus,
    PublishingState,
)


class PublishingSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)


class PublishingJobCreate(PublishingSchema):
    video_id: UUID


class WorkflowNote(PublishingSchema):
    note: str | None = Field(default=None, max_length=2000)


class ScheduleRequest(PublishingSchema):
    scheduled_for: AwareDatetime


class CancellationRequest(PublishingSchema):
    reason: str = Field(min_length=1, max_length=500)


class ApprovalRequestResponse(PublishingSchema):
    id: UUID
    publishing_job_id: UUID
    requested_by_user_id: UUID
    decided_by_user_id: UUID | None
    sequence: int
    status: ApprovalStatus
    request_note: str | None
    decision_note: str | None
    requested_at: datetime
    decided_at: datetime | None


class PublishingTransitionResponse(PublishingSchema):
    id: UUID
    actor_user_id: UUID | None
    from_state: PublishingState | None
    to_state: PublishingState
    reason: str | None
    created_at: datetime


class PublishingJobResponse(PublishingSchema):
    id: UUID
    workspace_id: UUID
    video_id: UUID
    created_by_user_id: UUID
    status: PublishingState
    scheduled_for: datetime | None
    approved_at: datetime | None
    published_at: datetime | None
    cancelled_at: datetime | None
    failed_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime
    approvals: list[ApprovalRequestResponse]
    transitions: list[PublishingTransitionResponse]


class ActivityEventResponse(PublishingSchema):
    id: UUID
    workspace_id: UUID
    actor_user_id: UUID | None
    publishing_job_id: UUID | None
    event_type: ActivityType
    event_data: dict[str, Any]
    created_at: datetime
