from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import publishing_service
from tests.test_core_apis import (
    create_channel,
    create_video,
    headers,
    register,
)


def create_job(
    client: TestClient,
    auth: dict,
    video_id: str,
    *,
    key: str = "publish-request-0001",
) -> dict:
    response = client.post(
        "/api/publishing/jobs",
        headers={
            **headers(auth, write=True),
            "Idempotency-Key": key,
        },
        json={"video_id": video_id},
    )
    assert response.status_code == 201
    return response.json()


def create_video_for(
    client: TestClient,
    auth: dict,
    *,
    suffix: str = "1",
) -> dict:
    channel = create_channel(
        client,
        auth,
        platform_channel_id=f"publishing-channel-{suffix}",
    )
    return create_video(
        client,
        auth,
        channel["id"],
        platform_video_id=f"publishing-video-{suffix}",
    )


def prepare_and_request(
    client: TestClient,
    auth: dict,
    job_id: str,
) -> dict:
    prepared = client.post(
        f"/api/publishing/jobs/{job_id}/prepare",
        headers=headers(auth, write=True),
    )
    assert prepared.status_code == 200
    requested = client.post(
        f"/api/publishing/jobs/{job_id}/request-approval",
        headers=headers(auth, write=True),
        json={"note": "Ready for a human review"},
    )
    assert requested.status_code == 200
    return requested.json()


def approve_latest(
    client: TestClient,
    auth: dict,
    job: dict,
) -> dict:
    approval_id = job["approvals"][-1]["id"]
    response = client.post(
        f"/api/publishing/approvals/{approval_id}/approve",
        headers=headers(auth, write=True),
        json={"note": "Approved by a workspace administrator"},
    )
    assert response.status_code == 200
    return response.json()


def test_job_creation_is_idempotent_and_workspace_scoped(
    client: TestClient,
) -> None:
    auth = register(client, "publisher-idempotency@example.com")
    first_video = create_video_for(client, auth)
    second_video = create_video(
        client,
        auth,
        first_video["channel_id"],
        platform_video_id="publishing-video-2",
        title="Second publish candidate",
    )
    created = create_job(client, auth, first_video["id"])
    repeated = client.post(
        "/api/publishing/jobs",
        headers={
            **headers(auth, write=True),
            "Idempotency-Key": "publish-request-0001",
        },
        json={"video_id": first_video["id"]},
    )
    conflicting = client.post(
        "/api/publishing/jobs",
        headers={
            **headers(auth, write=True),
            "Idempotency-Key": "publish-request-0001",
        },
        json={"video_id": second_video["id"]},
    )

    assert repeated.status_code == 200
    assert repeated.json()["id"] == created["id"]
    assert conflicting.status_code == 409

    client.cookies.clear()
    other = register(client, "other-publisher@example.com")
    hidden = client.get(
        f"/api/publishing/jobs/{created['id']}",
        headers=headers(other),
    )
    assert hidden.status_code == 404


def test_human_approval_is_required_before_scheduling(
    client: TestClient,
) -> None:
    auth = register(client, "approval-required@example.com")
    video = create_video_for(client, auth)
    job = create_job(client, auth, video["id"])
    future = datetime.now(UTC) + timedelta(hours=2)

    blocked = client.post(
        f"/api/publishing/jobs/{job['id']}/schedule",
        headers=headers(auth, write=True),
        json={"scheduled_for": future.isoformat()},
    )
    requested = prepare_and_request(client, auth, job["id"])
    duplicate_request = client.post(
        f"/api/publishing/jobs/{job['id']}/request-approval",
        headers=headers(auth, write=True),
        json={"note": "Duplicate request"},
    )
    approved = approve_latest(client, auth, requested)
    scheduled = client.post(
        f"/api/publishing/jobs/{job['id']}/schedule",
        headers=headers(auth, write=True),
        json={"scheduled_for": future.isoformat()},
    )

    assert blocked.status_code == 409
    assert duplicate_request.status_code == 200
    assert len(duplicate_request.json()["approvals"]) == 1
    assert approved["status"] == "approved"
    assert scheduled.status_code == 200
    assert scheduled.json()["status"] == "scheduled"
    assert datetime.fromisoformat(
        scheduled.json()["scheduled_for"].replace("Z", "+00:00")
    ) == future


def test_transitions_and_activity_form_an_audit_trail(
    client: TestClient,
) -> None:
    auth = register(client, "audit-trail@example.com")
    video = create_video_for(client, auth)
    job = create_job(client, auth, video["id"])
    requested = prepare_and_request(client, auth, job["id"])
    approve_latest(client, auth, requested)

    fetched = client.get(
        f"/api/publishing/jobs/{job['id']}",
        headers=headers(auth),
    )
    activity = client.get(
        "/api/publishing/activity",
        headers=headers(auth),
    )
    pending = client.get(
        "/api/publishing/approvals",
        headers=headers(auth),
    )

    assert fetched.status_code == 200
    assert [
        transition["to_state"]
        for transition in fetched.json()["transitions"]
    ] == ["draft", "preparing", "awaiting_approval", "approved"]
    assert {
        event["event_type"] for event in activity.json()
    } >= {
        "publishing_job_created",
        "publishing_state_changed",
        "approval_requested",
        "approval_approved",
    }
    assert pending.json() == []


