from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_admin,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.publishing import (
    ActivityEvent,
    ApprovalRequest,
    PublishingJob,
    PublishingState,
)
from app.schemas.publishing import (
    ActivityEventResponse,
    ApprovalRequestResponse,
    CancellationRequest,
    PublishingJobCreate,
    PublishingJobResponse,
    ScheduleRequest,
    WorkflowNote,
)
from app.services import publishing_service

router = APIRouter(prefix="/publishing", tags=["publishing"])


@router.post(
    "/jobs",
    response_model=PublishingJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    payload: PublishingJobCreate,
    response: Response,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=128,
        ),
    ],
) -> PublishingJob:
    job, created = publishing_service.create_job(
        db,
        workspace_id=context.workspace_id,
        user_id=context.auth.user.id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return job


@router.get("/jobs", response_model=list[PublishingJobResponse])
def list_jobs(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    job_status: Annotated[
        PublishingState | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PublishingJob]:
    return publishing_service.list_jobs(
        db,
        workspace_id=context.workspace_id,
        status=job_status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/approvals",
    response_model=list[ApprovalRequestResponse],
)
def list_pending_approvals(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ApprovalRequest]:
    return publishing_service.list_pending_approvals(
        db,
        workspace_id=context.workspace_id,
        limit=limit,
        offset=offset,
    )


@router.get("/activity", response_model=list[ActivityEventResponse])
def list_activity(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ActivityEvent]:
    return publishing_service.list_activity(
        db,
        workspace_id=context.workspace_id,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=PublishingJobResponse)
def get_job(
    job_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> PublishingJob:
    return publishing_service.get_job(
        db,
        workspace_id=context.workspace_id,
        job_id=job_id,
    )


@router.post(
    "/jobs/{job_id}/prepare",
    response_model=PublishingJobResponse,
)
def prepare_job(
    job_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> PublishingJob:
    return publishing_service.prepare_job(
        db,
        workspace_id=context.workspace_id,
        job_id=job_id,
        actor_user_id=context.auth.user.id,
    )


@router.post(
    "/jobs/{job_id}/request-approval",
    response_model=PublishingJobResponse,
)
def request_approval(
    job_id: UUID,
    payload: WorkflowNote,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> PublishingJob:
    return publishing_service.request_approval(
        db,
        workspace_id=context.workspace_id,
        job_id=job_id,
        actor_user_id=context.auth.user.id,
        note=payload.note,
    )


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=PublishingJobResponse,
)
def approve(
    approval_id: UUID,
    payload: WorkflowNote,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> PublishingJob:
    return publishing_service.decide_approval(
        db,
        workspace_id=context.workspace_id,
        approval_id=approval_id,
        actor_user_id=context.auth.user.id,
        approve=True,
        note=payload.note,
    )


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=PublishingJobResponse,
)
def reject(
    approval_id: UUID,
    payload: WorkflowNote,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> PublishingJob:
    return publishing_service.decide_approval(
        db,
        workspace_id=context.workspace_id,
        approval_id=approval_id,
        actor_user_id=context.auth.user.id,
        approve=False,
        note=payload.note,
    )


@router.post(
    "/jobs/{job_id}/schedule",
    response_model=PublishingJobResponse,
)
def schedule_job(
    job_id: UUID,
    payload: ScheduleRequest,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> PublishingJob:
    return publishing_service.schedule_job(
        db,
        workspace_id=context.workspace_id,
        job_id=job_id,
        actor_user_id=context.auth.user.id,
        scheduled_for=payload.scheduled_for,
    )


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=PublishingJobResponse,
)
def cancel_job(
    job_id: UUID,
    payload: CancellationRequest,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> PublishingJob:
    return publishing_service.cancel_job(
        db,
        workspace_id=context.workspace_id,
        job_id=job_id,
        actor_user_id=context.auth.user.id,
        reason=payload.reason,
    )
