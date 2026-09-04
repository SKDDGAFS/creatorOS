from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai import AIError, AIRetryableProviderError
from app.models.ai import AICapabilityTier
from app.models.durable_job import DurableJob
from app.schemas.research import ResearchOutput
from app.services import ai_service, research_service
from app.services.errors import ServiceError

from .runner import JobRegistry, PermanentJobError, RetryableJobError


@dataclass(frozen=True)
class ResearchWorkerDependencies:
    provider_builder: ai_service.ProviderBuilder = ai_service.build_provider


def _safe_failure(error: Exception) -> tuple[str, str, bool]:
    if isinstance(error, AIRetryableProviderError):
        return error.code[:100], error.safe_message[:500], True
    if isinstance(error, AIError):
        return error.code[:100], error.safe_message[:500], False
    if isinstance(error, ServiceError):
        return "research_output_invalid", "Research output is invalid", False
    return "research_run_failed", "Research run failed unexpectedly", True


def _handler(db: Session, *, dependencies: ResearchWorkerDependencies):
    def handle(job: DurableJob) -> dict[str, object]:
        run = research_service.get_run_for_job(db, job=job)
        research_service.mark_running(db, run=run)
        try:
            generation = ai_service.generate_structured(
                db,
                workspace_id=run.workspace_id,
                user_id=run.requested_by_user_id,
                prompt_name=research_service.RESEARCH_PROMPT_NAME,
                prompt_version_id=run.prompt_version_id,
                variables=research_service.prompt_variables(db, run=run),
                output_type=ResearchOutput,
                idempotency_key=f"research-run:{run.id}:attempt:{job.attempts}",
                capability_tier=AICapabilityTier.STANDARD,
                provider_builder=dependencies.provider_builder,
            )
            output = ResearchOutput.model_validate(generation.output)
            research_service.mark_succeeded(
                db,
                run=run,
                invocation=generation.invocation,
                output=output,
            )
            return {
                "research_run_id": str(run.id),
                "ai_invocation_id": str(generation.invocation.id),
                "status": run.status,
            }
        except Exception as exc:
            code, message, retryable = _safe_failure(exc)
            should_retry = retryable and job.attempts < job.max_attempts
            research_service.mark_failed(
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


def register_research_jobs(
    registry: JobRegistry,
    db: Session,
    *,
    dependencies: ResearchWorkerDependencies | None = None,
) -> None:
    registry.register_context_handler(
        research_service.RESEARCH_JOB_TYPE,
        _handler(db, dependencies=dependencies or ResearchWorkerDependencies()),
    )
