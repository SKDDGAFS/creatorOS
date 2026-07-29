import secrets
from threading import RLock
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr

from app.models.channel import Platform
from app.platforms.contracts import CredentialMaterial
from app.services.errors import ResourceNotFoundError


class CredentialStore(Protocol):
    """Secret-storage boundary; implementations must encrypt at rest."""

    def store(
        self,
        *,
        workspace_id: UUID,
        platform: Platform,
        credentials: CredentialMaterial,
    ) -> str: ...

    def load(self, reference: str) -> CredentialMaterial: ...

    def replace(
        self,
        reference: str,
        credentials: CredentialMaterial,
    ) -> None: ...

    def delete(self, reference: str) -> None: ...


class OAuthVerifierMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_verifier: SecretStr


class OAuthSecretStore(Protocol):
    def store_oauth_verifier(
        self,
        *,
        workspace_id: UUID,
        platform: Platform,
        verifier: OAuthVerifierMaterial,
    ) -> str: ...

    def load_oauth_verifier(
        self,
        reference: str,
    ) -> OAuthVerifierMaterial: ...

    def delete_oauth_verifier(self, reference: str) -> None: ...


class PlatformSecretStore(CredentialStore, OAuthSecretStore, Protocol):
    pass


class InMemoryPlatformSecretStore:
    """Local/test-only volatile store; never use as production persistence."""

    def __init__(self) -> None:
        self._credentials: dict[str, CredentialMaterial] = {}
        self._verifiers: dict[str, OAuthVerifierMaterial] = {}
        self._lock = RLock()

    @staticmethod
    def _reference(kind: str, platform: Platform) -> str:
        return (
            f"memory://{kind}/{platform.value}/"
            f"{secrets.token_urlsafe(24)}"
        )

    def store(
        self,
        *,
        workspace_id: UUID,
        platform: Platform,
        credentials: CredentialMaterial,
    ) -> str:
        del workspace_id
        reference = self._reference("credentials", platform)
        with self._lock:
            self._credentials[reference] = credentials
        return reference

    def load(self, reference: str) -> CredentialMaterial:
        with self._lock:
            try:
                return self._credentials[reference]
            except KeyError as exc:
                raise ResourceNotFoundError(
                    "Platform credentials are unavailable"
                ) from exc

    def replace(
        self,
        reference: str,
        credentials: CredentialMaterial,
    ) -> None:
        with self._lock:
            if reference not in self._credentials:
                raise ResourceNotFoundError(
                    "Platform credentials are unavailable"
                )
            self._credentials[reference] = credentials

    def delete(self, reference: str) -> None:
        with self._lock:
            self._credentials.pop(reference, None)

    def store_oauth_verifier(
        self,
        *,
        workspace_id: UUID,
        platform: Platform,
        verifier: OAuthVerifierMaterial,
    ) -> str:
        del workspace_id
        reference = self._reference("oauth", platform)
        with self._lock:
            self._verifiers[reference] = verifier
        return reference

    def load_oauth_verifier(
        self,
        reference: str,
    ) -> OAuthVerifierMaterial:
        with self._lock:
            try:
                return self._verifiers[reference]
            except KeyError as exc:
                raise ResourceNotFoundError(
                    "OAuth verifier is unavailable"
                ) from exc

    def delete_oauth_verifier(self, reference: str) -> None:
        with self._lock:
            self._verifiers.pop(reference, None)
