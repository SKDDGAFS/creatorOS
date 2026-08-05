from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

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
    PlatformAccountMetricSnapshot,
    PlatformQuotaUsage,
    RequestOutcome,
)
from app.platforms.contracts import (
    ConnectAccountRequest,
    CredentialMaterial,
    PublishRequest,
)
from app.platforms.credentials import InMemoryPlatformSecretStore
from app.platforms.errors import PlatformRateLimitError
from app.platforms.runtime import (
    get_platform_secret_store,
    get_tiktok_adapter_factory,
)
from app.platforms.tiktok import (
    TIKTOK_BASIC_SCOPE,
    TIKTOK_PROFILE_SCOPE,
    TIKTOK_PUBLISH_SCOPE,
    TIKTOK_STATS_SCOPE,
    TIKTOK_VIDEO_SCOPE,
    TikTokAdapter,
    claim_callback_state,
    start_authorization,
)
from app.platforms.tiktok.http_transport import TikTokHttpTransport
from app.services.errors import AuthorizationError, InvalidRequestError
from tests.test_core_apis import headers, register


def tiktok_settings(*, publishing: bool = False) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        tiktok_client_key="test-client-key",
        tiktok_client_secret="test-client-secret",
        tiktok_enable_publishing=publishing,
    )


class FakeTikTokTransport:
    def __init__(self, quota_recorder=None) -> None:
        self._quota_recorder = quota_recorder
        self.revoked = False

    def _quota(self, bucket: str) -> None:
        if self._quota_recorder is not None:
            self._quota_recorder(bucket, 1)

    @staticmethod
    def _ok(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "data": data,
            "error": {"code": "ok", "message": "", "log_id": "fake-log"},
        }

    def exchange_authorization_code(
        self,
        request: ConnectAccountRequest,
    ) -> CredentialMaterial:
        assert request.authorization_code.get_secret_value()
        return CredentialMaterial(
            access_token=SecretStr("tiktok-access-token"),
            refresh_token=SecretStr("tiktok-refresh-token"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            scopes=(
                TIKTOK_BASIC_SCOPE,
                TIKTOK_PROFILE_SCOPE,
                TIKTOK_STATS_SCOPE,
                TIKTOK_VIDEO_SCOPE,
                TIKTOK_PUBLISH_SCOPE,
            ),
        )

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial:
        return credentials.model_copy(
            update={
                "access_token": SecretStr("refreshed-tiktok-token"),
                "refresh_token": SecretStr("refreshed-tiktok-refresh-token"),
                "expires_at": datetime.now(UTC) + timedelta(days=1),
            }
        )

    def revoke_credentials(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        assert external_account_id == "tt-account-1"
        assert credentials.access_token.get_secret_value()
        self.revoked = True

    def get_profile(self, credentials: CredentialMaterial) -> dict[str, Any]:
        self._quota("tiktok_api_calls")
        assert credentials.access_token.get_secret_value()
        return self._ok(
            {
                "user": {
                    "open_id": "tt-account-1",
                    "display_name": "Creator",
                    "username": "creator",
                    "follower_count": 321,
                    "following_count": 45,
                    "likes_count": 9876,
                    "video_count": 1,
                }
            }
        )

    def list_videos(
        self,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self._quota("tiktok_api_calls")
        assert credentials.access_token.get_secret_value()
        assert cursor is None
        return self._ok(
            {
                "videos": [self._video("tt-video-1")],
                "cursor": 1721476800000,
                "has_more": True,
            }
        )

    def get_video(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("tiktok_api_calls")
        assert credentials.access_token.get_secret_value()
        return self._ok({"videos": [self._video(external_video_id)]})

    def get_creator_info(
        self,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("tiktok_publishing_calls")
        assert credentials.access_token.get_secret_value()
        return self._ok(
            {
                "creator_username": "creator",
                "privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"],
                "comment_disabled": False,
                "duet_disabled": False,
                "stitch_disabled": False,
                "max_video_post_duration_sec": 300,
            }
        )

    def initialize_publish(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("tiktok_publishing_calls")
        assert request.media_reference.startswith("https://")
        assert credentials.access_token.get_secret_value()
        return self._ok({"publish_id": "tt-publish-1"})

    def get_publish_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("tiktok_publishing_calls")
        assert external_publish_id == "tt-publish-1"
        assert credentials.access_token.get_secret_value()
        return self._ok(
            {
                "status": "PUBLISH_COMPLETE",
                "publicaly_available_post_id": ["tt-published-1"],
            }
        )

    @staticmethod
    def _video(video_id: str) -> dict[str, Any]:
        return {
            "id": video_id,
            "title": "Launch video",
            "video_description": "Launch video details",
            "create_time": 1721476800,
            "duration": 42,
            "view_count": 1000,
            "like_count": 70,
            "comment_count": 8,
            "share_count": 12,
        }


def test_tiktok_settings_scopes_and_one_time_state(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client)
    store = InMemoryPlatformSecretStore()
    settings = tiktok_settings(publishing=True)
    started = start_authorization(
        db_session,
        secret_store=store,
        settings=settings,
        workspace_id=UUID(auth["workspace_id"]),
        user_id=UUID(auth["user"]["id"]),
        publishing=True,
    )
    parsed = urlparse(started.authorization_url)
    query = parse_qs(parsed.query)
    state = query["state"][0]
    assert parsed.hostname == "www.tiktok.com"
    assert set(query["scope"][0].split(",")) == {
        TIKTOK_BASIC_SCOPE,
        TIKTOK_PROFILE_SCOPE,
        TIKTOK_STATS_SCOPE,
        TIKTOK_VIDEO_SCOPE,
        TIKTOK_PUBLISH_SCOPE,
    }
    assert query["disable_auto_auth"] == ["1"]
    assert "test-client-secret" not in started.authorization_url
    record = db_session.scalar(select(OAuthAuthorizationState))
    assert record is not None
    assert record.state_hash != state
    assert record.platform == "tiktok"

    claimed = claim_callback_state(
        db_session,
        secret_store=store,
        state=state,
        user_id=UUID(auth["user"]["id"]),
    )
    assert claimed.workspace_id == UUID(auth["workspace_id"])
    with pytest.raises(AuthorizationError):
        claim_callback_state(
            db_session,
            secret_store=store,
            state=state,
            user_id=UUID(auth["user"]["id"]),
        )

    with pytest.raises(InvalidRequestError):
        start_authorization(
            db_session,
            secret_store=store,
            settings=tiktok_settings(publishing=False),
            workspace_id=UUID(auth["workspace_id"]),
            user_id=UUID(auth["user"]["id"]),
            publishing=True,
        )


def test_tiktok_adapter_maps_metrics_and_publish_boundaries() -> None:
    transport = FakeTikTokTransport()
    adapter = TikTokAdapter(transport)
    request = ConnectAccountRequest(
        authorization_code=SecretStr("authorization-code"),
        redirect_uri="https://app.example.test/callback",
    )
    account = adapter.connect_account(request)
    credentials = account.credentials
    assert account.external_account_id == "tt-account-1"
    channel = adapter.sync_channel("tt-account-1", credentials)
    assert channel.handle == "creator"
    page = adapter.list_videos("tt-account-1", credentials)
    assert page.next_cursor == "1721476800000"
    assert page.items[0].title == "Launch video"
    assert page.items[0].duration_seconds == 42

    metric = adapter.sync_metrics("tt-video-1", credentials).items[0]
    assert metric.values["views"] == 1000
    assert metric.values["likes"] == 70
    assert "watch_time_seconds" in metric.unavailable_fields
    extension = metric.metadata["tiktok_extension"]
    assert extension["for_you_views"] is None
    assert extension["search_views"] is None

    account_metric = adapter.sync_account_metrics("tt-account-1", credentials).items[0]
    assert account_metric.values["follower_count"] == 321
    assert account_metric.period == "lifetime"

    invalid = adapter.validate_publish_request(
        PublishRequest(
            media_reference="http://127.0.0.1/private.mp4",
            title="Unsafe",
            options={"privacy_level": "SELF_ONLY", "duration_seconds": 42},
        ),
        credentials,
    )
    assert not invalid.valid
    publish_request = PublishRequest(
        media_reference="https://media.example.test/video.mp4",
        title="Launch",
        options={"privacy_level": "SELF_ONLY", "duration_seconds": 42},
    )
    assert adapter.validate_publish_request(publish_request, credentials).valid
    published = adapter.publish_video(
        publish_request,
        credentials,
        idempotency_key="opaque-key",
    )
    assert published.external_publish_id == "tt-publish-1"
    status = adapter.get_publish_status("tt-publish-1", credentials)
    assert status.status == "published"
    assert status.external_video_id == "tt-published-1"
    adapter.disconnect_account("tt-account-1", credentials)
    assert transport.revoked


def test_tiktok_http_transport_token_lifecycle_and_redacted_telemetry() -> None:
    recorded: list[tuple[str, str, int | None, RequestOutcome]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = request.content.decode()
        if request.url.path == "/v2/oauth/token/" and "authorization_code" in body:
            assert "test-client-secret" in body
            assert "authorization-code" in body
            return httpx2.Response(
                200,
                json={
                    "access_token": "first-token",
                    "refresh_token": "first-refresh",
                    "expires_in": 86400,
                    "scope": "user.info.basic,video.list",
                },
            )
        if request.url.path == "/v2/oauth/token/" and "refresh_token" in body:
            assert "first-refresh" in body
            return httpx2.Response(
                200,
                json={
                    "access_token": "second-token",
                    "refresh_token": "second-refresh",
                    "expires_in": 86400,
                    "scope": "user.info.basic,video.list",
                },
            )
        if request.url.path == "/v2/oauth/revoke/":
            assert "second-token" in body
            return httpx2.Response(200)
        raise AssertionError(f"Unexpected request: {request.url}")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    transport = TikTokHttpTransport(
        client_key="test-client-key",
        client_secret=SecretStr("test-client-secret"),
        client=client,
        request_recorder=lambda method, url, status, duration, outcome, request_id: (
            recorded.append((method, url, status, outcome))
        ),
    )
    credentials = transport.exchange_authorization_code(
        ConnectAccountRequest(
            authorization_code=SecretStr("authorization-code"),
            redirect_uri="https://app.example.test/callback",
        )
    )
    assert credentials.access_token.get_secret_value() == "first-token"
    refreshed = transport.refresh_credentials(credentials)
    assert refreshed.access_token.get_secret_value() == "second-token"
    transport.revoke_credentials("tt-account-1", refreshed)
    telemetry = repr(recorded)
    for secret in (
        "test-client-secret",
        "authorization-code",
        "first-token",
        "first-refresh",
        "second-token",
        "second-refresh",
    ):
        assert secret not in telemetry


def test_tiktok_http_transport_classifies_payload_rate_limits() -> None:
    client = httpx2.Client(
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(
                200,
                headers={"Retry-After": "30", "x-tt-logid": "request-1"},
                json={
                    "data": {},
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Provider detail must not escape",
                        "log_id": "request-1",
                    },
                },
            )
        )
    )
    transport = TikTokHttpTransport(
        client_key="test-client-key",
        client_secret=SecretStr("test-client-secret"),
        client=client,
    )
    with pytest.raises(PlatformRateLimitError) as raised:
        transport.get_profile(CredentialMaterial(access_token=SecretStr("token")))
    assert raised.value.retry_after_seconds == 30
    assert "Provider detail" not in raised.value.safe_message


def test_tiktok_routes_sync_authorize_and_disconnect(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client)
    store = InMemoryPlatformSecretStore()
    settings = tiktok_settings(publishing=True)

    def factory(quota_recorder=None, request_recorder=None) -> TikTokAdapter:
        del request_recorder
        return TikTokAdapter(FakeTikTokTransport(quota_recorder))

    app.dependency_overrides[get_platform_secret_store] = lambda: store
    app.dependency_overrides[get_tiktok_adapter_factory] = lambda: factory
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        denied = client.post(
            "/api/integrations/tiktok/oauth/start",
            headers=headers(auth),
            json={"publishing": True},
        )
        assert denied.status_code == 403
        started = client.post(
            "/api/integrations/tiktok/oauth/start",
            headers=headers(auth, write=True),
            json={"publishing": True},
        )
        assert started.status_code == 201
        state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][
            0
        ]
        completed = client.get(
            "/api/integrations/tiktok/oauth/callback",
            params={"state": state, "code": "authorization-code"},
        )
        assert completed.status_code == 200
        connection_id = completed.json()["id"]
        assert completed.json()["platform"] == "tiktok"

        videos = client.post(
            f"/api/integrations/tiktok/{connection_id}/sync/videos",
            headers=headers(auth, write=True),
        )
        assert videos.status_code == 200
        assert videos.json()["next_cursor"] == "1721476800000"
        video_id = videos.json()["videos"][0]["id"]

        metrics = client.post(
            (
                f"/api/integrations/tiktok/{connection_id}/sync/videos/"
                f"{video_id}/metrics"
            ),
            headers=headers(auth, write=True),
        )
        assert metrics.status_code == 200
        assert metrics.json()[0]["views"] == 1000
        assert metrics.json()[0]["tiktok_extension"]["for_you_views"] is None

        account_metrics = client.post(
            f"/api/integrations/tiktok/{connection_id}/sync/account-insights",
            headers=headers(auth, write=True),
        )
        assert account_metrics.status_code == 200
        assert account_metrics.json()[0]["values"]["follower_count"] == 321
        assert db_session.scalar(select(PlatformAccountMetricSnapshot)) is not None

        quota = client.get(
            f"/api/integrations/tiktok/{connection_id}/quota",
            headers=headers(auth),
        )
        assert quota.status_code == 200
        assert db_session.scalars(select(PlatformQuotaUsage)).all()

        other_client = TestClient(app)
        other_auth = register(other_client, "other@example.com")
        isolated = other_client.get(
            f"/api/integrations/tiktok/{connection_id}",
            headers=headers(other_auth),
        )
        assert isolated.status_code == 404

        disconnected = client.delete(
            f"/api/integrations/tiktok/{connection_id}",
            headers=headers(auth, write=True),
        )
        assert disconnected.status_code == 200
        assert disconnected.json()["status"] == "disconnected"
    finally:
        app.dependency_overrides.pop(get_platform_secret_store, None)
        app.dependency_overrides.pop(get_tiktok_adapter_factory, None)
        app.dependency_overrides.pop(get_settings, None)
