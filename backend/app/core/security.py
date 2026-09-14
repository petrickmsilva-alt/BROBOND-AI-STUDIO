from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def create_access_token(subject: str, workspace_id: str, expires_minutes: int = 60) -> str:
    """Create a short-lived access token; persist users in PostgreSQL in production."""

    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload = {"sub": subject, "workspace_id": workspace_id, "exp": expires_at}
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, str]:
    """Decode a token and raise a provider-neutral error for API dependencies."""

    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid access token") from exc
    return payload
