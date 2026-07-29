from functools import lru_cache

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    application_name: str = "CreatorOS API"
    environment: str = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://127.0.0.1/creatoros"
    frontend_origin: str = "http://localhost:3000"
    session_cookie_name: str = "creatoros_session"
    csrf_cookie_name: str = "creatoros_csrf"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 24
    password_reset_ttl_minutes: int = 30
    login_max_failures: int = 5
    login_window_minutes: int = 15
    login_block_minutes: int = 15
    oauth_state_ttl_minutes: int = 10
    youtube_client_id: str | None = None
    youtube_client_secret: SecretStr | None = None
    youtube_oauth_redirect_uri: str = (
        "http://127.0.0.1:8000/api/integrations/youtube/oauth/callback"
    )
    youtube_enable_publishing: bool = False
    youtube_http_timeout_seconds: float = 30.0
    youtube_analytics_lookback_days: int = 28

    @field_validator("youtube_client_id", "youtube_client_secret", mode="before")
    @classmethod
    def empty_optional_secrets_are_unset(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def require_secure_production_cookies(self) -> Settings:
        if self.environment.lower() == "production" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        if bool(self.youtube_client_id) != bool(self.youtube_client_secret):
            raise ValueError(
                "YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set together"
            )
        if (
            self.environment.lower() == "production"
            and self.youtube_client_id
            and not self.youtube_oauth_redirect_uri.startswith("https://")
        ):
            raise ValueError(
                "YOUTUBE_OAUTH_REDIRECT_URI must use HTTPS in production"
            )
        if self.youtube_http_timeout_seconds <= 0:
            raise ValueError("YOUTUBE_HTTP_TIMEOUT_SECONDS must be positive")
        if not 1 <= self.oauth_state_ttl_minutes <= 60:
            raise ValueError("OAUTH_STATE_TTL_MINUTES must be between 1 and 60")
        if not 1 <= self.youtube_analytics_lookback_days <= 3650:
            raise ValueError(
                "YOUTUBE_ANALYTICS_LOOKBACK_DAYS must be between 1 and 3650"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
