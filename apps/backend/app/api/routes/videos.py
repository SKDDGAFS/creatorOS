from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.errors import raise_service_http_error
from app.core.config import get_settings
from app.db.session import get_db
from app.models.video import Video, VideoStatus
from app.models.video_metric import VideoMetric
from app.schemas.video import VideoCreate, VideoResponse, VideoUpdate
from app.schemas.video_metric import VideoMetricCreate, VideoMetricResponse
from app.services import media_service, video_service
from app.services.errors import ServiceError

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post(
    "/upload", response_model=VideoResponse, status_code=status.HTTP_201_CREATED
)
def upload_video(
    channel_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Video:
    settings = get_settings()
    try:
        return media_service.save_upload(
            db,
            channel_id=channel_id,
            upload=file,
            storage_root=Path(settings.storage_path),
            max_size=settings.max_upload_size_bytes,
        )
    except ServiceError as exc:
        raise_service_http_error(exc)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "",
    response_model=VideoResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_video(
    payload: VideoCreate,
    db: Session = Depends(get_db),
) -> Video:
    try:
        return video_service.create_video(db, payload)
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.get("", response_model=list[VideoResponse])
def list_videos(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    channel_id: UUID | None = None,
    video_status: Annotated[
        VideoStatus | None,
        Query(alias="status"),
    ] = None,
    db: Session = Depends(get_db),
) -> list[Video]:
    return video_service.list_videos(
        db,
        limit=limit,
        offset=offset,
        channel_id=channel_id,
        status=video_status,
    )


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(
    video_id: UUID,
    db: Session = Depends(get_db),
) -> Video:
    try:
        return video_service.get_video(db, video_id)
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.patch("/{video_id}", response_model=VideoResponse)
def update_video(
    video_id: UUID,
    payload: VideoUpdate,
    db: Session = Depends(get_db),
) -> Video:
    try:
        return video_service.update_video(db, video_id, payload)
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.post(
    "/{video_id}/metrics",
    response_model=VideoMetricResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_metric(
    video_id: UUID,
    payload: VideoMetricCreate,
    db: Session = Depends(get_db),
) -> VideoMetric:
    try:
        return video_service.create_metric(db, video_id, payload)
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.get(
    "/{video_id}/metrics",
    response_model=list[VideoMetricResponse],
)
def list_metrics(
    video_id: UUID,
    order: Literal["newest", "oldest"] = "newest",
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[VideoMetric]:
    try:
        return video_service.list_metrics(
            db,
            video_id,
            order=order,
            limit=limit,
            offset=offset,
        )
    except ServiceError as exc:
        raise_service_http_error(exc)
