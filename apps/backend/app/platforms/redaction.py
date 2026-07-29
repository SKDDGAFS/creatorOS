from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, SecretStr

REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "code_verifier",
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, SecretStr):
        return REDACTED
    if isinstance(value, BaseModel):
        return redact_value(value.model_dump())
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [redact_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def safe_request_metadata(
    *,
    method: str,
    url: str,
    headers: Mapping[str, Any] | None = None,
    body: Any = None,
) -> dict[str, Any]:
    parsed = urlsplit(url)
    return {
        "method": method.upper()[:10],
        "host": (parsed.hostname or "")[:255],
        "path": (parsed.path or "/")[:1000],
        "headers": redact_value(headers or {}),
        "body": redact_value(body),
    }
