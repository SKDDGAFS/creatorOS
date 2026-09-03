from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.runner import JobRegistry, PermanentJobError, RetryableJobError
from app.models.channel import Channel, Platform
from app.models.durable_job import DurableJob
from app.models.platform_integration import PlatformConnection
from app.models.video import Video
from app.platforms.credentials import CredentialStore
from app.platforms.runtime import (
    InstagramAdapterFactory,
    TikTokAdapterFactory,
    YouTubeAdapterFactory,
    get_instagram_adapter_factory,
    get_platform_secret_store,
    get_tiktok_adapter_factory,
    get_youtube_adapter_factory,
)
from app.services import (
    analytics_sync_service,
    instagram_service,
    tiktok_service,
    youtube_service,
)
from app.services.errors import (
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    RateLimitError,
    ResourceNotFoundError,
    ServiceError,
)


class AnalyticsSyncJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: UUID


@dataclass(frozen=True)
class AnalyticsWorkerDependencies:
    secret_store: CredentialStore
    youtube_adapter_factory: YouTubeAdapterFactory | None = None
    instagram_adapter_factory: InstagramAdapterFactory | None = None
    tiktok_adapter_factory: TikTokAdapterFactory | None = None


def _videos_for_connection(
    db: Session,
    *,
    connection: PlatformConnection,
) -> list[Video]:
    return list(
        db.scalars(
            select(Video)
            .join(Channel)
            .where(
                Channel.workspace_id == connection.workspace_id,
                Channel.platform == connection.platform,
                Channel.platform_channel_id == connection.external_account_id,
                Channel.is_active.is_(True),
                Video.platform_video_id.is_not(None),
            )
            .order_by(Video.created_at, Video.id)
        ).all()
    )


def _disabled_channel(
    db: Session,
    *,
    connection: PlatformConnection,
) -> bool:
    channel = db.scalar(
        select(Channel).where(
            Channel.workspace_id == connection.workspace_id,
            Channel.platform == connection.platform,
            Channel.platform_channel_id == connection.external_account_id,
        )
    )
    return channel is not None and not channel.is_active


def _sync_youtube(
    db: Session,
    *,
    connection: PlatformConnection,
    dependencies: AnalyticsWorkerDependencies,
) -> dict[str, int]:
    factory = dependencies.youtube_adapter_factory or get_youtube_adapter_factory()
    videos = youtube_service.sync_videos(
        db,
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
        secret_store=dependencies.secret_store,
        adapter_factory=factory,
    )
    metric_count = sum(
        len(
            youtube_service.sync_metrics(
                db,
                workspace_id=connection.workspace_id,
                connection_id=connection.id,
                video_id=video.id,
                secret_store=dependencies.secret_store,
                adapter_factory=factory,
            )
        )
        for video in _videos_for_connection(db, connection=connection)
    )
    return {
        "channels_synced": 1,
        "videos_synced": len(videos.videos),
        "metrics_synced": metric_count,
        "account_metrics_synced": 0,
    }


def _sync_instagram(
    db: Session,
    *,
    connection: PlatformConnection,
    dependencies: AnalyticsWorkerDependencies,
) -> dict[str, int]:
    factory = dependencies.instagram_adapter_factory or get_instagram_adapter_factory()
    videos = instagram_service.sync_videos(
        db,
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
        secret_store=dependencies.secret_store,
        adapter_factory=factory,
    )
    account_metrics = instagram_service.sync_account_metrics(
        db,
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
        secret_store=dependencies.secret_store,
        adapter_factory=factory,
    )
    metric_count = sum(
        len(
            instagram_service.sync_metrics(
                db,
                workspace_id=connection.workspace_id,
                connection_id=connection.id,
                video_id=video.id,
                secret_store=dependencies.secret_store,
                adapter_factory=factory,
            )
        )
        for video in _videos_for_connection(db, connection=connection)
    )
    return {
        "channels_synced": 1,
        "videos_synced": len(videos.videos),
        "metrics_synced": metric_count,
        "account_metrics_synced": len(account_metrics),
    }


