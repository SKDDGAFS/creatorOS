from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_write,
)
from app.db.session import get_db
from app.models.video import Video, VideoStatus
from app.models.video_metric import VideoMetric
from app.schemas.video import VideoCreate, VideoResponse, VideoUpdate
from app.schemas.video_metric import VideoMetricCreate, VideoMetricResponse
from app.services import video_service

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post(
    "",
    response_model=VideoResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_video(
    payload: VideoCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> Video:
    return video_service.create_video(
        db,
        payload,
        workspace_id=context.workspace_id,
    )


@router.get("", response_model=list[VideoResponse])
def list_videos(
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    channel_id: UUID | None = None,
    video_status: Annotated[
        VideoStatus | None,
        Query(alias="status"),
    ] = None,
) -> list[Video]:
    return video_service.list_videos(
        db,
        limit=limit,
        offset=offset,
        workspace_id=context.workspace_id,
        channel_id=channel_id,
        status=video_status,
    )


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(
    video_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
) -> Video:
    return video_service.get_video(
        db,
        video_id,
        workspace_id=context.workspace_id,
    )


@router.patch("/{video_id}", response_model=VideoResponse)
def update_video(
    video_id: UUID,
    payload: VideoUpdate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> Video:
    return video_service.update_video(
        db,
        video_id,
        payload,
        workspace_id=context.workspace_id,
    )


@router.post(
    "/{video_id}/metrics",
    response_model=VideoMetricResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_metric(
    video_id: UUID,
    payload: VideoMetricCreate,
    context: Annotated[WorkspaceContext, Depends(require_workspace_write)],
    db: Annotated[Session, Depends(get_db)],
) -> VideoMetric:
    return video_service.create_metric(
        db,
        video_id,
        payload,
        workspace_id=context.workspace_id,
    )


@router.get(
    "/{video_id}/metrics",
    response_model=list[VideoMetricResponse],
)
def list_metrics(
    video_id: UUID,
    context: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    db: Annotated[Session, Depends(get_db)],
    order: Literal["newest", "oldest"] = "newest",
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[VideoMetric]:
    return video_service.list_metrics(
        db,
        video_id,
        workspace_id=context.workspace_id,
        order=order,
        limit=limit,
        offset=offset,
    )
