import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents import AgentRegistry, default_agent_registry
from app.models.agent_run import AgentRun, AgentRunStatus, AgentType
from app.models.ai import AIInvocation
from app.models.channel import Channel
from app.models.durable_job import DurableJob
from app.models.platform_integration import PlatformConnection
from app.models.publishing import ActivityEvent, ActivityType
from app.models.video import Video
from app.schemas.agent_run import (
    AgentInputKind,
    AgentInputReference,
    AgentRunCreate,
    AgentRunOutput,
)
from app.services import ai_service, durable_job_service
from app.services.errors import ConflictError, PersistenceError, ResourceNotFoundError

AGENT_RUN_JOB_TYPE = "agent.run"


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
    run: AgentRun,
    event_type: ActivityType,
    actor_user_id: UUID | None = None,
) -> None:
    db.add(
        ActivityEvent(
            workspace_id=run.workspace_id,
            actor_user_id=actor_user_id,
            agent_run_id=run.id,
            event_type=event_type.value,
            event_data={
                "agent_run_id": str(run.id),
                "agent_type": run.agent_type,
                "status": run.status,
            },
        )
    )


def _validate_input_references(
    db: Session,
    *,
    workspace_id: UUID,
    references: tuple[AgentInputReference, ...],
) -> None:
    for reference in references:
        if reference.kind is AgentInputKind.CHANNEL:
            exists = db.scalar(
                select(Channel.id).where(
                    Channel.id == reference.resource_id,
                    Channel.workspace_id == workspace_id,
                )
            )
        elif reference.kind is AgentInputKind.VIDEO:
            exists = db.scalar(
                select(Video.id)
                .join(Channel, Channel.id == Video.channel_id)
                .where(
                    Video.id == reference.resource_id,
                    Channel.workspace_id == workspace_id,
                )
            )
        else:
            exists = db.scalar(
                select(PlatformConnection.id).where(
                    PlatformConnection.id == reference.resource_id,
                    PlatformConnection.workspace_id == workspace_id,
                )
            )
        if exists is None:
            raise ResourceNotFoundError("Agent input reference not found")


def schedule_run(
    db: Session,
    *,
    workspace_id: UUID,
    requested_by_user_id: UUID,
    payload: AgentRunCreate,
    idempotency_key: str,
    registry: AgentRegistry | None = None,
) -> AgentRun:
    resolved_registry = registry or default_agent_registry()
    capability = resolved_registry.get(payload.agent_type)
    _validate_input_references(
        db,
        workspace_id=workspace_id,
        references=payload.input_references,
    )
    prompt = ai_service.get_active_prompt(
        db,
        workspace_id=workspace_id,
        name=capability.prompt_name,
    )
    normalized_inputs = [
        item.model_dump(mode="json") for item in payload.input_references
    ]
    job_payload = {
        "agent_type": payload.agent_type.value,
        "objective": payload.objective,
        "input_references": normalized_inputs,
        "prompt_version_id": str(prompt.id),
    }
    job, _ = durable_job_service.enqueue_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=requested_by_user_id,
        job_type=AGENT_RUN_JOB_TYPE,
        payload=job_payload,
        priority=payload.priority,
        max_attempts=payload.max_attempts,
        idempotency_key=idempotency_key,
    )
    run = db.scalar(select(AgentRun).where(AgentRun.durable_job_id == job.id))
    if run is not None:
        return run
    run = AgentRun(
        id=uuid4(),
        workspace_id=workspace_id,
        requested_by_user_id=requested_by_user_id,
        prompt_version_id=prompt.id,
        durable_job_id=job.id,
        agent_type=payload.agent_type.value,
        objective=payload.objective,
        input_references=normalized_inputs,
        status=AgentRunStatus.QUEUED.value,
    )
    db.add(run)
    _event(
        db,
        run=run,
        event_type=ActivityType.AGENT_RUN_SCHEDULED,
        actor_user_id=requested_by_user_id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(AgentRun).where(AgentRun.durable_job_id == job.id)
        )
        if concurrent is not None:
            return concurrent
        raise ConflictError("Unable to schedule agent run") from None
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to schedule agent run") from exc
    db.refresh(run)
    return run


