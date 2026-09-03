from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.analytics_sync import AnalyticsSyncRun, AnalyticsSyncStatus
from app.schemas.analytics_sync import (
    AnalyticsSyncHealthResponse,
    AnalyticsSyncRunResponse,
    AnalyticsSyncScheduleRequest,
)
from app.services import analytics_sync_service

router = APIRouter(prefix="/analytics-sync", tags=["analytics sync"])


@router.post(
    "/schedule",
    response_model=list[AnalyticsSyncRunResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def schedule_analytics_sync(
    payload: AnalyticsSyncScheduleRequest,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> list[AnalyticsSyncRun]:
    return analytics_sync_service.schedule_sync_runs(
        db,
        workspace_id=context.workspace_id,
        requested_by_user_id=context.auth.user.id,
        idempotency_key=idempotency_key,
        connection_ids=payload.connection_ids,
        scheduled_for=payload.scheduled_for,
        priority=payload.priority,
        max_attempts=payload.max_attempts,
    )


@router.get("/runs", response_model=list[AnalyticsSyncRunResponse])
def list_analytics_sync_runs(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    connection_id: UUID | None = None,
    run_status: Annotated[
        AnalyticsSyncStatus | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AnalyticsSyncRun]:
    return analytics_sync_service.list_sync_runs(
        db,
        workspace_id=context.workspace_id,
        connection_id=connection_id,
        status=run_status,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=AnalyticsSyncRunResponse)
def get_analytics_sync_run(
    run_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> AnalyticsSyncRun:
    return analytics_sync_service.get_sync_run(
        db,
        workspace_id=context.workspace_id,
        run_id=run_id,
    )


@router.get("/health", response_model=list[AnalyticsSyncHealthResponse])
def list_analytics_sync_health(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[analytics_sync_service.AnalyticsSyncHealth]:
    return analytics_sync_service.list_sync_health(
        db,
        workspace_id=context.workspace_id,
    )
