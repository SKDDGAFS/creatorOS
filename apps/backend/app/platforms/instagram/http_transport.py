from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol

import httpx2
from pydantic import SecretStr

from app.models.platform_integration import RequestOutcome
from app.platforms.contracts import (
    ConnectAccountRequest,
    CredentialMaterial,
    PublishRequest,
)
from app.platforms.errors import (
    PlatformAdapterError,
    PlatformAuthenticationError,
    PlatformCredentialExpiredError,
    PlatformPermanentError,
    PlatformRateLimitError,
    PlatformTransientError,
)

INSTAGRAM_SHORT_TOKEN_ENDPOINT = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_GRAPH_ORIGIN = "https://graph.instagram.com"
INSTAGRAM_LONG_TOKEN_ENDPOINT = f"{INSTAGRAM_GRAPH_ORIGIN}/access_token"
INSTAGRAM_REFRESH_ENDPOINT = f"{INSTAGRAM_GRAPH_ORIGIN}/refresh_access_token"

API_CALL_BUCKET = "instagram_api_calls"
INSIGHTS_BUCKET = "instagram_insights_calls"
PUBLISH_BUCKET = "instagram_publishing_calls"


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


def _error_payload(response: httpx2.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    error = payload.get("error")
    return error if isinstance(error, dict) else payload


def _provider_request_id(response: httpx2.Response) -> str | None:
    header = response.headers.get("x-fb-request-id")
    if header:
        return header[:255]
    trace = _error_payload(response).get("fbtrace_id")
    return trace[:255] if isinstance(trace, str) and trace else None


def _retry_after(response: httpx2.Response) -> int | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    return max(0, seconds)


def _error_code(response: httpx2.Response) -> tuple[int | None, int | None, bool]:
    error = _error_payload(response)
    code = error.get("code")
    subcode = error.get("error_subcode")
    return (
        code if isinstance(code, int) else None,
        subcode if isinstance(subcode, int) else None,
        error.get("is_transient") is True,
    )


class InstagramHttpTransport:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: SecretStr,
        api_version: str,
        client: httpx2.Client | None = None,
        quota_recorder: QuotaRecorder | None = None,
        request_recorder: RequestRecorder | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not app_id.strip():
            raise ValueError("app_id cannot be empty")
        if not api_version.startswith("v"):
            raise ValueError("api_version must be versioned")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._app_id = app_id
        self._app_secret = app_secret
        self._api_version = api_version
        self._client = client
        self._quota_recorder = quota_recorder
        self._request_recorder = request_recorder
        self._timeout_seconds = timeout_seconds

    def _graph_url(self, path: str) -> str:
        return f"{INSTAGRAM_GRAPH_ORIGIN}/{self._api_version}/{path.lstrip('/')}"

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
                "instagram_timeout",
                "Instagram did not respond before the request timeout",
            ) from exc
        except httpx2.RequestError as exc:
            raise PlatformTransientError(
                "instagram_network_error",
                "Instagram could not be reached",
            ) from exc

    def _outcome(self, response: httpx2.Response) -> RequestOutcome:
        code, subcode, transient = _error_code(response)
        if (
            response.status_code == 401
            or code == 190
            or subcode in {458, 459, 460, 463, 464, 467}
        ):
            return RequestOutcome.AUTH_FAILURE
        if response.status_code == 429 or code in {4, 17, 32, 613}:
            return RequestOutcome.RATE_LIMITED
        if response.status_code >= 500 or transient:
            return RequestOutcome.TRANSIENT_FAILURE
        return RequestOutcome.PERMANENT_FAILURE

    def _raise_provider_error(self, response: httpx2.Response) -> None:
        code, subcode, transient = _error_code(response)
        provider_request_id = _provider_request_id(response)
        identifier = subcode or code or response.status_code
        safe_code = f"instagram_{identifier}"
        if response.status_code == 401 or code == 190:
            raise PlatformCredentialExpiredError(
                safe_code,
                "Instagram authorization expired or was revoked",
            )
        if code in {10, 200}:
            raise PlatformAuthenticationError(
                safe_code,
                "Instagram authorization does not grant the required permission",
            )
        if response.status_code == 429 or code in {4, 17, 32, 613}:
            raise PlatformRateLimitError(
                safe_code,
                "Instagram request or publishing rate limit was reached",
                retry_after_seconds=_retry_after(response),
                provider_request_id=provider_request_id,
            )
        if response.status_code >= 500 or transient:
            raise PlatformTransientError(
                safe_code,
                "Instagram temporarily could not complete the request",
                provider_request_id=provider_request_id,
            )
        raise PlatformPermanentError(
            safe_code,
            "Instagram rejected the request",
            provider_request_id=provider_request_id,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        credentials: CredentialMaterial | None = None,
        quota_bucket: str | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx2.Response:
        request_headers = dict(headers or {})
        if credentials is not None:
            request_headers["Authorization"] = (
                f"Bearer {credentials.access_token.get_secret_value()}"
            )
        if quota_bucket is not None and self._quota_recorder is not None:
            self._quota_recorder(quota_bucket, 1)
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
        outcome = (
            RequestOutcome.SUCCEEDED
            if response.status_code in expected_statuses
            else self._outcome(response)
        )
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
                "instagram_invalid_response",
                "Instagram returned an invalid response",
                provider_request_id=_provider_request_id(response),
            ) from exc
        if not isinstance(payload, dict):
            raise PlatformTransientError(
                "instagram_invalid_response",
                "Instagram returned an invalid response",
                provider_request_id=_provider_request_id(response),
            )
        return payload

    @staticmethod
    def _credential_material(
        payload: dict[str, Any],
        *,
        fallback_scopes: tuple[str, ...] = (),
    ) -> CredentialMaterial:
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise PlatformAuthenticationError(
                "instagram_token_missing",
                "Instagram did not return an access token",
            )
        permissions = payload.get("permissions")
        scopes = (
            tuple(item for item in permissions if isinstance(item, str))
            if isinstance(permissions, list)
            else fallback_scopes
        )
        expires_at: datetime | None = None
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, int) and expires_in > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        secret = SecretStr(token)
        return CredentialMaterial(
            access_token=secret,
            refresh_token=secret,
            expires_at=expires_at,
            scopes=scopes,
        )

    def exchange_authorization_code(
        self,
        request: ConnectAccountRequest,
    ) -> CredentialMaterial:
        short_payload = self._request_json(
            "POST",
            INSTAGRAM_SHORT_TOKEN_ENDPOINT,
            data={
                "client_id": self._app_id,
                "client_secret": self._app_secret.get_secret_value(),
                "grant_type": "authorization_code",
                "redirect_uri": request.redirect_uri,
                "code": request.authorization_code.get_secret_value(),
            },
        )
        short_token = self._credential_material(short_payload)
        long_payload = self._request_json(
            "GET",
            INSTAGRAM_LONG_TOKEN_ENDPOINT,
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": self._app_secret.get_secret_value(),
                "access_token": short_token.access_token.get_secret_value(),
            },
        )
        return self._credential_material(
            long_payload,
            fallback_scopes=short_token.scopes,
        )

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial:
        token = credentials.refresh_token or credentials.access_token
        payload = self._request_json(
            "GET",
            INSTAGRAM_REFRESH_ENDPOINT,
            params={
                "grant_type": "ig_refresh_token",
                "access_token": token.get_secret_value(),
            },
        )
        return self._credential_material(
            payload,
            fallback_scopes=credentials.scopes,
        )

    def revoke_credentials(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        del external_account_id
        self._request(
            "DELETE",
            self._graph_url("me/permissions"),
            credentials=credentials,
            quota_bucket=API_CALL_BUCKET,
        )

    def get_profile(
        self,
        credentials: CredentialMaterial,
        *,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request_json(
            "GET",
            self._graph_url(account_id or "me"),
            credentials=credentials,
            quota_bucket=API_CALL_BUCKET,
            params={
                "fields": (
                    "id,user_id,username,name,account_type,profile_picture_url,"
                    "followers_count,media_count"
                )
            },
        )

    def list_media(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "fields": (
                "id,caption,media_type,media_product_type,permalink,"
                "thumbnail_url,timestamp,username"
            ),
            "limit": 50,
        }
        if cursor:
            params["after"] = cursor
        return self._request_json(
            "GET",
            self._graph_url(f"{external_account_id}/media"),
            credentials=credentials,
            quota_bucket=API_CALL_BUCKET,
            params=params,
        )

    def get_media(
        self,
        external_media_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._request_json(
            "GET",
            self._graph_url(external_media_id),
            credentials=credentials,
            quota_bucket=API_CALL_BUCKET,
            params={
                "fields": (
                    "id,caption,media_type,media_product_type,permalink,"
                    "thumbnail_url,timestamp,username"
                )
            },
        )

    def media_insights(
        self,
        external_media_id: str,
        media_product_type: str | None,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        metrics = [
            "views",
            "reach",
            "likes",
            "comments",
            "shares",
            "saved",
            "total_interactions",
        ]
        if (media_product_type or "").upper() == "REELS":
            metrics.extend(
                [
                    "ig_reels_video_view_total_time",
                    "ig_reels_avg_watch_time",
                ]
            )
        return self._request_json(
            "GET",
            self._graph_url(f"{external_media_id}/insights"),
            credentials=credentials,
            quota_bucket=INSIGHTS_BUCKET,
            params={"metric": ",".join(metrics)},
        )

    def account_insights(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        time_params: dict[str, str] = {
            "metric": "reach,profile_views,follower_count",
            "period": "day",
        }
        if cursor:
            time_params["after"] = cursor
        time_series = self._request_json(
            "GET",
            self._graph_url(f"{external_account_id}/insights"),
            credentials=credentials,
            quota_bucket=INSIGHTS_BUCKET,
            params=time_params,
        )
        totals = self._request_json(
            "GET",
            self._graph_url(f"{external_account_id}/insights"),
            credentials=credentials,
            quota_bucket=INSIGHTS_BUCKET,
            params={
                "metric": (
                    "accounts_engaged,total_interactions,follows_and_unfollows"
                ),
                "period": "day",
                "metric_type": "total_value",
            },
        )
        return time_series, totals

    def create_media_container(
        self,
        external_account_id: str,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        media_type = str(request.options.get("media_type", "REELS")).upper()
        data: dict[str, str] = {
            "media_type": media_type,
            "caption": request.title
            + (f"\n\n{request.description}" if request.description else ""),
        }
        if media_type == "IMAGE":
            data["image_url"] = request.media_reference
        else:
            data["video_url"] = request.media_reference
        if media_type == "REELS":
            data["share_to_feed"] = str(
                bool(request.options.get("share_to_feed", True))
            ).lower()
        cover_url = request.options.get("cover_url")
        if isinstance(cover_url, str) and cover_url:
            data["cover_url"] = cover_url
        return self._request_json(
            "POST",
            self._graph_url(f"{external_account_id}/media"),
            credentials=credentials,
            quota_bucket=PUBLISH_BUCKET,
            data=data,
        )

    def get_container_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._request_json(
            "GET",
            self._graph_url(external_publish_id),
            credentials=credentials,
            quota_bucket=PUBLISH_BUCKET,
            params={"fields": "id,status_code,status"},
        )

    def publish_container(
        self,
        external_account_id: str,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            self._graph_url(f"{external_account_id}/media_publish"),
            credentials=credentials,
            quota_bucket=PUBLISH_BUCKET,
            data={"creation_id": external_publish_id},
        )

    def publishing_limit(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._request_json(
            "GET",
            self._graph_url(f"{external_account_id}/content_publishing_limit"),
            credentials=credentials,
            quota_bucket=PUBLISH_BUCKET,
            params={"fields": "quota_usage,config"},
        )
