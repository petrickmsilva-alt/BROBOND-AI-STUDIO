"""Environment-backed settings for local and hosted deployments."""
import os

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: PR009.4 — the development-only fallback. It must never survive on Render:
#: the model validator below refuses to boot production on SQLite.
SQLITE_DEV_FALLBACK = "sqlite:///./brobond.db"


def _running_on_render() -> bool:
    """True when the process runs on Render (the platform sets `RENDER=true`
    on every service). Accepts the usual truthy spellings defensively."""
    return os.environ.get("RENDER", "").strip().lower() in {"true", "1", "yes", "on"}


class Settings(BaseSettings):
    app_name: str = "BROBOND AI STUDIO API"
    #: PR009.4 — read priority: BROBOND_DATABASE_URL, then DATABASE_URL (the
    #: name PaaS providers inject by convention), then the SQLite dev
    #: fallback. `AliasChoices` is ordered: the first environment variable
    #: found wins, so an explicit BROBOND_DATABASE_URL always beats a
    #: platform-injected DATABASE_URL.
    database_url: str = Field(
        default=SQLITE_DEV_FALLBACK,
        validation_alias=AliasChoices("BROBOND_DATABASE_URL", "DATABASE_URL"),
    )
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
    #: PR009 — provider execution deadlines (seconds), configurable per
    #: deployment via `BROBOND_PROVIDER_TIMEOUT_*_SECONDS`. Flux renders are
    #: bounded at 90s and Wan renders at 300s by default; anything else gets
    #: the generic deadline. A deadline of 0 disables the guard.
    provider_timeout_flux_seconds: float = 90.0
    provider_timeout_wan_seconds: float = 300.0
    provider_timeout_default_seconds: float = 120.0
    #: PR009 — retry engine backoff base delay (seconds). The attempt budget
    #: itself (3) is a product invariant and lives in `providers/retry_policy`.
    provider_retry_base_delay_seconds: float = 0.25
    #: PR009 — optional JSONL sink for provider telemetry records. Empty keeps
    #: telemetry in-process only.
    provider_telemetry_log: str = ""
    # Comma-separated list of browser origins allowed by the CORS middleware.
    # Render sets the same value explicitly (see render.yaml).
    cors_origins: str = "https://brobond-studio-web.onrender.com,http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BROBOND_", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Accept PaaS connection strings (e.g. Render's `postgres://...`) and
        map driverless PostgreSQL URLs to the bundled psycopg (v3) driver."""
        if isinstance(value, str) and value.startswith(("postgres://", "postgresql://")):
            value = "postgresql+psycopg://" + value.split("://", 1)[1]
        return value

    @model_validator(mode="after")
    def refuse_sqlite_on_render(self) -> "Settings":
        """PR009.4: production never boots on SQLite.

        On Render (`RENDER=true`) the database URL must come from the
        environment — `BROBOND_DATABASE_URL` or `DATABASE_URL`. If neither is
        set the app previously fell back to an ephemeral SQLite file inside
        the container and silently lost all data on every deploy. Now it
        refuses to start instead.
        """

        if _running_on_render() and self.database_url.startswith("sqlite"):
            raise RuntimeError(
                "Refusing to start on Render with a SQLite database: data "
                "would be wiped on every deploy or restart. Set "
                "BROBOND_DATABASE_URL (or DATABASE_URL) to the managed "
                "Postgres connection string — see render.yaml "
                "(envVars.BROBOND_DATABASE_URL fromDatabase brobond-studio-db) "
                "and docs/DEPLOYMENT.md."
            )
        return self

    def is_production_database(self) -> bool:
        """PR009.4: True only when the configured database is PostgreSQL."""
        return self.database_url.startswith(("postgresql", "postgres"))

    def database_banner(self) -> str:
        """PR009.4: the startup banner line — unmissable, never plain INFO."""
        if self.is_production_database():
            return "🟢 PostgreSQL Connected"
        return "🔴 SQLite Development Mode"

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

    @staticmethod
    def parse_cors_origins(value: str) -> list[str]:
        """Parse ``BROBOND_CORS_ORIGINS`` as a trimmed comma-separated list."""
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return self.parse_cors_origins(self.cors_origins)


settings = Settings()
