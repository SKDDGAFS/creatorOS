from typing import Literal
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.video import Video, VideoStatus
from app.models.video_metric import VideoMetric
from app.schemas.video import VideoCreate, VideoUpdate
from app.schemas.video_metric import VideoMetricCreate
from app.services.errors import (
    ConflictError,
    PersistenceError,
    ResourceNotFoundError,
)

MetricOrder = Literal["newest", "oldest"]


def _get_workspace_channel(
    db: Session,
    channel_id: UUID,
    workspace_id: UUID,
) -> Channel | None:
    return db.scalar(
        select(Channel).where(
            Channel.id == channel_id,
            Channel.workspace_id == workspace_id,
        )
    )


def create_video(
    db: Session,
    payload: VideoCreate,
    *,
    workspace_id: UUID,
) -> Video:
    if _get_workspace_channel(db, payload.channel_id, workspace_id) is None:
        raise ResourceNotFoundError("Channel not found")

    values = payload.model_dump()
    values["status"] = payload.status.value
    video = Video(**values)
    db.add(video)

    try:
        db.commit()
        db.refresh(video)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "A video with this channel_id and platform_video_id already exists"
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to save video") from exc

    return video


def list_videos(
    db: Session,
    *,
    limit: int,
    offset: int,
    workspace_id: UUID,
    channel_id: UUID | None = None,
    status: VideoStatus | None = None,
) -> list[Video]:
    statement: Select[tuple[Video]] = (
        select(Video)
        .join(Channel)
        .where(Channel.workspace_id == workspace_id)
    )

    if channel_id is not None:
        statement = statement.where(Video.channel_id == channel_id)
    if status is not None:
        statement = statement.where(Video.status == status.value)

    statement = statement.order_by(
        Video.created_at.asc(),
        Video.id.asc(),
    ).offset(offset).limit(limit)

    return list(db.scalars(statement).all())


def get_video(
    db: Session,
    video_id: UUID,
    *,
    workspace_id: UUID,
) -> Video:
    video = db.scalar(
        select(Video)
        .join(Channel)
        .where(
            Video.id == video_id,
            Channel.workspace_id == workspace_id,
        )
    )
    if video is None:
        raise ResourceNotFoundError("Video not found")
    return video


def update_video(
    db: Session,
    video_id: UUID,
    payload: VideoUpdate,
    *,
    workspace_id: UUID,
) -> Video:
    video = get_video(db, video_id, workspace_id=workspace_id)
    changes = payload.model_dump(exclude_unset=True)

    if "status" in changes:
        assert payload.status is not None
        changes["status"] = payload.status.value

    for field_name, value in changes.items():
        setattr(video, field_name, value)

    try:
        db.commit()
        db.refresh(video)
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "A video with this channel_id and platform_video_id already exists"
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to update video") from exc

    return video


def create_metric(
    db: Session,
    video_id: UUID,
    payload: VideoMetricCreate,
    *,
    workspace_id: UUID,
) -> VideoMetric:
    get_video(db, video_id, workspace_id=workspace_id)

    values = payload.model_dump(exclude={"captured_at"})
    if payload.captured_at is not None:
        values["captured_at"] = payload.captured_at

    metric = VideoMetric(video_id=video_id, **values)
    db.add(metric)

    try:
        db.commit()
        db.refresh(metric)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to save video metric") from exc

    return metric


def list_metrics(
    db: Session,
    video_id: UUID,
    *,
    workspace_id: UUID,
    order: MetricOrder,
    limit: int,
    offset: int,
) -> list[VideoMetric]:
    get_video(db, video_id, workspace_id=workspace_id)

    if order == "newest":
        ordering = (
            VideoMetric.captured_at.desc(),
            VideoMetric.id.desc(),
        )
    else:
        ordering = (
            VideoMetric.captured_at.asc(),
            VideoMetric.id.asc(),
        )

    statement = (
        select(VideoMetric)
        .where(VideoMetric.video_id == video_id)
        .order_by(*ordering)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())
