"""JWT authentication helpers and user-facing auth schemas."""
from collections import deque
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os
import time

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.config import settings
from .db import get_db
from .models import User, Workspace

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def _hash_password(password: str) -> str:
    """Hash with scrypt, avoiding bcrypt's 72-byte input limit."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.urlsafe_b64encode(salt + digest).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        encoded = password_hash.removeprefix("scrypt$")
        raw = base64.urlsafe_b64decode(encoded.encode())
        salt, expected = raw[:16], raw[16:]
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_for(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": user.id, "exp": expires}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def optional_user(token: str | None = Depends(optional_oauth2_scheme), db: Session = Depends(get_db)) -> User | None:
    return _user_for_token(token, db)


def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials", headers={"WWW-Authenticate": "Bearer"})
    user = _user_for_token(token, db)
    if not user:
        raise credentials_error
    return user


# ---------------------------------------------------------------------------
# PR002 — rate limiting on the credential endpoints
# ---------------------------------------------------------------------------

#: Sliding one-minute window per (client IP, endpoint). In-memory and
#: per-process on purpose: the production blueprint has no shared cache, and a
#: limiter that only protects one process is still a real reduction of brute
#: force, not a simulation of a distributed one. A shared store (Redis) is the
# declared next step, not a pretend one.
_auth_attempts: dict[tuple[str, str], deque[float]] = {}


def auth_rate_limiter(request: Request) -> None:
    """Refuse credential traffic above `settings.rate_limit_auth_per_minute`.

    The limit is configurable (Bible §16: "Rate Limit configurável") and set
    to 0 disables the limiter. The window is one minute, keyed by client IP
    and endpoint so login and register budgets do not collide.
    """

    limit = settings.rate_limit_auth_per_minute
    if limit <= 0:
        return
    key = (request.client.host if request.client else "unknown", request.url.path)
    now = time.monotonic()
    window = _auth_attempts.setdefault(key, deque())
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts, slow down",
            headers={"Retry-After": "60"},
        )
    window.append(now)


def _user_for_token(token: str | None, db: Session) -> User | None:
    """Validate a bearer token and return its user, or None.

    The shared core of `current_user` and `ws_identity`: one decoding path,
    so a token accepted by a WebSocket is accepted by the HTTP route and vice
    versa.
    """

    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.get(User, user_id)


def ws_identity(token: str | None, db: Session) -> User | None:
    """Identity for WebSocket routes, which cannot carry an Authorization header.

    Browsers open WebSockets without custom headers, so the token arrives as
    the `token` query parameter. Returns the authenticated user or None; the
    route closes with 1008 when it is None.
    """

    return _user_for_token(token, db)


def register(request: RegisterRequest, db: Session) -> TokenResponse:
    if db.scalar(select(User).where(User.email == request.email.lower())):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=request.email.lower(), name=request.name, password_hash=_hash_password(request.password))
    user.workspaces.append(Workspace(name="Personal workspace"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=_token_for(user), user=UserResponse.model_validate(user, from_attributes=True))


def login(request: LoginRequest, db: Session) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == request.email.lower()))
    if not user or not _verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenResponse(access_token=_token_for(user), user=UserResponse.model_validate(user, from_attributes=True))


def google_user(db: Session, *, email: str, name: str) -> TokenResponse:
    """Find or provision a Google identity without storing provider tokens."""
    normalized = email.lower()
    user = db.scalar(select(User).where(User.email == normalized))
    if not user:
        # Google accounts do not use the password flow; retain the existing
        # schema and make the generated value intentionally unreachable.
        user = User(email=normalized, name=name[:120] or normalized, password_hash=_hash_password(os.urandom(32).hex()))
        user.workspaces.append(Workspace(name="Personal workspace"))
        db.add(user)
        db.commit()
        db.refresh(user)
    return TokenResponse(access_token=_token_for(user), user=UserResponse.model_validate(user, from_attributes=True))