def _sync_tiktok(
    db: Session,
    *,
    connection: PlatformConnection,
    dependencies: AnalyticsWorkerDependencies,
) -> dict[str, int]:
    factory = dependencies.tiktok_adapter_factory or get_tiktok_adapter_factory()
    videos = tiktok_service.sync_videos(
        db,
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
        secret_store=dependencies.secret_store,
        adapter_factory=factory,
    )
    account_metrics = tiktok_service.sync_account_metrics(
        db,
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
        secret_store=dependencies.secret_store,
        adapter_factory=factory,
    )
    metric_count = sum(
        len(
            tiktok_service.sync_metrics(
                db,
                workspace_id=connection.workspace_id,
                connection_id=connection.id,
                video_id=video.id,
                secret_store=dependencies.secret_store,
                adapter_factory=factory,
            )
        )
        for video in _videos_for_connection(db, connection=connection)
    )
    return {
        "channels_synced": 1,
        "videos_synced": len(videos.videos),
        "metrics_synced": metric_count,
        "account_metrics_synced": len(account_metrics),
    }


def _safe_failure(error: ServiceError) -> tuple[str, str, bool]:
    if isinstance(error, RateLimitError):
        return (
            "analytics_rate_limited",
            "Analytics synchronization was rate limited",
            True,
        )
    if isinstance(error, PersistenceError):
        return (
            "analytics_temporary_failure",
            "Analytics synchronization failed temporarily",
            True,
        )
    if isinstance(error, (ConflictError, AuthorizationError)):
        return (
            "analytics_connection_unavailable",
            "Analytics connection requires attention",
            False,
        )
    if isinstance(error, (InvalidRequestError, ResourceNotFoundError)):
        return (
            "analytics_request_invalid",
            "Analytics synchronization request is invalid",
            False,
        )
    return (
        "analytics_sync_failed",
        "Analytics synchronization failed",
        False,
    )


def _handler(
    db: Session,
    *,
    dependencies: AnalyticsWorkerDependencies,
):
    def handle(job: DurableJob) -> dict[str, object]:
        run = analytics_sync_service.get_run_for_job(db, job=job)
        analytics_sync_service.mark_running(db, run=run)
        error: ServiceError
        try:
            payload = AnalyticsSyncJobPayload.model_validate(job.payload)
            connection = db.scalar(
                select(PlatformConnection).where(
                    PlatformConnection.id == payload.connection_id,
                    PlatformConnection.workspace_id == job.workspace_id,
                )
            )
            if connection is None:
                raise ResourceNotFoundError("Platform connection not found")
            if _disabled_channel(db, connection=connection):
                result: dict[str, object] = {
                    "platform": connection.platform,
                    "skipped": True,
                    "reason": "channel_inactive",
                }
                analytics_sync_service.mark_succeeded(
                    db,
                    run=run,
                    channels_synced=0,
                    videos_synced=0,
                    metrics_synced=0,
                    account_metrics_synced=0,
                    summary=result,
                    skipped=True,
                )
                return result

            platform = Platform(connection.platform)
            if platform is Platform.YOUTUBE:
                counts = _sync_youtube(
                    db,
                    connection=connection,
                    dependencies=dependencies,
                )
            elif platform is Platform.INSTAGRAM:
                counts = _sync_instagram(
                    db,
                    connection=connection,
                    dependencies=dependencies,
                )
            else:
                counts = _sync_tiktok(
                    db,
                    connection=connection,
                    dependencies=dependencies,
                )
            result = {"platform": platform.value, **counts}
            analytics_sync_service.mark_succeeded(
                db,
                run=run,
                channels_synced=counts["channels_synced"],
                videos_synced=counts["videos_synced"],
                metrics_synced=counts["metrics_synced"],
                account_metrics_synced=counts["account_metrics_synced"],
                summary=result,
            )
            return result
        except ValidationError as exc:
            error = InvalidRequestError("Analytics job payload is invalid")
            error.__cause__ = exc
        except ServiceError as exc:
            error = exc

        code, message, retryable = _safe_failure(error)
        analytics_sync_service.mark_failed(
            db,
            run=run,
            error_code=code,
            safe_message=message,
            retryable=retryable and job.attempts < job.max_attempts,
        )
        if retryable:
            raise RetryableJobError(code, message) from error
        raise PermanentJobError(code, message) from error

    return handle


def register_analytics_jobs(
    registry: JobRegistry,
    db: Session,
    *,
    dependencies: AnalyticsWorkerDependencies | None = None,
) -> None:
    resolved = dependencies or AnalyticsWorkerDependencies(
        secret_store=get_platform_secret_store()
    )
    registry.register_context_handler(
        analytics_sync_service.ANALYTICS_SYNC_JOB_TYPE,
        _handler(db, dependencies=resolved),
    )
