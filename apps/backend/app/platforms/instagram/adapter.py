from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from app.models.channel import Platform
from app.platforms.contracts import (
    AdapterPage,
    ConnectAccountRequest,
    ConnectedAccount,
    CredentialMaterial,
    PublishRequest,
    PublishResult,
    PublishStatus,
    PublishValidation,
    RemoteAccountMetricSnapshot,
    RemoteChannel,
    RemoteMetricSnapshot,
    RemoteVideo,
)
from app.platforms.errors import PlatformPermanentError
from app.platforms.instagram.oauth import INSTAGRAM_PUBLISH_SCOPE
from app.platforms.instagram.transport import InstagramTransport


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    return (
        [item for item in data if isinstance(item, dict)]
        if isinstance(data, list)
        else []
    )


def _next_cursor(payload: dict[str, Any]) -> str | None:
    paging = payload.get("paging")
    if not isinstance(paging, dict):
        return None
    cursors = paging.get("cursors")
    if not isinstance(cursors, dict):
        return None
    value = cursors.get("after")
    return value if isinstance(value, str) and value else None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except InvalidOperation:
            return None
        return int(parsed) if parsed == parsed.to_integral() else float(parsed)
    return None


def _insight_value(item: dict[str, Any]) -> Any:
    total_value = item.get("total_value")
    if isinstance(total_value, dict) and "value" in total_value:
        return total_value["value"]
    values = item.get("values")
    if isinstance(values, list) and values:
        latest = values[-1]
        if isinstance(latest, dict):
            return latest.get("value")
    return None


def _latest_end_time(payloads: tuple[dict[str, Any], ...]) -> datetime:
    candidates: list[datetime] = []
    for payload in payloads:
        for item in _items(payload):
            values = item.get("values")
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict):
                    parsed = _parse_datetime(value.get("end_time"))
                    if parsed is not None:
                        candidates.append(parsed)
    return max(candidates, default=datetime.now(UTC))


def _safe_public_https_url(value: str) -> bool:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


