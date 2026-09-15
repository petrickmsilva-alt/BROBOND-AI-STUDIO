"""PR002 — the security matrix, measured.

The audit (SPRINT1_AUDIT_REPORT.md, P0-2) found 48 of 58 routes open, persona
PII readable without a token, downloads with no identity and no tenant check,
and WebSockets that accepted anyone. This file pins the closed state:

* every protected route answers 401 to an anonymous caller;
* a token never lets one tenant reach another tenant's jobs, assets or runs;
* the credential endpoints rate-limit, and the limiter is configurable;
* the JWT secret validator refuses a key shorter than RFC 7518's 32 bytes;
* both WebSockets authenticate through the `token` query parameter.

One behaviour is deliberately documented here as a *consequence*, not an
oversight: a job created anonymously (the generation routes still accept
anonymous callers by design) carries no workspace, so no token can read it
back. The API still answers the creation; tracking it is what login is for.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings, settings
from app.db import SessionLocal
from app.main import app

client = TestClient(app)


def _register(email: str | None = None) -> str:
    payload = {
        "email": email or f"sec-{uuid.uuid4()}@example.com",
        "name": "Security Test",
        "password": "correct-horse-battery-staple",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_job(token: str) -> str:
    response = client.post(
        "/api/v1/generations/images",
        headers=_headers(token),
        json={"prompt": "a security test render", "model": "flux-dev", "aspect_ratio": "1:1"},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


@pytest.fixture(autouse=True)
def clean_rate_limit_state():
    """The limiter's window is module state; tests must not inherit each other's attempts."""

    from app import auth

    auth._auth_attempts.clear()
    yield
    auth._auth_attempts.clear()


# ---------------------------------------------------------------------------
# 401 without a token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/queue"),
        ("get", "/api/v1/jobs/00000000-0000-0000-0000-000000000000"),
        ("post", "/api/v1/jobs/00000000-0000-0000-0000-000000000000/cancel"),
        ("get", "/api/v1/assets/download/some/key.png"),
        ("get", "/api/v1/knowledge"),
        ("post", "/api/v1/personas"),
        ("post", "/api/v1/personas/00000000-0000-0000-0000-000000000000/train"),
        (
            "get",
            "/api/v1/personas/00000000-0000-0000-0000-000000000000/training/00000000-0000-0000-0000-000000000000",
        ),
        ("get", "/api/v1/core/personas"),
        ("get", "/api/v1/core/personas/CHAR_PETRICK"),
        ("post", "/api/v1/core/personas/CHAR_PETRICK/revise"),
        ("post", "/api/v1/core/personas/CHAR_PETRICK/approve"),
    ],
)
def test_protected_routes_reject_anonymous_callers(method: str, path: str) -> None:
    if method == "post":
        response = client.post(path, json={"actor": "x", "reason": "y", "reference_asset_ids": [str(uuid.uuid4())], "name": "P", "age": 1})
    else:
        response = client.get(path)
    assert response.status_code == 401, f"{method.upper()} {path} answered {response.status_code} without identity"


def test_protected_routes_reject_a_garbage_token() -> None:
    assert client.get("/api/v1/queue", headers=_headers("not-a-real-token")).status_code == 401
    assert client.get("/api/v1/knowledge", headers=_headers("not-a-real-token")).status_code == 401


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_a_token_cannot_read_another_tenants_job() -> None:
    owner_token = _register()
    foreign_token = _register()
    job_id = _create_job(owner_token)

    assert client.get(f"/api/v1/jobs/{job_id}", headers=_headers(owner_token)).status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}", headers=_headers(foreign_token)).status_code == 404, (
        "a foreign job must look absent, not forbidden"
    )
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=_headers(foreign_token)).status_code == 404


def test_the_queue_lists_only_the_callers_own_jobs() -> None:
    owner_token = _register()
    foreign_token = _register()
    own = _create_job(owner_token)
    _create_job(foreign_token)

    own_ids = {job["id"] for job in client.get("/api/v1/queue", headers=_headers(owner_token)).json()}
    foreign_ids = {job["id"] for job in client.get("/api/v1/queue", headers=_headers(foreign_token)).json()}
    assert own in own_ids
    assert own not in foreign_ids
    assert foreign_ids.isdisjoint(own_ids)


def test_a_token_cannot_download_another_tenants_asset(monkeypatch, tmp_path) -> None:
    from app.storage import storage

    monkeypatch.setattr(storage, "local_root", tmp_path)
    owner_token = _register()
    foreign_token = _register()

    upload = client.post(
        "/api/v1/assets/upload",
        headers=_headers(owner_token),
        files={"file": ("portrait.png", b"secret-bytes", "image/png")},
    )
    assert upload.status_code == 201
    key = upload.json()["object_key"]

    assert client.get(f"/api/v1/assets/download/{key}", headers=_headers(owner_token)).status_code == 200
    assert client.get(f"/api/v1/assets/download/{key}", headers=_headers(foreign_token)).status_code == 404


def test_an_anonymous_job_cannot_be_read_back_with_any_token() -> None:
    """The documented consequence of optional_user on /generations/* (see module docstring)."""

    anonymous = client.post("/api/v1/generations/images", json={"prompt": "anonymous render"}).json()
    assert anonymous["status"] == "queued"
    token = _register()
    assert client.get(f"/api/v1/jobs/{anonymous['id']}", headers=_headers(token)).status_code == 404
    assert f"{anonymous['id']}" not in [job["id"] for job in client.get("/api/v1/queue", headers=_headers(token)).json()]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_the_auth_endpoints_rate_limit_and_report_retry_after(monkeypatch) -> None:
    email = f"brute-{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "name": "Brute", "password": "correct-horse-battery-staple"})

    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 3)

    responses = [
        client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password-1"})
        for _ in range(4)
    ]
    assert [r.status_code for r in responses] == [401, 401, 401, 429]
    assert responses[-1].headers.get("Retry-After") == "60"


def test_the_rate_limit_is_configurable_per_minute(monkeypatch) -> None:
    """Bible §16: "Rate Limit configurável". A higher budget raises the budget."""

    email = f"budget-{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "name": "Budget", "password": "correct-horse-battery-staple"})

    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 5)
    statuses = [client.post("/api/v1/auth/login", json={"email": email, "password": "x"}).status_code for _ in range(6)]
    assert statuses == [401] * 5 + [429]


def test_a_zero_budget_disables_the_limiter(monkeypatch) -> None:
    email = f"zero-{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "name": "Zero", "password": "correct-horse-battery-staple"})

    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 0)
    assert all(
        client.post("/api/v1/auth/login", json={"email": email, "password": "x"}).status_code == 401
        for _ in range(10)
    )


# ---------------------------------------------------------------------------
# JWT secret strength
# ---------------------------------------------------------------------------


def test_the_jwt_secret_validator_refuses_a_short_key() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Settings(_env_file=None, jwt_secret="too-short")


def test_the_default_secret_meets_the_minimum() -> None:
    assert len(settings.jwt_secret.encode("utf-8")) >= 32


def test_a_short_configured_secret_refuses_to_boot() -> None:
    import importlib

    import app.core.config as config_module

    with pytest.raises(ValueError, match="BROBOND_JWT_SECRET"):
        config_module.Settings(_env_file=None, jwt_secret="change-me-in-production")


# ---------------------------------------------------------------------------
# WebSocket authentication
# ---------------------------------------------------------------------------


def test_the_queue_socket_refuses_an_anonymous_client() -> None:
    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(f"/api/v1/queue/events/{uuid.uuid4()}"):
            pass
    assert raised.value.code == 1008


def test_the_queue_socket_refuses_a_token_that_does_not_own_the_job() -> None:
    owner_token = _register()
    foreign_token = _register()
    job_id = _create_job(owner_token)

    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(f"/api/v1/queue/events/{job_id}?token={foreign_token}"):
            pass
    assert raised.value.code == 1008


def test_the_training_socket_refuses_an_anonymous_client() -> None:
    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(f"/api/v1/personas/{uuid.uuid4()}/training/events/{uuid.uuid4()}"):
            pass
    assert raised.value.code == 1008


def test_the_training_socket_refuses_a_token_for_a_foreign_run() -> None:
    token = _register()
    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(f"/api/v1/personas/{uuid.uuid4()}/training/events/{uuid.uuid4()}?token={token}"):
            pass
    assert raised.value.code == 1008


# ---------------------------------------------------------------------------
# The audit trail exists for the actions above
# ---------------------------------------------------------------------------


def test_failed_logins_are_audited_anonymously() -> None:
    from sqlalchemy import select

    from app.models import AuditLog

    email = f"audited-{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "name": "Audited", "password": "correct-horse-battery-staple"})
    client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})

    with SessionLocal() as db:
        entry = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "auth.login.failed")
            .order_by(AuditLog.created_at.desc())
        )
    assert entry is not None, "a failed login left no audit row"
    assert entry.actor_id is None, "a failed login has no authenticated actor to attribute it to"
