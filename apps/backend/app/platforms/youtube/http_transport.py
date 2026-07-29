from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx2
from pydantic import SecretStr

from app.models.platform_integration import RequestOutcome
from app.platforms.contracts import (
    ConnectAccountRequest,
    CredentialMaterial,
    PublishRequest,
    PublishResult,
    PublishStatus,
)
from app.platforms.errors import (
    PlatformAdapterError,
    PlatformAuthenticationError,
    PlatformCapabilityError,
    PlatformCredentialExpiredError,
    PlatformPermanentError,
    PlatformRateLimitError,
    PlatformTransientError,
)

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
YOUTUBE_DATA_API = "https://www.googleapis.com/youtube/v3"
YOUTUBE_ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2"
YOUTUBE_UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3/videos"

DATA_API_BUCKET = "data_api"
ANALYTICS_API_BUCKET = "analytics_api"
VIDEO_UPLOAD_BUCKET = "video_uploads"


class YouTubeMediaUpload(Protocol):
    content_type: str
    size_bytes: int

    def iter_bytes(self, chunk_size: int = 8 * 1024 * 1024) -> Iterable[bytes]: ...


class YouTubeMediaSource(Protocol):
    def open_upload(self, media_reference: str) -> YouTubeMediaUpload: ...


class QuotaRecorder(Protocol):
    def __call__(self, quota_bucket: str, units: int) -> None: ...


class RequestRecorder(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        status_code: int | None,
        duration_ms: int,
        outcome: RequestOutcome,
        provider_request_id: str | None,
    ) -> None: ...


class DisabledYouTubeMediaSource:
    def open_upload(self, media_reference: str) -> YouTubeMediaUpload:
        del media_reference
        raise PlatformCapabilityError(
            "youtube_media_unavailable",
            "YouTube uploads require the configured CreatorOS media store",
        )


def _provider_request_id(response: httpx2.Response) -> str | None:
    value = response.headers.get("x-goog-request-id") or response.headers.get(
        "x-guploader-uploadid"
    )
    return value[:255] if value else None


def _retry_after(response: httpx2.Response) -> int | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        return None


def _error_reason(response: httpx2.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, str):
        return error[:100]
    if not isinstance(error, dict):
        return None
    errors = error.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict) and isinstance(item.get("reason"), str):
                return item["reason"][:100]
    status = error.get("status")
    if isinstance(status, str):
        return status[:100]
    return None


