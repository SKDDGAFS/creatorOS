from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.models.platform_integration import (
    OAuthAuthorizationState,
    PlatformQuotaUsage,
    RequestOutcome,
)
from app.platforms.contracts import (
    ConnectAccountRequest,
    CredentialMaterial,
    PublishRequest,
    PublishResult,
    PublishStatus,
)
from app.platforms.credentials import InMemoryPlatformSecretStore
from app.platforms.errors import (
    PlatformPermanentError,
    PlatformRateLimitError,
)
from app.platforms.runtime import (
    get_platform_secret_store,
    get_youtube_adapter_factory,
)
from app.platforms.youtube import (
    YOUTUBE_ANALYTICS_SCOPE,
    YOUTUBE_READ_SCOPE,
    YOUTUBE_UPLOAD_SCOPE,
    YouTubeAdapter,
    claim_callback_state,
    start_authorization,
)
from app.platforms.youtube.http_transport import (
    ANALYTICS_API_BUCKET,
    DATA_API_BUCKET,
    VIDEO_UPLOAD_BUCKET,
    YouTubeHttpTransport,
)
from app.services import platform_integration_service, youtube_service
from app.services.errors import (
    AuthorizationError,
    InvalidRequestError,
    ResourceNotFoundError,
)
from tests.test_core_apis import headers, register


def youtube_settings(*, publishing: bool = False) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        youtube_client_id="test-client-id",
        youtube_client_secret="test-client-secret",
        youtube_enable_publishing=publishing,
    )


