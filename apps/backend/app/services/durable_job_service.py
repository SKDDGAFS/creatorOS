import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_token
from app.models.durable_job import (
    DurableJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
)
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
)

JOB_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
TERMINAL_STATUSES = {
    JobStatus.SUCCEEDED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
}
JOB_LOAD_OPTIONS = (selectinload(DurableJob.attempt_history),)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise InvalidRequestError("Job timestamps must include a timezone")
    return value.astimezone(UTC)


def _stored_as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _normalize_payload(value: dict[str, Any]) -> dict[str, Any]:
    try:
        serialized = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        normalized = json.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise InvalidRequestError("Job payload must be a JSON object") from exc
    if not isinstance(normalized, dict):
        raise InvalidRequestError("Job payload must be a JSON object")
    return normalized


def _validate_job_type(job_type: str) -> str:
    normalized = job_type.strip().lower()
    if not JOB_TYPE_PATTERN.fullmatch(normalized):
        raise InvalidRequestError(
            "job_type must start with a letter and contain only "
            "lowercase letters, numbers, dots, underscores, or hyphens"
        )
    return normalized


def _validate_worker(worker_id: str, lease_seconds: int) -> str:
    normalized = worker_id.strip()
    if not normalized or len(normalized) > 255:
        raise InvalidRequestError("worker_id must contain 1 through 255 characters")
    if lease_seconds < 1 or lease_seconds > 3600:
        raise InvalidRequestError("lease_seconds must be between 1 and 3600")
    return normalized


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(message) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(message) from exc


