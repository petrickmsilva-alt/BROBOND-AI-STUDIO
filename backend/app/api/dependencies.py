from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_access_token
from app.schemas.auth import SessionUser


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> SessionUser:
    """Resolve the request identity from JWT for protected routes."""

    try:
        payload = decode_access_token(token)
        return SessionUser(id=payload["sub"], email=payload["sub"], workspace_id=payload["workspace_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