class FakeYouTubeTransport:
    def __init__(self, quota_recorder=None) -> None:
        self._quota_recorder = quota_recorder
        self.revoked = False

    def _quota(self, bucket: str, units: int = 1) -> None:
        if self._quota_recorder is not None:
            self._quota_recorder(bucket, units)

    def exchange_authorization_code(
        self,
        request: ConnectAccountRequest,
    ) -> CredentialMaterial:
        assert request.authorization_code.get_secret_value() == "callback-code"
        assert request.code_verifier is not None
        return CredentialMaterial(
            access_token=SecretStr("access-token"),
            refresh_token=SecretStr("refresh-token"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=(YOUTUBE_READ_SCOPE, YOUTUBE_ANALYTICS_SCOPE),
        )

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial:
        return credentials.model_copy(
            update={
                "access_token": SecretStr("refreshed-token"),
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            }
        )

    def revoke_credentials(self, credentials: CredentialMaterial) -> None:
        assert credentials.refresh_token is not None
        self.revoked = True

    def list_channels(
        self,
        credentials: CredentialMaterial,
        *,
        channel_id: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        del credentials, cursor
        self._quota(DATA_API_BUCKET)
        return {
            "items": [
                {
                    "id": channel_id or "channel-yt",
                    "snippet": {
                        "title": "Creator Channel",
                        "customUrl": "@creator",
                    },
                    "contentDetails": {"relatedPlaylists": {"uploads": "uploads-1"}},
                    "statistics": {
                        "viewCount": "1000",
                        "subscriberCount": "50",
                        "videoCount": "2",
                    },
                }
            ]
        }

    def list_upload_items(
        self,
        uploads_playlist_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        del credentials, cursor
        assert uploads_playlist_id == "uploads-1"
        self._quota(DATA_API_BUCKET)
        return {
            "items": [
                {"contentDetails": {"videoId": "video-yt-1"}},
                {"contentDetails": {"videoId": "video-yt-2"}},
            ],
            "nextPageToken": None,
        }

    def list_videos(
        self,
        video_ids: tuple[str, ...],
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        del credentials
        self._quota(DATA_API_BUCKET)
        return {
            "items": [
                {
                    "id": video_id,
                    "snippet": {
                        "channelId": "channel-yt",
                        "title": f"Video {video_id}",
                        "description": "Synced description",
                        "publishedAt": "2026-07-01T12:00:00Z",
                    },
                    "contentDetails": {"duration": "PT1M30S"},
                    "status": {
                        "privacyStatus": "public",
                        "uploadStatus": "processed",
                    },
                    "statistics": {
                        "viewCount": "100",
                        "likeCount": "10",
                        "commentCount": "2",
                    },
                    "processingDetails": {"processingStatus": "succeeded"},
                }
                for video_id in video_ids
            ]
        }

    def analytics_activity(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        del channel_id, video_id, credentials, cursor
        self._quota(ANALYTICS_API_BUCKET)
        return {
            "columnHeaders": [
                {"name": name}
                for name in (
                    "views",
                    "engagedViews",
                    "likes",
                    "comments",
                    "shares",
                    "estimatedMinutesWatched",
                    "averageViewDuration",
                    "subscribersGained",
                    "subscribersLost",
                )
            ],
            "rows": [[100, 80, 10, 2, 4, 150, 45, 3, 1]],
        }

    def analytics_retention(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        del channel_id, video_id, credentials
        self._quota(ANALYTICS_API_BUCKET)
        return {
            "columnHeaders": [
                {"name": "elapsedVideoTimeRatio"},
                {"name": "audienceWatchRatio"},
                {"name": "relativeRetentionPerformance"},
            ],
            "rows": [[0.5, 1.2, 0.75]],
        }

    def analytics_traffic_sources(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        del channel_id, video_id, credentials
        self._quota(ANALYTICS_API_BUCKET)
        return {
            "columnHeaders": [
                {"name": "insightTrafficSourceType"},
                {"name": "views"},
                {"name": "engagedViews"},
                {"name": "estimatedMinutesWatched"},
            ],
            "rows": [
                ["RELATED_VIDEO", 60, 50, 90],
                ["YT_SEARCH", 40, 30, 60],
            ],
        }

    def analytics_subscriber_status(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        del channel_id, video_id, credentials
        self._quota(ANALYTICS_API_BUCKET)
        return {
            "columnHeaders": [
                {"name": "subscribedStatus"},
                {"name": "views"},
            ],
            "rows": [["SUBSCRIBED", 30], ["UNSUBSCRIBED", 70]],
        }

    def upload_video(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> PublishResult:
        del request, credentials
        return PublishResult(
            external_publish_id="uploaded-video",
            external_video_id="uploaded-video",
            status="processing",
        )

    def get_upload_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishStatus:
        del credentials
        return PublishStatus(
            external_publish_id=external_publish_id,
            external_video_id=external_publish_id,
            status="ready",
            updated_at=datetime.now(UTC),
        )


class MemoryUpload:
    content_type = "video/mp4"
    size_bytes = 11

    def iter_bytes(self, chunk_size: int = 8 * 1024 * 1024):
        del chunk_size
        yield b"video-bytes"


class MemoryMediaSource:
    def open_upload(self, media_reference: str) -> MemoryUpload:
        assert media_reference == "media://asset-1"
        return MemoryUpload()


def fake_adapter_factory(
    quota_recorder=None,
    request_recorder=None,
) -> YouTubeAdapter:
    del request_recorder
    return YouTubeAdapter(FakeYouTubeTransport(quota_recorder))


def test_youtube_settings_and_scope_gates() -> None:
    with pytest.raises(ValueError, match="must be set together"):
        Settings(_env_file=None, youtube_client_id="client-only")
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(
            _env_file=None,
            environment="production",
            session_cookie_secure=True,
            youtube_client_id="client",
            youtube_client_secret="secret",
            youtube_oauth_redirect_uri="http://localhost/callback",
        )
    with pytest.raises(ValueError, match="OAUTH_STATE_TTL_MINUTES"):
        Settings(_env_file=None, oauth_state_ttl_minutes=0)
    settings = youtube_settings()
    with pytest.raises(InvalidRequestError, match="disabled"):
        from app.platforms.youtube.oauth import requested_scopes

        requested_scopes(publishing=True, settings=settings)


def test_oauth_start_uses_hashed_state_pkce_and_one_time_claim(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "youtube-oauth@example.com")
    store = InMemoryPlatformSecretStore()
    settings = youtube_settings()
    started = start_authorization(
        db_session,
        secret_store=store,
        settings=settings,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        publishing=False,
    )
    parsed = urlparse(started.authorization_url)
    query = parse_qs(parsed.query)
    state = query["state"][0]
    record = db_session.scalar(select(OAuthAuthorizationState))

    assert parsed.scheme == "https"
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    assert YOUTUBE_READ_SCOPE in query["scope"][0]
    assert "test-client-secret" not in started.authorization_url
    assert record is not None
    assert record.state_hash != state
    assert state not in record.state_hash

    claimed = claim_callback_state(
        db_session,
        secret_store=store,
        state=state,
        user_id=UUID(auth["user"]["id"]),
    )
    assert claimed.workspace_id == UUID(auth["workspace_id"])
    assert claimed.verifier.code_verifier.get_secret_value()
    with pytest.raises(AuthorizationError, match="already used"):
        claim_callback_state(
            db_session,
            secret_store=store,
            state=state,
            user_id=UUID(auth["user"]["id"]),
        )


def test_oauth_state_rejects_wrong_user_and_expiry(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "youtube-state@example.com")
    store = InMemoryPlatformSecretStore()
    started = start_authorization(
        db_session,
        secret_store=store,
        settings=youtube_settings(),
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        publishing=False,
    )
    state = parse_qs(urlparse(started.authorization_url).query)["state"][0]
    with pytest.raises(AuthorizationError, match="does not match"):
        claim_callback_state(
            db_session,
            secret_store=store,
            state=state,
            user_id=uuid4(),
        )
    record = db_session.scalar(select(OAuthAuthorizationState))
    assert record is not None
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(AuthorizationError, match="expired"):
        claim_callback_state(
            db_session,
            secret_store=store,
            state=state,
            user_id=UUID(auth["user"]["id"]),
        )


def test_adapter_maps_pagination_metrics_and_publish_rules() -> None:
    adapter = fake_adapter_factory()
    credentials = CredentialMaterial(
        access_token=SecretStr("access"),
        refresh_token=SecretStr("refresh"),
        scopes=(
            YOUTUBE_READ_SCOPE,
            YOUTUBE_ANALYTICS_SCOPE,
            YOUTUBE_UPLOAD_SCOPE,
        ),
    )
    channels = adapter.list_channels(credentials)
    videos = adapter.list_videos("channel-yt", credentials)
    metrics = adapter.sync_metrics("video-yt-1", credentials).items[0]

    assert channels.items[0].metadata["uploads_playlist_id"] == "uploads-1"
    assert videos.items[0].duration_seconds == 90
    assert metrics.values["watch_time_seconds"] == 9000
    assert metrics.metadata["retention_points"][0]["audience_retention_ratio"] == 1.2
    assert metrics.metadata["youtube_extension"] == {
        "suggested_video_views": 60,
        "browse_feature_views": None,
        "subscriber_views": 30,
        "unsubscribed_views": 70,
        "search_views": 40,
        "external_views": None,
        "end_screen_views": None,
        "reported_impressions_ctr": None,
    }

    scheduled = PublishRequest(
        media_reference="media://asset-1",
        title="Scheduled",
        scheduled_for=datetime.now(UTC) + timedelta(hours=2),
        options={"privacy_status": "public", "made_for_kids": False},
    )
    validation = adapter.validate_publish_request(scheduled, credentials)
    assert not validation.valid
    assert "Scheduled YouTube videos must be private" in validation.errors
    malformed = adapter.validate_publish_request(
        scheduled.model_copy(
            update={
                "title": "x" * 101,
                "options": {
                    "privacy_status": "private",
                    "made_for_kids": "false",
                    "tags": ["ok", ""],
                },
            }
        ),
        credentials,
    )
    assert not malformed.valid
    assert "made_for_kids must be true or false" in malformed.errors
    assert "YouTube titles cannot exceed 100 characters" in malformed.errors
    with pytest.raises(PlatformPermanentError, match="idempotency"):
        adapter.publish_video(
            scheduled.model_copy(
                update={
                    "options": {"privacy_status": "private", "made_for_kids": False}
                }
            ),
            credentials,
            idempotency_key="short",
        )


def test_http_transport_exchanges_refreshes_and_revokes_without_leaking() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path.endswith("/token"):
            body = request.content.decode()
            if "authorization_code" in body:
                return httpx2.Response(
                    200,
                    json={
                        "access_token": "oauth-access",
                        "refresh_token": "oauth-refresh",
                        "expires_in": 3600,
                        "scope": f"{YOUTUBE_READ_SCOPE} {YOUTUBE_ANALYTICS_SCOPE}",
                    },
                )
            return httpx2.Response(
                200,
                json={"access_token": "refreshed", "expires_in": 3600},
            )
        if request.url.path.endswith("/revoke"):
            return httpx2.Response(200)
        return httpx2.Response(500)

    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        transport = YouTubeHttpTransport(
            client_id="client-id",
            client_secret=SecretStr("client-secret"),
            media_source=MemoryMediaSource(),
            client=client,
        )
        credentials = transport.exchange_authorization_code(
            ConnectAccountRequest(
                authorization_code=SecretStr("authorization-code"),
                redirect_uri="http://127.0.0.1/callback",
                code_verifier=SecretStr("pkce-verifier"),
            )
        )
        refreshed = transport.refresh_credentials(credentials)
        transport.revoke_credentials(refreshed)

    assert credentials.access_token.get_secret_value() == "oauth-access"
    assert refreshed.access_token.get_secret_value() == "refreshed"
    assert refreshed.refresh_token is not None
    assert refreshed.refresh_token.get_secret_value() == "oauth-refresh"
    assert all("client-secret" not in str(request.url) for request in requests)


def test_http_transport_classifies_quota_errors() -> None:
    outcomes: list[RequestOutcome] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        del request
        return httpx2.Response(
            403,
            headers={"Retry-After": "60", "X-Goog-Request-Id": "request-1"},
            json={
                "error": {
                    "errors": [{"reason": "quotaExceeded"}],
                    "code": 403,
                }
            },
        )

    credentials = CredentialMaterial(access_token=SecretStr("access"))
    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        transport = YouTubeHttpTransport(
            client_id="client-id",
            client_secret=SecretStr("client-secret"),
            media_source=MemoryMediaSource(),
            client=client,
            request_recorder=(
                lambda method, url, status_code, duration_ms, outcome, request_id: (
                    outcomes.append(outcome)
                )
            ),
        )
        with pytest.raises(PlatformRateLimitError) as error:
            transport.list_channels(credentials)
    assert error.value.retry_after_seconds == 60
    assert error.value.provider_request_id == "request-1"
    assert "quota" in error.value.safe_message.lower()
    assert outcomes == [RequestOutcome.RATE_LIMITED]


def test_http_transport_resumable_upload_and_quota_callback() -> None:
    bodies: list[bytes] = []
    quotas: list[tuple[str, int]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            assert request.headers["x-upload-content-type"] == "video/mp4"
            return httpx2.Response(
                200,
                headers={"Location": "https://www.googleapis.com/upload/session-1"},
            )
        bodies.append(request.content)
        return httpx2.Response(
            200,
            headers={"X-Goog-Request-Id": "upload-request"},
            json={"id": "youtube-video-id"},
        )

    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        transport = YouTubeHttpTransport(
            client_id="client-id",
            client_secret=SecretStr("client-secret"),
            media_source=MemoryMediaSource(),
            client=client,
            quota_recorder=lambda bucket, units: quotas.append((bucket, units)),
        )
        result = transport.upload_video(
            PublishRequest(
                media_reference="media://asset-1",
                title="Approved upload",
                options={"privacy_status": "private", "made_for_kids": False},
            ),
            CredentialMaterial(access_token=SecretStr("access")),
        )

    assert result.external_video_id == "youtube-video-id"
    assert bodies == [b"video-bytes"]
    assert quotas == [(VIDEO_UPLOAD_BUCKET, 1)]


def test_oauth_callback_sync_and_quota_are_persisted(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "youtube-sync@example.com")
    workspace_id = UUID(auth["workspace_id"])
    user_id = UUID(auth["user"]["id"])
    store = InMemoryPlatformSecretStore()
    started = start_authorization(
        db_session,
        secret_store=store,
        settings=youtube_settings(),
        workspace_id=workspace_id,
        user_id=user_id,
        publishing=False,
    )
    state = parse_qs(urlparse(started.authorization_url).query)["state"][0]
    connection = youtube_service.complete_authorization(
        db_session,
        secret_store=store,
        adapter_factory=fake_adapter_factory,
        state=state,
        authorization_code="callback-code",
        provider_error=None,
        user_id=user_id,
    )
    videos = youtube_service.sync_videos(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        secret_store=store,
        adapter_factory=fake_adapter_factory,
    )
    metrics = youtube_service.sync_metrics(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        video_id=videos.videos[0].id,
        secret_store=store,
        adapter_factory=fake_adapter_factory,
    )
    usage = platform_integration_service.list_quota_usage(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
    )
    disconnected = youtube_service.disconnect(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        secret_store=store,
        adapter_factory=fake_adapter_factory,
    )

    assert connection.external_account_id == "channel-yt"
    assert len(videos.videos) == 2
    assert metrics[0].views == 100
    assert metrics[0].retention_points[0].audience_retention_ratio == Decimal(
        "1.200000"
    )
    usage_by_bucket = {item.quota_bucket: item for item in usage}
    assert usage_by_bucket[DATA_API_BUCKET].request_count >= 5
    assert usage_by_bucket[ANALYTICS_API_BUCKET].request_count == 4
    assert db_session.scalar(select(PlatformQuotaUsage)) is not None
    assert disconnected.status == "disconnected"
    with pytest.raises(ResourceNotFoundError):
        store.load(connection.credential_reference)


def test_integration_routes_require_csrf_and_use_state_callback(
    client: TestClient,
) -> None:
    auth = register(client, "youtube-route@example.com")
    store = InMemoryPlatformSecretStore()
    settings = youtube_settings()
    app.dependency_overrides[get_platform_secret_store] = lambda: store
    app.dependency_overrides[get_youtube_adapter_factory] = lambda: fake_adapter_factory
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        denied = client.post(
            "/api/integrations/youtube/oauth/start",
            headers=headers(auth),
            json={"publishing": False},
        )
        started = client.post(
            "/api/integrations/youtube/oauth/start",
            headers=headers(auth, write=True),
            json={"publishing": False},
        )
        state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][
            0
        ]
        callback = client.get(
            "/api/integrations/youtube/oauth/callback",
            params={"state": state, "code": "callback-code"},
        )
        listed = client.get(
            "/api/integrations",
            headers=headers(auth),
        )
    finally:
        app.dependency_overrides.pop(get_platform_secret_store, None)
        app.dependency_overrides.pop(get_youtube_adapter_factory, None)
        app.dependency_overrides.pop(get_settings, None)

    assert denied.status_code == 403
    assert started.status_code == 201
    assert callback.status_code == 200
    assert callback.json()["external_account_id"] == "channel-yt"
    assert listed.status_code == 200
    assert listed.json()[0]["platform"] == "youtube"
