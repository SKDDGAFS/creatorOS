from typing import Literal
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.analytics import (
    InstagramMetricExtension,
    TikTokMetricExtension,
    VideoAudienceDemographic,
    VideoAudienceGeography,
    VideoDiscoveryAsset,
    VideoRetentionPoint,
    VideoTrafficSource,
    YouTubeMetricExtension,
)
from app.models.channel import Channel, Platform
from app.models.video import Video, VideoStatus
from app.models.video_metric import VideoMetric
from app.schemas.video import VideoCreate, VideoUpdate
from app.schemas.video_metric import VideoMetricCreate
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
)

MetricOrder = Literal["newest", "oldest"]

NESTED_ANALYTICS_FIELDS = {
    "retention_points",
    "traffic_sources",
    "demographics",
    "geography",
    "discovery_assets",
    "tiktok_extension",
    "instagram_extension",
    "youtube_extension",
}

ANALYTICS_LOAD_OPTIONS = (
    joinedload(VideoMetric.video),
    selectinload(VideoMetric.retention_points),
    selectinload(VideoMetric.traffic_sources),
    selectinload(VideoMetric.demographics),
    selectinload(VideoMetric.geography),
    selectinload(VideoMetric.discovery_assets),
    joinedload(VideoMetric.tiktok_extension),
    joinedload(VideoMetric.instagram_extension),
    joinedload(VideoMetric.youtube_extension),
)

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
    video = get_video(db, video_id, workspace_id=workspace_id)

    values = payload.model_dump(
        exclude={"captured_at", *NESTED_ANALYTICS_FIELDS}
    )
    if payload.captured_at is not None:
        values["captured_at"] = payload.captured_at

    metric = VideoMetric(video_id=video_id, **values)
    _attach_platform_extension(metric, payload, video.channel.platform)
    metric.video = video
    metric.retention_points = [
        VideoRetentionPoint(**point.model_dump())
        for point in payload.retention_points
    ]
    metric.traffic_sources = [
        VideoTrafficSource(
            **source.model_dump(exclude={"source_type"}),
            source_type=source.source_type.lower(),
        )
        for source in payload.traffic_sources
    ]
    metric.demographics = [
        VideoAudienceDemographic(
            **item.model_dump(exclude={"dimension"}),
            dimension=item.dimension.lower(),
        )
        for item in payload.demographics
    ]
    metric.geography = [
        VideoAudienceGeography(
            **item.model_dump(exclude={"country_code"}),
            country_code=item.country_code.upper(),
        )
        for item in payload.geography
    ]
    metric.discovery_assets = [
        VideoDiscoveryAsset(
            **item.model_dump(exclude={"asset_type"}),
            asset_type=item.asset_type.value,
        )
        for item in payload.discovery_assets
    ]
    db.add(metric)

    try:
        db.commit()
        db.refresh(metric)
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to save video metric") from exc

    return metric


def _attach_platform_extension(
    metric: VideoMetric,
    payload: VideoMetricCreate,
    platform: str,
) -> None:
    extensions = (
        (
            Platform.TIKTOK.value,
            payload.tiktok_extension,
            TikTokMetricExtension,
            "tiktok_extension",
        ),
        (
            Platform.INSTAGRAM.value,
            payload.instagram_extension,
            InstagramMetricExtension,
            "instagram_extension",
        ),
        (
            Platform.YOUTUBE.value,
            payload.youtube_extension,
            YouTubeMetricExtension,
            "youtube_extension",
        ),
    )
    for expected_platform, extension, model, relationship_name in extensions:
        if extension is None:
            continue
        if platform != expected_platform:
            raise InvalidRequestError(
                f"{expected_platform} analytics require a "
                f"{expected_platform} video"
            )
        setattr(metric, relationship_name, model(**extension.model_dump()))


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
        .options(*ANALYTICS_LOAD_OPTIONS)
        .where(VideoMetric.video_id == video_id)
        .order_by(*ordering)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())
