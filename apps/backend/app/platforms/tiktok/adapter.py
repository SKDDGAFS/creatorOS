from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
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
from app.platforms.tiktok.oauth import TIKTOK_PUBLISH_SCOPE
from app.platforms.tiktok.transport import TikTokTransport


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _profile(payload: dict[str, Any]) -> dict[str, Any]:
    user = _data(payload).get("user")
    return user if isinstance(user, dict) else {}


def _videos(payload: dict[str, Any]) -> list[dict[str, Any]]:
    videos = _data(payload).get("videos")
    return (
        [item for item in videos if isinstance(item, dict)]
        if isinstance(videos, list)
        else []
    )


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int | float) else None


def _positive_integer(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


def _published_at(value: Any) -> datetime | None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except OverflowError, OSError, ValueError:
        return None


def _next_cursor(payload: dict[str, Any]) -> str | None:
    data = _data(payload)
    if data.get("has_more") is not True:
        return None
    cursor = data.get("cursor")
    return str(cursor) if isinstance(cursor, int | str) and str(cursor) else None


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


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


class TikTokAdapter:
    platform = Platform.TIKTOK

    def __init__(self, transport: TikTokTransport) -> None:
        self._transport = transport

    def connect_account(
        self,
        request: ConnectAccountRequest,
    ) -> ConnectedAccount:
        credentials = self._transport.exchange_authorization_code(request)
        profile = _profile(self._transport.get_profile(credentials))
        account_id = profile.get("open_id")
        if not isinstance(account_id, str) or not account_id:
            raise PlatformPermanentError(
                "tiktok_account_missing",
                "TikTok did not return the authorized account",
            )
        display = profile.get("display_name") or profile.get("username")
        return ConnectedAccount(
            external_account_id=account_id,
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
        remote = self._map_profile(self._transport.get_profile(credentials))
        if remote.external_channel_id != external_channel_id:
            raise PlatformPermanentError(
                "tiktok_account_mismatch",
                "TikTok returned a different authorized account",
            )
        return remote

    def list_videos(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteVideo]:
        payload = self._transport.list_videos(credentials, cursor=cursor)
        return AdapterPage(
            items=tuple(
                self._map_video(item, external_channel_id) for item in _videos(payload)
            ),
            next_cursor=_next_cursor(payload),
        )

    def sync_video(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteVideo:
        channel = self._map_profile(self._transport.get_profile(credentials))
        rows = _videos(self._transport.get_video(external_video_id, credentials))
        if not rows:
            raise PlatformPermanentError(
                "tiktok_video_missing",
                "TikTok did not return the requested video",
            )
        return self._map_video(rows[0], channel.external_channel_id)

    def sync_metrics(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteMetricSnapshot]:
        if cursor:
            return AdapterPage(items=(), next_cursor=None)
        rows = _videos(self._transport.get_video(external_video_id, credentials))
        if not rows:
            raise PlatformPermanentError(
                "tiktok_video_missing",
                "TikTok did not return the requested video",
            )
        video = rows[0]
        values: dict[str, int | float | str | bool | None] = {
            "views": _number(video.get("view_count")),
            "likes": _number(video.get("like_count")),
            "comments": _number(video.get("comment_count")),
            "shares": _number(video.get("share_count")),
            "unique_viewers": None,
            "engaged_views": None,
            "saves": None,
            "watch_time_seconds": None,
            "average_view_duration_seconds": None,
        }
        return AdapterPage(
            items=(
                RemoteMetricSnapshot(
                    external_video_id=external_video_id,
                    captured_at=datetime.now(UTC),
                    values=values,
                    unavailable_fields=tuple(
                        key for key, value in values.items() if value is None
                    ),
                    metadata={
                        "tiktok_extension": {
                            "for_you_views": None,
                            "following_feed_views": None,
                            "search_views": None,
                            "profile_views": None,
                            "sound_views": None,
                        },
                        "source": "tiktok_display_api",
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
        if cursor:
            return AdapterPage(items=(), next_cursor=None)
        profile = _profile(self._transport.get_profile(credentials))
        if profile.get("open_id") != external_account_id:
            raise PlatformPermanentError(
                "tiktok_account_mismatch",
                "TikTok returned statistics for another account",
            )
        keys = ("follower_count", "following_count", "likes_count", "video_count")
        values: dict[str, int | float | str | bool | None] = {
            key: _number(profile.get(key)) for key in keys
        }
        return AdapterPage(
            items=(
                RemoteAccountMetricSnapshot(
                    external_account_id=external_account_id,
                    captured_at=datetime.now(UTC),
                    period="lifetime",
                    values=values,
                    unavailable_fields=tuple(
                        key for key, value in values.items() if value is None
                    ),
                    metadata={"source": "tiktok_user_info"},
                ),
            ),
            next_cursor=None,
        )

    def validate_publish_request(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> PublishValidation:
        errors: list[str] = []
        warnings: list[str] = []
        if TIKTOK_PUBLISH_SCOPE not in credentials.scopes:
            errors.append("TikTok publishing permission is not granted")
        if not _safe_public_https_url(request.media_reference):
            errors.append("TikTok media must use a public HTTPS URL")
        caption = request.title
        if request.description:
            caption = f"{caption}\n\n{request.description}"
        if _utf16_units(caption) > 2200:
            errors.append("TikTok caption must not exceed 2200 UTF-16 units")
        supported_options = {
            "privacy_level",
            "duration_seconds",
            "disable_duet",
            "disable_comment",
            "disable_stitch",
            "brand_content_toggle",
            "brand_organic_toggle",
            "is_aigc",
        }
        if set(request.options) - supported_options:
            errors.append("TikTok publishing options are not supported")
        privacy_level = request.options.get("privacy_level")
        if not isinstance(privacy_level, str) or not privacy_level:
            errors.append("TikTok privacy_level must be selected by the creator")
        duration = _positive_integer(request.options.get("duration_seconds"))
        if duration is None:
            errors.append("TikTok duration_seconds must be a positive integer")
        creator = _data(self._transport.get_creator_info(credentials))
        privacy_options = creator.get("privacy_level_options")
        if (
            isinstance(privacy_level, str)
            and isinstance(privacy_options, list)
            and privacy_level not in privacy_options
        ):
            errors.append("TikTok privacy_level is unavailable for this creator")
        maximum_duration = _positive_integer(creator.get("max_video_post_duration_sec"))
        if (
            duration is not None
            and maximum_duration is not None
            and duration > maximum_duration
        ):
            errors.append("TikTok video exceeds this creator's duration limit")
        interaction_fields = {
            "comment_disabled": "disable_comment",
            "duet_disabled": "disable_duet",
            "stitch_disabled": "disable_stitch",
        }
        for creator_field, option_field in interaction_fields.items():
            if (
                creator.get(creator_field) is True
                and request.options.get(option_field) is not True
            ):
                errors.append(f"TikTok requires {option_field}=true for this creator")
        if request.scheduled_for is not None:
            warnings.append(
                "TikTok scheduling is enforced by the CreatorOS publishing worker"
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
                "tiktok_publish_invalid",
                validation.errors[0],
            )
        result = _data(self._transport.initialize_publish(request, credentials))
        publish_id = result.get("publish_id")
        if not isinstance(publish_id, str) or not publish_id:
            raise PlatformPermanentError(
                "tiktok_publish_id_missing",
                "TikTok did not return a publishing identifier",
            )
        return PublishResult(
            external_publish_id=publish_id,
            status="processing",
        )

    def get_publish_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishStatus:
        data = _data(
            self._transport.get_publish_status(external_publish_id, credentials)
        )
        provider_status = str(data.get("status", "PROCESSING_UPLOAD")).upper()
        status_map = {
            "PROCESSING_UPLOAD": "processing",
            "PROCESSING_DOWNLOAD": "processing",
            "SEND_TO_USER_INBOX": "awaiting_user",
            "PUBLISH_COMPLETE": "published",
            "FAILED": "failed",
        }
        public_ids = data.get("publicaly_available_post_id")
        external_video_id: str | None = None
        if isinstance(public_ids, list) and public_ids:
            first = public_ids[0]
            if isinstance(first, str | int) and str(first):
                external_video_id = str(first)
        fail_reason = data.get("fail_reason")
        safe_message = (
            "TikTok could not publish the media"
            if provider_status == "FAILED"
            else None
        )
        if provider_status == "FAILED" and isinstance(fail_reason, str):
            safe_message = f"TikTok publishing failed: {fail_reason[:200]}"
        return PublishStatus(
            external_publish_id=external_publish_id,
            status=status_map.get(provider_status, "processing"),
            external_video_id=external_video_id,
            updated_at=datetime.now(UTC),
            safe_message=safe_message,
        )

    def delete_or_revoke_connection(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        self.disconnect_account(external_account_id, credentials)

    @staticmethod
    def _map_profile(payload: dict[str, Any]) -> RemoteChannel:
        profile = _profile(payload)
        account_id = profile.get("open_id")
        if not isinstance(account_id, str) or not account_id:
            raise PlatformPermanentError(
                "tiktok_account_missing",
                "TikTok did not return the authorized account",
            )
        username = profile.get("username")
        name = profile.get("display_name") or username or f"TikTok {account_id}"
        return RemoteChannel(
            external_channel_id=account_id,
            name=str(name),
            handle=str(username) if username else None,
            metadata={
                "avatar_url": profile.get("avatar_url"),
                "bio_description": profile.get("bio_description"),
                "profile_deep_link": profile.get("profile_deep_link"),
                "is_verified": profile.get("is_verified"),
                "follower_count": _number(profile.get("follower_count")),
                "following_count": _number(profile.get("following_count")),
                "likes_count": _number(profile.get("likes_count")),
                "video_count": _number(profile.get("video_count")),
            },
        )

    @staticmethod
    def _map_video(
        video: dict[str, Any],
        external_channel_id: str,
    ) -> RemoteVideo:
        video_id = video.get("id")
        if not isinstance(video_id, str | int) or not str(video_id):
            raise PlatformPermanentError(
                "tiktok_video_missing",
                "TikTok returned a video without an ID",
            )
        description = video.get("video_description")
        description = str(description) if isinstance(description, str) else None
        title = video.get("title")
        if not isinstance(title, str) or not title.strip():
            title = description or f"TikTok video {video_id}"
        return RemoteVideo(
            external_video_id=str(video_id),
            external_channel_id=external_channel_id,
            title=title[:500],
            description=description,
            published_at=_published_at(video.get("create_time")),
            duration_seconds=_positive_integer(video.get("duration")),
            metadata={
                "cover_image_url": video.get("cover_image_url"),
                "share_url": video.get("share_url"),
                "embed_link": video.get("embed_link"),
                "height": _number(video.get("height")),
                "width": _number(video.get("width")),
            },
        )