def enqueue_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_type: str,
    payload: dict[str, Any],
    created_by_user_id: UUID | None = None,
    priority: int = 50,
    scheduled_for: datetime | None = None,
    max_attempts: int = 3,
    idempotency_key: str | None = None,
) -> tuple[DurableJob, bool]:
    normalized_type = _validate_job_type(job_type)
    normalized_payload = _normalize_payload(payload)
    if priority < 0 or priority > 100:
        raise InvalidRequestError("priority must be between 0 and 100")
    if max_attempts < 1 or max_attempts > 100:
        raise InvalidRequestError("max_attempts must be between 1 and 100")
    normalized_schedule = (
        _as_utc(scheduled_for) if scheduled_for is not None else _utc_now()
    )
    key_hash = hash_token(idempotency_key) if idempotency_key else None

    if key_hash is not None:
        existing = db.scalar(
            select(DurableJob)
            .options(*JOB_LOAD_OPTIONS)
            .where(
                DurableJob.workspace_id == workspace_id,
                DurableJob.job_type == normalized_type,
                DurableJob.idempotency_key_hash == key_hash,
            )
        )
        if existing is not None:
            if existing.payload != normalized_payload:
                raise ConflictError(
                    "Idempotency key was already used with another payload"
                )
            return existing, False

    job = DurableJob(
        workspace_id=workspace_id,
        created_by_user_id=created_by_user_id,
        job_type=normalized_type,
        payload=normalized_payload,
        priority=priority,
        scheduled_for=normalized_schedule,
        max_attempts=max_attempts,
        idempotency_key_hash=key_hash,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if key_hash is not None:
            concurrent = db.scalar(
                select(DurableJob)
                .options(*JOB_LOAD_OPTIONS)
                .where(
                    DurableJob.workspace_id == workspace_id,
                    DurableJob.job_type == normalized_type,
                    DurableJob.idempotency_key_hash == key_hash,
                )
            )
            if concurrent is not None and concurrent.payload == normalized_payload:
                return concurrent, False
        raise ConflictError("Unable to enqueue durable job") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to enqueue durable job") from exc
    db.refresh(job)
    return job, True


def get_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    lock: bool = False,
) -> DurableJob:
    statement = (
        select(DurableJob)
        .options(*JOB_LOAD_OPTIONS)
        .where(
            DurableJob.id == job_id,
            DurableJob.workspace_id == workspace_id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    job = db.scalar(statement)
    if job is None:
        raise ResourceNotFoundError("Durable job not found")
    return job


def list_jobs(
    db: Session,
    *,
    workspace_id: UUID,
    status: JobStatus | None,
    job_type: str | None,
    limit: int,
    offset: int,
) -> list[DurableJob]:
    statement: Select[tuple[DurableJob]] = (
        select(DurableJob)
        .options(*JOB_LOAD_OPTIONS)
        .where(DurableJob.workspace_id == workspace_id)
    )
    if status is not None:
        statement = statement.where(DurableJob.status == status.value)
    if job_type is not None:
        statement = statement.where(
            DurableJob.job_type == _validate_job_type(job_type)
        )
    statement = (
        statement.order_by(DurableJob.created_at.desc(), DurableJob.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def claim_next_job(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = 300,
    job_types: set[str] | None = None,
    now: datetime | None = None,
) -> DurableJob | None:
    normalized_worker = _validate_worker(worker_id, lease_seconds)
    claimed_at = _as_utc(now) if now is not None else _utc_now()
    normalized_types = (
        {_validate_job_type(job_type) for job_type in job_types}
        if job_types
        else None
    )
    statement = select(DurableJob).where(
        DurableJob.status.in_(
            [
                JobStatus.PENDING.value,
                JobStatus.RETRY_SCHEDULED.value,
            ]
        ),
        DurableJob.scheduled_for <= claimed_at,
    )
    if normalized_types is not None:
        statement = statement.where(DurableJob.job_type.in_(normalized_types))
    statement = (
        statement.order_by(
            DurableJob.priority.desc(),
            DurableJob.scheduled_for.asc(),
            DurableJob.created_at.asc(),
            DurableJob.id.asc(),
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.scalar(statement)
    if job is None:
        db.rollback()
        return None

    job.status = JobStatus.RUNNING.value
    job.attempts += 1
    job.lock_owner = normalized_worker
    job.lock_expires_at = claimed_at + timedelta(seconds=lease_seconds)
    job.started_at = job.started_at or claimed_at
    job.completed_at = None
    job.failed_at = None
    job.attempt_history.append(
        JobAttempt(
            attempt_number=job.attempts,
            worker_id=normalized_worker,
            status=JobAttemptStatus.RUNNING.value,
            started_at=claimed_at,
        )
    )
    _commit(db, "Unable to claim durable job")
    return job


def _require_lease(
    job: DurableJob,
    *,
    worker_id: str,
    now: datetime,
) -> JobAttempt:
    if job.status != JobStatus.RUNNING.value:
        raise ConflictError("Durable job is not running")
    if job.lock_owner != worker_id:
        raise ConflictError("Durable job lease is owned by another worker")
    if job.lock_expires_at is None or _stored_as_utc(job.lock_expires_at) <= now:
        raise ConflictError("Durable job lease has expired")
    for attempt in reversed(job.attempt_history):
        if (
            attempt.attempt_number == job.attempts
            and attempt.status == JobAttemptStatus.RUNNING.value
        ):
            return attempt
    raise ConflictError("Durable job has no active attempt")


def heartbeat_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    worker_id: str,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> DurableJob:
    normalized_worker = _validate_worker(worker_id, lease_seconds)
    heartbeat_at = _as_utc(now) if now is not None else _utc_now()
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    try:
        _require_lease(job, worker_id=normalized_worker, now=heartbeat_at)
    except ConflictError:
        db.rollback()
        raise
    job.lock_expires_at = heartbeat_at + timedelta(seconds=lease_seconds)
    _commit(db, "Unable to extend durable job lease")
    return job


def complete_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    worker_id: str,
    result: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> DurableJob:
    normalized_worker = _validate_worker(worker_id, 300)
    completed_at = _as_utc(now) if now is not None else _utc_now()
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    try:
        attempt = _require_lease(
            job,
            worker_id=normalized_worker,
            now=completed_at,
        )
    except ConflictError:
        db.rollback()
        raise
    job.result = _normalize_payload(result) if result is not None else None
    job.status = JobStatus.SUCCEEDED.value
    job.completed_at = completed_at
    job.lock_owner = None
    job.lock_expires_at = None
    job.last_error_code = None
    job.last_error_message = None
    attempt.status = JobAttemptStatus.SUCCEEDED.value
    attempt.completed_at = completed_at
    _commit(db, "Unable to complete durable job")
    return job


def retry_delay_seconds(
    attempt_number: int,
    *,
    base_seconds: int = 30,
    maximum_seconds: int = 3600,
) -> int:
    if attempt_number < 1 or base_seconds < 1 or maximum_seconds < 1:
        raise InvalidRequestError("Retry timing values must be positive")
    return min(base_seconds * (2 ** (attempt_number - 1)), maximum_seconds)


def fail_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    worker_id: str,
    error_code: str,
    safe_message: str,
    retryable: bool,
    base_backoff_seconds: int = 30,
    maximum_backoff_seconds: int = 3600,
    now: datetime | None = None,
) -> DurableJob:
    normalized_worker = _validate_worker(worker_id, 300)
    failed_at = _as_utc(now) if now is not None else _utc_now()
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    try:
        attempt = _require_lease(job, worker_id=normalized_worker, now=failed_at)
    except ConflictError:
        db.rollback()
        raise
    code = error_code.strip()[:100] or "job_error"
    message = safe_message.strip()[:500] or "Job execution failed"
    job.last_error_code = code
    job.last_error_message = message
    job.lock_owner = None
    job.lock_expires_at = None
    attempt.completed_at = failed_at
    attempt.error_code = code
    attempt.safe_error_message = message

    if retryable and job.attempts < job.max_attempts:
        delay = retry_delay_seconds(
            job.attempts,
            base_seconds=base_backoff_seconds,
            maximum_seconds=maximum_backoff_seconds,
        )
        job.status = JobStatus.RETRY_SCHEDULED.value
        job.scheduled_for = failed_at + timedelta(seconds=delay)
        attempt.status = JobAttemptStatus.RETRY_SCHEDULED.value
    else:
        job.status = JobStatus.FAILED.value
        job.failed_at = failed_at
        attempt.status = JobAttemptStatus.FAILED.value
    _commit(db, "Unable to record durable job failure")
    return job


def cancel_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    now: datetime | None = None,
) -> DurableJob:
    cancelled_at = _as_utc(now) if now is not None else _utc_now()
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    if job.status == JobStatus.CANCELLED.value:
        return job
    if job.status in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}:
        db.rollback()
        raise ConflictError("Completed durable jobs cannot be cancelled")
    if job.status == JobStatus.RUNNING.value:
        for attempt in reversed(job.attempt_history):
            if attempt.status == JobAttemptStatus.RUNNING.value:
                attempt.status = JobAttemptStatus.CANCELLED.value
                attempt.completed_at = cancelled_at
                break
    job.status = JobStatus.CANCELLED.value
    job.cancelled_at = cancelled_at
    job.lock_owner = None
    job.lock_expires_at = None
    _commit(db, "Unable to cancel durable job")
    return job


def recover_stale_jobs(
    db: Session,
    *,
    limit: int = 100,
    base_backoff_seconds: int = 30,
    maximum_backoff_seconds: int = 3600,
    now: datetime | None = None,
) -> list[DurableJob]:
    if limit < 1 or limit > 1000:
        raise InvalidRequestError("limit must be between 1 and 1000")
    recovered_at = _as_utc(now) if now is not None else _utc_now()
    statement = (
        select(DurableJob)
        .options(*JOB_LOAD_OPTIONS)
        .where(
            DurableJob.status == JobStatus.RUNNING.value,
            DurableJob.lock_expires_at <= recovered_at,
        )
        .order_by(DurableJob.lock_expires_at.asc(), DurableJob.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    jobs = list(db.scalars(statement).all())
    for job in jobs:
        for attempt in reversed(job.attempt_history):
            if attempt.status == JobAttemptStatus.RUNNING.value:
                attempt.status = JobAttemptStatus.ABANDONED.value
                attempt.completed_at = recovered_at
                attempt.error_code = "stale_lock"
                attempt.safe_error_message = "Worker lease expired"
                break
        job.lock_owner = None
        job.lock_expires_at = None
        job.last_error_code = "stale_lock"
        job.last_error_message = "Worker lease expired"
        if job.attempts < job.max_attempts:
            delay = retry_delay_seconds(
                job.attempts,
                base_seconds=base_backoff_seconds,
                maximum_seconds=maximum_backoff_seconds,
            )
            job.status = JobStatus.RETRY_SCHEDULED.value
            job.scheduled_for = recovered_at + timedelta(seconds=delay)
        else:
            job.status = JobStatus.FAILED.value
            job.failed_at = recovered_at
    if jobs:
        _commit(db, "Unable to recover stale durable jobs")
    else:
        db.rollback()
    return jobs