def test_rejection_retry_and_cancellation_follow_the_state_machine(
    client: TestClient,
) -> None:
    auth = register(client, "retry-cancel@example.com")
    video = create_video_for(client, auth)
    job = create_job(client, auth, video["id"])
    requested = prepare_and_request(client, auth, job["id"])
    approval_id = requested["approvals"][0]["id"]
    rejected = client.post(
        f"/api/publishing/approvals/{approval_id}/reject",
        headers=headers(auth, write=True),
        json={"note": "Needs a corrected caption"},
    )
    retried = client.post(
        f"/api/publishing/jobs/{job['id']}/prepare",
        headers=headers(auth, write=True),
    )
    requested_again = client.post(
        f"/api/publishing/jobs/{job['id']}/request-approval",
        headers=headers(auth, write=True),
        json={"note": "Caption corrected"},
    )
    cancelled = client.post(
        f"/api/publishing/jobs/{job['id']}/cancel",
        headers=headers(auth, write=True),
        json={"reason": "Campaign was paused"},
    )
    terminal_retry = client.post(
        f"/api/publishing/jobs/{job['id']}/prepare",
        headers=headers(auth, write=True),
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert retried.json()["status"] == "preparing"
    assert requested_again.json()["approvals"][-1]["sequence"] == 2
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["approvals"][-1]["status"] == "cancelled"
    assert terminal_retry.status_code == 409


def test_schedule_validation_and_job_filtering(client: TestClient) -> None:
    auth = register(client, "schedule-validation@example.com")
    video = create_video_for(client, auth)
    job = create_job(client, auth, video["id"])
    requested = prepare_and_request(client, auth, job["id"])
    approve_latest(client, auth, requested)
    past = datetime.now(UTC) - timedelta(minutes=1)

    invalid = client.post(
        f"/api/publishing/jobs/{job['id']}/schedule",
        headers=headers(auth, write=True),
        json={"scheduled_for": past.isoformat()},
    )
    approved_jobs = client.get(
        "/api/publishing/jobs?status=approved",
        headers=headers(auth),
    )
    invalid_filter = client.get(
        "/api/publishing/jobs?status=unknown",
        headers=headers(auth),
    )

    assert invalid.status_code == 422
    assert [item["id"] for item in approved_jobs.json()] == [job["id"]]
    assert invalid_filter.status_code == 422


def test_worker_service_records_failure_retry_and_success(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "worker-flow@example.com")
    video = create_video_for(client, auth)
    job = create_job(client, auth, video["id"])
    requested = prepare_and_request(client, auth, job["id"])
    approved = approve_latest(client, auth, requested)
    workspace_id = UUID(auth["workspace_id"])
    job_id = UUID(approved["id"])
    actor_user_id = UUID(auth["user"]["id"])

    publishing = publishing_service.start_publishing(
        db_session,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    publishing_status = publishing.status
    failed = publishing_service.fail_job(
        db_session,
        workspace_id=workspace_id,
        job_id=job_id,
        error_code="adapter_timeout",
        safe_message="The platform adapter timed out",
    )
    failed_status = failed.status
    failed_error_code = failed.last_error_code
    retried = publishing_service.prepare_job(
        db_session,
        workspace_id=workspace_id,
        job_id=job_id,
        actor_user_id=actor_user_id,
    )
    retried_status = retried.status
    requested_again = publishing_service.request_approval(
        db_session,
        workspace_id=workspace_id,
        job_id=job_id,
        actor_user_id=actor_user_id,
        note="Retry approved content",
    )
    approved_again = publishing_service.decide_approval(
        db_session,
        workspace_id=workspace_id,
        approval_id=requested_again.approvals[-1].id,
        actor_user_id=actor_user_id,
        approve=True,
        note="Retry authorized",
    )
    publishing_service.start_publishing(
        db_session,
        workspace_id=workspace_id,
        job_id=approved_again.id,
    )
    completed = publishing_service.mark_published(
        db_session,
        workspace_id=workspace_id,
        job_id=approved_again.id,
    )

    assert publishing_status == "publishing"
    assert failed_status == "failed"
    assert failed_error_code == "adapter_timeout"
    assert retried_status == "preparing"
    assert completed.status == "published"
    assert completed.published_at is not None


def test_viewers_cannot_create_publishing_jobs(
    client: TestClient,
) -> None:
    owner = register(client, "publishing-owner@example.com")
    video = create_video_for(client, owner)
    client.cookies.clear()
    viewer = register(client, "publishing-viewer@example.com")
    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={
            "email": "publishing-owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    owner["csrf"] = login.json()["csrf_token"]
    added = client.post(
        f"/api/workspaces/{owner['workspace_id']}/members",
        headers=headers(owner, write=True),
        json={
            "email": "publishing-viewer@example.com",
            "role": "viewer",
        },
    )
    assert added.status_code == 201

    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={
            "email": "publishing-viewer@example.com",
            "password": "correct horse battery staple",
        },
    )
    viewer["csrf"] = login.json()["csrf_token"]
    viewer["workspace_id"] = owner["workspace_id"]
    blocked = client.post(
        "/api/publishing/jobs",
        headers={
            **headers(viewer, write=True),
            "Idempotency-Key": "viewer-cannot-publish",
        },
        json={"video_id": video["id"]},
    )

    assert blocked.status_code == 403
