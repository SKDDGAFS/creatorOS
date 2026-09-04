from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents import AgentRegistry, default_agent_registry
from app.ai import AIError, AIRetryableProviderError
from app.models.agent_run import AgentType
from app.models.durable_job import DurableJob
from app.schemas.agent_run import AgentRunOutput
from app.services import agent_run_service, ai_service
from app.services.errors import ServiceError

from .runner import JobRegistry, PermanentJobError, RetryableJobError


@dataclass(frozen=True)
class AgentWorkerDependencies:
    provider_builder: ai_service.ProviderBuilder = ai_service.build_provider
    agent_registry: AgentRegistry | None = None


def _safe_failure(error: Exception) -> tuple[str, str, bool]:
    if isinstance(error, AIRetryableProviderError):
        return error.code[:100], error.safe_message[:500], True
    if isinstance(error, AIError):
        return error.code[:100], error.safe_message[:500], False
    if isinstance(error, ServiceError):
        return "agent_request_invalid", "Agent run request is invalid", False
    return "agent_run_failed", "Agent run failed unexpectedly", True


def _handler(
    db: Session,
    *,
    dependencies: AgentWorkerDependencies,
):
    registry = dependencies.agent_registry or default_agent_registry()

    def handle(job: DurableJob) -> dict[str, object]:
        run = agent_run_service.get_run_for_job(db, job=job)
        agent_run_service.mark_running(db, run=run)
        try:
            agent_type = AgentType(run.agent_type)
            capability = registry.get(agent_type)
            generation = ai_service.generate_structured(
                db,
                workspace_id=run.workspace_id,
                user_id=run.requested_by_user_id,
                prompt_name=capability.prompt_name,
                prompt_version_id=run.prompt_version_id,
                variables=agent_run_service.prompt_variables(run),
                output_type=AgentRunOutput,
                idempotency_key=f"agent-run:{run.id}:attempt:{job.attempts}",
                capability_tier=capability.capability_tier,
                provider_builder=dependencies.provider_builder,
            )
            output = AgentRunOutput.model_validate(generation.output)
            agent_run_service.mark_succeeded(
                db,
                run=run,
                invocation=generation.invocation,
                output=output,
            )
            return {
                "agent_run_id": str(run.id),
                "ai_invocation_id": str(generation.invocation.id),
                "status": run.status,
            }
        except Exception as exc:
            code, message, retryable = _safe_failure(exc)
            should_retry = retryable and job.attempts < job.max_attempts
            agent_run_service.mark_failed(
                db,
                run=run,
                error_code=code,
                safe_message=message,
                retryable=should_retry,
            )
            if should_retry:
                raise RetryableJobError(code, message) from exc
            raise PermanentJobError(code, message) from exc

    return handle


def register_agent_jobs(
    registry: JobRegistry,
    db: Session,
    *,
    dependencies: AgentWorkerDependencies | None = None,
) -> None:
    registry.register_context_handler(
        agent_run_service.AGENT_RUN_JOB_TYPE,
        _handler(db, dependencies=dependencies or AgentWorkerDependencies()),
    )
