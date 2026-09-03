from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.analytics_sync import AnalyticsSyncRun, AnalyticsSyncStatus
from app.models.channel import Platform
from app.models.durable_job import DurableJob
from app.models.platform_integration import ConnectionStatus, PlatformConnection
from app.models.publishing import ActivityEvent, ActivityType
from app.services import durable_job_service
from app.services.errors import (
    ConflictError,
    PersistenceError,
    ResourceNotFoundError,
)

ANALYTICS_SYNC_JOB_TYPE = "analytics.sync_connection"


@dataclass(frozen=True)
class AnalyticsSyncHealth:
    connection_id: UUID
    platform: Platform
    connection_status: ConnectionStatus
    latest_run: AnalyticsSyncRun | None
    healthy: bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(message) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(message) from exc


def _event(
    db: Session,
    *,
    run: AnalyticsSyncRun,
    event_type: ActivityType,
    actor_user_id: UUID | None = None,
) -> None:
    db.add(
        ActivityEvent(
            workspace_id=run.workspace_id,
            actor_user_id=actor_user_id,
            event_type=event_type.value,
            event_data={
                "analytics_sync_run_id": str(run.id),
                "connection_id": str(run.connection_id),
                "status": run.status,
            },
        )
    )


def schedule_sync_runs(
    db: Session,
    *,
    workspace_id: UUID,
    requested_by_user_id: UUID,
    idempotency_key: str,
    connection_ids: tuple[UUID, ...] = (),
    scheduled_for: datetime | None = None,
    priority: int = 50,
    max_attempts: int = 3,
) -> list[AnalyticsSyncRun]:
    statement: Select[tuple[PlatformConnection]] = select(PlatformConnection).where(
        PlatformConnection.workspace_id == workspace_id,
        PlatformConnection.status == ConnectionStatus.CONNECTED.value,
    )
    if connection_ids:
        unique_ids = set(connection_ids)
        statement = statement.where(PlatformConnection.id.in_(unique_ids))
    connections = list(
        db.scalars(
            statement.order_by(
                PlatformConnection.platform,
                PlatformConnection.id,
            )
        ).all()
    )
    if connection_ids and len(connections) != len(set(connection_ids)):
        raise ResourceNotFoundError(
            "One or more connected platform connections were not found"
        )

    runs: list[AnalyticsSyncRun] = []
    for connection in connections:
        job, _ = durable_job_service.enqueue_job(
            db,
            workspace_id=workspace_id,
            created_by_user_id=requested_by_user_id,
            job_type=ANALYTICS_SYNC_JOB_TYPE,
            payload={"connection_id": str(connection.id)},
            priority=priority,
            scheduled_for=scheduled_for,
            max_attempts=max_attempts,
            idempotency_key=f"{idempotency_key}:{connection.id}",
        )
        run = db.scalar(
            select(AnalyticsSyncRun).where(AnalyticsSyncRun.durable_job_id == job.id)
        )
        if run is None:
            run = AnalyticsSyncRun(
                id=uuid4(),
                workspace_id=workspace_id,
                connection_id=connection.id,
                durable_job_id=job.id,
                status=AnalyticsSyncStatus.QUEUED.value,
            )
            db.add(run)
            _event(
                db,
                run=run,
                event_type=ActivityType.ANALYTICS_SYNC_SCHEDULED,
                actor_user_id=requested_by_user_id,
            )
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                run = db.scalar(
                    select(AnalyticsSyncRun).where(
                        AnalyticsSyncRun.durable_job_id == job.id
                    )
                )
                if run is None:
                    raise ConflictError(
                        "Unable to schedule analytics synchronization"
                    ) from None
            except SQLAlchemyError as exc:
                db.rollback()
                raise PersistenceError(
                    "Unable to schedule analytics synchronization"
                ) from exc
        runs.append(run)
    return runs


def get_sync_run(
    db: Session,
    *,
    workspace_id: UUID,
    run_id: UUID,
    lock: bool = False,
) -> AnalyticsSyncRun:
    statement = select(AnalyticsSyncRun).where(
        AnalyticsSyncRun.id == run_id,
        AnalyticsSyncRun.workspace_id == workspace_id,
    )
    if lock:
        statement = statement.with_for_update()
    run = db.scalar(statement)
    if run is None:
        raise ResourceNotFoundError("Analytics synchronization run not found")
    return run


def get_run_for_job(
    db: Session,
    *,
    job: DurableJob,
    lock: bool = False,
) -> AnalyticsSyncRun:
    statement = select(AnalyticsSyncRun).where(
        AnalyticsSyncRun.durable_job_id == job.id,
        AnalyticsSyncRun.workspace_id == job.workspace_id,
    )
    if lock:
        statement = statement.with_for_update()
    run = db.scalar(statement)
    if run is None:
        raise ResourceNotFoundError("Analytics synchronization run not found")
    return run