class YouTubeHttpTransport:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: SecretStr,
        media_source: YouTubeMediaSource,
        client: httpx2.Client | None = None,
        quota_recorder: QuotaRecorder | None = None,
        request_recorder: RequestRecorder | None = None,
        timeout_seconds: float = 30.0,
        analytics_lookback_days: int = 28,
    ) -> None:
        if not client_id.strip():
            raise ValueError("client_id cannot be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if analytics_lookback_days < 1 or analytics_lookback_days > 3650:
            raise ValueError("analytics_lookback_days must be between 1 and 3650")
        self._client_id = client_id
        self._client_secret = client_secret
        self._media_source = media_source
        self._client = client
        self._quota_recorder = quota_recorder
        self._request_recorder = request_recorder
        self._timeout_seconds = timeout_seconds
        self._analytics_lookback_days = analytics_lookback_days

    def _send(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx2.Response:
        try:
            if self._client is not None:
                return self._client.request(method, url, **kwargs)
            with httpx2.Client(
                timeout=self._timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                return client.request(method, url, **kwargs)
        except httpx2.TimeoutException as exc:
            raise PlatformTransientError(
                "youtube_timeout",
                "YouTube did not respond before the request timeout",
            ) from exc
        except httpx2.RequestError as exc:
            raise PlatformTransientError(
                "youtube_network_error",
                "YouTube could not be reached",
            ) from exc

    def _raise_provider_error(self, response: httpx2.Response) -> None:
        reason = _error_reason(response)
        code = f"youtube_{(reason or f'http_{response.status_code}').lower()}"
        request_id = _provider_request_id(response)
        normalized = (reason or "").lower()
        if response.status_code == 401 or normalized in {
            "invalid_grant",
            "invalid_token",
            "autherror",
        }:
            raise PlatformCredentialExpiredError(
                code,
                "YouTube authorization expired or was revoked",
            )
        if normalized in {
            "insufficientpermissions",
            "forbidden",
            "accessnotconfigured",
        }:
            raise PlatformAuthenticationError(
                code,
                "YouTube authorization does not grant the required permission",
            )
        if response.status_code == 429 or normalized in {
            "quotaexceeded",
            "dailylimitexceeded",
            "ratelimitexceeded",
            "userratelimitexceeded",
        }:
            raise PlatformRateLimitError(
                code,
                "YouTube request quota or rate limit was reached",
                retry_after_seconds=_retry_after(response),
                provider_request_id=request_id,
            )
        if response.status_code >= 500:
            raise PlatformTransientError(
                code,
                "YouTube temporarily could not complete the request",
                provider_request_id=request_id,
            )
        raise PlatformPermanentError(
            code,
            "YouTube rejected the request",
            provider_request_id=request_id,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        credentials: CredentialMaterial | None = None,
        quota_bucket: str | None = None,
        quota_units: int = 0,
        expected_statuses: tuple[int, ...] = (200,),
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx2.Response:
        request_headers = dict(headers or {})
        if credentials is not None:
            request_headers["Authorization"] = (
                f"Bearer {credentials.access_token.get_secret_value()}"
            )
        if (
            quota_bucket is not None
            and quota_units > 0
            and self._quota_recorder is not None
        ):
            self._quota_recorder(quota_bucket, quota_units)
        started_at = perf_counter()
        try:
            response = self._send(
                method,
                url,
                headers=request_headers,
                **kwargs,
            )
        except PlatformAdapterError:
            if self._request_recorder is not None:
                self._request_recorder(
                    method,
                    url,
                    None,
                    max(0, round((perf_counter() - started_at) * 1000)),
                    RequestOutcome.TRANSIENT_FAILURE,
                    None,
                )
            raise
        if response.status_code in expected_statuses:
            outcome = RequestOutcome.SUCCEEDED
        else:
            reason = (_error_reason(response) or "").lower()
            if response.status_code == 401 or reason in {
                "invalid_grant",
                "invalid_token",
                "autherror",
                "insufficientpermissions",
            }:
                outcome = RequestOutcome.AUTH_FAILURE
            elif response.status_code == 429 or reason in {
                "quotaexceeded",
                "dailylimitexceeded",
                "ratelimitexceeded",
                "userratelimitexceeded",
            }:
                outcome = RequestOutcome.RATE_LIMITED
            elif response.status_code >= 500:
                outcome = RequestOutcome.TRANSIENT_FAILURE
            else:
                outcome = RequestOutcome.PERMANENT_FAILURE
        if self._request_recorder is not None:
            self._request_recorder(
                method,
                url,
                response.status_code,
                max(0, round((perf_counter() - started_at) * 1000)),
                outcome,
                _provider_request_id(response),
            )
        if response.status_code not in expected_statuses:
            self._raise_provider_error(response)
        return response

    def _request_json(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = self._request(method, url, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise PlatformTransientError(
                "youtube_invalid_response",
                "YouTube returned an invalid response",
                provider_request_id=_provider_request_id(response),
            ) from exc
        if not isinstance(payload, dict):
            raise PlatformTransientError(
                "youtube_invalid_response",
                "YouTube returned an invalid response",
                provider_request_id=_provider_request_id(response),
            )
        return payload

    @staticmethod
    def _credential_material(
        payload: dict[str, Any],
        *,
        fallback_refresh_token: SecretStr | None = None,
        fallback_scopes: tuple[str, ...] = (),
    ) -> CredentialMaterial:
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise PlatformAuthenticationError(
                "youtube_token_missing",
                "Google did not return an access token",
            )
        refresh_value = payload.get("refresh_token")
        refresh_token = (
            SecretStr(refresh_value)
            if isinstance(refresh_value, str) and refresh_value
            else fallback_refresh_token
        )
        scope_value = payload.get("scope")
        scopes = (
            tuple(scope_value.split())
            if isinstance(scope_value, str)
            else fallback_scopes
        )
        expires_at: datetime | None = None
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, int) and expires_in > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return CredentialMaterial(
            access_token=SecretStr(access_token),
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scopes,
        )

    def exchange_authorization_code(
        self,
        request: ConnectAccountRequest,
    ) -> CredentialMaterial:
        if request.code_verifier is None:
            raise PlatformAuthenticationError(
                "youtube_pkce_missing",
                "YouTube authorization is missing its PKCE verifier",
            )
        payload = self._request_json(
            "POST",
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
                "code": request.authorization_code.get_secret_value(),
                "code_verifier": request.code_verifier.get_secret_value(),
                "grant_type": "authorization_code",
                "redirect_uri": request.redirect_uri,
            },
        )
        return self._credential_material(payload)

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial:
        if credentials.refresh_token is None:
            raise PlatformCredentialExpiredError(
                "youtube_refresh_token_missing",
                "YouTube authorization must be reconnected",
            )
        payload = self._request_json(
            "POST",
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
                "refresh_token": credentials.refresh_token.get_secret_value(),
                "grant_type": "refresh_token",
            },
        )
        return self._credential_material(
            payload,
            fallback_refresh_token=credentials.refresh_token,
            fallback_scopes=credentials.scopes,
        )

    def revoke_credentials(self, credentials: CredentialMaterial) -> None:
        token = credentials.refresh_token or credentials.access_token
        self._request(
            "POST",
            GOOGLE_REVOKE_ENDPOINT,
            data={"token": token.get_secret_value()},
            expected_statuses=(200, 400),
        )

    def list_channels(
        self,
        credentials: CredentialMaterial,
        *,
        channel_id: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "part": "snippet,contentDetails,statistics",
            "maxResults": 50,
        }
        if channel_id is None:
            params["mine"] = "true"
        else:
            params["id"] = channel_id
        if cursor:
            params["pageToken"] = cursor
        return self._request_json(
            "GET",
            f"{YOUTUBE_DATA_API}/channels",
            credentials=credentials,
            quota_bucket=DATA_API_BUCKET,
            quota_units=1,
            params=params,
        )

    def list_upload_items(
        self,
        uploads_playlist_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "part": "contentDetails,snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": 50,
        }
        if cursor:
            params["pageToken"] = cursor
        return self._request_json(
            "GET",
            f"{YOUTUBE_DATA_API}/playlistItems",
            credentials=credentials,
            quota_bucket=DATA_API_BUCKET,
            quota_units=1,
            params=params,
        )

    def list_videos(
        self,
        video_ids: tuple[str, ...],
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        if not video_ids or len(video_ids) > 50:
            raise PlatformPermanentError(
                "youtube_video_batch_invalid",
                "YouTube video batches must contain 1 through 50 IDs",
            )
        return self._request_json(
            "GET",
            f"{YOUTUBE_DATA_API}/videos",
            credentials=credentials,
            quota_bucket=DATA_API_BUCKET,
            quota_units=1,
            params={
                "part": "snippet,contentDetails,status,statistics,processingDetails",
                "id": ",".join(video_ids),
            },
        )

    @staticmethod
    def _start_index(cursor: str | None) -> int:
        if cursor is None:
            return 1
        try:
            value = int(cursor)
        except ValueError as exc:
            raise PlatformPermanentError(
                "youtube_analytics_cursor_invalid",
                "YouTube analytics cursor is invalid",
            ) from exc
        if value < 1:
            raise PlatformPermanentError(
                "youtube_analytics_cursor_invalid",
                "YouTube analytics cursor is invalid",
            )
        return value

    def _analytics_report(
        self,
        *,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
        metrics: str,
        dimensions: str | None = None,
        cursor: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        start_index = self._start_index(cursor)
        end_date = date.today()
        start_date = end_date - timedelta(days=self._analytics_lookback_days)
        params: dict[str, str | int] = {
            "ids": f"channel=={channel_id}",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "filters": f"video=={video_id}",
            "metrics": metrics,
            "startIndex": start_index,
            "maxResults": 200,
        }
        if dimensions:
            params["dimensions"] = dimensions
        if sort:
            params["sort"] = sort
        payload = self._request_json(
            "GET",
            f"{YOUTUBE_ANALYTICS_API}/reports",
            credentials=credentials,
            quota_bucket=ANALYTICS_API_BUCKET,
            quota_units=1,
            params=params,
        )
        page_info = payload.get("pageInfo")
        if isinstance(page_info, dict):
            total = page_info.get("totalResults")
            per_page = page_info.get("resultsPerPage")
            if isinstance(total, int) and isinstance(per_page, int):
                next_index = start_index + per_page
                if per_page > 0 and next_index <= total:
                    payload["next_cursor"] = str(next_index)
        return payload

    def analytics_activity(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self._analytics_report(
            channel_id=channel_id,
            video_id=video_id,
            credentials=credentials,
            cursor=cursor,
            metrics=(
                "views,engagedViews,likes,comments,shares,"
                "estimatedMinutesWatched,averageViewDuration,"
                "subscribersGained,subscribersLost"
            ),
        )

    def analytics_retention(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._analytics_report(
            channel_id=channel_id,
            video_id=video_id,
            credentials=credentials,
            dimensions="elapsedVideoTimeRatio",
            metrics="audienceWatchRatio,relativeRetentionPerformance",
        )

    def analytics_traffic_sources(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._analytics_report(
            channel_id=channel_id,
            video_id=video_id,
            credentials=credentials,
            dimensions="insightTrafficSourceType",
            metrics="views,engagedViews,estimatedMinutesWatched",
            sort="-views",
        )

    def analytics_subscriber_status(
        self,
        channel_id: str,
        video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._analytics_report(
            channel_id=channel_id,
            video_id=video_id,
            credentials=credentials,
            dimensions="subscribedStatus",
            metrics="views",
        )

    @staticmethod
    def _upload_metadata(request: PublishRequest) -> dict[str, Any]:
        snippet: dict[str, Any] = {
            "title": request.title,
            "description": request.description or "",
        }
        category_id = request.options.get("category_id")
        if category_id is not None:
            snippet["categoryId"] = str(category_id)
        tags = request.options.get("tags")
        if isinstance(tags, list):
            snippet["tags"] = [str(tag) for tag in tags]
        status: dict[str, Any] = {
            "privacyStatus": request.options.get("privacy_status", "private"),
            "selfDeclaredMadeForKids": request.options["made_for_kids"],
        }
        if request.scheduled_for is not None:
            status["publishAt"] = (
                request.scheduled_for.astimezone(UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
        return {"snippet": snippet, "status": status}

    @staticmethod
    def _validate_upload_location(location: str) -> None:
        parsed = urlparse(location)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not host
            or not (
                host == "www.googleapis.com"
                or host.endswith(".googleapis.com")
                or host == "upload.youtube.com"
            )
        ):
            raise PlatformTransientError(
                "youtube_upload_location_invalid",
                "YouTube returned an invalid upload location",
            )

    def upload_video(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> PublishResult:
        upload = self._media_source.open_upload(request.media_reference)
        if upload.size_bytes <= 0:
            raise PlatformPermanentError(
                "youtube_media_empty",
                "The selected media file is empty",
            )
        if not upload.content_type.startswith("video/"):
            raise PlatformPermanentError(
                "youtube_media_type_invalid",
                "The selected media is not a supported video",
            )
        initiation = self._request(
            "POST",
            YOUTUBE_UPLOAD_API,
            credentials=credentials,
            quota_bucket=VIDEO_UPLOAD_BUCKET,
            quota_units=1,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(upload.size_bytes),
                "X-Upload-Content-Type": upload.content_type,
            },
            json=self._upload_metadata(request),
            expected_statuses=(200, 201),
        )
        location = initiation.headers.get("location")
        if not location:
            raise PlatformTransientError(
                "youtube_upload_location_missing",
                "YouTube did not provide an upload location",
                provider_request_id=_provider_request_id(initiation),
            )
        self._validate_upload_location(location)
        result = self._request(
            "PUT",
            location,
            credentials=credentials,
            headers={
                "Content-Length": str(upload.size_bytes),
                "Content-Type": upload.content_type,
            },
            content=upload.iter_bytes(),
            expected_statuses=(200, 201),
        )
        try:
            payload = result.json()
        except ValueError as exc:
            raise PlatformTransientError(
                "youtube_upload_response_invalid",
                "YouTube returned an invalid upload response",
                provider_request_id=_provider_request_id(result),
            ) from exc
        video_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(video_id, str) or not video_id:
            raise PlatformTransientError(
                "youtube_upload_id_missing",
                "YouTube did not return the uploaded video ID",
                provider_request_id=_provider_request_id(result),
            )
        return PublishResult(
            external_publish_id=video_id,
            external_video_id=video_id,
            status="processing",
            provider_request_id=_provider_request_id(result),
        )

    def get_upload_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> PublishStatus:
        payload = self.list_videos((external_publish_id,), credentials)
        items = payload.get("items")
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            raise PlatformPermanentError(
                "youtube_upload_not_found",
                "YouTube upload was not found",
            )
        item = items[0]
        status_data = item.get("status")
        processing_data = item.get("processingDetails")
        status_map = status_data if isinstance(status_data, dict) else {}
        processing_map = processing_data if isinstance(processing_data, dict) else {}
        processing_status = processing_map.get("processingStatus")
        upload_status = status_map.get("uploadStatus")
        rejection_reason = status_map.get("rejectionReason")
        if rejection_reason or processing_status in {"failed", "terminated"}:
            status = "failed"
            safe_message = "YouTube could not process the uploaded video"
        elif processing_status == "succeeded" or upload_status == "processed":
            status = "ready"
            safe_message = None
        else:
            status = "processing"
            safe_message = None
        return PublishStatus(
            external_publish_id=external_publish_id,
            external_video_id=external_publish_id,
            status=status,
            updated_at=datetime.now(UTC),
            safe_message=safe_message,
        )
