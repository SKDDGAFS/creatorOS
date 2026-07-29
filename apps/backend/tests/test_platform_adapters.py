import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.models.channel import Platform
from app.models.platform_integration import (
    ConnectionStatus,
    RequestOutcome,
)
from app.platforms import (
    AdapterPage,
    ConnectAccountRequest,
    ConnectedAccount,
    CredentialMaterial,
    PlatformAdapterRegistry,
    PlatformCapabilityError,
    PlatformRateLimitError,
    PublishRequest,
    PublishResult,
    PublishStatus,
    PublishValidation,
    RemoteAccountMetricSnapshot,
    RemoteChannel,
    RemoteMetricSnapshot,
    RemoteVideo,
)
from app.platforms.redaction import REDACTED, safe_request_metadata
from app.services import platform_integration_service
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    ResourceNotFoundError,
)
from tests.test_core_apis import register


class FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[str, CredentialMaterial] = {}

    def store(
        self,
        *,
        workspace_id: UUID,
        platform: Platform,
        credentials: CredentialMaterial,
    ) -> str:
        reference = f"memory://{workspace_id}/{platform.value}/{uuid4()}"
        self.values[reference] = credentials
        return reference

    def load(self, reference: str) -> CredentialMaterial:
        return self.values[reference]

    def replace(
        self,
        reference: str,
        credentials: CredentialMaterial,
    ) -> None:
        self.values[reference] = credentials

    def delete(self, reference: str) -> None:
        del self.values[reference]