def get_run(
    db: Session,
    *,
    workspace_id: UUID,
    run_id: UUID,
    lock: bool = False,
) -> AgentRun:
    statement = select(AgentRun).where(
        AgentRun.id == run_id,
        AgentRun.workspace_id == workspace_id,
    )
    if lock:
        statement = statement.with_for_update()
    run = db.scalar(statement)
    if run is None:
        raise ResourceNotFoundError("Agent run not found")
    return run


def get_run_for_job(db: Session, *, job: DurableJob) -> AgentRun:
    run = db.scalar(
        select(AgentRun).where(
            AgentRun.durable_job_id == job.id,
            AgentRun.workspace_id == job.workspace_id,
        )
    )
    if run is None:
        raise ResourceNotFoundError("Agent run not found")
    return run


def list_runs(
    db: Session,
    *,
    workspace_id: UUID,
    agent_type: AgentType | None,
    status: AgentRunStatus | None,
    limit: int,
    offset: int,
) -> list[AgentRun]:
    statement: Select[tuple[AgentRun]] = select(AgentRun).where(
        AgentRun.workspace_id == workspace_id
    )
    if agent_type is not None:
        statement = statement.where(AgentRun.agent_type == agent_type.value)
    if status is not None:
        statement = statement.where(AgentRun.status == status.value)
    return list(
        db.scalars(
            statement.order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )


def mark_running(db: Session, *, run: AgentRun) -> AgentRun:
    run.status = AgentRunStatus.RUNNING.value
    run.started_at = run.started_at or _utc_now()
    run.completed_at = None
    run.last_error_code = None
    run.last_error_message = None
    _event(db, run=run, event_type=ActivityType.AGENT_RUN_STARTED)
    _commit(db, "Unable to start agent run")
    return run


def mark_succeeded(
    db: Session,
    *,
    run: AgentRun,
    invocation: AIInvocation,
    output: AgentRunOutput,
) -> AgentRun:
    run.status = AgentRunStatus.SUCCEEDED.value
    run.ai_invocation_id = invocation.id
    run.model_name = invocation.model_name
    run.estimated_cost_usd = invocation.estimated_cost_usd
    run.output = output.model_dump(mode="json")
    run.confidence = output.overall_confidence
    run.completed_at = _utc_now()
    run.last_error_code = None
    run.last_error_message = None
    _event(db, run=run, event_type=ActivityType.AGENT_RUN_SUCCEEDED)
    _commit(db, "Unable to complete agent run")
    return run


def mark_failed(
    db: Session,
    *,
    run: AgentRun,
    error_code: str,
    safe_message: str,
    retryable: bool,
) -> AgentRun:
    run.status = (
        AgentRunStatus.RETRY_SCHEDULED.value
        if retryable
        else AgentRunStatus.FAILED.value
    )
    run.last_error_code = error_code.strip()[:100] or "agent_run_failed"
    run.last_error_message = safe_message.strip()[:500] or "Agent run failed"
    run.completed_at = None if retryable else _utc_now()
    _event(
        db,
        run=run,
        event_type=(
            ActivityType.AGENT_RUN_RETRY_SCHEDULED
            if retryable
            else ActivityType.AGENT_RUN_FAILED
        ),
    )
    _commit(db, "Unable to record agent run failure")
    return run


def cancel_run(
    db: Session,
    *,
    workspace_id: UUID,
    run_id: UUID,
    actor_user_id: UUID,
) -> AgentRun:
    run = get_run(db, workspace_id=workspace_id, run_id=run_id, lock=True)
    if run.status == AgentRunStatus.CANCELLED.value:
        db.rollback()
        return run
    durable_job_service.cancel_job(
        db,
        workspace_id=workspace_id,
        job_id=run.durable_job_id,
    )
    run = get_run(db, workspace_id=workspace_id, run_id=run_id, lock=True)
    run.status = AgentRunStatus.CANCELLED.value
    run.completed_at = _utc_now()
    _event(
        db,
        run=run,
        event_type=ActivityType.AGENT_RUN_CANCELLED,
        actor_user_id=actor_user_id,
    )
    _commit(db, "Unable to cancel agent run")
    return run


def prompt_variables(run: AgentRun) -> dict[str, str]:
    return {
        "agent_type": run.agent_type,
        "objective": run.objective,
        "input_references": json.dumps(
            run.input_references,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "output_contract": (
            "Return only the requested structured recommendations. "
            "Do not publish, message anyone, or execute commands."
        ),
    }
