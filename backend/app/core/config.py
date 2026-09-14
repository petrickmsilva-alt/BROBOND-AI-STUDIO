"""Environment-backed settings for local and hosted deployments."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BROBOND AI STUDIO API"
    database_url: str = "sqlite:///./brobond.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BROBOND_", extra="ignore")


settings = Settings()
