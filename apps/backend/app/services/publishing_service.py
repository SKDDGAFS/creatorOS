from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_token
from app.models.publishing import (
    ActivityEvent,
    ActivityType,
    ApprovalRequest,
    ApprovalStatus,
    PublishingJob,
    PublishingState,
    PublishingTransition,
)
from app.schemas.publishing import PublishingJobCreate
from app.services import video_service
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
)

ALLOWED_TRANSITIONS: dict[PublishingState, frozenset[PublishingState]] = {
    PublishingState.DRAFT: frozenset(
        {PublishingState.PREPARING, PublishingState.CANCELLED}
    ),
    PublishingState.PREPARING: frozenset(
        {
            PublishingState.AWAITING_APPROVAL,
            PublishingState.FAILED,
            PublishingState.CANCELLED,
        }
    ),
    PublishingState.AWAITING_APPROVAL: frozenset(
        {
            PublishingState.APPROVED,
            PublishingState.REJECTED,
            PublishingState.CANCELLED,
        }
    ),
    PublishingState.APPROVED: frozenset(
        {
            PublishingState.SCHEDULED,
            PublishingState.PUBLISHING,
            PublishingState.CANCELLED,
        }
    ),
    PublishingState.SCHEDULED: frozenset(
        {PublishingState.PUBLISHING, PublishingState.CANCELLED}
    ),
    PublishingState.PUBLISHING: frozenset(
        {PublishingState.PUBLISHED, PublishingState.FAILED}
    ),
    PublishingState.REJECTED: frozenset(
        {PublishingState.PREPARING, PublishingState.CANCELLED}
    ),
    PublishingState.FAILED: frozenset(
        {PublishingState.PREPARING, PublishingState.CANCELLED}
    ),
    PublishingState.PUBLISHED: frozenset(),
    PublishingState.CANCELLED: frozenset(),
}

JOB_LOAD_OPTIONS = (
    selectinload(PublishingJob.approvals),
    selectinload(PublishingJob.transitions),
)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(message) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(message) from exc


def _activity(
    db: Session,
    job: PublishingJob,
    event_type: ActivityType,
    *,
    actor_user_id: UUID | None,
    data: dict[str, str | int | None] | None = None,
) -> None:
    db.add(
        ActivityEvent(
            workspace_id=job.workspace_id,
            actor_user_id=actor_user_id,
            publishing_job=job,
            event_type=event_type.value,
            event_data=data or {},
        )
    )


def _transition(
    db: Session,
    job: PublishingJob,
    target: PublishingState,
    *,
    actor_user_id: UUID | None,
    reason: str | None = None,
) -> bool:
    current = PublishingState(job.status)
    safe_reason = reason[:500] if reason is not None else None
    if current == target:
        return False
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ConflictError(
            f"Publishing job cannot transition from {current.value} "
            f"to {target.value}"
        )
    job.status = target.value
    job.transitions.append(
        PublishingTransition(
            actor_user_id=actor_user_id,
            from_state=current.value,
            to_state=target.value,
            reason=safe_reason,
        )
    )
    _activity(
        db,
        job,
        ActivityType.STATE_CHANGED,
        actor_user_id=actor_user_id,
        data={
            "from_state": current.value,
            "to_state": target.value,
            "reason": safe_reason,
        },
    )
    return True


