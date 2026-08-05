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

TIKTOK_API_ORIGIN = "https://open.tiktokapis.com"
TIKTOK_TOKEN_ENDPOINT = f"{TIKTOK_API_ORIGIN}/v2/oauth/token/"
TIKTOK_REVOKE_ENDPOINT = f"{TIKTOK_API_ORIGIN}/v2/oauth/revoke/"

API_CALL_BUCKET = "tiktok_api_calls"
PUBLISH_BUCKET = "tiktok_publishing_calls"

PROFILE_FIELDS = (
    "open_id,union_id,avatar_url,display_name,bio_description,"
    "profile_deep_link,is_verified,username,follower_count,following_count,"
    "likes_count,video_count"
)
VIDEO_FIELDS = (
    "id,create_time,cover_image_url,share_url,video_description,duration,"
    "height,width,title,embed_link,like_count,comment_count,share_count,"
    "view_count"
)


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


def _json_payload(response: httpx2.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _error_details(response: httpx2.Response) -> tuple[str | None, str | None]:
    payload = _json_payload(response)
    error = payload.get("error")
    if isinstance(error, str):
        description = payload.get("error_description")
        return error, description if isinstance(description, str) else None
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        return (
            code if isinstance(code, str) and code.lower() != "ok" else None,
            message if isinstance(message, str) else None,
        )
    return None, None


def _provider_request_id(response: httpx2.Response) -> str | None:
    for header_name in ("x-tt-logid", "x-tt-trace-id"):
        header = response.headers.get(header_name)
        if header:
            return header[:255]
    payload = _json_payload(response)
    nested = payload.get("error")
    if isinstance(nested, dict):
        value = nested.get("log_id") or nested.get("logid")
        if isinstance(value, str) and value:
            return value[:255]
    value = payload.get("log_id") or payload.get("logid")
    return value[:255] if isinstance(value, str) and value else None


def _retry_after(response: httpx2.Response) -> int | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    return max(0, seconds)


AUTH_CODES = {
    "access_denied",
    "invalid_client",
    "invalid_grant",
    "invalid_scope",
    "scope_not_authorized",
    "token_not_authorized_for_specified_publish_id",
    "unauthorized_client",
}
EXPIRED_CODES = {"access_token_invalid", "invalid_grant"}
RATE_LIMIT_CODES = {
    "rate_limit_exceeded",
    "reached_active_user_cap",
    "spam_risk_too_many_pending_share",
    "spam_risk_too_many_posts",
}
TRANSIENT_CODES = {"internal_error", "server_error", "temporarily_unavailable"}


class TikTokHttpTransport:
    def __init__(
        self,
        *,
        client_key: str,
        client_secret: SecretStr,
        client: httpx2.Client | None = None,
        quota_recorder: QuotaRecorder | None = None,
        request_recorder: RequestRecorder | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not client_key.strip():
            raise ValueError("client_key cannot be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client_key = client_key
        self._client_secret = client_secret
        self._client = client
        self._quota_recorder = quota_recorder
        self._request_recorder = request_recorder
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _url(path: str) -> str:
        return f"{TIKTOK_API_ORIGIN}/{path.lstrip('/')}"

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx2.Response:
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
                "tiktok_timeout",
                "TikTok did not respond before the request timeout",
            ) from exc
        except httpx2.RequestError as exc:
            raise PlatformTransientError(
                "tiktok_network_error",
                "TikTok could not be reached",
            ) from exc

    @staticmethod
    def _outcome(response: httpx2.Response) -> RequestOutcome:
        code, _ = _error_details(response)
        if response.status_code == 401 or code in AUTH_CODES or code in EXPIRED_CODES:
            return RequestOutcome.AUTH_FAILURE
        if response.status_code == 429 or code in RATE_LIMIT_CODES:
            return RequestOutcome.RATE_LIMITED
        if response.status_code >= 500 or code in TRANSIENT_CODES:
            return RequestOutcome.TRANSIENT_FAILURE
        return RequestOutcome.PERMANENT_FAILURE

    @staticmethod
    def _raise_provider_error(response: httpx2.Response) -> None:
        code, _ = _error_details(response)
        provider_request_id = _provider_request_id(response)
        safe_code = f"tiktok_{code or response.status_code}"
        if response.status_code == 401 or code in EXPIRED_CODES:
            raise PlatformCredentialExpiredError(
                safe_code,
                "TikTok authorization expired or was revoked",
            )
        if code in AUTH_CODES:
            raise PlatformAuthenticationError(
                safe_code,
                "TikTok authorization does not grant the required permission",
            )
        if response.status_code == 429 or code in RATE_LIMIT_CODES:
            raise PlatformRateLimitError(
                safe_code,
                "TikTok request or publishing rate limit was reached",
                retry_after_seconds=_retry_after(response),
                provider_request_id=provider_request_id,
            )
        if response.status_code >= 500 or code in TRANSIENT_CODES:
            raise PlatformTransientError(
                safe_code,
                "TikTok temporarily could not complete the request",
                provider_request_id=provider_request_id,
            )
        raise PlatformPermanentError(
            safe_code,
            "TikTok rejected the request",
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
            response = self._send(method, url, headers=request_headers, **kwargs)
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
        error_code, _ = _error_details(response)
        succeeded = response.status_code in expected_statuses and error_code is None
        outcome = RequestOutcome.SUCCEEDED if succeeded else self._outcome(response)
        if self._request_recorder is not None:
            self._request_recorder(
                method,
                url,
                response.status_code,
                max(0, round((perf_counter() - started_at) * 1000)),
                outcome,
                _provider_request_id(response),
            )
        if not succeeded:
            self._raise_provider_error(response)
        return response

    def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request(method, url, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise PlatformTransientError(
                "tiktok_invalid_response",
                "TikTok returned an invalid response",
                provider_request_id=_provider_request_id(response),
            ) from exc
        if not isinstance(payload, dict):
            raise PlatformTransientError(
                "tiktok_invalid_response",
                "TikTok returned an invalid response",
                provider_request_id=_provider_request_id(response),
            )
        return payload

    @staticmethod
    def _credential_material(payload: dict[str, Any]) -> CredentialMaterial:
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise PlatformAuthenticationError(
                "tiktok_token_missing",
                "TikTok did not return an access token",
            )
        refresh_token = payload.get("refresh_token")
        scope = payload.get("scope")
        scopes = (
            tuple(item.strip() for item in scope.split(",") if item.strip())
            if isinstance(scope, str)
            else ()
        )
        expires_at: datetime | None = None
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, int) and expires_in > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return CredentialMaterial(
            access_token=SecretStr(access_token),
            refresh_token=(
                SecretStr(refresh_token)
                if isinstance(refresh_token, str) and refresh_token
                else None
            ),
            expires_at=expires_at,
            scopes=scopes,
        )

    def exchange_authorization_code(
        self,
        request: ConnectAccountRequest,
    ) -> CredentialMaterial:
        data = {
            "client_key": self._client_key,
            "client_secret": self._client_secret.get_secret_value(),
            "code": request.authorization_code.get_secret_value(),
            "grant_type": "authorization_code",
            "redirect_uri": request.redirect_uri,
        }
        if request.code_verifier is not None:
            data["code_verifier"] = request.code_verifier.get_secret_value()
        return self._credential_material(
            self._request_json("POST", TIKTOK_TOKEN_ENDPOINT, data=data)
        )

    def refresh_credentials(
        self,
        credentials: CredentialMaterial,
    ) -> CredentialMaterial:
        if credentials.refresh_token is None:
            raise PlatformCredentialExpiredError(
                "tiktok_refresh_token_missing",
                "TikTok credentials cannot be refreshed",
            )
        return self._credential_material(
            self._request_json(
                "POST",
                TIKTOK_TOKEN_ENDPOINT,
                data={
                    "client_key": self._client_key,
                    "client_secret": self._client_secret.get_secret_value(),
                    "grant_type": "refresh_token",
                    "refresh_token": credentials.refresh_token.get_secret_value(),
                },
            )
        )

    def revoke_credentials(
        self,
        external_account_id: str,
        credentials: CredentialMaterial,
    ) -> None:
        del external_account_id
        self._request(
            "POST",
            TIKTOK_REVOKE_ENDPOINT,
            data={
                "client_key": self._client_key,
                "client_secret": self._client_secret.get_secret_value(),
                "token": credentials.access_token.get_secret_value(),
            },
        )

    def get_profile(self, credentials: CredentialMaterial) -> dict[str, Any]:
        return self._request_json(
            "GET",
            self._url("v2/user/info/"),
            credentials=credentials,
            quota_bucket=API_CALL_BUCKET,
            params={"fields": PROFILE_FIELDS},
        )

    def list_videos(
        self,
        credentials: CredentialMaterial,
        *,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, int] = {"max_count": 20}
        if cursor is not None:
            try:
                body["cursor"] = int(cursor)
            except ValueError as exc:
                raise PlatformPermanentError(
                    "tiktok_cursor_invalid",
                    "TikTok video cursor is invalid",
                ) from exc
        return self._request_json(
            "POST",
            self._url("v2/video/list/"),
            credentials=credentials,
            quota_bucket=API_CALL_BUCKET,
            params={"fields": VIDEO_FIELDS},
            json=body,
        )

    def get_video(
        self,
        external_video_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            self._url("v2/video/query/"),
            credentials=credentials,
            quota_bucket=API_CALL_BUCKET,
            params={"fields": VIDEO_FIELDS},
            json={"filters": {"video_ids": [external_video_id]}},
        )

    def get_creator_info(
        self,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            self._url("v2/post/publish/creator_info/query/"),
            credentials=credentials,
            quota_bucket=PUBLISH_BUCKET,
            json={},
        )

    def initialize_publish(
        self,
        request: PublishRequest,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        options = request.options
        caption = request.title
        if request.description:
            caption = f"{caption}\n\n{request.description}"
        post_info = {
            "title": caption,
            "privacy_level": options["privacy_level"],
            "disable_duet": bool(options.get("disable_duet", False)),
            "disable_comment": bool(options.get("disable_comment", False)),
            "disable_stitch": bool(options.get("disable_stitch", False)),
            "brand_content_toggle": bool(options.get("brand_content_toggle", False)),
            "brand_organic_toggle": bool(options.get("brand_organic_toggle", False)),
            "is_aigc": bool(options.get("is_aigc", False)),
        }
        return self._request_json(
            "POST",
            self._url("v2/post/publish/video/init/"),
            credentials=credentials,
            quota_bucket=PUBLISH_BUCKET,
            json={
                "post_info": post_info,
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": request.media_reference,
                },
            },
        )

    def get_publish_status(
        self,
        external_publish_id: str,
        credentials: CredentialMaterial,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            self._url("v2/post/publish/status/fetch/"),
            credentials=credentials,
            quota_bucket=PUBLISH_BUCKET,
            json={"publish_id": external_publish_id},
        )
