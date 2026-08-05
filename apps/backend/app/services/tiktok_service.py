from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.channel import Channel, Platform
from app.models.platform_integration import (
    ConnectionStatus,
    PlatformAccountMetricSnapshot,
    PlatformConnection,
    RequestOutcome,
)
from app.models.video import Video, VideoStatus
from app.models.video_metric import VideoMetric
from app.platforms.contracts import (
    ConnectAccountRequest,
    CredentialMaterial,
    RemoteMetricSnapshot,
)
from app.platforms.credentials import (
    CredentialStore,
    OAuthSecretStore,
    PlatformSecretStore,
)
from app.platforms.errors import (
    PlatformAdapterError,
    PlatformAuthenticationError,
    PlatformCredentialExpiredError,
    PlatformPermanentError,
    PlatformRateLimitError,
    PlatformTransientError,
)
from app.platforms.runtime import TikTokAdapterFactory
from app.platforms.tiktok import (
    OAuthStartResponse,
    claim_callback_state,
    start_authorization,
)
from app.platforms.tiktok.adapter import TikTokAdapter
from app.schemas.video_metric import (
    TikTokMetricExtensionCreate,
    VideoMetricCreate,
)
from app.services import platform_integration_service, video_service
from app.services.errors import (
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    RateLimitError,
    ResourceNotFoundError,
)


@dataclass(frozen=True)
class VideoSyncResult:
    videos: tuple[Video, ...]
    next_cursor: str | None


