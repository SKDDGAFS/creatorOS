from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.models.account import Account


@dataclass(frozen=True)
class PlatformAccountInfo:
    channel_id: str
    account_name: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class PublishResult:
    external_id: str
    status: str
    published_at: datetime | None = None


@dataclass(frozen=True)
class PlatformAnalytics:
    external_id: str
    captured_at: datetime
    metrics: dict[str, int | float | None]


class PlatformAdapter(Protocol):
    platform: str

    def connect(self, authorization_code: str, state: str) -> Account: ...

    def refresh_tokens(self, account: Account) -> Account: ...

    def get_account_info(self, account: Account) -> PlatformAccountInfo: ...

    def upload_video(
        self,
        account: Account,
        media_path: Path,
        metadata: dict[str, object],
    ) -> PublishResult: ...

    def schedule_post(
        self,
        account: Account,
        video_id: UUID,
        scheduled_at: datetime,
        metadata: dict[str, object],
    ) -> PublishResult: ...

    def fetch_analytics(
        self,
        account: Account,
        since: datetime,
        until: datetime,
    ) -> list[PlatformAnalytics]: ...

    def get_channel_metrics(
        self, account: Account
    ) -> dict[str, int | float | None]: ...

    def handle_errors(self, error: Exception) -> str: ...