def list_sync_runs(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID | None,
    status: AnalyticsSyncStatus | None,
    limit: int,
    offset: int,
) -> list[AnalyticsSyncRun]:
    statement: Select[tuple[AnalyticsSyncRun]] = select(AnalyticsSyncRun).where(
        AnalyticsSyncRun.workspace_id == workspace_id
    )
    if connection_id is not None:
        statement = statement.where(AnalyticsSyncRun.connection_id == connection_id)
    if status is not None:
        statement = statement.where(AnalyticsSyncRun.status == status.value)
    statement = (
        statement.order_by(
            AnalyticsSyncRun.created_at.desc(),
            AnalyticsSyncRun.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def list_sync_health(
    db: Session,
    *,
    workspace_id: UUID,
) -> list[AnalyticsSyncHealth]:
    connections = list(
        db.scalars(
            select(PlatformConnection)
            .where(PlatformConnection.workspace_id == workspace_id)
            .order_by(PlatformConnection.platform, PlatformConnection.id)
        ).all()
    )
    health: list[AnalyticsSyncHealth] = []
    for connection in connections:
        latest = db.scalar(
            select(AnalyticsSyncRun)
            .where(
                AnalyticsSyncRun.workspace_id == workspace_id,
                AnalyticsSyncRun.connection_id == connection.id,
            )
            .order_by(
                AnalyticsSyncRun.created_at.desc(),
                AnalyticsSyncRun.id.desc(),
            )
            .limit(1)
        )
        connection_status = ConnectionStatus(connection.status)
        healthy = connection_status is ConnectionStatus.CONNECTED and (
            latest is None
            or latest.status
            in {
                AnalyticsSyncStatus.QUEUED.value,
                AnalyticsSyncStatus.RUNNING.value,
                AnalyticsSyncStatus.RETRY_SCHEDULED.value,
                AnalyticsSyncStatus.SUCCEEDED.value,
                AnalyticsSyncStatus.SKIPPED.value,
            }
        )
        health.append(
            AnalyticsSyncHealth(
                connection_id=connection.id,
                platform=Platform(connection.platform),
                connection_status=connection_status,
                latest_run=latest,
                healthy=healthy,
            )
        )
    return health


def mark_running(db: Session, *, run: AnalyticsSyncRun) -> AnalyticsSyncRun:
    run.status = AnalyticsSyncStatus.RUNNING.value
    run.started_at = run.started_at or _utc_now()
    run.completed_at = None
    run.last_error_code = None
    run.last_error_message = None
    _event(db, run=run, event_type=ActivityType.ANALYTICS_SYNC_STARTED)
    _commit(db, "Unable to start analytics synchronization")
    return run


def mark_succeeded(
    db: Session,
    *,
    run: AnalyticsSyncRun,
    channels_synced: int,
    videos_synced: int,
    metrics_synced: int,
    account_metrics_synced: int,
    summary: dict[str, object],
    skipped: bool = False,
) -> AnalyticsSyncRun:
    run.status = (
        AnalyticsSyncStatus.SKIPPED.value
        if skipped
        else AnalyticsSyncStatus.SUCCEEDED.value
    )
    run.channels_synced = channels_synced
    run.videos_synced = videos_synced
    run.metrics_synced = metrics_synced
    run.account_metrics_synced = account_metrics_synced
    run.summary = summary
    run.completed_at = _utc_now()
    run.last_error_code = None
    run.last_error_message = None
    _event(
        db,
        run=run,
        event_type=(
            ActivityType.ANALYTICS_SYNC_SKIPPED
            if skipped
            else ActivityType.ANALYTICS_SYNC_SUCCEEDED
        ),
    )
    _commit(db, "Unable to complete analytics synchronization")
    return run


def mark_failed(
    db: Session,
    *,
    run: AnalyticsSyncRun,
    error_code: str,
    safe_message: str,
    retryable: bool,
) -> AnalyticsSyncRun:
    run.status = (
        AnalyticsSyncStatus.RETRY_SCHEDULED.value
        if retryable
        else AnalyticsSyncStatus.FAILED.value
    )
    run.last_error_code = error_code.strip()[:100] or "analytics_sync_error"
    run.last_error_message = (
        safe_message.strip()[:500] or "Analytics synchronization failed"
    )
    run.completed_at = None if retryable else _utc_now()
    _event(
        db,
        run=run,
        event_type=(
            ActivityType.ANALYTICS_SYNC_RETRY_SCHEDULED
            if retryable
            else ActivityType.ANALYTICS_SYNC_FAILED
        ),
    )
    _commit(db, "Unable to record analytics synchronization failure")
    return run
