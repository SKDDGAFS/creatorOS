from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.durable_job import JobAttemptStatus, JobStatus


class JobSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JobAttemptResponse(JobSchema):
    id: UUID
    attempt_number: int
    worker_id: str
    status: JobAttemptStatus
    started_at: datetime
    completed_at: datetime | None
    error_code: str | None
    safe_error_message: str | None


class DurableJobResponse(JobSchema):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID | None
    job_type: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    status: JobStatus
    priority: int
    scheduled_for: datetime
    attempts: int
    max_attempts: int
    lock_owner: str | None
    lock_expires_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None
    updated_at: datetime
    attempt_history: list[JobAttemptResponse]
