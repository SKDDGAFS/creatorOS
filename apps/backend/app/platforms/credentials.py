from typing import Protocol
from uuid import UUID

from app.models.channel import Platform
from app.platforms.contracts import CredentialMaterial


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
