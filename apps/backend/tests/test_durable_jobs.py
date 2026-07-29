from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.jobs import JobRegistry, run_once
from app.services import durable_job_service
from app.services.errors import ConflictError
from tests.test_core_apis import headers, register


def identifiers(auth: dict) -> tuple[UUID, UUID]:
    return UUID(auth["workspace_id"]), UUID(auth["user"]["id"])


def enqueue(
    db: Session,
    auth: dict,
    *,
    job_type: str = "test.work",
    payload: dict | None = None,
    priority: int = 50,
    scheduled_for: datetime | None = None,
    max_attempts: int = 3,
    key: str | None = None,
):
    workspace_id, user_id = identifiers(auth)
    return durable_job_service.enqueue_job(
        db,
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        job_type=job_type,
        payload=payload or {"value": 1},
        priority=priority,
        scheduled_for=scheduled_for,
        max_attempts=max_attempts,
        idempotency_key=key,
    )


def test_enqueue_is_idempotent_and_validated(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "durable-idempotency@example.com")
    first, created = enqueue(
        db_session,
        auth,
        payload={"nested": {"value": 1}},
        key="job-idempotency-key",
    )
    repeated, repeated_created = enqueue(
        db_session,
        auth,
        payload={"nested": {"value": 1}},
        key="job-idempotency-key",
    )

    assert created
    assert not repeated_created
    assert repeated.id == first.id
    assert first.idempotency_key_hash != "job-idempotency-key"
    with pytest.raises(ConflictError):
        enqueue(
            db_session,
            auth,
            payload={"nested": {"value": 2}},
            key="job-idempotency-key",
        )


def test_claim_respects_schedule_priority_and_worker_lease(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "durable-claim@example.com")
    workspace_id, _ = identifiers(auth)
    now = datetime.now(UTC)
    low, _ = enqueue(
        db_session,
        auth,
        priority=10,
        scheduled_for=now - timedelta(minutes=1),
        key="low-priority",
    )
    high, _ = enqueue(
        db_session,
        auth,
        priority=90,
        scheduled_for=now - timedelta(minutes=1),
        key="high-priority",
    )
    enqueue(
        db_session,
        auth,
        priority=100,
        scheduled_for=now + timedelta(hours=1),
        key="future-job",
    )

    claimed = durable_job_service.claim_next_job(
        db_session,
        worker_id="worker-a",
        lease_seconds=60,
        now=now,
    )
    assert claimed is not None
    assert claimed.id == high.id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.attempt_history[0].worker_id == "worker-a"

    with pytest.raises(ConflictError):
        durable_job_service.complete_job(
            db_session,
            workspace_id=workspace_id,
            job_id=claimed.id,
            worker_id="worker-b",
            now=now + timedelta(seconds=1),
        )
    db_session.rollback()
    completed = durable_job_service.complete_job(
        db_session,
        workspace_id=workspace_id,
        job_id=claimed.id,
        worker_id="worker-a",
        result={"ok": True},
        now=now + timedelta(seconds=1),
    )
    assert completed.status == "succeeded"
    assert completed.result == {"ok": True}

    next_job = durable_job_service.claim_next_job(
        db_session,
        worker_id="worker-a",
        now=now + timedelta(seconds=2),
    )
    assert next_job is not None
    assert next_job.id == low.id


def test_retry_backoff_and_maximum_attempts(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "durable-retry@example.com")
    workspace_id, _ = identifiers(auth)
    now = datetime.now(UTC)
    job, _ = enqueue(
        db_session,
        auth,
        max_attempts=2,
        scheduled_for=now - timedelta(seconds=1),
    )
    claimed = durable_job_service.claim_next_job(
        db_session,
        worker_id="retry-worker",
        now=now,
    )
    assert claimed is not None
    retried = durable_job_service.fail_job(
        db_session,
        workspace_id=workspace_id,
        job_id=job.id,
        worker_id="retry-worker",
        error_code="temporary",
        safe_message="Temporary provider failure",
        retryable=True,
        now=now + timedelta(seconds=1),
    )
    expected_retry = now + timedelta(seconds=31)
    assert retried.status == "retry_scheduled"
    assert retried.scheduled_for == expected_retry
    assert durable_job_service.claim_next_job(
        db_session,
        worker_id="retry-worker",
        now=expected_retry - timedelta(seconds=1),
    ) is None

    claimed_again = durable_job_service.claim_next_job(
        db_session,
        worker_id="retry-worker",
        now=expected_retry,
    )
    assert claimed_again is not None
    exhausted = durable_job_service.fail_job(
        db_session,
        workspace_id=workspace_id,
        job_id=job.id,
        worker_id="retry-worker",
        error_code="temporary",
        safe_message="Still unavailable",
        retryable=True,
        now=expected_retry + timedelta(seconds=1),
    )
    assert exhausted.status == "failed"
    assert exhausted.failed_at is not None
    assert [attempt.status for attempt in exhausted.attempt_history] == [
        "retry_scheduled",
        "failed",
    ]


