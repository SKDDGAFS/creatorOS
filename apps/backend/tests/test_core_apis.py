from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient


def register(client: TestClient, email: str = "creator@example.com") -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "display_name": "Test Creator",
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 201
    auth = response.json()
    workspaces = client.get("/api/workspaces")
    assert workspaces.status_code == 200
    return {
        "user": auth["user"],
        "csrf": auth["csrf_token"],
        "workspace_id": workspaces.json()[0]["id"],
    }


def headers(auth: dict, *, write: bool = False) -> dict[str, str]:
    result = {"X-Workspace-ID": auth["workspace_id"]}
    if write:
        result["X-CSRF-Token"] = auth["csrf"]
    return result


def create_channel(
    client: TestClient,
    auth: dict,
    *,
    platform: str = "youtube",
    platform_channel_id: str = "channel-1",
    name: str = "Main Channel",
) -> dict:
    response = client.post(
        "/api/channels",
        headers=headers(auth, write=True),
        json={
            "platform": platform,
            "platform_channel_id": platform_channel_id,
            "name": name,
            "handle": "@creator",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_video(
    client: TestClient,
    auth: dict,
    channel_id: str,
    *,
    platform_video_id: str | None = "video-1",
    title: str = "First Video",
    video_status: str = "draft",
    duration_seconds: int | None = None,
) -> dict:
    response = client.post(
        "/api/videos",
        headers=headers(auth, write=True),
        json={
            "channel_id": channel_id,
            "platform_video_id": platform_video_id,
            "title": title,
            "description": "A test video",
            "duration_seconds": duration_seconds,
            "status": video_status,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_channel_crud_is_owned_by_authenticated_workspace(
    client: TestClient,
) -> None:
    auth = register(client)
    channel = create_channel(client, auth)

    assert "user_id" not in {
        "platform": "youtube",
        "platform_channel_id": "channel-1",
        "name": "Main Channel",
    }
    assert channel["user_id"] == auth["user"]["id"]
    assert channel["workspace_id"] == auth["workspace_id"]

    fetched = client.get(
        f"/api/channels/{channel['id']}",
        headers=headers(auth),
    )
    updated = client.patch(
        f"/api/channels/{channel['id']}",
        headers=headers(auth, write=True),
        json={"name": "Renamed Channel"},
    )

    assert fetched.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed Channel"


def test_channel_validation_conflict_filtering_and_pagination(
    client: TestClient,
) -> None:
    auth = register(client)
    invalid = client.post(
        "/api/channels",
        headers=headers(auth, write=True),
        json={
            "platform": "unsupported",
            "platform_channel_id": "invalid",
            "name": "Invalid",
        },
    )
    assert invalid.status_code == 422

    first = create_channel(client, auth)
    create_channel(
        client,
        auth,
        platform="tiktok",
        platform_channel_id="channel-2",
        name="Second Channel",
    )
    duplicate = client.post(
        "/api/channels",
        headers=headers(auth, write=True),
        json={
            "platform": "youtube",
            "platform_channel_id": "channel-1",
            "name": "Duplicate",
        },
    )
    filtered = client.get(
        "/api/channels?platform=youtube&is_active=true",
        headers=headers(auth),
    )
    paged = client.get(
        "/api/channels?limit=1&offset=1",
        headers=headers(auth),
    )

    assert duplicate.status_code == 409
    assert [item["id"] for item in filtered.json()] == [first["id"]]
    assert paged.json()[0]["name"] == "Second Channel"


def test_video_crud_supports_nullable_platform_id(client: TestClient) -> None:
    auth = register(client)
    channel = create_channel(client, auth)
    first = create_video(
        client,
        auth,
        channel["id"],
        platform_video_id=None,
    )
    second = create_video(
        client,
        auth,
        channel["id"],
        platform_video_id=None,
        title="Second Draft",
    )
    updated = client.patch(
        f"/api/videos/{first['id']}",
        headers=headers(auth, write=True),
        json={"title": "Updated Title"},
    )

    assert first["platform_video_id"] is None
    assert second["platform_video_id"] is None
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated Title"


def test_video_validation_conflict_filtering_and_pagination(
    client: TestClient,
) -> None:
    auth = register(client)
    channel = create_channel(client, auth)
    invalid = client.post(
        "/api/videos",
        headers=headers(auth, write=True),
        json={
            "channel_id": channel["id"],
            "title": "Invalid",
            "status": "unknown",
        },
    )
    assert invalid.status_code == 422

    first = create_video(client, auth, channel["id"])
    create_video(
        client,
        auth,
        channel["id"],
        platform_video_id="video-2",
        title="Published Video",
        video_status="published",
    )
    duplicate = client.post(
        "/api/videos",
        headers=headers(auth, write=True),
        json={
            "channel_id": channel["id"],
            "platform_video_id": "video-1",
            "title": "Duplicate",
        },
    )
    filtered = client.get(
        f"/api/videos?channel_id={channel['id']}&status=draft",
        headers=headers(auth),
    )
    paged = client.get(
        "/api/videos?limit=1&offset=1",
        headers=headers(auth),
    )

    assert duplicate.status_code == 409
    assert [item["id"] for item in filtered.json()] == [first["id"]]
    assert paged.json()[0]["title"] == "Published Video"


def test_metric_snapshots_are_appended_and_ordered(
    client: TestClient,
) -> None:
    auth = register(client)
    channel = create_channel(client, auth)
    video = create_video(client, auth, channel["id"])

    older = client.post(
        f"/api/videos/{video['id']}/metrics",
        headers=headers(auth, write=True),
        json={
            "captured_at": "2026-07-28T10:00:00+00:00",
            "views": 100,
            "likes": 10,
            "click_through_rate": "0.0500",
        },
    )
    newer = client.post(
        f"/api/videos/{video['id']}/metrics",
        headers=headers(auth, write=True),
        json={
            "captured_at": "2026-07-28T11:00:00+00:00",
            "views": 150,
            "likes": 15,
            "click_through_rate": "0.0750",
        },
    )
    newest_first = client.get(
        f"/api/videos/{video['id']}/metrics",
        headers=headers(auth),
    )
    oldest_first = client.get(
        f"/api/videos/{video['id']}/metrics?order=oldest",
        headers=headers(auth),
    )

    assert older.status_code == 201
    assert newer.status_code == 201
    assert Decimal(older.json()["click_through_rate"]) == Decimal("0.0500")
    assert [item["views"] for item in newest_first.json()] == [150, 100]
    assert [item["views"] for item in oldest_first.json()] == [100, 150]


def test_missing_resources_and_query_validation(client: TestClient) -> None:
    auth = register(client)
    missing_id = uuid4()

    assert client.get(
        f"/api/channels/{missing_id}",
        headers=headers(auth),
    ).status_code == 404
    assert client.post(
        "/api/videos",
        headers=headers(auth, write=True),
        json={"channel_id": str(missing_id), "title": "Missing"},
    ).status_code == 404
    assert client.get(
        "/api/channels?limit=101",
        headers=headers(auth),
    ).status_code == 422
    assert client.get(
        f"/api/videos/{missing_id}/metrics?order=invalid",
        headers=headers(auth),
    ).status_code == 422
