from collections.abc import Callable

from app.core.config import get_settings
from app.platforms.credentials import InMemoryPlatformSecretStore
from app.platforms.errors import PlatformCapabilityError
from app.platforms.youtube import (
    DisabledYouTubeMediaSource,
    YouTubeAdapter,
    YouTubeHttpTransport,
)
from app.platforms.youtube.http_transport import QuotaRecorder, RequestRecorder
from app.services.errors import InvalidRequestError

YouTubeAdapterFactory = Callable[
    [QuotaRecorder | None, RequestRecorder | None],
    YouTubeAdapter,
]

_development_secret_store = InMemoryPlatformSecretStore()


def get_platform_secret_store() -> InMemoryPlatformSecretStore:
    settings = get_settings()
    if settings.environment.lower() == "production":
        raise InvalidRequestError(
            "A production platform secret store must be configured"
        )
    return _development_secret_store


def get_youtube_adapter_factory() -> YouTubeAdapterFactory:
    settings = get_settings()
    client_id = settings.youtube_client_id
    client_secret = settings.youtube_client_secret
    if client_id is None or client_secret is None:
        raise InvalidRequestError("YouTube OAuth is not configured")

    def factory(
        quota_recorder: QuotaRecorder | None,
        request_recorder: RequestRecorder | None,
    ) -> YouTubeAdapter:
        return YouTubeAdapter(
            YouTubeHttpTransport(
                client_id=client_id,
                client_secret=client_secret,
                media_source=DisabledYouTubeMediaSource(),
                quota_recorder=quota_recorder,
                request_recorder=request_recorder,
                timeout_seconds=settings.youtube_http_timeout_seconds,
                analytics_lookback_days=settings.youtube_analytics_lookback_days,
            )
        )

    return factory


def require_youtube_publishing_media() -> None:
    raise PlatformCapabilityError(
        "youtube_media_unavailable",
        "YouTube publishing requires the CreatorOS media-storage sprint",
    )
