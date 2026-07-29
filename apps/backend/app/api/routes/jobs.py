from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_admin,
)
from app.db.session import get_db
from app.models.durable_job import DurableJob, JobStatus
from app.schemas.durable_job import DurableJobResponse
from app.services import durable_job_service

router = APIRouter(prefix="/jobs", tags=["durable jobs"])


@router.get("", response_model=list[DurableJobResponse])
def list_jobs(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    job_status: Annotated[
        JobStatus | None,
        Query(alias="status"),
    ] = None,
    job_type: Annotated[
        str | None,
        Query(min_length=1, max_length=100),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DurableJob]:
    return durable_job_service.list_jobs(
        db,
        workspace_id=context.workspace_id,
        status=job_status,
        job_type=job_type,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=DurableJobResponse)
def get_job(
    job_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> DurableJob:
    return durable_job_service.get_job(
        db,
        workspace_id=context.workspace_id,
        job_id=job_id,
    )


@router.post("/{job_id}/cancel", response_model=DurableJobResponse)
def cancel_job(
    job_id: UUID,
    context: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> DurableJob:
    return durable_job_service.cancel_job(
        db,
        workspace_id=context.workspace_id,
        job_id=job_id,
    )
