"""Environment-backed settings for local and hosted deployments."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BROBOND AI STUDIO API"
    database_url: str = "sqlite:///./brobond.db"
    redis_url: str = "redis://localhost:6379/0"
    queue_enabled: bool = False
    storage_enabled: bool = False
    inference_enabled: bool = False
    training_enabled: bool = False
    lora_trainer_command: str = ""
    video_model_id: str = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
    weights_dir: str = "weights"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "brobond"
    minio_secret_key: str = "brobond_local_storage"
    minio_bucket: str = "brobond-assets"
    local_media_dir: str = "media"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    # Comma-separated list of browser origins allowed by the CORS middleware.
    # Render sets the deployed web origin here (see render.yaml).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BROBOND_", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Accept PaaS connection strings (e.g. Render's `postgres://...`) and
        map driverless PostgreSQL URLs to the bundled psycopg (v3) driver."""
        if isinstance(value, str) and value.startswith(("postgres://", "postgresql://")):
            value = "postgresql+psycopg://" + value.split("://", 1)[1]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
