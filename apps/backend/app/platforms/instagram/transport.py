from typing import Any, Protocol

from app.platforms.contracts import (
    ConnectAccountRequest,
    CredentialMaterial,
    PublishRequest,
)


class InstagramTransport(Protocol):
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
        *,
        account_id: str | None = None,
    ) -> dict[str, Any]: ...

    def list_media(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]: ...

    def get_media(
        self,
        external_media_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def media_insights(
        self,
        external_media_id: str,
        media_product_type: str | None,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def account_insights(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def create_media_container(
        self,
        external_account_id: str,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def get_container_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def publish_container(
        self,
        external_account_id: str,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...

    def publishing_limit(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]: ...