def create_job(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    payload: PublishingJobCreate,
    idempotency_key: str,
) -> tuple[PublishingJob, bool]:
    video_service.get_video(
        db,
        payload.video_id,
        workspace_id=workspace_id,
    )
    key_hash = hash_token(idempotency_key)
    existing = db.scalar(
        select(PublishingJob)
        .options(*JOB_LOAD_OPTIONS)
        .where(
            PublishingJob.workspace_id == workspace_id,
            PublishingJob.idempotency_key_hash == key_hash,
        )
    )
    if existing is not None:
        if existing.video_id != payload.video_id:
            raise ConflictError(
                "Idempotency key was already used for another publishing job"
            )
        return existing, False

    job = PublishingJob(
        workspace_id=workspace_id,
        video_id=payload.video_id,
        created_by_user_id=user_id,
        idempotency_key_hash=key_hash,
    )
    job.transitions.append(
        PublishingTransition(
            actor_user_id=user_id,
            from_state=None,
            to_state=PublishingState.DRAFT.value,
            reason="Publishing job created",
        )
    )
    db.add(job)
    _activity(
        db,
        job,
        ActivityType.JOB_CREATED,
        actor_user_id=user_id,
        data={"video_id": str(payload.video_id)},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        concurrent = db.scalar(
            select(PublishingJob)
            .options(*JOB_LOAD_OPTIONS)
            .where(
                PublishingJob.workspace_id == workspace_id,
                PublishingJob.idempotency_key_hash == key_hash,
            )
        )
        if concurrent is not None and concurrent.video_id == payload.video_id:
            return concurrent, False
        raise ConflictError("Unable to create publishing job") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to create publishing job") from exc
    db.refresh(job)
    return job, True


def get_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    lock: bool = False,
) -> PublishingJob:
    statement = (
        select(PublishingJob)
        .options(*JOB_LOAD_OPTIONS)
        .where(
            PublishingJob.id == job_id,
            PublishingJob.workspace_id == workspace_id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    job = db.scalar(statement)
    if job is None:
        raise ResourceNotFoundError("Publishing job not found")
    return job


def list_jobs(
    db: Session,
    *,
    workspace_id: UUID,
    status: PublishingState | None,
    limit: int,
    offset: int,
) -> list[PublishingJob]:
    statement: Select[tuple[PublishingJob]] = (
        select(PublishingJob)
        .options(*JOB_LOAD_OPTIONS)
        .where(PublishingJob.workspace_id == workspace_id)
    )
    if status is not None:
        statement = statement.where(PublishingJob.status == status.value)
    statement = (
        statement.order_by(
            PublishingJob.created_at.desc(),
            PublishingJob.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def prepare_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    actor_user_id: UUID,
) -> PublishingJob:
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    changed = _transition(
        db,
        job,
        PublishingState.PREPARING,
        actor_user_id=actor_user_id,
        reason="Content preparation started",
    )
    if changed:
        job.failed_at = None
        job.approved_at = None
        job.scheduled_for = None
        job.last_error_code = None
        job.last_error_message = None
        _commit(db, "Unable to prepare publishing job")
    return job


def request_approval(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    actor_user_id: UUID,
    note: str | None,
) -> PublishingJob:
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    if job.status == PublishingState.AWAITING_APPROVAL.value and any(
        approval.status == ApprovalStatus.PENDING.value
        for approval in job.approvals
    ):
        return job
    _transition(
        db,
        job,
        PublishingState.AWAITING_APPROVAL,
        actor_user_id=actor_user_id,
        reason=note or "Human approval requested",
    )
    approval = ApprovalRequest(
        requested_by_user_id=actor_user_id,
        sequence=len(job.approvals) + 1,
        request_note=note,
    )
    job.approvals.append(approval)
    _activity(
        db,
        job,
        ActivityType.APPROVAL_REQUESTED,
        actor_user_id=actor_user_id,
        data={"approval_sequence": approval.sequence},
    )
    _commit(db, "Unable to request publishing approval")
    return job


def _get_approval(
    db: Session,
    *,
    workspace_id: UUID,
    approval_id: UUID,
) -> tuple[PublishingJob, ApprovalRequest]:
    approval = db.scalar(
        select(ApprovalRequest)
        .join(PublishingJob)
        .where(
            ApprovalRequest.id == approval_id,
            PublishingJob.workspace_id == workspace_id,
        )
    )
    if approval is None:
        raise ResourceNotFoundError("Approval request not found")
    job = get_job(
        db,
        workspace_id=workspace_id,
        job_id=approval.publishing_job_id,
        lock=True,
    )
    approval = next(item for item in job.approvals if item.id == approval_id)
    return job, approval


def decide_approval(
    db: Session,
    *,
    workspace_id: UUID,
    approval_id: UUID,
    actor_user_id: UUID,
    approve: bool,
    note: str | None,
) -> PublishingJob:
    job, approval = _get_approval(
        db,
        workspace_id=workspace_id,
        approval_id=approval_id,
    )
    target_approval_status = (
        ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    )
    target_job_status = (
        PublishingState.APPROVED if approve else PublishingState.REJECTED
    )
    if approval.status == target_approval_status.value:
        return job
    if approval.status != ApprovalStatus.PENDING.value:
        raise ConflictError("Approval request has already been decided")
    if job.status != PublishingState.AWAITING_APPROVAL.value:
        raise ConflictError("Publishing job is not awaiting approval")

    now = datetime.now(UTC)
    approval.status = target_approval_status.value
    approval.decided_by_user_id = actor_user_id
    approval.decision_note = note
    approval.decided_at = now
    _transition(
        db,
        job,
        target_job_status,
        actor_user_id=actor_user_id,
        reason=note,
    )
    event_type = (
        ActivityType.APPROVAL_APPROVED
        if approve
        else ActivityType.APPROVAL_REJECTED
    )
    if approve:
        job.approved_at = now
    _activity(
        db,
        job,
        event_type,
        actor_user_id=actor_user_id,
        data={"approval_id": str(approval.id)},
    )
    _commit(db, "Unable to record approval decision")
    return job


def schedule_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    actor_user_id: UUID,
    scheduled_for: datetime,
) -> PublishingJob:
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    normalized_schedule = _as_utc(scheduled_for)
    if normalized_schedule <= datetime.now(UTC):
        raise InvalidRequestError("scheduled_for must be in the future")
    if job.status == PublishingState.SCHEDULED.value:
        if job.scheduled_for and _as_utc(job.scheduled_for) == normalized_schedule:
            return job
        raise ConflictError("Publishing job is already scheduled")
    if not any(
        approval.status == ApprovalStatus.APPROVED.value
        for approval in job.approvals
    ):
        raise ConflictError("Publishing requires human approval")
    _transition(
        db,
        job,
        PublishingState.SCHEDULED,
        actor_user_id=actor_user_id,
        reason="Publishing scheduled",
    )
    job.scheduled_for = normalized_schedule
    _activity(
        db,
        job,
        ActivityType.SCHEDULED,
        actor_user_id=actor_user_id,
        data={"scheduled_for": normalized_schedule.isoformat()},
    )
    _commit(db, "Unable to schedule publishing job")
    return job


def cancel_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> PublishingJob:
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    if job.status == PublishingState.CANCELLED.value:
        return job
    _transition(
        db,
        job,
        PublishingState.CANCELLED,
        actor_user_id=actor_user_id,
        reason=reason,
    )
    job.cancelled_at = datetime.now(UTC)
    for approval in job.approvals:
        if approval.status == ApprovalStatus.PENDING.value:
            approval.status = ApprovalStatus.CANCELLED.value
            approval.decided_by_user_id = actor_user_id
            approval.decided_at = job.cancelled_at
    _activity(
        db,
        job,
        ActivityType.CANCELLED,
        actor_user_id=actor_user_id,
        data={"reason": reason},
    )
    _commit(db, "Unable to cancel publishing job")
    return job


def start_publishing(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
) -> PublishingJob:
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    if not any(
        approval.status == ApprovalStatus.APPROVED.value
        for approval in job.approvals
    ):
        raise ConflictError("Publishing requires human approval")
    changed = _transition(
        db,
        job,
        PublishingState.PUBLISHING,
        actor_user_id=None,
        reason="Publishing worker started",
    )
    if changed:
        _commit(db, "Unable to start publishing job")
    return job


def mark_published(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
) -> PublishingJob:
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    changed = _transition(
        db,
        job,
        PublishingState.PUBLISHED,
        actor_user_id=None,
        reason="Platform publish confirmed",
    )
    if changed:
        job.published_at = datetime.now(UTC)
        _activity(
            db,
            job,
            ActivityType.PUBLISHED,
            actor_user_id=None,
        )
        _commit(db, "Unable to complete publishing job")
    return job


def fail_job(
    db: Session,
    *,
    workspace_id: UUID,
    job_id: UUID,
    error_code: str,
    safe_message: str,
) -> PublishingJob:
    job = get_job(db, workspace_id=workspace_id, job_id=job_id, lock=True)
    changed = _transition(
        db,
        job,
        PublishingState.FAILED,
        actor_user_id=None,
        reason=safe_message,
    )
    if changed:
        job.failed_at = datetime.now(UTC)
        job.last_error_code = error_code[:100]
        job.last_error_message = safe_message[:500]
        _activity(
            db,
            job,
            ActivityType.FAILED,
            actor_user_id=None,
            data={"error_code": job.last_error_code},
        )
        _commit(db, "Unable to fail publishing job safely")
    return job


def list_pending_approvals(
    db: Session,
    *,
    workspace_id: UUID,
    limit: int,
    offset: int,
) -> list[ApprovalRequest]:
    statement = (
        select(ApprovalRequest)
        .join(PublishingJob)
        .where(
            PublishingJob.workspace_id == workspace_id,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
        .order_by(
            ApprovalRequest.requested_at.asc(),
            ApprovalRequest.id.asc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def list_activity(
    db: Session,
    *,
    workspace_id: UUID,
    limit: int,
    offset: int,
) -> list[ActivityEvent]:
    statement = (
        select(ActivityEvent)
        .where(ActivityEvent.workspace_id == workspace_id)
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())
