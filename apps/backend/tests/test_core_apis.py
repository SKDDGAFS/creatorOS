from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User


def add_user(
    db_session: Session,
    *,
    email: str = "creator@example.com",
) -> User:
    user = User(email=email, display_name="Test Creator")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_channel(
    client: TestClient,
    user: User,
    *,
    platform: str = "youtube",
    platform_channel_id: str = "channel-1",
    name: str = "Main Channel",
) -> dict:
    response = client.post(
        "/api/channels",
        json={
            "user_id": str(user.id),
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
    channel_id: str,
    *,
    platform_video_id: str | None = "video-1",
    title: str = "First Video",
    status: str = "draft",
) -> dict:
    response = client.post(
        "/api/videos",
        json={
            "channel_id": channel_id,
            "platform_video_id": platform_video_id,
            "title": title,
            "description": "A test video",
            "status": status,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_channel_creation_and_retrieval(
    client: TestClient,
    db_session: Session,
) -> None:
    user = add_user(db_session)
    channel = create_channel(client, user)

    response = client.get(f"/api/channels/{channel['id']}")

    assert response.status_code == 200
    assert response.json()["user_id"] == str(user.id)
    assert response.json()["platform"] == "youtube"
    assert response.json()["name"] == "Main Channel"


def test_channel_creation_requires_existing_user(client: TestClient) -> None:
    response = client.post(
        "/api/channels",
        json={
            "user_id": str(uuid4()),
            "platform": "youtube",
            "platform_channel_id": "missing-user-channel",
            "name": "Missing Parent",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_channel_validation_and_duplicate_conflict(
    client: TestClient,
    db_session: Session,
) -> None:
    user = add_user(db_session)
    invalid = client.post(
        "/api/channels",
        json={
            "user_id": str(user.id),
            "platform": "unsupported",
            "platform_channel_id": "invalid",
            "name": "Invalid",
        },
    )
    assert invalid.status_code == 422

    create_channel(client, user)
    duplicate = client.post(
        "/api/channels",
        json={
            "user_id": str(user.id),
            "platform": "youtube",
            "platform_channel_id": "channel-1",
            "name": "Duplicate",
        },
    )

    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": (
            "A channel with this platform and platform_channel_id already exists"
        )
    }


def test_channel_partial_update_filtering_and_pagination(
    client: TestClient,
    db_session: Session,
) -> None:
    user = add_user(db_session)
    first = create_channel(client, user)
    create_channel(
        client,
        user,
        platform="tiktok",
        platform_channel_id="channel-2",
        name="Second Channel",
    )

    updated = client.patch(
        f"/api/channels/{first['id']}",
        json={"name": "Renamed Channel"},
    )
    filtered = client.get(
        f"/api/channels?user_id={user.id}&platform=youtube&is_active=true"
    )
    paged = client.get("/api/channels?limit=1&offset=1")

    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed Channel"
    assert updated.json()["handle"] == "@creator"
    assert [item["id"] for item in filtered.json()] == [first["id"]]
    assert paged.status_code == 200
    assert len(paged.json()) == 1
    assert paged.json()[0]["name"] == "Second Channel"


def test_missing_channel_returns_stable_404(client: TestClient) -> None:
    response = client.get(f"/api/channels/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Channel not found"}


def test_video_creation_and_retrieval_allows_null_platform_id(
    client: TestClient,
    db_session: Session,
) -> None:
    user = add_user(db_session)
    channel = create_channel(client, user)
    video = create_video(client, channel["id"], platform_video_id=None)

    response = client.get(f"/api/videos/{video['id']}")
    second = create_video(
        client,
        channel["id"],
        platform_video_id=None,
        title="Second Draft",
    )

    assert response.status_code == 200
    assert response.json()["platform_video_id"] is None
    assert response.json()["status"] == "draft"
    assert second["platform_video_id"] is None


def test_video_creation_requires_existing_channel(client: TestClient) -> None:
    response = client.post(
        "/api/videos",
        json={
            "channel_id": str(uuid4()),
            "title": "Missing Channel",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Channel not found"}


def test_video_validation_and_duplicate_conflict(
    client: TestClient,
    db_session: Session,
) -> None:
    user = add_user(db_session)
    channel = create_channel(client, user)

    invalid = client.post(
        "/api/videos",
        json={
            "channel_id": channel["id"],
            "title": "Invalid Status",
            "status": "unknown",
        },
    )
    assert invalid.status_code == 422

    create_video(client, channel["id"])
    duplicate = client.post(
        "/api/videos",
        json={
            "channel_id": channel["id"],
            "platform_video_id": "video-1",
            "title": "Duplicate",
        },
    )

    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": (
            "A video with this channel_id and platform_video_id already exists"
        )
    }


def test_video_partial_update_filtering_and_pagination(
    client: TestClient,
    db_session: Session,
) -> None:
    user = add_user(db_session)
    channel = create_channel(client, user)
    first = create_video(client, channel["id"])
    create_video(
        client,
        channel["id"],
        platform_video_id="video-2",
        title="Published Video",
        status="published",
    )

    updated = client.patch(
        f"/api/videos/{first['id']}",
        json={"title": "Updated Title"},
    )
    filtered = client.get(
        f"/api/videos?channel_id={channel['id']}&status=draft"
    )
    paged = client.get("/api/videos?limit=1&offset=1")

    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated Title"
    assert updated.json()["description"] == "A test video"
    assert [item["id"] for item in filtered.json()] == [first["id"]]
    assert paged.status_code == 200
    assert len(paged.json()) == 1
    assert paged.json()[0]["title"] == "Published Video"


def test_missing_video_returns_stable_404(client: TestClient) -> None:
    response = client.get(f"/api/videos/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Video not found"}


def test_metric_snapshots_are_appended_and_ordered(
    client: TestClient,
    db_session: Session,
) -> None:
    user = add_user(db_session)
    channel = create_channel(client, user)
    video = create_video(client, channel["id"])

    older = client.post(
        f"/api/videos/{video['id']}/metrics",
        json={
            "captured_at": "2026-07-28T10:00:00+00:00",
            "views": 100,
            "likes": 10,
            "click_through_rate": "0.0500",
        },
    )
    newer = client.post(
        f"/api/videos/{video['id']}/metrics",
        json={
            "captured_at": "2026-07-28T11:00:00+00:00",
            "views": 150,
            "likes": 15,
            "click_through_rate": "0.0750",
        },
    )
    newest_first = client.get(f"/api/videos/{video['id']}/metrics")
    oldest_first = client.get(
        f"/api/videos/{video['id']}/metrics?order=oldest"
    )

    assert older.status_code == 201
    assert newer.status_code == 201
    assert Decimal(older.json()["click_through_rate"]) == Decimal("0.0500")
    assert [item["views"] for item in newest_first.json()] == [150, 100]
    assert [item["views"] for item in oldest_first.json()] == [100, 150]


def test_metric_validation_and_missing_video(client: TestClient) -> None:
    missing_video_id = uuid4()
    missing = client.post(
        f"/api/videos/{missing_video_id}/metrics",
        json={"views": 1},
    )
    invalid_count = client.post(
        f"/api/videos/{missing_video_id}/metrics",
        json={"views": -1},
    )
    invalid_rate = client.post(
        f"/api/videos/{missing_video_id}/metrics",
        json={"click_through_rate": "1.1"},
    )

    assert missing.status_code == 404
    assert missing.json() == {"detail": "Video not found"}
    assert invalid_count.status_code == 422
    assert invalid_rate.status_code == 422


def test_list_query_limits_are_bounded(client: TestClient) -> None:
    assert client.get("/api/channels?limit=101").status_code == 422
    assert client.get("/api/videos?limit=0").status_code == 422
    assert client.get(
        f"/api/videos/{uuid4()}/metrics?order=invalid"
    ).status_code == 422