class FakeAdapter:
    platform = Platform.YOUTUBE

    def connect_account(
        self,
        request: ConnectAccountRequest,
    ) -> ConnectedAccount:
        assert request.authorization_code.get_secret_value()
        return ConnectedAccount(
            external_account_id="account-1",
            display_name="Creator",
            credentials=CredentialMaterial(
                access_token=SecretStr("access-token"),
                refresh_token=SecretStr("refresh-token"),
                scopes=("read", "publish"),
            ),
        )

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial:
        assert credentials.access_token.get_secret_value()
        return credentials.model_copy(
            update={"access_token": SecretStr("refreshed-access-token")}
        )

    def disconnect_account(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        assert external_account_id
        assert credentials.access_token.get_secret_value()

    def list_channels(
        self,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteChannel]:
        del credentials, cursor
        return AdapterPage(
            items=(
                RemoteChannel(
                    external_channel_id="channel-1",
                    name="Creator",
                ),
            ),
            next_cursor="channels-next",
        )

    def sync_channel(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteChannel:
        del credentials
        return RemoteChannel(
            external_channel_id=external_channel_id,
            name="Creator",
        )

    def list_videos(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteVideo]:
        del credentials, cursor
        return AdapterPage(
            items=(
                RemoteVideo(
                    external_video_id="video-1",
                    external_channel_id=external_channel_id,
                    title="Video",
                ),
            ),
            next_cursor=None,
        )

    def sync_video(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteVideo:
        del credentials
        return RemoteVideo(
            external_video_id=external_video_id,
            external_channel_id="channel-1",
            title="Video",
        )

    def sync_metrics(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteMetricSnapshot]:
        del credentials, cursor
        return AdapterPage(
            items=(
                RemoteMetricSnapshot(
                    external_video_id=external_video_id,
                    captured_at=datetime.now(UTC),
                    values={"views": 100, "unsupported": None},
                    unavailable_fields=("unsupported",),
                ),
            ),
            next_cursor="metrics-next",
        )

    def sync_account_metrics(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteAccountMetricSnapshot]:
        del credentials, cursor
        return AdapterPage(
            items=(
                RemoteAccountMetricSnapshot(
                    external_account_id=external_account_id,
                    captured_at=datetime.now(UTC),
                    period="day",
                    values={"reach": 100},
                ),
            ),
            next_cursor=None,
        )

    def validate_publish_request(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> PublishValidation:
        del credentials
        return PublishValidation(valid=bool(request.media_reference))

    def publish_video(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
        *,
        idempotency_key: str,
    ) -> PublishResult:
        del request, credentials
        assert idempotency_key
        return PublishResult(
            external_publish_id="publish-1",
            status="processing",
        )

    def get_publish_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishStatus:
        del credentials
        return PublishStatus(
            external_publish_id=external_publish_id,
            status="published",
            external_video_id="video-1",
            updated_at=datetime.now(UTC),
        )

    def delete_or_revoke_connection(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        self.disconnect_account(external_account_id, credentials)


def ids(auth: dict) -> tuple[UUID, UUID]:
    return UUID(auth["workspace_id"]), UUID(auth["user"]["id"])


def create_connection(
    db: Session,
    auth: dict,
    *,
    platform: Platform = Platform.YOUTUBE,
    account_id: str = "account-1",
):
    workspace_id, user_id = ids(auth)
    return platform_integration_service.create_connection(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        platform=platform,
        external_account_id=account_id,
        display_name="Creator",
        credential_reference=f"vault://{platform.value}/{account_id}",
        scopes=("publish", "read", "read"),
        token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_adapter_contract_covers_sync_and_publish_without_network() -> None:
    adapter = FakeAdapter()
    request = ConnectAccountRequest(
        authorization_code=SecretStr("one-time-code"),
        redirect_uri="http://127.0.0.1/callback",
    )
    account = adapter.connect_account(request)
    credentials = adapter.refresh_credentials(account.credentials)

    assert adapter.list_channels(credentials).next_cursor == "channels-next"
    assert adapter.sync_channel("channel-1", credentials).name == "Creator"
    assert adapter.list_videos(
        "channel-1",
        credentials,
    ).items[0].external_video_id == "video-1"
    assert adapter.sync_video(
        "video-1",
        credentials,
    ).external_channel_id == "channel-1"
    metric = adapter.sync_metrics("video-1", credentials).items[0]
    assert metric.values["unsupported"] is None
    assert metric.unavailable_fields == ("unsupported",)

    publish_request = PublishRequest(
        media_reference="media://asset-1",
        title="Approved content",
    )
    assert adapter.validate_publish_request(
        publish_request,
        credentials,
    ).valid
    published = adapter.publish_video(
        publish_request,
        credentials,
        idempotency_key="publish-key-1",
    )
    assert adapter.get_publish_status(
        published.external_publish_id,
        credentials,
    ).status == "published"
    adapter.disconnect_account(account.external_account_id, credentials)
    adapter.delete_or_revoke_connection(
        account.external_account_id,
        credentials,
    )


def test_adapter_registry_and_error_classification() -> None:
    registry = PlatformAdapterRegistry()
    adapter = FakeAdapter()
    registry.register(adapter)

    assert registry.get(Platform.YOUTUBE) is adapter
    assert registry.platforms == frozenset({Platform.YOUTUBE})
    with pytest.raises(ConflictError):
        registry.register(FakeAdapter())
    with pytest.raises(ResourceNotFoundError):
        registry.get(Platform.TIKTOK)

    limited = PlatformRateLimitError(
        "quota",
        "Provider quota reached",
        retry_after_seconds=60,
    )
    unsupported = PlatformCapabilityError(
        "unsupported",
        "Metric is unavailable",
    )
    assert limited.retryable
    assert limited.retry_after_seconds == 60
    assert not unsupported.retryable


def test_credential_store_keeps_secrets_out_of_connection_rows(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "adapter-credentials@example.com")
    workspace_id, _ = ids(auth)
    store = FakeCredentialStore()
    credentials = CredentialMaterial(
        access_token=SecretStr("raw-access-token"),
        refresh_token=SecretStr("raw-refresh-token"),
    )
    reference = store.store(
        workspace_id=workspace_id,
        platform=Platform.YOUTUBE,
        credentials=credentials,
    )
    connection = platform_integration_service.create_connection(
        db_session,
        workspace_id=workspace_id,
        user_id=ids(auth)[1],
        platform=Platform.YOUTUBE,
        external_account_id="secure-account",
        display_name="Secure Creator",
        credential_reference=reference,
        scopes=("read",),
        token_expires_at=None,
    )

    serialized = " ".join(
        str(value)
        for value in connection.__dict__.values()
        if not str(value).startswith("<")
    )
    assert "raw-access-token" not in serialized
    assert "raw-refresh-token" not in serialized
    assert not hasattr(connection, "access_token")
    assert store.load(reference).access_token.get_secret_value() == (
        "raw-access-token"
    )


def test_connections_are_workspace_scoped_and_unique(
    client: TestClient,
    db_session: Session,
) -> None:
    first = register(client, "adapter-first@example.com")
    connection = create_connection(db_session, first)
    with pytest.raises(ConflictError):
        create_connection(db_session, first)

    client.cookies.clear()
    second = register(client, "adapter-second@example.com")
    with pytest.raises(ResourceNotFoundError):
        platform_integration_service.get_connection(
            db_session,
            workspace_id=ids(second)[0],
            connection_id=connection.id,
        )
    assert platform_integration_service.list_connections(
        db_session,
        workspace_id=ids(second)[0],
        platform=None,
        include_disconnected=False,
    ) == []


def test_cursor_persistence_updates_one_resource_record(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "adapter-cursor@example.com")
    connection = create_connection(db_session, auth)
    first = platform_integration_service.save_cursor(
        db_session,
        workspace_id=ids(auth)[0],
        connection_id=connection.id,
        resource_type="videos",
        cursor="page-1",
    )
    updated = platform_integration_service.save_cursor(
        db_session,
        workspace_id=ids(auth)[0],
        connection_id=connection.id,
        resource_type="videos",
        cursor="page-2",
    )
    loaded = platform_integration_service.get_cursor(
        db_session,
        workspace_id=ids(auth)[0],
        connection_id=connection.id,
        resource_type="videos",
    )

    assert first.id == updated.id
    assert loaded is not None
    assert loaded.cursor == "page-2"
    with pytest.raises(InvalidRequestError):
        platform_integration_service.save_cursor(
            db_session,
            workspace_id=ids(auth)[0],
            connection_id=connection.id,
            resource_type="videos",
            cursor="x" * 2001,
        )


def test_operations_are_idempotent_and_fingerprint_bound(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "adapter-operation@example.com")
    connection = create_connection(db_session, auth)
    workspace_id = ids(auth)[0]
    operation, created = platform_integration_service.begin_operation(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        operation_type="publish_video",
        idempotency_key="operation-key-1",
        request={"video_id": "video-1", "caption": "Hello"},
    )
    repeated, repeated_created = platform_integration_service.begin_operation(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        operation_type="publish_video",
        idempotency_key="operation-key-1",
        request={"caption": "Hello", "video_id": "video-1"},
    )

    assert created
    assert not repeated_created
    assert repeated.id == operation.id
    assert operation.idempotency_key_hash != "operation-key-1"
    with pytest.raises(ConflictError):
        platform_integration_service.begin_operation(
            db_session,
            workspace_id=workspace_id,
            connection_id=connection.id,
            operation_type="publish_video",
            idempotency_key="operation-key-1",
            request={"video_id": "video-2"},
        )
    completed = platform_integration_service.complete_operation(
        db_session,
        workspace_id=workspace_id,
        operation_id=operation.id,
        external_resource_id="provider-video-1",
    )
    assert completed.status == "succeeded"


def test_request_logging_redacts_secrets_and_url_queries(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "adapter-log@example.com")
    connection = create_connection(db_session, auth)
    workspace_id = ids(auth)[0]
    operation, _ = platform_integration_service.begin_operation(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        operation_type="sync_metrics",
        idempotency_key="request-log-key",
        request={"video_id": "video-1"},
    )
    log = platform_integration_service.record_request_log(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        operation_id=operation.id,
        method="post",
        url=(
            "https://api.example.com/v1/metrics"
            "?access_token=query-secret&cursor=cursor-secret"
        ),
        headers={
            "Authorization": "Bearer header-secret",
            "X-Request-ID": "safe-request-id",
            "Cookie": "session=cookie-secret",
        },
        body={
            "video_id": "video-1",
            "refresh_token": "body-secret",
            "nested": {"client-secret": "nested-secret"},
        },
        status_code=200,
        duration_ms=42,
        outcome=RequestOutcome.SUCCEEDED,
        provider_request_id="provider-request-1",
    )
    serialized = json.dumps(log.request_metadata)

    assert log.method == "POST"
    assert log.host == "api.example.com"
    assert log.path == "/v1/metrics"
    assert log.request_metadata["headers"]["Authorization"] == REDACTED
    assert log.request_metadata["body"]["refresh_token"] == REDACTED
    assert log.request_metadata["body"]["nested"]["client-secret"] == REDACTED
    for secret in (
        "query-secret",
        "cursor-secret",
        "header-secret",
        "cookie-secret",
        "body-secret",
        "nested-secret",
    ):
        assert secret not in serialized

    metadata = safe_request_metadata(
        method="post",
        url="https://user:password@example.com/path?code=query-secret",
        body=ConnectAccountRequest(
            authorization_code=SecretStr("authorization-secret"),
            redirect_uri="https://app.example.com/callback",
        ),
    )
    assert "authorization-secret" not in json.dumps(metadata)
    assert "password" not in json.dumps(metadata)


def test_connection_status_lifecycle_is_terminal_after_disconnect(
    client: TestClient,
    db_session: Session,
) -> None:
    auth = register(client, "adapter-status@example.com")
    connection = create_connection(db_session, auth)
    workspace_id = ids(auth)[0]
    expired = platform_integration_service.mark_connection_status(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        status=ConnectionStatus.EXPIRED,
    )
    assert expired.status == "expired"
    disconnected = platform_integration_service.mark_connection_status(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        status=ConnectionStatus.DISCONNECTED,
    )
    assert disconnected.disconnected_at is not None
    with pytest.raises(ConflictError):
        platform_integration_service.mark_connection_status(
            db_session,
            workspace_id=workspace_id,
            connection_id=connection.id,
            status=ConnectionStatus.CONNECTED,
        )
    reconnected = platform_integration_service.replace_credential_reference(
        db_session,
        workspace_id=workspace_id,
        connection_id=connection.id,
        credential_reference="vault://youtube/account-1/reconnected",
        scopes=("read",),
        token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert reconnected.status == "connected"
    assert reconnected.disconnected_at is None
