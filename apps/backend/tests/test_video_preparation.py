from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import videos
from app.core.config import get_settings
from app.models.video import Video
from tests.test_core_apis import add_user, create_channel


class FakeAIProvider:
    def transcribe(self, media_path: Path) -> str:
        assert media_path.is_file()
        return "A local transcript"

    def analyze_video(self, transcript: str) -> dict[str, object]:
        assert transcript == "A local transcript"
        return {"summary": "A concise summary", "topics": ["creator tools"]}

    def generate_metadata(
        self,
        transcript: str,
        analysis: dict[str, object],
        platform: str,
    ) -> dict[str, object]:
        assert platform == "youtube"
        return {"title": "Editable local draft", "tags": ["creator"]}

    def research_topic(self, topic: str) -> dict[str, object]:
        return {"topic": topic}

    def recommend_time(
        self,
        metrics: list[dict[str, object]],
        timezone: str,
    ) -> dict[str, object]:
        return {"available": False, "sample_count": len(metrics)}


def test_prepare_video_persists_local_draft(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = get_settings()
    settings.storage_path = str(tmp_path)
    settings.max_upload_size_bytes = 500_000_000
    user = add_user(db_session)
    channel = create_channel(client, user)
    uploaded = client.post(
        "/api/videos/upload",
        data={"channel_id": channel["id"]},
        files={"file": ("clip.mp4", b"local media", "video/mp4")},
    )
    video = uploaded.json()

    monkeypatch.setattr(videos, "get_ai_provider", lambda: FakeAIProvider())
    prepared = client.post(f"/api/videos/{video['id']}/prepare")

    assert prepared.status_code == 200
    assert prepared.json()["transcript"] == "A local transcript"
    assert prepared.json()["ai_analysis"]["summary"] == "A concise summary"
    assert (
        prepared.json()["draft_metadata"]["fields"]["title"]
        == "Editable local draft"
    )
    stored = db_session.get(Video, UUID(video["id"]))
    assert stored is not None
    assert stored.draft_metadata == {
        "platform": "youtube",
        "fields": {"title": "Editable local draft", "tags": ["creator"]},
    }


def test_prepare_video_rejects_media_path_outside_storage(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    settings = get_settings()
    settings.storage_path = str(tmp_path)
    user = add_user(db_session)
    channel = create_channel(client, user)
    created = client.post(
        "/api/videos",
        json={"channel_id": channel["id"], "title": "No local media"},
    )
    settings.storage_path = str(tmp_path / "storage")
    video_id = UUID(created.json()["id"])
    db_session.query(Video).filter_by(id=video_id).update(
        {"media_path": "../outside.mp4"}
    )
    db_session.commit()

    response = client.post(f"/api/videos/{video_id}/prepare")

    assert response.status_code == 409
    assert "outside local storage" in response.json()["detail"]
