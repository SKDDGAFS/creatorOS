from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
)

from app.models.channel import Platform


class AdapterModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CredentialMaterial(AdapterModel):
    access_token: SecretStr
    refresh_token: SecretStr | None = None
    expires_at: AwareDatetime | None = None
    scopes: tuple[str, ...] = ()


class ConnectAccountRequest(AdapterModel):
    authorization_code: SecretStr
    redirect_uri: str = Field(min_length=1, max_length=2000)
    code_verifier: SecretStr | None = None


class ConnectedAccount(AdapterModel):
    external_account_id: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    credentials: CredentialMaterial


class RemoteChannel(AdapterModel):
    external_channel_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=500)
    handle: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RemoteVideo(AdapterModel):
    external_video_id: str = Field(min_length=1, max_length=255)
    external_channel_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    published_at: AwareDatetime | None = None
    duration_seconds: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


MetricValue = int | float | str | bool | None


class RemoteMetricSnapshot(AdapterModel):
    external_video_id: str = Field(min_length=1, max_length=255)
    captured_at: AwareDatetime
    values: dict[str, MetricValue] = Field(default_factory=dict)
    unavailable_fields: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class RemoteAccountMetricSnapshot(AdapterModel):
    external_account_id: str = Field(min_length=1, max_length=255)
    captured_at: AwareDatetime
    period: str = Field(min_length=1, max_length=30)
    values: dict[str, MetricValue] = Field(default_factory=dict)
    unavailable_fields: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublishRequest(AdapterModel):
    media_reference: str = Field(min_length=1, max_length=1000)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    scheduled_for: AwareDatetime | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class PublishValidation(AdapterModel):
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class PublishResult(AdapterModel):
    external_publish_id: str = Field(min_length=1, max_length=255)
    external_video_id: str | None = Field(default=None, max_length=255)
    status: str = Field(min_length=1, max_length=100)
    provider_request_id: str | None = Field(default=None, max_length=255)


class PublishStatus(AdapterModel):
    external_publish_id: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=100)
    external_video_id: str | None = Field(default=None, max_length=255)
    updated_at: datetime
    safe_message: str | None = Field(default=None, max_length=500)


class AdapterPage[PageItem: AdapterModel](AdapterModel):
    items: tuple[PageItem, ...]
    next_cursor: str | None = Field(default=None, max_length=2000)


class PlatformAdapter(Protocol):
    platform: Platform

    def connect_account(
        self,
        request: ConnectAccountRequest,
    ) -> ConnectedAccount: ...

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial: ...

    def disconnect_account(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None: ...

    def list_channels(
        self,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteChannel]: ...

    def sync_channel(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteChannel: ...

    def list_videos(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteVideo]: ...

    def sync_video(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteVideo: ...

    def sync_metrics(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteMetricSnapshot]: ...

    def sync_account_metrics(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteAccountMetricSnapshot]: ...

    def validate_publish_request(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> PublishValidation: ...

    def publish_video(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
        *,
        idempotency_key: str,
    ) -> PublishResult: ...

    def get_publish_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishStatus: ...

    def delete_or_revoke_connection(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None: ...
