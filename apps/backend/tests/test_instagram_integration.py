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
from app.platforms.instagram import (
    INSTAGRAM_BASIC_SCOPE,
    INSTAGRAM_INSIGHTS_SCOPE,
    INSTAGRAM_PUBLISH_SCOPE,
    InstagramAdapter,
    claim_callback_state,
    start_authorization,
)
from app.platforms.instagram.http_transport import InstagramHttpTransport
from app.platforms.runtime import (
    get_instagram_adapter_factory,
    get_platform_secret_store,
)
from app.services.errors import AuthorizationError, InvalidRequestError
from tests.test_core_apis import headers, register


def instagram_settings(*, publishing: bool = False) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        instagram_app_id="test-app-id",
        instagram_app_secret="test-app-secret",
        instagram_enable_publishing=publishing,
        instagram_api_version="v23.0",
    )


class FakeInstagramTransport:
    def __init__(self, quota_recorder=None) -> None:
        self._quota_recorder = quota_recorder
        self.revoked = False
        self.container_status = "FINISHED"

    def _quota(self, bucket: str) -> None:
        if self._quota_recorder is not None:
            self._quota_recorder(bucket, 1)

    def exchange_authorization_code(
        self,
        request: ConnectAccountRequest,
    ) -> CredentialMaterial:
        assert request.authorization_code.get_secret_value()
        return CredentialMaterial(
            access_token=SecretStr("instagram-access-token"),
            refresh_token=SecretStr("instagram-access-token"),
            expires_at=datetime.now(UTC) + timedelta(days=60),
            scopes=(
                INSTAGRAM_BASIC_SCOPE,
                INSTAGRAM_INSIGHTS_SCOPE,
                INSTAGRAM_PUBLISH_SCOPE,
            ),
        )

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial:
        return credentials.model_copy(
            update={
                "access_token": SecretStr("refreshed-instagram-token"),
                "refresh_token": SecretStr("refreshed-instagram-token"),
                "expires_at": datetime.now(UTC) + timedelta(days=60),
            }
        )

    def revoke_credentials(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        assert external_account_id == "ig-account-1"
        assert credentials.access_token.get_secret_value()
        self.revoked = True

    def get_profile(
        self,
        credentials: CredentialMaterial,
        *,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        self._quota("instagram_api_calls")
        assert credentials.access_token.get_secret_value()
        return {
            "id": account_id or "ig-account-1",
            "username": "creator",
            "name": "Creator",
            "account_type": "MEDIA_CREATOR",
            "followers_count": 321,
            "media_count": 1,
        }

    def list_media(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self._quota("instagram_api_calls")
        assert external_account_id == "ig-account-1"
        assert credentials.access_token.get_secret_value()
        assert cursor is None
        return {
            "data": [
                {
                    "id": "ig-media-1",
                    "caption": "Launch reel\nMore details",
                    "media_type": "VIDEO",
                    "media_product_type": "REELS",
                    "permalink": "https://www.instagram.com/reel/example/",
                    "timestamp": "2026-07-20T12:00:00+0000",
                }
            ],
            "paging": {"cursors": {"after": "media-next"}},
        }

    def get_media(
        self,
        external_media_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("instagram_api_calls")
        assert credentials.access_token.get_secret_value()
        return {
            "id": external_media_id,
            "caption": "Launch reel",
            "media_type": "VIDEO",
            "media_product_type": "REELS",
            "timestamp": "2026-07-20T12:00:00+0000",
        }

    def media_insights(
        self,
        external_media_id: str,
        media_product_type: str | None,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("instagram_insights_calls")
        assert external_media_id == "ig-media-1"
        assert media_product_type == "REELS"
        assert credentials.access_token.get_secret_value()
        values = {
            "views": 1000,
            "reach": 800,
            "likes": 70,
            "comments": 8,
            "shares": 12,
            "saved": 15,
            "total_interactions": 105,
            "ig_reels_video_view_total_time": 120000,
            "ig_reels_avg_watch_time": 12000,
        }
        return {
            "data": [
                {
                    "name": name,
                    "values": [{"value": value}],
                }
                for name, value in values.items()
            ]
        }

    def account_insights(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self._quota("instagram_insights_calls")
        assert external_account_id == "ig-account-1"
        assert credentials.access_token.get_secret_value()
        assert cursor is None
        end_time = "2026-07-28T00:00:00+0000"
        time_series = {
            "data": [
                {
                    "name": "reach",
                    "values": [{"value": 900, "end_time": end_time}],
                },
                {
                    "name": "profile_views",
                    "values": [{"value": 40, "end_time": end_time}],
                },
                {
                    "name": "follower_count",
                    "values": [{"value": 321, "end_time": end_time}],
                },
            ]
        }
        totals = {
            "data": [
                {"name": "accounts_engaged", "total_value": {"value": 120}},
                {"name": "total_interactions", "total_value": {"value": 150}},
                {
                    "name": "follows_and_unfollows",
                    "total_value": {
                        "value": {"follows": 8, "unfollows": 2}
                    },
                },
            ]
        }
        return time_series, totals

    def create_media_container(
        self,
        external_account_id: str,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("instagram_publishing_calls")
        assert external_account_id == "ig-account-1"
        assert request.media_reference.startswith("https://")
        assert credentials.access_token.get_secret_value()
        return {"id": "ig-container-1"}

    def get_container_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("instagram_publishing_calls")
        assert external_publish_id == "ig-container-1"
        assert credentials.access_token.get_secret_value()
        return {"id": external_publish_id, "status_code": self.container_status}

    def publish_container(
        self,
        external_account_id: str,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("instagram_publishing_calls")
        assert external_account_id == "ig-account-1"
        assert external_publish_id == "ig-container-1"
        assert credentials.access_token.get_secret_value()
        return {"id": "ig-published-1"}

    def publishing_limit(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        self._quota("instagram_publishing_calls")
        assert external_account_id == "ig-account-1"
        assert credentials.access_token.get_secret_value()
        return {
            "data": [
                {
                    "quota_usage": 4,
                    "config": {
                        "quota_total": 100,
                        "quota_duration": 86400,
                    },
                }
            ]
        }


def test_instagram_settings_scopes_and_one_time_state(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client)
    store = InMemoryPlatformSecretStore()
    settings = instagram_settings(publishing=True)
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
    assert parsed.hostname == "www.instagram.com"
    assert set(query["scope"][0].split(",")) == {
        INSTAGRAM_BASIC_SCOPE,
        INSTAGRAM_INSIGHTS_SCOPE,
        INSTAGRAM_PUBLISH_SCOPE,
    }
    assert "test-app-secret" not in started.authorization_url
    record = db_session.scalar(select(OAuthAuthorizationState))
    assert record is not None
    assert record.state_hash != state
    assert record.platform == "instagram"

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
            settings=instagram_settings(publishing=False),
            workspace_id=UUID(auth["workspace_id"]),
            user_id=UUID(auth["user"]["id"]),
            publishing=True,
        )


def test_instagram_adapter_maps_sync_insights_and_publishing() -> None:
    transport = FakeInstagramTransport()
    adapter = InstagramAdapter(transport)
    credentials = transport.exchange_authorization_code(
        ConnectAccountRequest(
            authorization_code=SecretStr("authorization-code"),
            redirect_uri="https://app.example.test/callback",
        )
    )
    account = adapter.connect_account(
        ConnectAccountRequest(
            authorization_code=SecretStr("authorization-code"),
            redirect_uri="https://app.example.test/callback",
        )
    )
    assert account.external_account_id == "ig-account-1"
    page = adapter.list_videos("ig-account-1", credentials)
    assert page.next_cursor == "media-next"
    assert page.items[0].title == "Launch reel"
    assert page.items[0].published_at is not None

    metric_page = adapter.sync_metrics("ig-media-1", credentials)
    metric = metric_page.items[0]
    assert metric.values["views"] == 1000
    assert metric.values["watch_time_seconds"] == 120
    extension = metric.metadata["instagram_extension"]
    assert extension["accounts_reached"] == 800
    assert extension["reels_tab_reach"] is None
    assert extension["feed_reach"] is None
    assert extension["explore_reach"] is None

    account_page = adapter.sync_account_metrics("ig-account-1", credentials)
    account_metric = account_page.items[0]
    assert account_metric.values["accounts_engaged"] == 120
    assert account_metric.values["follows"] == 8

    invalid = adapter.validate_publish_request(
        PublishRequest(
            media_reference="http://127.0.0.1/private.mp4",
            title="Unsafe",
        ),
        credentials,
    )
    assert not invalid.valid
    publish_request = PublishRequest(
        media_reference="https://media.example.test/reel.mp4",
        title="Launch",
        options={"media_type": "REELS", "share_to_feed": True},
    )
    assert adapter.validate_publish_request(publish_request, credentials).valid
    published = adapter.publish_video(
        publish_request,
        credentials,
        idempotency_key="opaque-key",
    )
    assert published.status == "published"
    assert published.external_video_id == "ig-published-1"
    status = adapter.get_publish_status("ig-container-1", credentials)
    assert status.status == "finished"
    assert adapter.get_publishing_limit("ig-account-1", credentials) == (
        4,
        100,
        86400,
    )
    adapter.disconnect_account("ig-account-1", credentials)
    assert transport.revoked


def test_instagram_http_transport_token_lifecycle_and_redacted_telemetry() -> None:
    recorded: list[tuple[str, str, int | None, RequestOutcome]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "api.instagram.com":
            body = request.content.decode()
            assert "test-app-secret" in body
            assert "authorization-code" in body
            return httpx2.Response(
                200,
                json={
                    "access_token": "short-token",
                    "user_id": "ig-account-1",
                    "permissions": [
                        INSTAGRAM_BASIC_SCOPE,
                        INSTAGRAM_INSIGHTS_SCOPE,
                    ],
                },
            )
        if request.url.path == "/access_token":
            assert request.url.params["access_token"] == "short-token"
            assert request.url.params["client_secret"] == "test-app-secret"
            return httpx2.Response(
                200,
                json={"access_token": "long-token", "expires_in": 5184000},
            )
        if request.url.path == "/refresh_access_token":
            assert request.url.params["access_token"] == "long-token"
            return httpx2.Response(
                200,
                json={"access_token": "refreshed-token", "expires_in": 5184000},
            )
        if request.url.path == "/v23.0/me/permissions":
            assert request.method == "DELETE"
            assert request.headers["authorization"] == "Bearer refreshed-token"
            return httpx2.Response(200, json={"success": True})
        raise AssertionError(f"Unexpected request: {request.url}")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    transport = InstagramHttpTransport(
        app_id="test-app-id",
        app_secret=SecretStr("test-app-secret"),
        api_version="v23.0",
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
    assert credentials.access_token.get_secret_value() == "long-token"
    assert credentials.refresh_token is not None
    refreshed = transport.refresh_credentials(credentials)
    assert refreshed.access_token.get_secret_value() == "refreshed-token"
    transport.revoke_credentials("ig-account-1", refreshed)
    telemetry = repr(recorded)
    assert "test-app-secret" not in telemetry
    assert "authorization-code" not in telemetry
    assert "short-token" not in telemetry
    assert "long-token" not in telemetry
    assert "refreshed-token" not in telemetry


def test_instagram_http_transport_classifies_rate_limits() -> None:
    client = httpx2.Client(
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(
                429,
                headers={"Retry-After": "30", "x-fb-request-id": "request-1"},
                json={
                    "error": {
                        "code": 4,
                        "message": "Provider detail must not escape",
                    }
                },
            )
        )
    )
    transport = InstagramHttpTransport(
        app_id="test-app-id",
        app_secret=SecretStr("test-app-secret"),
        api_version="v23.0",
        client=client,
    )
    with pytest.raises(PlatformRateLimitError) as raised:
        transport.get_profile(
            CredentialMaterial(access_token=SecretStr("token"))
        )
    assert raised.value.retry_after_seconds == 30
    assert "Provider detail" not in raised.value.safe_message


def test_instagram_routes_sync_and_disconnect(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client)
    store = InMemoryPlatformSecretStore()
    settings = instagram_settings(publishing=True)

    def factory(quota_recorder=None, request_recorder=None) -> InstagramAdapter:
        del request_recorder
        return InstagramAdapter(FakeInstagramTransport(quota_recorder))

    app.dependency_overrides[get_platform_secret_store] = lambda: store
    app.dependency_overrides[get_instagram_adapter_factory] = lambda: factory
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        denied = client.post(
            "/api/integrations/instagram/oauth/start",
            headers=headers(auth),
            json={"publishing": True},
        )
        assert denied.status_code == 403
        started = client.post(
            "/api/integrations/instagram/oauth/start",
            headers=headers(auth, write=True),
            json={"publishing": True},
        )
        assert started.status_code == 201
        state = parse_qs(urlparse(started.json()["authorization_url"]).query)[
            "state"
        ][0]
        completed = client.get(
            "/api/integrations/instagram/oauth/callback",
            params={"state": state, "code": "authorization-code"},
        )
        assert completed.status_code == 200
        connection_id = completed.json()["id"]
        assert completed.json()["platform"] == "instagram"

        videos = client.post(
            f"/api/integrations/instagram/{connection_id}/sync/videos",
            headers=headers(auth, write=True),
        )
        assert videos.status_code == 200
        assert videos.json()["next_cursor"] == "media-next"
        video_id = videos.json()["videos"][0]["id"]

        metrics = client.post(
            (
                f"/api/integrations/instagram/{connection_id}/sync/videos/"
                f"{video_id}/metrics"
            ),
            headers=headers(auth, write=True),
        )
        assert metrics.status_code == 200
        assert metrics.json()[0]["views"] == 1000
        assert metrics.json()[0]["instagram_extension"]["feed_reach"] is None

        account_metrics = client.post(
            (
                f"/api/integrations/instagram/{connection_id}/"
                "sync/account-insights"
            ),
            headers=headers(auth, write=True),
        )
        assert account_metrics.status_code == 200
        assert account_metrics.json()[0]["values"]["reach"] == 900
        assert db_session.scalar(
            select(PlatformAccountMetricSnapshot)
        ) is not None

        publishing_limit = client.get(
            (
                f"/api/integrations/instagram/{connection_id}/"
                "publishing-limit"
            ),
            headers=headers(auth),
        )
        assert publishing_limit.status_code == 200
        assert publishing_limit.json() == {
            "quota_usage": 4,
            "quota_total": 100,
            "quota_duration_seconds": 86400,
        }
        quota = client.get(
            f"/api/integrations/instagram/{connection_id}/quota",
            headers=headers(auth),
        )
        assert quota.status_code == 200
        assert db_session.scalars(select(PlatformQuotaUsage)).all()

        disconnected = client.delete(
            f"/api/integrations/instagram/{connection_id}",
            headers=headers(auth, write=True),
        )
        assert disconnected.status_code == 200
        assert disconnected.json()["status"] == "disconnected"
    finally:
        app.dependency_overrides.pop(get_platform_secret_store, None)
        app.dependency_overrides.pop(get_instagram_adapter_factory, None)
        app.dependency_overrides.pop(get_settings, None)
