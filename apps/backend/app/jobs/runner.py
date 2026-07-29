from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.models.durable_job import DurableJob
from app.services import durable_job_service
from app.services.errors import InvalidRequestError

type JobHandler = Callable[
    [dict[str, Any]],
    dict[str, Any] | None,
]


class RetryableJobError(Exception):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class PermanentJobError(Exception):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class JobRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        normalized = durable_job_service.normalize_job_type(job_type)
        if normalized in self._handlers:
            raise InvalidRequestError(
                f"A handler is already registered for {normalized}"
            )
        self._handlers[normalized] = handler

    def get(self, job_type: str) -> JobHandler | None:
        return self._handlers.get(job_type)

    @property
    def job_types(self) -> set[str]:
        return set(self._handlers)


def run_once(
    db: Session,
    *,
    registry: JobRegistry,
    worker_id: str,
    lease_seconds: int = 300,
) -> DurableJob | None:
    if not registry.job_types:
        return None
    job = durable_job_service.claim_next_job(
        db,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        job_types=registry.job_types,
    )
    if job is None:
        return None
    handler = registry.get(job.job_type)
    if handler is None:
        return durable_job_service.fail_job(
            db,
            workspace_id=job.workspace_id,
            job_id=job.id,
            worker_id=worker_id,
            error_code="handler_not_registered",
            safe_message="No handler is registered for this job type",
            retryable=False,
        )
    try:
        result = handler(job.payload)
    except RetryableJobError as exc:
        return durable_job_service.fail_job(
            db,
            workspace_id=job.workspace_id,
            job_id=job.id,
            worker_id=worker_id,
            error_code=exc.code,
            safe_message=exc.safe_message,
            retryable=True,
        )
    except PermanentJobError as exc:
        return durable_job_service.fail_job(
            db,
            workspace_id=job.workspace_id,
            job_id=job.id,
            worker_id=worker_id,
            error_code=exc.code,
            safe_message=exc.safe_message,
            retryable=False,
        )
    except Exception:
        return durable_job_service.fail_job(
            db,
            workspace_id=job.workspace_id,
            job_id=job.id,
            worker_id=worker_id,
            error_code="unhandled_worker_error",
            safe_message="Job handler failed unexpectedly",
            retryable=True,
        )
    return durable_job_service.complete_job(
        db,
        workspace_id=job.workspace_id,
        job_id=job.id,
        worker_id=worker_id,
        result=result,
    )
