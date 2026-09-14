"""JWT authentication helpers and user-facing auth schemas."""
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os

import jwt
from fastapi import Depends, HTTPException, status
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
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        return db.get(User, user_id) if user_id else None
    except jwt.PyJWTError:
        return None


def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_error
    except jwt.PyJWTError as error:
        raise credentials_error from error
    user = db.get(User, user_id)
    if not user:
        raise credentials_error
    return user


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
