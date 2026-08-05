from typing import Any, Protocol

from app.platforms.contracts import (
    ConnectAccountRequest,
    CredentialMaterial,
    PublishRequest,
)


class TikTokTransport(Protocol):
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
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None: ...

    def get_profile(
        self,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def list_videos(
        self,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]: ...

    def get_video(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def get_creator_info(
        self,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def initialize_publish(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def get_publish_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...
