from __future__ import annotations

import json
from collections.abc import Mapping

import httpx2
from pydantic import SecretStr

from app.ai.contracts import (
    AIProviderHealth,
    AIProviderResult,
    AIStructuredRequest,
)
from app.ai.errors import (
    AIOutputValidationError,
    AIPermanentProviderError,
    AIRetryableProviderError,
)

MAX_PROVIDER_RESPONSE_BYTES = 5_000_000


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AIOutputValidationError(
            "ai_response_invalid",
            "AI provider returned an invalid structured response",
        )
    return {str(key): item for key, item in value.items()}


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, str):
        raise AIOutputValidationError(
            "ai_response_invalid",
            "AI provider returned an invalid structured response",
        )
    try:
        return _object(json.loads(value))
    except (json.JSONDecodeError, TypeError) as exc:
        raise AIOutputValidationError(
            "ai_response_invalid",
            "AI provider returned invalid JSON",
        ) from exc


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _request_id(headers: Mapping[str, str]) -> str | None:
    for name in ("x-request-id", "request-id"):
        value = headers.get(name)
        if value:
            return value[:255]
    return None


def _raise_http_error(response: httpx2.Response) -> None:
    if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
        raise AIRetryableProviderError(
            "ai_provider_temporarily_unavailable",
            "AI provider is temporarily unavailable",
        )
    if response.status_code in {401, 403}:
        raise AIPermanentProviderError(
            "ai_provider_authentication_failed",
            "AI provider authentication failed",
        )
    raise AIPermanentProviderError(
        "ai_provider_request_rejected",
        "AI provider rejected the request",
    )


def _check_response_size(response: httpx2.Response) -> None:
    content_length = response.headers.get("content-length")
    if (
        content_length
        and content_length.isdigit()
        and int(content_length) > MAX_PROVIDER_RESPONSE_BYTES
    ):
        raise AIPermanentProviderError(
            "ai_response_too_large",
            "AI provider response exceeds the allowed size",
        )
    if len(response.content) > MAX_PROVIDER_RESPONSE_BYTES:
        raise AIPermanentProviderError(
            "ai_response_too_large",
            "AI provider response exceeds the allowed size",
        )


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        client: httpx2.Client | None = None,
    ) -> None:
        self._base_url = f"{base_url.rstrip('/')}/"
        self._timeout_seconds = timeout_seconds
        self._client = client

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
    ) -> httpx2.Response:
        if self._client is not None:
            if json_body is None:
                return self._client.request(method, path)
            return self._client.request(method, path, json=json_body)
        with httpx2.Client(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            if json_body is None:
                return client.request(method, path)
            return client.request(method, path, json=json_body)

    def generate_structured(
        self,
        request: AIStructuredRequest,
    ) -> AIProviderResult:
        try:
            response = self._request(
                "POST",
                "api/chat",
                json_body={
                    "model": request.model,
                    "messages": [
                        message.model_dump(mode="json") for message in request.messages
                    ],
                    "format": request.output_schema,
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": request.max_output_tokens,
                    },
                },
            )
        except httpx2.TimeoutException as exc:
            raise AIRetryableProviderError(
                "ai_provider_timeout",
                "AI provider timed out",
            ) from exc
        except httpx2.RequestError as exc:
            raise AIRetryableProviderError(
                "ai_provider_unreachable",
                "AI provider is unavailable",
            ) from exc
        if response.status_code >= 400:
            _raise_http_error(response)
        _check_response_size(response)
        try:
            payload = _object(response.json())
            message = _object(payload.get("message"))
            output = _json_object(message.get("content"))
        except (ValueError, AIOutputValidationError) as exc:
            raise AIOutputValidationError(
                "ai_response_invalid",
                "AI provider returned an invalid structured response",
            ) from exc
        return AIProviderResult(
            output=output,
            input_tokens=_integer(payload.get("prompt_eval_count")),
            output_tokens=_integer(payload.get("eval_count")),
            finish_reason=(
                str(payload["done_reason"])[:100]
                if payload.get("done_reason") is not None
                else None
            ),
            provider_request_id=_request_id(response.headers),
        )

    def health_check(self) -> AIProviderHealth:
        try:
            response = self._request("GET", "api/tags")
        except httpx2.RequestError:
            return AIProviderHealth(
                healthy=False,
                safe_message="Local AI provider is unavailable",
            )
        try:
            _check_response_size(response)
        except AIPermanentProviderError:
            return AIProviderHealth(
                healthy=False,
                safe_message="Local AI provider returned an invalid response",
            )
        return AIProviderHealth(
            healthy=response.status_code < 400,
            safe_message=(
                "Local AI provider is ready"
                if response.status_code < 400
                else "Local AI provider is unavailable"
            ),
        )


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        api_key: SecretStr | None,
        client: httpx2.Client | None = None,
    ) -> None:
        headers = {"Content-Type": "application/json"}
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key.get_secret_value()}"
        self._base_url = f"{base_url.rstrip('/')}/"
        self._headers = headers
        self._timeout_seconds = timeout_seconds
        self._client = client

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
    ) -> httpx2.Response:
        if self._client is not None:
            if json_body is None:
                return self._client.request(method, path, headers=self._headers)
            return self._client.request(
                method,
                path,
                headers=self._headers,
                json=json_body,
            )
        with httpx2.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            if json_body is None:
                return client.request(method, path)
            return client.request(method, path, json=json_body)

    def generate_structured(
        self,
        request: AIStructuredRequest,
    ) -> AIProviderResult:
        try:
            response = self._request(
                "POST",
                "chat/completions",
                json_body={
                    "model": request.model,
                    "messages": [
                        message.model_dump(mode="json") for message in request.messages
                    ],
                    "max_tokens": request.max_output_tokens,
                    "temperature": request.temperature,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": request.output_schema_name,
                            "strict": True,
                            "schema": request.output_schema,
                        },
                    },
                },
            )
        except httpx2.TimeoutException as exc:
            raise AIRetryableProviderError(
                "ai_provider_timeout",
                "AI provider timed out",
            ) from exc
        except httpx2.RequestError as exc:
            raise AIRetryableProviderError(
                "ai_provider_unreachable",
                "AI provider is unavailable",
            ) from exc
        if response.status_code >= 400:
            _raise_http_error(response)
        _check_response_size(response)
        try:
            payload = _object(response.json())
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError
            choice = _object(choices[0])
            message = _object(choice.get("message"))
            output = _json_object(message.get("content"))
            usage = _object(payload.get("usage", {}))
        except (ValueError, AIOutputValidationError) as exc:
            raise AIOutputValidationError(
                "ai_response_invalid",
                "AI provider returned an invalid structured response",
            ) from exc
        return AIProviderResult(
            output=output,
            input_tokens=_integer(usage.get("prompt_tokens")),
            output_tokens=_integer(usage.get("completion_tokens")),
            finish_reason=(
                str(choice["finish_reason"])[:100]
                if choice.get("finish_reason") is not None
                else None
            ),
            provider_request_id=_request_id(response.headers),
        )

    def health_check(self) -> AIProviderHealth:
        try:
            response = self._request("GET", "models")
        except httpx2.RequestError:
            return AIProviderHealth(
                healthy=False,
                safe_message="AI provider is unavailable",
            )
        try:
            _check_response_size(response)
        except AIPermanentProviderError:
            return AIProviderHealth(
                healthy=False,
                safe_message="AI provider returned an invalid response",
            )
        return AIProviderHealth(
            healthy=response.status_code < 400,
            safe_message=(
                "AI provider is ready"
                if response.status_code < 400
                else "AI provider is unavailable"
            ),
        )
