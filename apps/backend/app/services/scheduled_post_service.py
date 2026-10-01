from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.scheduled_post import ScheduledPost, ScheduledPostStatus
from app.models.video import Video
from app.schemas.scheduled_post import ScheduledPostCreate, ScheduledPostUpdate
from app.services.errors import ConflictError, PersistenceError, ResourceNotFoundError


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ConflictError("scheduled_at must include a timezone offset")
    return value.astimezone(UTC)


def _check_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ConflictError("timezone must be a valid IANA timezone") from exc


def _validate_metadata(platform: str, metadata: dict[str, object]) -> None:
    if platform == "youtube" and not metadata.get("title"):
        raise ConflictError("YouTube metadata requires a title")
    if platform in {"instagram", "tiktok"} and not metadata.get("caption"):
        raise ConflictError(f"{platform.title()} metadata requires a caption")


def create_post(db: Session, payload: ScheduledPostCreate) -> ScheduledPost:
    video = db.get(Video, payload.video_id)
    channel = db.get(Channel, payload.channel_id)
    if video is None:
        raise ResourceNotFoundError("Video not found")
    if channel is None:
        raise ResourceNotFoundError("Channel not found")
    if video.channel_id != channel.id:
        raise ConflictError("Video and target channel must belong together")
    _check_timezone(payload.timezone)
    _validate_metadata(channel.platform, payload.metadata.model_dump())
    post = ScheduledPost(
        video_id=video.id,
        channel_id=channel.id,
        scheduled_at=_utc(payload.scheduled_at),
        recommended_at=_utc(payload.recommended_at),
        timezone=payload.timezone,
        status=payload.status.value,
        metadata_json=payload.metadata.model_dump(),
    )
    db.add(post)
    try:
        db.commit()
        db.refresh(post)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to save scheduled post") from exc
    return post


def list_posts(
    db: Session, status: ScheduledPostStatus | None = None
) -> list[ScheduledPost]:
    statement: Select[tuple[ScheduledPost]] = select(ScheduledPost)
    if status is not None:
        statement = statement.where(ScheduledPost.status == status.value)
    return list(
        db.scalars(
            statement.order_by(
                ScheduledPost.scheduled_at.asc().nulls_last(),
                ScheduledPost.created_at.desc(),
            )
        ).all()
    )


def get_post(db: Session, post_id: UUID) -> ScheduledPost:
    post = db.get(ScheduledPost, post_id)
    if post is None:
        raise ResourceNotFoundError("Scheduled post not found")
    return post


def update_post(
    db: Session, post_id: UUID, payload: ScheduledPostUpdate
) -> ScheduledPost:
    post = get_post(db, post_id)
    if post.status == ScheduledPostStatus.CANCELLED.value:
        raise ConflictError("Cancelled posts cannot be changed")
    changes = payload.model_dump(exclude_unset=True)
    if "timezone" in changes:
        _check_timezone(changes["timezone"])
    if payload.metadata is not None:
        _validate_metadata(post.channel.platform, payload.metadata.model_dump())
        changes["metadata_json"] = payload.metadata.model_dump()
    if "scheduled_at" in changes:
        changes["scheduled_at"] = _utc(payload.scheduled_at)
    if payload.status is not None:
        changes["status"] = payload.status.value
    for name, value in changes.items():
        setattr(post, name, value)
    try:
        db.commit()
        db.refresh(post)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to update scheduled post") from exc
    return post
