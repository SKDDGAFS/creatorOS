from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.analytics_sync import AnalyticsSyncStatus
from app.models.channel import Platform
from app.models.platform_integration import ConnectionStatus


class AnalyticsSyncSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class AnalyticsSyncScheduleRequest(AnalyticsSyncSchema):
    connection_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    scheduled_for: AwareDatetime | None = None
    priority: int = Field(default=50, ge=0, le=100)
    max_attempts: int = Field(default=3, ge=1, le=10)


class AnalyticsSyncRunResponse(AnalyticsSyncSchema):
    id: UUID
    workspace_id: UUID
    connection_id: UUID
    durable_job_id: UUID
    status: AnalyticsSyncStatus
    channels_synced: int
    videos_synced: int
    metrics_synced: int
    account_metrics_synced: int
    summary: dict[str, object]
    last_error_code: str | None
    last_error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AnalyticsSyncHealthResponse(AnalyticsSyncSchema):
    connection_id: UUID
    platform: Platform
    connection_status: ConnectionStatus
    latest_run: AnalyticsSyncRunResponse | None
    healthy: bool
