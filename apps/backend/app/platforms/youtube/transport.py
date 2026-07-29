from typing import Any, Protocol

from app.platforms.contracts import (
    ConnectAccountRequest,
    CredentialMaterial,
    PublishRequest,
    PublishResult,
    PublishStatus,
)


class YouTubeTransport(Protocol):
    def exchange_authorization_code(
        self,
        request: ConnectAccountRequest,
    ) -> CredentialMaterial: ...

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial: ...

    def revoke_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> None: ...

    def list_channels(
        self,
        credentials: CredentialMaterial,
        *,
        channel_id: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]: ...

    def list_upload_items(
        self,
        uploads_playlist_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]: ...

    def list_videos(
        self,
        video_ids: tuple[str, ...],
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def analytics_activity(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]: ...

    def analytics_retention(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def analytics_traffic_sources(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def analytics_subscriber_status(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def upload_video(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> PublishResult: ...

    def get_upload_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishStatus: ...
