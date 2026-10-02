from functools import lru_cache

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
    storage_path: str = "storage"
    watch_folder_path: str = "watch"
    max_upload_size_bytes: int = 500_000_000
    credential_encryption_key: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    whisper_model: str = "small"


@lru_cache
def get_settings() -> Settings:
    return Settings()
