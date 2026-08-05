from collections.abc import Callable

from app.core.config import get_settings
from app.platforms.credentials import InMemoryPlatformSecretStore
from app.platforms.errors import PlatformCapabilityError
from app.platforms.instagram import InstagramAdapter, InstagramHttpTransport
from app.platforms.instagram.http_transport import (
    QuotaRecorder as InstagramQuotaRecorder,
)
from app.platforms.instagram.http_transport import (
    RequestRecorder as InstagramRequestRecorder,
)
from app.platforms.tiktok import TikTokAdapter, TikTokHttpTransport
from app.platforms.tiktok.http_transport import QuotaRecorder as TikTokQuotaRecorder
from app.platforms.tiktok.http_transport import (
    RequestRecorder as TikTokRequestRecorder,
)
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
InstagramAdapterFactory = Callable[
    [InstagramQuotaRecorder | None, InstagramRequestRecorder | None],
    InstagramAdapter,
]
TikTokAdapterFactory = Callable[
    [TikTokQuotaRecorder | None, TikTokRequestRecorder | None],
    TikTokAdapter,
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


def get_instagram_adapter_factory() -> InstagramAdapterFactory:
    settings = get_settings()
    app_id = settings.instagram_app_id
    app_secret = settings.instagram_app_secret
    if app_id is None or app_secret is None:
        raise InvalidRequestError("Instagram OAuth is not configured")

    def factory(
        quota_recorder: InstagramQuotaRecorder | None,
        request_recorder: InstagramRequestRecorder | None,
    ) -> InstagramAdapter:
        return InstagramAdapter(
            InstagramHttpTransport(
                app_id=app_id,
                app_secret=app_secret,
                api_version=settings.instagram_api_version,
                quota_recorder=quota_recorder,
                request_recorder=request_recorder,
                timeout_seconds=settings.instagram_http_timeout_seconds,
            )
        )

    return factory


def get_tiktok_adapter_factory() -> TikTokAdapterFactory:
    settings = get_settings()
    client_key = settings.tiktok_client_key
    client_secret = settings.tiktok_client_secret
    if client_key is None or client_secret is None:
        raise InvalidRequestError("TikTok OAuth is not configured")

    def factory(
        quota_recorder: TikTokQuotaRecorder | None,
        request_recorder: TikTokRequestRecorder | None,
    ) -> TikTokAdapter:
        return TikTokAdapter(
            TikTokHttpTransport(
                client_key=client_key,
                client_secret=client_secret,
                quota_recorder=quota_recorder,
                request_recorder=request_recorder,
                timeout_seconds=settings.tiktok_http_timeout_seconds,
            )
        )

    return factory


def require_youtube_publishing_media() -> None:
    raise PlatformCapabilityError(
        "youtube_media_unavailable",
        "YouTube publishing requires the CreatorOS media-storage sprint",
    )


def require_instagram_publishing_media() -> None:
    raise PlatformCapabilityError(
        "instagram_media_unavailable",
        "Instagram publishing requires the CreatorOS media-storage sprint",
    )


def require_tiktok_publishing_media() -> None:
    raise PlatformCapabilityError(
        "tiktok_media_unavailable",
        "TikTok publishing requires the CreatorOS media-storage sprint",
    )
