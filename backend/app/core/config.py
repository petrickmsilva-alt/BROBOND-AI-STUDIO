from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration shared by the API and worker processes."""

    app_name: str = "BROBOND AI STUDIO API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://brobond:brobond@localhost:5432/brobond"
    minio_endpoint: str = "localhost:9000"
    minio_bucket: str = "brobond-assets"
    secret_key: str = "change-me-in-production"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object so dependencies share one configuration."""

    return Settings()