def test_heartbeat_stale_recovery_and_final_failure(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "durable-stale@example.com")
    workspace_id, _ = identifiers(auth)
    now = datetime.now(UTC)
    job, _ = enqueue(
        db_session,
        auth,
        max_attempts=1,
        scheduled_for=now - timedelta(seconds=1),
    )
    claimed = durable_job_service.claim_next_job(
        db_session,
        worker_id="stale-worker",
        lease_seconds=10,
        now=now,
    )
    assert claimed is not None
    heartbeat = durable_job_service.heartbeat_job(
        db_session,
        workspace_id=workspace_id,
        job_id=job.id,
        worker_id="stale-worker",
        lease_seconds=20,
        now=now + timedelta(seconds=5),
    )
    assert heartbeat.lock_expires_at == now + timedelta(seconds=25)
    assert durable_job_service.recover_stale_jobs(
        db_session,
        now=now + timedelta(seconds=24),
    ) == []

    recovered = durable_job_service.recover_stale_jobs(
        db_session,
        now=now + timedelta(seconds=26),
    )
    assert len(recovered) == 1
    assert recovered[0].status == "failed"
    assert recovered[0].last_error_code == "stale_lock"
    assert recovered[0].attempt_history[0].status == "abandoned"


def test_cancellation_invalidates_an_active_worker(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "durable-cancel@example.com")
    workspace_id, _ = identifiers(auth)
    now = datetime.now(UTC)
    job, _ = enqueue(
        db_session,
        auth,
        scheduled_for=now - timedelta(seconds=1),
    )
    durable_job_service.claim_next_job(
        db_session,
        worker_id="cancelled-worker",
        now=now,
    )
    cancelled = durable_job_service.cancel_job(
        db_session,
        workspace_id=workspace_id,
        job_id=job.id,
        now=now + timedelta(seconds=1),
    )
    assert cancelled.status == "cancelled"
    assert cancelled.lock_owner is None
    assert cancelled.attempt_history[0].status == "cancelled"
    with pytest.raises(ConflictError):
        durable_job_service.complete_job(
            db_session,
            workspace_id=workspace_id,
            job_id=job.id,
            worker_id="cancelled-worker",
            now=now + timedelta(seconds=2),
        )


def test_runner_handles_success_and_redacts_unexpected_errors(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "durable-runner@example.com")
    enqueue(
        db_session,
        auth,
        job_type="test.success",
        payload={"value": 4},
    )
    registry = JobRegistry()
    registry.register(
        "test.success",
        lambda payload: {"doubled": payload["value"] * 2},
    )
    succeeded = run_once(
        db_session,
        registry=registry,
        worker_id="runner-1",
    )
    assert succeeded is not None
    assert succeeded.status == "succeeded"
    assert succeeded.result == {"doubled": 8}

    enqueue(
        db_session,
        auth,
        job_type="test.retry",
        payload={"secret": "must-not-appear"},
    )
    retry_registry = JobRegistry()

    def fail_safely(_payload: dict) -> None:
        raise RuntimeError("sensitive provider detail")

    retry_registry.register("test.retry", fail_safely)
    retried = run_once(
        db_session,
        registry=retry_registry,
        worker_id="runner-2",
    )
    assert retried is not None
    assert retried.status == "retry_scheduled"
    assert retried.last_error_code == "unhandled_worker_error"
    assert retried.last_error_message == "Job handler failed unexpectedly"
    assert "sensitive" not in retried.last_error_message


def test_job_observability_authorization_and_admin_cancellation(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = register(client, "durable-api-owner@example.com")
    job, _ = enqueue(db_session, owner, job_type="analytics.sync")
    listed = client.get("/api/jobs", headers=headers(owner))
    fetched = client.get(f"/api/jobs/{job.id}", headers=headers(owner))

    assert listed.status_code == 200
    assert listed.json()[0]["id"] == str(job.id)
    assert fetched.status_code == 200
    assert "idempotency_key_hash" not in fetched.json()

    client.cookies.clear()
    other = register(client, "durable-api-other@example.com")
    hidden = client.get(f"/api/jobs/{job.id}", headers=headers(other))
    assert hidden.status_code == 404

    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={
            "email": "durable-api-owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    owner["csrf"] = login.json()["csrf_token"]
    cancelled = client.post(
        f"/api/jobs/{job.id}/cancel",
        headers=headers(owner, write=True),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
