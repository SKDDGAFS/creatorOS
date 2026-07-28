from functools import lru_cache

from pydantic import model_validator
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

    @model_validator(mode="after")
    def require_secure_production_cookies(self) -> Settings:
        if self.environment.lower() == "production" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
