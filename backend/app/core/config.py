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
    video_model_id: str = ""
    weights_dir: str = "weights"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "brobond"
    minio_secret_key: str = "brobond_local_storage"
    minio_bucket: str = "brobond-assets"
    local_media_dir: str = "media"
    #: PR002: the default is a dev-only 70-byte secret. RFC 7518 requires at
    #: least 32 bytes for an HS256 HMAC key, and the validator below refuses
    #: anything shorter, including a misconfigured environment variable.
    jwt_secret: str = "brobond-local-development-secret-0123456789-abcdefghijklmnopqrstuvwxyz"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    #: PR002: auth endpoints (login/register) accept at most this many attempts
    #: per client IP per minute, per process. Set to 0 to disable the limiter.
    rate_limit_auth_per_minute: int = 20
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

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_be_long_enough(cls, value: str) -> str:
        """PR002: fail at startup instead of signing with a weak key.

        The previous 23-byte default was below RFC 7518's 32-byte minimum for
        HS256 and PyJWT warned on every call. A deployment that sets a short
        `BROBOND_JWT_SECRET` now refuses to boot instead of running insecure.
        """

        if len(value.encode("utf-8")) < 32:
            raise ValueError("BROBOND_JWT_SECRET must be at least 32 bytes (RFC 7518, HS256)")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
