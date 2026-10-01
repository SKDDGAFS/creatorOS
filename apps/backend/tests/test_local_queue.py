from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from tests.test_core_apis import add_user, create_channel


def test_local_setup_is_idempotent(client: TestClient) -> None:
    first = client.post("/api/local/setup")
    second = client.post("/api/local/setup")

    assert first.status_code == 200
    assert second.status_code == 200
    assert [item["platform"] for item in first.json()] == [
        "youtube",
        "instagram",
        "tiktok",
    ]
    assert [item["id"] for item in first.json()] == [
        item["id"] for item in second.json()
    ]
    assert all(item["is_authorized"] is False for item in first.json())


def test_upload_queue_reschedule_cancel_and_persistence(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    settings = get_settings()
    settings.storage_path = str(tmp_path)
    user = add_user(db_session)
    channel = create_channel(client, user)

    uploaded = client.post(
        "/api/videos/upload",
        data={"channel_id": channel["id"]},
        files={"file": ("launch.mp4", b"video bytes", "video/mp4")},
    )
    assert uploaded.status_code == 201
    video = uploaded.json()
    stored = tmp_path / video["media_path"]
    assert stored.read_bytes() == b"video bytes"

    scheduled = client.post(
        "/api/scheduled-posts",
        json={
            "video_id": video["id"],
            "channel_id": channel["id"],
            "scheduled_at": "2026-10-01T15:00:00-04:00",
            "timezone": "America/New_York",
            "status": "scheduled",
            "metadata": {"title": "Launch", "description": "", "tags": []},
        },
    )
    assert scheduled.status_code == 201
    post_id = scheduled.json()["id"]
    assert scheduled.json()["scheduled_at"].endswith(("Z", "+00:00"))

    rescheduled = client.patch(
        f"/api/scheduled-posts/{post_id}",
        json={"scheduled_at": "2026-10-02T15:00:00-04:00"},
    )
    assert rescheduled.status_code == 200
    assert rescheduled.json()["status"] == "scheduled"

    after_restart = client.get("/api/scheduled-posts")
    assert after_restart.status_code == 200
    assert after_restart.json()[0]["id"] == post_id

    cancelled = client.patch(
        f"/api/scheduled-posts/{post_id}",
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert stored.exists()


def test_upload_rejects_type_and_cleans_oversized_file(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    settings = get_settings()
    settings.storage_path = str(tmp_path)
    settings.max_upload_size_bytes = 4
    user = add_user(db_session)
    channel = create_channel(client, user, platform_channel_id="upload-channel")

    invalid = client.post(
        "/api/videos/upload",
        data={"channel_id": str(channel["id"])},
        files={"file": ("notes.txt", b"text", "text/plain")},
    )
    oversized = client.post(
        "/api/videos/upload",
        data={"channel_id": str(channel["id"])},
        files={"file": ("large.mp4", b"12345", "video/mp4")},
    )

    assert invalid.status_code == 422
    assert oversized.status_code == 422
    assert list(tmp_path.rglob("*")) == []


def test_watch_folder_ingests_supported_files_once_and_reports_skips(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    settings = get_settings()
    settings.storage_path = str(tmp_path / "storage")
    settings.watch_folder_path = str(tmp_path / "watch")
    settings.max_upload_size_bytes = 4
    user = add_user(db_session)
    channel = create_channel(client, user)
    watch_folder = Path(settings.watch_folder_path)
    watch_folder.mkdir()
    (watch_folder / "draft.mp4").write_bytes(b"clip")
    (watch_folder / "notes.txt").write_text("not a video")
    (watch_folder / "large.mov").write_bytes(b"oversized")

    response = client.post(
        "/api/videos/ingest",
        json={"channel_id": channel["id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert [video["title"] for video in body["imported"]] == ["draft"]
    assert {item["filename"] for item in body["skipped"]} == {
        "notes.txt",
        "large.mov",
    }
    stored_video = Path(settings.storage_path) / body["imported"][0]["media_path"]
    assert stored_video.read_bytes() == b"clip"
    assert len(list((watch_folder / "processed").iterdir())) == 1

    repeated = client.post(
        "/api/videos/ingest",
        json={"channel_id": channel["id"]},
    )
    assert repeated.status_code == 200
    assert repeated.json()["imported"] == []
    assert len(client.get("/api/videos").json()) == 1
