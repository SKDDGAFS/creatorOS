import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

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
from app.platforms.errors import PlatformCapabilityError, PlatformPermanentError
from app.platforms.youtube.oauth import YOUTUBE_UPLOAD_SCOPE
from app.platforms.youtube.transport import YouTubeTransport

ISO_DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?$"
)


def _items(response: dict[str, Any]) -> list[dict[str, Any]]:
    items = response.get("items", [])
    return [item for item in items if isinstance(item, dict)]


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


def _duration_seconds(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = ISO_DURATION_PATTERN.fullmatch(value)
    if match is None:
        return None
    try:
        seconds = (
            int(match.group("days") or 0) * 86400
            + int(match.group("hours") or 0) * 3600
            + int(match.group("minutes") or 0) * 60
            + float(match.group("seconds") or 0)
        )
    except ValueError:
        return None
    return max(1, round(seconds))


def _table_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    headers = response.get("columnHeaders", [])
    names: list[str] = []
    for header in headers:
        if isinstance(header, dict) and isinstance(header.get("name"), str):
            names.append(header["name"])
    rows = response.get("rows", [])
    return [
        dict(zip(names, row, strict=False)) for row in rows if isinstance(row, list)
    ]


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except InvalidOperation, TypeError, ValueError:
        return None


class YouTubeAdapter:
    platform = Platform.YOUTUBE

    def __init__(self, transport: YouTubeTransport) -> None:
        self._transport = transport

    def connect_account(
        self,
        request: ConnectAccountRequest,
    ) -> ConnectedAccount:
        credentials = self._transport.exchange_authorization_code(request)
        channels = self._transport.list_channels(credentials)
        items = _items(channels)
        if not items:
            raise PlatformPermanentError(
                "youtube_channel_missing",
                "The Google account does not have an accessible YouTube channel",
            )
        channel = self._map_channel(items[0])
        return ConnectedAccount(
            external_account_id=channel.external_channel_id,
            display_name=channel.name,
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
        del external_account_id
        self._transport.revoke_credentials(credentials)

    def list_channels(
        self,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteChannel]:
        response = self._transport.list_channels(
            credentials,
            cursor=cursor,
        )
        return AdapterPage(
            items=tuple(self._map_channel(item) for item in _items(response)),
            next_cursor=response.get("nextPageToken"),
        )

    def sync_channel(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteChannel:
        response = self._transport.list_channels(
            credentials,
            channel_id=external_channel_id,
        )
        items = _items(response)
        if not items:
            raise PlatformPermanentError(
                "youtube_channel_not_found",
                "YouTube channel was not found",
            )
        return self._map_channel(items[0])

    def list_videos(
        self,
        external_channel_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteVideo]:
        channel_response = self._transport.list_channels(
            credentials,
            channel_id=external_channel_id,
        )
        channels = _items(channel_response)
        if not channels:
            raise PlatformPermanentError(
                "youtube_channel_not_found",
                "YouTube channel was not found",
            )
        playlist_id = (
            channels[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if not isinstance(playlist_id, str) or not playlist_id:
            raise PlatformPermanentError(
                "youtube_uploads_playlist_missing",
                "YouTube uploads playlist is unavailable",
            )
        page = self._transport.list_upload_items(
            playlist_id,
            credentials,
            cursor=cursor,
        )
        video_ids = tuple(
            video_id
            for item in _items(page)
            if isinstance(
                video_id := item.get("contentDetails", {}).get("videoId"),
                str,
            )
        )
        video_response = (
            self._transport.list_videos(video_ids, credentials)
            if video_ids
            else {"items": []}
        )
        return AdapterPage(
            items=tuple(self._map_video(item) for item in _items(video_response)),
            next_cursor=page.get("nextPageToken"),
        )

    def sync_video(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
    ) -> RemoteVideo:
        response = self._transport.list_videos(
            (external_video_id,),
            credentials,
        )
        items = _items(response)
        if not items:
            raise PlatformPermanentError(
                "youtube_video_not_found",
                "YouTube video was not found",
            )
        return self._map_video(items[0])

    def sync_metrics(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteMetricSnapshot]:
        video = self.sync_video(external_video_id, credentials)
        channel_id = video.external_channel_id
        activity = self._transport.analytics_activity(
            channel_id,
            external_video_id,
            credentials,
            cursor=cursor,
        )
        retention = self._transport.analytics_retention(
            channel_id,
            external_video_id,
            credentials,
        )
        traffic = self._transport.analytics_traffic_sources(
            channel_id,
            external_video_id,
            credentials,
        )
        subscriber_status = self._transport.analytics_subscriber_status(
            channel_id,
            external_video_id,
            credentials,
        )
        activity_rows = _table_rows(activity)
        row = activity_rows[0] if activity_rows else {}
        values: dict[str, int | float | str | bool | None] = {
            "views": row.get("views"),
            "engaged_views": row.get("engagedViews"),
            "likes": row.get("likes"),
            "comments": row.get("comments"),
            "shares": row.get("shares"),
            "average_view_duration_seconds": row.get("averageViewDuration"),
            "subscribers_gained": row.get("subscribersGained"),
            "subscribers_lost": row.get("subscribersLost"),
        }
        minutes = _decimal(row.get("estimatedMinutesWatched"))
        values["watch_time_seconds"] = (
            int(minutes * 60) if minutes is not None else None
        )
        unavailable = tuple(name for name, value in values.items() if value is None)
        retention_points = [
            {
                "position_ratio": item.get("elapsedVideoTimeRatio"),
                "audience_retention_ratio": item.get("audienceWatchRatio"),
                "relative_retention_performance": item.get(
                    "relativeRetentionPerformance"
                ),
            }
            for item in _table_rows(retention)
        ]
        traffic_sources = [
            {
                "source_type": item.get("insightTrafficSourceType"),
                "views": item.get("views"),
                "engaged_views": item.get("engagedViews"),
                "watch_time_seconds": (
                    int(minutes * 60)
                    if (minutes := _decimal(item.get("estimatedMinutesWatched")))
                    is not None
                    else None
                ),
            }
            for item in _table_rows(traffic)
        ]
        subscriber_rows = _table_rows(subscriber_status)
        subscriber_views = next(
            (
                item.get("views")
                for item in subscriber_rows
                if item.get("subscribedStatus") == "SUBSCRIBED"
            ),
            None,
        )
        unsubscribed_views = next(
            (
                item.get("views")
                for item in subscriber_rows
                if item.get("subscribedStatus") == "UNSUBSCRIBED"
            ),
            None,
        )
        traffic_views = {
            str(item["source_type"]): item["views"]
            for item in traffic_sources
            if item["source_type"] is not None and isinstance(item["views"], int)
        }
        snapshot = RemoteMetricSnapshot(
            external_video_id=external_video_id,
            captured_at=datetime.now(UTC),
            values=values,
            unavailable_fields=unavailable,
            metadata={
                "retention_points": retention_points,
                "traffic_sources": traffic_sources,
                "youtube_extension": {
                    "suggested_video_views": traffic_views.get("RELATED_VIDEO"),
                    "browse_feature_views": None,
                    "subscriber_views": subscriber_views,
                    "unsubscribed_views": unsubscribed_views,
                    "search_views": traffic_views.get("YT_SEARCH"),
                    "external_views": traffic_views.get("EXT_URL"),
                    "end_screen_views": traffic_views.get("END_SCREEN"),
                    "reported_impressions_ctr": None,
                },
            },
        )
        return AdapterPage(
            items=(snapshot,),
            next_cursor=activity.get("next_cursor"),
        )

    def sync_account_metrics(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> AdapterPage[RemoteAccountMetricSnapshot]:
        del external_account_id, credentials, cursor
        raise PlatformCapabilityError(
            "youtube_account_metrics_unsupported",
            "YouTube account metrics are not implemented by this adapter",
        )

    def validate_publish_request(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> PublishValidation:
        errors: list[str] = []
        warnings: list[str] = []
        if YOUTUBE_UPLOAD_SCOPE not in credentials.scopes:
            errors.append("YouTube upload permission is not granted")
        if len(request.title) > 100:
            errors.append("YouTube titles cannot exceed 100 characters")
        if request.description is not None and len(request.description) > 5000:
            errors.append("YouTube descriptions cannot exceed 5000 characters")
        tags = request.options.get("tags")
        if tags is not None:
            if not isinstance(tags, list) or not all(
                isinstance(tag, str) and tag.strip() for tag in tags
            ):
                errors.append("YouTube tags must be a list of non-empty strings")
            elif len(",".join(tags)) > 500:
                errors.append("YouTube tags cannot exceed 500 characters")
        privacy = request.options.get("privacy_status", "private")
        if privacy not in {"private", "unlisted", "public"}:
            errors.append("privacy_status must be private, unlisted, or public")
        if request.scheduled_for is not None:
            if request.scheduled_for <= datetime.now(UTC):
                errors.append("scheduled_for must be in the future")
            if privacy != "private":
                errors.append("Scheduled YouTube videos must be private")
        if "made_for_kids" not in request.options:
            errors.append("made_for_kids must be explicitly provided")
        elif not isinstance(request.options["made_for_kids"], bool):
            errors.append("made_for_kids must be true or false")
        if privacy != "private":
            warnings.append("Unverified YouTube API projects force uploads to private")
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
        if len(idempotency_key.strip()) < 8 or len(idempotency_key) > 256:
            raise PlatformPermanentError(
                "youtube_idempotency_key_invalid",
                "YouTube publishing requires an idempotency key of 8 to 256 characters",
            )
        validation = self.validate_publish_request(request, credentials)
        if not validation.valid:
            raise PlatformPermanentError(
                "youtube_publish_invalid",
                "; ".join(validation.errors),
            )
        return self._transport.upload_video(request, credentials)

    def get_publish_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishStatus:
        return self._transport.get_upload_status(
            external_publish_id,
            credentials,
        )

    def delete_or_revoke_connection(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        self.disconnect_account(external_account_id, credentials)

    @staticmethod
    def _map_channel(item: dict[str, Any]) -> RemoteChannel:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        statistics = item.get("statistics", {})
        return RemoteChannel(
            external_channel_id=str(item.get("id", "")),
            name=str(snippet.get("title") or "YouTube channel"),
            handle=snippet.get("customUrl"),
            metadata={
                "description": snippet.get("description"),
                "country": snippet.get("country"),
                "uploads_playlist_id": content.get(
                    "relatedPlaylists",
                    {},
                ).get("uploads"),
                "view_count": statistics.get("viewCount"),
                "subscriber_count": statistics.get("subscriberCount"),
                "hidden_subscriber_count": statistics.get("hiddenSubscriberCount"),
                "video_count": statistics.get("videoCount"),
            },
        )

    @staticmethod
    def _map_video(item: dict[str, Any]) -> RemoteVideo:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        status = item.get("status", {})
        statistics = item.get("statistics", {})
        processing = item.get("processingDetails", {})
        return RemoteVideo(
            external_video_id=str(item.get("id", "")),
            external_channel_id=str(snippet.get("channelId", "")),
            title=str(snippet.get("title") or "YouTube video"),
            description=snippet.get("description"),
            published_at=_parse_datetime(snippet.get("publishedAt")),
            duration_seconds=_duration_seconds(content.get("duration")),
            metadata={
                "privacy_status": status.get("privacyStatus"),
                "publish_at": status.get("publishAt"),
                "upload_status": status.get("uploadStatus"),
                "rejection_reason": status.get("rejectionReason"),
                "processing_status": processing.get("processingStatus"),
                "view_count": statistics.get("viewCount"),
                "like_count": statistics.get("likeCount"),
                "comment_count": statistics.get("commentCount"),
            },
        )
