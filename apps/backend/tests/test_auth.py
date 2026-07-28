from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.auth_session import AuthSession
from app.models.user import User
from app.models.workspace import WorkspaceMembership, WorkspaceRole
from tests.test_core_apis import create_channel, headers, register


def test_registration_hashes_password_and_creates_personal_workspace(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client)
    user = db_session.scalar(select(User).where(User.email == "creator@example.com"))
    membership = db_session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == UUID(auth["workspace_id"])
        )
    )

    assert user is not None
    assert user.password_hash is not None
    assert "correct horse battery staple" not in user.password_hash
    assert verify_password("correct horse battery staple", user.password_hash)
    assert membership is not None
    assert membership.role == WorkspaceRole.OWNER.value


def test_duplicate_registration_and_generic_login_failure(
    client: TestClient,
) -> None:
    register(client)
    duplicate = client.post(
        "/api/auth/register",
        json={
            "email": "creator@example.com",
            "display_name": "Duplicate",
            "password": "another secure password phrase",
        },
    )
    wrong_password = client.post(
        "/api/auth/login",
        json={
            "email": "creator@example.com",
            "password": "incorrect password",
        },
    )
    missing_user = client.post(
        "/api/auth/login",
        json={
            "email": "missing@example.com",
            "password": "incorrect password",
        },
    )

    assert duplicate.status_code == 409
    assert wrong_password.status_code == 401
    assert missing_user.status_code == 401
    assert wrong_password.json() == missing_user.json()


def test_login_me_logout_and_revoked_session(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client)
    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={
            "email": "creator@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    me = client.get("/api/auth/me")
    logout = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf},
    )

    assert me.status_code == 200
    assert me.json()["id"] == auth["user"]["id"]
    assert logout.status_code == 204
    assert db_session.scalar(
        select(AuthSession).where(AuthSession.revoked_at.is_not(None))
    )
    assert client.get("/api/auth/me").status_code == 401


def test_authenticated_writes_require_csrf(client: TestClient) -> None:
    auth = register(client)
    response = client.post(
        "/api/channels",
        headers=headers(auth),
        json={
            "platform": "youtube",
            "platform_channel_id": "channel-1",
            "name": "Main Channel",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF validation failed"}


def test_workspace_membership_controls_access(client: TestClient) -> None:
    first = register(client, "first@example.com")
    channel = create_channel(client, first)
    client.cookies.clear()
    second = register(client, "second@example.com")

    hidden = client.get(
        f"/api/channels/{channel['id']}",
        headers=headers(second),
    )
    denied_workspace = client.get(
        "/api/channels",
        headers={"X-Workspace-ID": first["workspace_id"]},
    )

    assert hidden.status_code == 404
    assert denied_workspace.status_code == 403


def test_owner_can_add_member_and_viewer_cannot_write(
    client: TestClient,
) -> None:
    owner = register(client, "owner@example.com")
    client.cookies.clear()
    viewer = register(client, "viewer@example.com")
    client.cookies.clear()
    login = client.post(
        "/api/auth/login",
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    owner["csrf"] = login.json()["csrf_token"]

    added = client.post(
        f"/api/workspaces/{owner['workspace_id']}/members",
        headers=headers(owner, write=True),
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    assert added.status_code == 201

    client.cookies.clear()
    viewer_login = client.post(
        "/api/auth/login",
        json={
            "email": "viewer@example.com",
            "password": "correct horse battery staple",
        },
    )
    viewer["csrf"] = viewer_login.json()["csrf_token"]
    viewer["workspace_id"] = owner["workspace_id"]
    blocked = client.post(
        "/api/channels",
        headers=headers(viewer, write=True),
        json={
            "platform": "youtube",
            "platform_channel_id": "blocked",
            "name": "Blocked",
        },
    )

    assert blocked.status_code == 403
    assert blocked.json() == {"detail": "Workspace write access denied"}


def test_login_throttle_blocks_repeated_failures(client: TestClient) -> None:
    register(client)
    client.cookies.clear()
    for _ in range(5):
        response = client.post(
            "/api/auth/login",
            json={
                "email": "creator@example.com",
                "password": "wrong password",
            },
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/auth/login",
        json={
            "email": "creator@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert blocked.status_code == 429
