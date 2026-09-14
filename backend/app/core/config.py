"""Environment-backed settings for local and hosted deployments."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BROBOND AI STUDIO API"
    database_url: str = "sqlite:///./brobond.db"
    redis_url: str = "redis://localhost:6379/0"
    queue_enabled: bool = False
    storage_enabled: bool = False
    inference_enabled: bool = False
    weights_dir: str = "weights"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "brobond"
    minio_secret_key: str = "brobond_local_storage"
    minio_bucket: str = "brobond-assets"
    local_media_dir: str = "media"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BROBOND_", extra="ignore")


settings = Settings()