@dataclass
class QuotaAccumulator:
    _usage: dict[str, tuple[int, int]] = field(default_factory=dict)

    def record(self, quota_bucket: str, units: int) -> None:
        existing_units, existing_requests = self._usage.get(
            quota_bucket,
            (0, 0),
        )
        self._usage[quota_bucket] = (
            existing_units + units,
            existing_requests + 1,
        )

    def flush(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> None:
        for bucket, (units, request_count) in sorted(self._usage.items()):
            platform_integration_service.record_quota_usage(
                db,
                workspace_id=workspace_id,
                connection_id=connection_id,
                quota_bucket=bucket,
                units=units,
                request_count=request_count,
            )
        self._usage.clear()


@dataclass(frozen=True)
class RequestLogEntry:
    method: str
    url: str
    status_code: int | None
    duration_ms: int
    outcome: RequestOutcome
    provider_request_id: str | None


@dataclass
class RequestLogAccumulator:
    _entries: list[RequestLogEntry] = field(default_factory=list)

    def record(
        self,
        method: str,
        url: str,
        status_code: int | None,
        duration_ms: int,
        outcome: RequestOutcome,
        provider_request_id: str | None,
    ) -> None:
        self._entries.append(
            RequestLogEntry(
                method=method,
                url=url,
                status_code=status_code,
                duration_ms=duration_ms,
                outcome=outcome,
                provider_request_id=provider_request_id,
            )
        )

    def flush(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        connection_id: UUID,
    ) -> None:
        for entry in self._entries:
            platform_integration_service.record_request_log(
                db,
                workspace_id=workspace_id,
                connection_id=connection_id,
                operation_id=None,
                method=entry.method,
                url=entry.url,
                headers=None,
                body=None,
                status_code=entry.status_code,
                duration_ms=entry.duration_ms,
                outcome=entry.outcome,
                provider_request_id=entry.provider_request_id,
            )
        self._entries.clear()


def _flush_telemetry(
    db: Session,
    *,
    connection: PlatformConnection,
    quota: QuotaAccumulator,
    requests: RequestLogAccumulator,
) -> None:
    quota.flush(
        db,
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
    )
    requests.flush(
        db,
        workspace_id=connection.workspace_id,
        connection_id=connection.id,
    )


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(message) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(message) from exc


def _get_tiktok_connection(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    require_connected: bool = True,
) -> PlatformConnection:
    connection = platform_integration_service.get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    if connection.platform != Platform.TIKTOK.value:
        raise InvalidRequestError("Connection is not an TikTok connection")
    if require_connected and connection.status != ConnectionStatus.CONNECTED.value:
        raise ConflictError("TikTok connection must be reconnected")
    return connection


def _raise_adapter_error(
    db: Session,
    *,
    connection: PlatformConnection | None,
    error: PlatformAdapterError,
) -> None:
    if isinstance(error, PlatformCredentialExpiredError):
        if (
            connection is not None
            and connection.status != ConnectionStatus.DISCONNECTED.value
        ):
            connection.status = ConnectionStatus.RECONNECT_REQUIRED.value
            _commit(db, "Unable to update TikTok connection status")
        raise ConflictError(error.safe_message) from error
    if isinstance(error, PlatformRateLimitError):
        raise RateLimitError(error.safe_message) from error
    if isinstance(error, PlatformTransientError):
        raise PersistenceError(error.safe_message) from error
    if isinstance(error, PlatformAuthenticationError):
        raise AuthorizationError(error.safe_message) from error
    if isinstance(error, PlatformPermanentError):
        raise InvalidRequestError(error.safe_message) from error
    raise PersistenceError("TikTok request failed") from error


def _invoke[Result](
    db: Session,
    *,
    connection: PlatformConnection,
    secret_store: CredentialStore,
    adapter_factory: TikTokAdapterFactory,
    operation: Callable[[TikTokAdapter, CredentialMaterial], Result],
) -> Result:
    quota = QuotaAccumulator()
    requests = RequestLogAccumulator()
    adapter = adapter_factory(quota.record, requests.record)
    try:
        credentials = secret_store.load(connection.credential_reference)
    except ResourceNotFoundError as exc:
        connection.status = ConnectionStatus.RECONNECT_REQUIRED.value
        _commit(db, "Unable to update TikTok connection status")
        raise ConflictError(
            "TikTok credentials are unavailable; reconnect the account"
        ) from exc
    try:
        expires_at = credentials.expires_at
        if expires_at is not None and expires_at <= datetime.now(UTC) + timedelta(
            minutes=5
        ):
            credentials = adapter.refresh_credentials(credentials)
            secret_store.replace(connection.credential_reference, credentials)
            platform_integration_service.replace_credential_reference(
                db,
                workspace_id=connection.workspace_id,
                connection_id=connection.id,
                credential_reference=connection.credential_reference,
                scopes=credentials.scopes,
                token_expires_at=credentials.expires_at,
            )
        result = operation(adapter, credentials)
    except PlatformAdapterError as exc:
        _flush_telemetry(
            db,
            connection=connection,
            quota=quota,
            requests=requests,
        )
        _raise_adapter_error(db, connection=connection, error=exc)
    _flush_telemetry(
        db,
        connection=connection,
        quota=quota,
        requests=requests,
    )
    return result


def begin_authorization(
    db: Session,
    *,
    secret_store: OAuthSecretStore,
    settings: Settings,
    workspace_id: UUID,
    user_id: UUID,
    publishing: bool,
) -> OAuthStartResponse:
    return start_authorization(
        db,
        secret_store=secret_store,
        settings=settings,
        workspace_id=workspace_id,
        user_id=user_id,
        publishing=publishing,
    )


def complete_authorization(
    db: Session,
    *,
    secret_store: PlatformSecretStore,
    adapter_factory: TikTokAdapterFactory,
    state: str,
    authorization_code: str | None,
    provider_error: str | None,
    user_id: UUID,
) -> PlatformConnection:
    claimed = claim_callback_state(
        db,
        secret_store=secret_store,
        state=state,
        user_id=user_id,
    )
    quota = QuotaAccumulator()
    requests = RequestLogAccumulator()
    try:
        if provider_error is not None:
            raise AuthorizationError("TikTok authorization was not completed")
        if authorization_code is None or not authorization_code.strip():
            raise InvalidRequestError("TikTok authorization code is missing")
        adapter = adapter_factory(quota.record, requests.record)
        try:
            connected = adapter.connect_account(
                ConnectAccountRequest(
                    authorization_code=SecretStr(authorization_code),
                    redirect_uri=claimed.redirect_uri,
                )
            )
        except PlatformAdapterError as exc:
            _raise_adapter_error(db, connection=None, error=exc)

        credentials = connected.credentials
        if not credentials.scopes:
            credentials = credentials.model_copy(
                update={"scopes": claimed.requested_scopes}
            )
        if not set(claimed.requested_scopes).issubset(credentials.scopes):
            with suppress(PlatformAdapterError):
                adapter.disconnect_account(
                    connected.external_account_id,
                    credentials,
                )
            raise AuthorizationError(
                "Meta did not grant all requested TikTok permissions"
            )
        credential_reference = secret_store.store(
            workspace_id=claimed.workspace_id,
            platform=Platform.TIKTOK,
            credentials=credentials,
        )
        existing = db.scalar(
            select(PlatformConnection).where(
                PlatformConnection.workspace_id == claimed.workspace_id,
                PlatformConnection.platform == Platform.TIKTOK.value,
                PlatformConnection.external_account_id == connected.external_account_id,
            )
        )
        old_reference: str | None = None
        try:
            if existing is None:
                connection = platform_integration_service.create_connection(
                    db,
                    workspace_id=claimed.workspace_id,
                    user_id=claimed.user_id,
                    platform=Platform.TIKTOK,
                    external_account_id=connected.external_account_id,
                    display_name=connected.display_name,
                    credential_reference=credential_reference,
                    scopes=credentials.scopes,
                    token_expires_at=credentials.expires_at,
                )
            else:
                old_reference = existing.credential_reference
                connection = platform_integration_service.replace_credential_reference(
                    db,
                    workspace_id=claimed.workspace_id,
                    connection_id=existing.id,
                    credential_reference=credential_reference,
                    scopes=credentials.scopes,
                    token_expires_at=credentials.expires_at,
                )
                connection.display_name = connected.display_name
                _commit(db, "Unable to reconnect TikTok account")
        except Exception:
            secret_store.delete(credential_reference)
            raise
        if old_reference is not None and old_reference != credential_reference:
            secret_store.delete(old_reference)
        quota.flush(
            db,
            workspace_id=claimed.workspace_id,
            connection_id=connection.id,
        )
        requests.flush(
            db,
            workspace_id=claimed.workspace_id,
            connection_id=connection.id,
        )
        return connection
    finally:
        secret_store.delete_oauth_verifier(claimed.secret_reference)


def _upsert_channel(
    db: Session,
    *,
    connection: PlatformConnection,
    remote_id: str,
    name: str,
    handle: str | None,
) -> Channel:
    channel = db.scalar(
        select(Channel).where(
            Channel.platform == Platform.TIKTOK.value,
            Channel.platform_channel_id == remote_id,
        )
    )
    if channel is not None and channel.workspace_id != connection.workspace_id:
        raise ConflictError(
            "This TikTok account belongs to another CreatorOS workspace"
        )
    if channel is None:
        channel = Channel(
            user_id=connection.created_by_user_id,
            workspace_id=connection.workspace_id,
            platform=Platform.TIKTOK.value,
            platform_channel_id=remote_id,
            name=name[:255],
            handle=handle,
            is_active=True,
        )
        db.add(channel)
    else:
        channel.name = name[:255]
        channel.handle = handle
        channel.is_active = True
    _commit(db, "Unable to synchronize TikTok account")
    db.refresh(channel)
    return channel


def sync_channel(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    secret_store: CredentialStore,
    adapter_factory: TikTokAdapterFactory,
) -> Channel:
    connection = _get_tiktok_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    remote = _invoke(
        db,
        connection=connection,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
        operation=lambda adapter, credentials: adapter.sync_channel(
            connection.external_account_id,
            credentials,
        ),
    )
    return _upsert_channel(
        db,
        connection=connection,
        remote_id=remote.external_channel_id,
        name=remote.name,
        handle=remote.handle,
    )


def sync_videos(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    secret_store: CredentialStore,
    adapter_factory: TikTokAdapterFactory,
) -> VideoSyncResult:
    connection = _get_tiktok_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    channel = sync_channel(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
    )
    cursor_record = platform_integration_service.get_cursor(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        resource_type="videos",
    )
    page = _invoke(
        db,
        connection=connection,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
        operation=lambda adapter, credentials: adapter.list_videos(
            connection.external_account_id,
            credentials,
            cursor=cursor_record.cursor if cursor_record is not None else None,
        ),
    )
    synchronized: list[Video] = []
    for remote in page.items:
        video = db.scalar(
            select(Video).where(
                Video.channel_id == channel.id,
                Video.platform_video_id == remote.external_video_id,
            )
        )
        if video is None:
            video = Video(
                channel_id=channel.id,
                platform_video_id=remote.external_video_id,
                title=remote.title,
            )
            db.add(video)
        video.title = remote.title
        video.description = remote.description
        video.duration_seconds = remote.duration_seconds
        video.status = (
            VideoStatus.PUBLISHED.value
            if remote.published_at is not None
            else VideoStatus.DRAFT.value
        )
        video.published_at = remote.published_at
        synchronized.append(video)
    _commit(db, "Unable to synchronize TikTok media")
    for video in synchronized:
        db.refresh(video)
    platform_integration_service.save_cursor(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        resource_type="videos",
        cursor=page.next_cursor,
    )
    return VideoSyncResult(
        videos=tuple(synchronized),
        next_cursor=page.next_cursor,
    )


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _metric_payload(snapshot: RemoteMetricSnapshot) -> VideoMetricCreate:
    extension_data = snapshot.metadata.get("tiktok_extension")
    extension = (
        TikTokMetricExtensionCreate.model_validate(extension_data)
        if isinstance(extension_data, dict)
        else TikTokMetricExtensionCreate()
    )
    values = snapshot.values
    try:
        return VideoMetricCreate(
            captured_at=snapshot.captured_at,
            views=_integer(values.get("views")),
            unique_viewers=_integer(values.get("unique_viewers")),
            engaged_views=_integer(values.get("engaged_views")),
            likes=_integer(values.get("likes")),
            comments=_integer(values.get("comments")),
            shares=_integer(values.get("shares")),
            saves=_integer(values.get("saves")),
            watch_time_seconds=_integer(values.get("watch_time_seconds")),
            average_view_duration_seconds=_integer(
                values.get("average_view_duration_seconds")
            ),
            tiktok_extension=extension,
        )
    except ValidationError as exc:
        raise InvalidRequestError(
            "TikTok returned analytics outside supported ranges"
        ) from exc


def sync_metrics(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    video_id: UUID,
    secret_store: CredentialStore,
    adapter_factory: TikTokAdapterFactory,
) -> tuple[VideoMetric, ...]:
    connection = _get_tiktok_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    video = video_service.get_video(
        db,
        video_id,
        workspace_id=workspace_id,
    )
    if (
        video.channel.platform != Platform.TIKTOK.value
        or video.channel.platform_channel_id != connection.external_account_id
        or video.platform_video_id is None
    ):
        raise InvalidRequestError("Video does not belong to this TikTok connection")
    resource_type = f"metrics.{video.platform_video_id.lower()}"
    cursor_record = platform_integration_service.get_cursor(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        resource_type=resource_type,
    )
    page = _invoke(
        db,
        connection=connection,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
        operation=lambda adapter, credentials: adapter.sync_metrics(
            video.platform_video_id or "",
            credentials,
            cursor=cursor_record.cursor if cursor_record is not None else None,
        ),
    )
    metrics = tuple(
        video_service.create_metric(
            db,
            video.id,
            _metric_payload(snapshot),
            workspace_id=workspace_id,
        )
        for snapshot in page.items
    )
    platform_integration_service.save_cursor(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        resource_type=resource_type,
        cursor=page.next_cursor,
    )
    return metrics


def sync_account_metrics(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    secret_store: CredentialStore,
    adapter_factory: TikTokAdapterFactory,
) -> tuple[PlatformAccountMetricSnapshot, ...]:
    connection = _get_tiktok_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    cursor_record = platform_integration_service.get_cursor(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        resource_type="account_metrics",
    )
    page = _invoke(
        db,
        connection=connection,
        secret_store=secret_store,
        adapter_factory=adapter_factory,
        operation=lambda adapter, credentials: adapter.sync_account_metrics(
            connection.external_account_id,
            credentials,
            cursor=cursor_record.cursor if cursor_record is not None else None,
        ),
    )
    synchronized: list[PlatformAccountMetricSnapshot] = []
    for remote in page.items:
        if remote.external_account_id != connection.external_account_id:
            raise InvalidRequestError("TikTok returned insights for another account")
        snapshot = db.scalar(
            select(PlatformAccountMetricSnapshot).where(
                PlatformAccountMetricSnapshot.connection_id == connection.id,
                PlatformAccountMetricSnapshot.captured_at == remote.captured_at,
                PlatformAccountMetricSnapshot.period == remote.period,
            )
        )
        if snapshot is None:
            snapshot = PlatformAccountMetricSnapshot(
                connection_id=connection.id,
                captured_at=remote.captured_at,
                period=remote.period,
                values=dict(remote.values),
                unavailable_fields=list(remote.unavailable_fields),
                provider_metadata=dict(remote.metadata),
            )
            db.add(snapshot)
        synchronized.append(snapshot)
    _commit(db, "Unable to synchronize TikTok account insights")
    for snapshot in synchronized:
        db.refresh(snapshot)
    platform_integration_service.save_cursor(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        resource_type="account_metrics",
        cursor=page.next_cursor,
    )
    return tuple(synchronized)


def disconnect(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    secret_store: CredentialStore,
    adapter_factory: TikTokAdapterFactory,
) -> PlatformConnection:
    connection = _get_tiktok_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        require_connected=False,
    )
    if connection.status == ConnectionStatus.DISCONNECTED.value:
        return connection
    try:
        credentials = secret_store.load(connection.credential_reference)
    except ResourceNotFoundError as exc:
        connection.status = ConnectionStatus.RECONNECT_REQUIRED.value
        _commit(db, "Unable to update TikTok connection status")
        raise ConflictError(
            "TikTok credentials are unavailable; reconnect before disconnecting"
        ) from exc
    adapter = adapter_factory(None, None)
    try:
        adapter.disconnect_account(
            connection.external_account_id,
            credentials,
        )
    except PlatformCredentialExpiredError:
        pass
    except PlatformAdapterError as exc:
        _raise_adapter_error(db, connection=connection, error=exc)
    connection = platform_integration_service.mark_connection_status(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        status=ConnectionStatus.DISCONNECTED,
    )
    secret_store.delete(connection.credential_reference)
    return connection


def get_connection(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
) -> PlatformConnection:
    return _get_tiktok_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        require_connected=False,
    )