class InstagramAdapter:
    platform = Platform.INSTAGRAM

    def __init__(self, transport: InstagramTransport) -> None:
        self._transport = transport

    def connect_account(
        self,
        request: ConnectAccountRequest,
    ) -> ConnectedAccount:
        credentials = self._transport.exchange_authorization_code(request)
        profile = self._transport.get_profile(credentials)
        account_id = profile.get("id") or profile.get("user_id")
        if not isinstance(account_id, str | int) or not str(account_id):
            raise PlatformPermanentError(
                "instagram_account_missing",
                "Instagram did not return a professional account",
            )
        account_type = profile.get("account_type")
        if isinstance(account_type, str) and account_type.upper() not in {
            "BUSINESS",
            "MEDIA_CREATOR",
            "CREATOR",
        }:
            raise PlatformPermanentError(
                "instagram_professional_account_required",
                "Instagram requires a Business or Creator professional account",
            )
        display = profile.get("username") or profile.get("name")
        return ConnectedAccount(
            external_account_id=str(account_id),
            display_name=str(display) if display else None,
            credentials=credentials,
        )

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial:
        return self._transport.refresh_credentials(credentials)

    def disconnect_account(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        self._transport.revoke_credentials(external_account_id, credentials)

    def list_channels(
        self,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteChannel]:
        if cursor:
            return AdapterPage(items=(), next_cursor=None)
        return AdapterPage(
            items=(self._map_profile(self._transport.get_profile(credentials)),),
            next_cursor=None,
        )

    def sync_channel(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteChannel:
        return self._map_profile(
            self._transport.get_profile(
                credentials,
                account_id=external_channel_id,
            )
        )

    def list_videos(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteVideo]:
        payload = self._transport.list_media(
            external_channel_id,
            credentials,
            cursor=cursor,
        )
        return AdapterPage(
            items=tuple(
                self._map_media(item, external_channel_id)
                for item in _items(payload)
            ),
            next_cursor=_next_cursor(payload),
        )

    def sync_video(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteVideo:
        profile = self._transport.get_profile(credentials)
        channel_id = profile.get("id") or profile.get("user_id")
        if not isinstance(channel_id, str | int):
            raise PlatformPermanentError(
                "instagram_account_missing",
                "Instagram did not return a professional account",
            )
        return self._map_media(
            self._transport.get_media(external_video_id, credentials),
            str(channel_id),
        )

    def sync_metrics(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteMetricSnapshot]:
        if cursor:
            return AdapterPage(items=(), next_cursor=None)
        media = self._transport.get_media(external_video_id, credentials)
        product_type = media.get("media_product_type")
        payload = self._transport.media_insights(
            external_video_id,
            product_type if isinstance(product_type, str) else None,
            credentials,
        )
        values: dict[str, int | float | str | bool | None] = {}
        for item in _items(payload):
            name = item.get("name")
            if isinstance(name, str):
                number = _number(_insight_value(item))
                if number is not None:
                    values[name] = number
        total_watch_ms = _number(values.get("ig_reels_video_view_total_time"))
        average_watch_ms = _number(values.get("ig_reels_avg_watch_time"))
        mapped_values: dict[str, int | float | str | bool | None] = {
            "views": values.get("views"),
            "likes": values.get("likes"),
            "comments": values.get("comments"),
            "shares": values.get("shares"),
            "saves": values.get("saved"),
            "engaged_views": values.get("total_interactions"),
            "unique_viewers": values.get("reach"),
            "watch_time_seconds": (
                int(float(total_watch_ms) / 1000)
                if total_watch_ms is not None
                else None
            ),
            "average_view_duration_seconds": (
                int(float(average_watch_ms) / 1000)
                if average_watch_ms is not None
                else None
            ),
        }
        return AdapterPage(
            items=(
                RemoteMetricSnapshot(
                    external_video_id=external_video_id,
                    captured_at=datetime.now(UTC),
                    values=mapped_values,
                    unavailable_fields=tuple(
                        key
                        for key, value in mapped_values.items()
                        if value is None
                    ),
                    metadata={
                        "instagram_extension": {
                            "reels_tab_reach": None,
                            "feed_reach": None,
                            "explore_reach": None,
                            "profile_reach": None,
                            "accounts_reached": values.get("reach"),
                            "accounts_engaged": None,
                        },
                        "media_product_type": product_type,
                    },
                ),
            ),
            next_cursor=None,
        )

    def sync_account_metrics(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteAccountMetricSnapshot]:
        time_series, totals = self._transport.account_insights(
            external_account_id,
            credentials,
            cursor=cursor,
        )
        values: dict[str, int | float | str | bool | None] = {}
        for payload in (time_series, totals):
            for item in _items(payload):
                name = item.get("name")
                if not isinstance(name, str):
                    continue
                raw = _insight_value(item)
                if name == "follows_and_unfollows" and isinstance(raw, dict):
                    values["follows"] = _number(raw.get("follows"))
                    values["unfollows"] = _number(raw.get("unfollows"))
                else:
                    values[name] = _number(raw)
        expected = {
            "reach",
            "profile_views",
            "follower_count",
            "accounts_engaged",
            "total_interactions",
            "follows",
            "unfollows",
        }
        return AdapterPage(
            items=(
                RemoteAccountMetricSnapshot(
                    external_account_id=external_account_id,
                    captured_at=_latest_end_time((time_series, totals)),
                    period="day",
                    values=values,
                    unavailable_fields=tuple(sorted(expected - values.keys())),
                    metadata={"source": "instagram_account_insights"},
                ),
            ),
            next_cursor=_next_cursor(time_series),
        )

    def validate_publish_request(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> PublishValidation:
        errors: list[str] = []
        warnings: list[str] = []
        if INSTAGRAM_PUBLISH_SCOPE not in credentials.scopes:
            errors.append("Instagram publishing permission is not granted")
        if not _safe_public_https_url(request.media_reference):
            errors.append("Instagram media must use a public HTTPS URL")
        media_type = str(request.options.get("media_type", "REELS")).upper()
        if media_type not in {"IMAGE", "VIDEO", "REELS"}:
            errors.append("Instagram media_type must be IMAGE, VIDEO, or REELS")
        if len(request.title) + len(request.description or "") + 2 > 2200:
            errors.append("Instagram caption must not exceed 2200 characters")
        if set(request.options) - {
            "media_type",
            "share_to_feed",
            "cover_url",
        }:
            errors.append("Instagram publishing options are not supported")
        cover_url = request.options.get("cover_url")
        if isinstance(cover_url, str) and not _safe_public_https_url(cover_url):
            errors.append("Instagram cover_url must use a public HTTPS URL")
        if request.scheduled_for is not None:
            warnings.append(
                "Instagram scheduling is enforced by the CreatorOS publishing worker"
            )
        return PublishValidation(
            valid=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def publish_video(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
        *,
        idempotency_key: str,
    ) -> PublishResult:
        del idempotency_key
        validation = self.validate_publish_request(request, credentials)
        if not validation.valid:
            raise PlatformPermanentError(
                "instagram_publish_invalid",
                validation.errors[0],
            )
        profile = self._transport.get_profile(credentials)
        account_id = profile.get("id") or profile.get("user_id")
        if not isinstance(account_id, str | int):
            raise PlatformPermanentError(
                "instagram_account_missing",
                "Instagram did not return a professional account",
            )
        container = self._transport.create_media_container(
            str(account_id),
            request,
            credentials,
        )
        container_id = container.get("id")
        if not isinstance(container_id, str | int) or not str(container_id):
            raise PlatformPermanentError(
                "instagram_container_missing",
                "Instagram did not return a publishing container",
            )
        status = self._transport.get_container_status(
            str(container_id),
            credentials,
        )
        status_code = str(status.get("status_code", "IN_PROGRESS")).upper()
        if status_code == "FINISHED":
            return self.finalize_publish(
                str(account_id),
                str(container_id),
                credentials,
            )
        if status_code in {"ERROR", "EXPIRED"}:
            raise PlatformPermanentError(
                "instagram_container_failed",
                "Instagram could not prepare the media for publishing",
            )
        return PublishResult(
            external_publish_id=str(container_id),
            status=status_code.lower(),
        )

    def finalize_publish(
        self,
        external_account_id: str,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishResult:
        result = self._transport.publish_container(
            external_account_id,
            external_publish_id,
            credentials,
        )
        media_id = result.get("id")
        if not isinstance(media_id, str | int) or not str(media_id):
            raise PlatformPermanentError(
                "instagram_media_missing",
                "Instagram did not return the published media",
            )
        return PublishResult(
            external_publish_id=external_publish_id,
            external_video_id=str(media_id),
            status="published",
        )

    def get_publish_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishStatus:
        payload = self._transport.get_container_status(
            external_publish_id,
            credentials,
        )
        status_code = str(payload.get("status_code", "IN_PROGRESS")).upper()
        messages = {
            "ERROR": "Instagram could not prepare the media",
            "EXPIRED": "Instagram publishing container expired",
            "FINISHED": "Instagram media is ready to publish",
            "IN_PROGRESS": "Instagram is preparing the media",
            "PUBLISHED": "Instagram media was published",
        }
        return PublishStatus(
            external_publish_id=external_publish_id,
            status=status_code.lower(),
            updated_at=datetime.now(UTC),
            safe_message=messages.get(status_code),
        )

    def get_publishing_limit(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> tuple[int, int, int]:
        payload = self._transport.publishing_limit(
            external_account_id,
            credentials,
        )
        rows = _items(payload)
        row = rows[0] if rows else payload
        usage = _number(row.get("quota_usage"))
        config = row.get("config")
        config = config if isinstance(config, dict) else {}
        total = _number(config.get("quota_total"))
        duration = _number(config.get("quota_duration"))
        if usage is None or total is None or duration is None:
            raise PlatformPermanentError(
                "instagram_publishing_limit_invalid",
                "Instagram returned an invalid publishing limit",
            )
        return int(usage), int(total), int(duration)

    def delete_or_revoke_connection(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        self.disconnect_account(external_account_id, credentials)

    @staticmethod
    def _map_profile(profile: dict[str, Any]) -> RemoteChannel:
        account_id = profile.get("id") or profile.get("user_id")
        if not isinstance(account_id, str | int) or not str(account_id):
            raise PlatformPermanentError(
                "instagram_account_missing",
                "Instagram did not return a professional account",
            )
        username = profile.get("username")
        name = profile.get("name") or username or f"Instagram {account_id}"
        return RemoteChannel(
            external_channel_id=str(account_id),
            name=str(name),
            handle=str(username) if username else None,
            metadata={
                "account_type": profile.get("account_type"),
                "followers_count": _number(profile.get("followers_count")),
                "media_count": _number(profile.get("media_count")),
            },
        )

    @staticmethod
    def _map_media(
        media: dict[str, Any],
        external_channel_id: str,
    ) -> RemoteVideo:
        media_id = media.get("id")
        if not isinstance(media_id, str | int) or not str(media_id):
            raise PlatformPermanentError(
                "instagram_media_missing",
                "Instagram returned media without an ID",
            )
        caption = media.get("caption")
        description = str(caption) if isinstance(caption, str) else None
        first_line = (
            next(
                (line.strip() for line in description.splitlines() if line.strip()),
                "",
            )
            if description
            else ""
        )
        product_type = media.get("media_product_type")
        title = first_line[:500] or f"Instagram {product_type or 'media'} {media_id}"
        return RemoteVideo(
            external_video_id=str(media_id),
            external_channel_id=external_channel_id,
            title=title,
            description=description,
            published_at=_parse_datetime(media.get("timestamp")),
            metadata={
                "media_type": media.get("media_type"),
                "media_product_type": product_type,
                "permalink": media.get("permalink"),
                "thumbnail_url": media.get("thumbnail_url"),
            },
        )
