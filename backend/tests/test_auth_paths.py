"""ETAPA 16 tests — authentication paths that were never exercised.

`auth.py` sat at 89% because the uncovered lines are all refusals: a malformed
password hash, a token signed with the wrong key, a token with no subject, a
token for a user who no longer exists, and a login for an unknown email. Those
are exactly the lines that decide who gets in, so they are worth pinning even
though the happy path already worked.

A real in-memory SQLite session is used rather than a fake: the queries are part
of what is being tested.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def db():
    from app.db import Base
    from app import models  # noqa: F401 — importing registers the tables on Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user(db):
    from app.auth import _hash_password
    from app.models import User, Workspace

    record = User(
        email="director@brobond.ai",
        name="Petrick Martins",
        password_hash=_hash_password("correct-horse-battery"),
    )
    record.workspaces.append(Workspace(name="Personal workspace"))
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _token(sub: str | None, secret: str | None = None, expired: bool = False) -> str:
    from app.core.config import settings

    payload: dict = {"sub": sub}
    expires = datetime.now(timezone.utc) + timedelta(minutes=-5 if expired else 30)
    payload["exp"] = expires
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_a_password_round_trips_through_scrypt() -> None:
    from app.auth import _hash_password, _verify_password

    hashed = _hash_password("correct-horse-battery")
    assert hashed.startswith("scrypt$")
    assert _verify_password("correct-horse-battery", hashed) is True
    assert _verify_password("wrong-password", hashed) is False


def test_the_same_password_hashes_differently_each_time() -> None:
    """A per-password salt, not a global one."""

    from app.auth import _hash_password

    assert _hash_password("same") != _hash_password("same")


@pytest.mark.parametrize(
    "broken",
    [
        "",                      # nothing at all
        "scrypt$",               # prefix with no payload
        "scrypt$not-base64!!",   # undecodable
        "scrypt$c2hvcnQ=",       # shorter than the 16-byte salt
        "plaintext-hash",        # a hash from another scheme
    ],
)
def test_a_malformed_hash_is_refused_not_raised(broken: str) -> None:
    """A corrupt row must deny access, not 500 the login endpoint."""

    from app.auth import _verify_password

    assert _verify_password("anything", broken) is False


def test_an_empty_password_does_not_match_a_real_hash() -> None:
    from app.auth import _hash_password, _verify_password

    assert _verify_password("", _hash_password("correct-horse-battery")) is False


# ---------------------------------------------------------------------------
# optional_user — an absent or bad token is simply no user
# ---------------------------------------------------------------------------


def test_optional_user_returns_none_without_a_token(db) -> None:
    from app.auth import optional_user

    assert optional_user(token=None, db=db) is None
    assert optional_user(token="", db=db) is None


def test_optional_user_resolves_a_valid_token(db, user) -> None:
    from app.auth import optional_user

    resolved = optional_user(token=_token(user.id), db=db)
    assert resolved is not None and resolved.email == user.email


def test_optional_user_returns_none_for_a_forged_token(db) -> None:
    from app.auth import optional_user

    assert optional_user(token=_token("someone", secret="not-the-server-secret"), db=db) is None


def test_optional_user_returns_none_for_an_expired_token(db, user) -> None:
    from app.auth import optional_user

    assert optional_user(token=_token(user.id, expired=True), db=db) is None


def test_optional_user_returns_none_for_a_token_without_a_subject(db) -> None:
    from app.auth import optional_user

    assert optional_user(token=_token(None), db=db) is None


def test_optional_user_returns_none_for_a_deleted_user(db) -> None:
    from app.auth import optional_user

    assert optional_user(token=_token("no-such-user"), db=db) is None


# ---------------------------------------------------------------------------
# current_user — every refusal is a 401, never a leak
# ---------------------------------------------------------------------------


def test_current_user_resolves_a_valid_token(db, user) -> None:
    from app.auth import current_user

    assert current_user(token=_token(user.id), db=db).email == user.email


def test_current_user_refuses_a_forged_signature(db) -> None:
    from app.auth import current_user

    with pytest.raises(HTTPException) as info:
        current_user(token=_token("someone", secret="not-the-server-secret"), db=db)
    assert info.value.status_code == 401
    assert info.value.headers["WWW-Authenticate"] == "Bearer"


def test_current_user_refuses_an_expired_token(db, user) -> None:
    from app.auth import current_user

    with pytest.raises(HTTPException) as info:
        current_user(token=_token(user.id, expired=True), db=db)
    assert info.value.status_code == 401


def test_current_user_refuses_garbage(db) -> None:
    from app.auth import current_user

    with pytest.raises(HTTPException) as info:
        current_user(token="not.a.jwt", db=db)
    assert info.value.status_code == 401


def test_current_user_refuses_a_token_with_no_subject(db) -> None:
    """A well-signed token that names nobody must not become an anonymous user."""

    from app.auth import current_user

    with pytest.raises(HTTPException) as info:
        current_user(token=_token(None), db=db)
    assert info.value.status_code == 401


def test_current_user_refuses_a_token_for_a_deleted_user(db) -> None:
    from app.auth import current_user

    with pytest.raises(HTTPException) as info:
        current_user(token=_token("no-such-user"), db=db)
    assert info.value.status_code == 401


def test_current_user_does_not_reveal_which_case_failed(db, user) -> None:
    """Forged, expired, subjectless and deleted must be indistinguishable."""

    from app.auth import current_user

    details = set()
    for token in (_token("x", secret="wrong"), _token(user.id, expired=True), _token(None), _token("gone")):
        with pytest.raises(HTTPException) as info:
            current_user(token=token, db=db)
        details.add(info.value.detail)
    assert len(details) == 1, details


# ---------------------------------------------------------------------------
# register / login
# ---------------------------------------------------------------------------


def test_register_creates_a_user_and_a_default_workspace(db) -> None:
    from app.auth import RegisterRequest, register

    result = register(
        RegisterRequest(email="NEW@Brobond.AI", name="Petrick Martins", password="correct-horse"),
        db,
    )
    assert result.user.email == "new@brobond.ai", "emails are normalised on the way in"
    assert result.access_token
    assert jwt.decode(result.access_token, options={"verify_signature": False})["sub"] == result.user.id


def test_register_refuses_a_duplicate_email(db, user) -> None:
    from app.auth import RegisterRequest, register

    with pytest.raises(HTTPException) as info:
        register(RegisterRequest(email="DIRECTOR@brobond.ai", name="Someone Else", password="correct-horse"), db)
    assert info.value.status_code == 409


def test_register_stores_a_hash_not_the_password(db) -> None:
    from app.auth import RegisterRequest, register
    from app.models import User

    register(RegisterRequest(email="hash@brobond.ai", name="Petrick Martins", password="correct-horse"), db)
    stored = db.query(User).filter_by(email="hash@brobond.ai").one()
    assert "correct-horse" not in stored.password_hash
    assert stored.password_hash.startswith("scrypt$")


def test_login_accepts_the_right_credentials(db, user) -> None:
    from app.auth import LoginRequest, login

    result = login(LoginRequest(email="Director@brobond.ai", password="correct-horse-battery"), db)
    assert result.user.id == user.id
    assert result.access_token


def test_login_refuses_a_wrong_password(db, user) -> None:
    from app.auth import LoginRequest, login

    with pytest.raises(HTTPException) as info:
        login(LoginRequest(email="director@brobond.ai", password="not-the-password"), db)
    assert info.value.status_code == 401


def test_login_refuses_an_unknown_email(db) -> None:
    from app.auth import LoginRequest, login

    with pytest.raises(HTTPException) as info:
        login(LoginRequest(email="nobody@brobond.ai", password="whatever-123"), db)
    assert info.value.status_code == 401


def test_login_says_the_same_thing_for_both_failures(db, user) -> None:
    """Otherwise the endpoint becomes an account-enumeration oracle."""

    from app.auth import LoginRequest, login

    details = set()
    for request in (
        LoginRequest(email="nobody@brobond.ai", password="whatever-123"),
        LoginRequest(email="director@brobond.ai", password="not-the-password"),
    ):
        with pytest.raises(HTTPException) as info:
            login(request, db)
        details.add(info.value.detail)
    assert len(details) == 1, details
