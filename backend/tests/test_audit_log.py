"""PR002 — the audit trail for critical actions (Bible §16).

A security review must be able to answer "who did what, from where, when".
`app.audit.audit()` writes one append-only row per critical action plus a
structured line on the `brobond.audit` logger. These tests pin the actions
that carry an audit row and the facts the row must carry.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog

client = TestClient(app)


def _register() -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"audit-{uuid.uuid4()}@example.com",
            "name": "Audit Test",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _latest(action: str) -> AuditLog | None:
    with SessionLocal() as db:
        return db.scalar(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at.desc()))


def test_registration_is_audited() -> None:
    token = _register()
    entry = _latest("auth.register")
    assert entry is not None
    assert entry.actor_id, "the actor is the account that was just created"
    assert entry.resource_type == "user"
    assert entry.detail and "email" in json.loads(entry.detail)


def test_successful_login_is_audited() -> None:
    email = f"login-{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "name": "Login", "password": "correct-horse-battery-staple"})
    client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery-staple"})

    entry = _latest("auth.login")
    assert entry is not None
    assert entry.actor_id is not None


def test_failed_login_is_audited_without_an_actor() -> None:
    email = f"failed-{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "name": "Failed", "password": "correct-horse-battery-staple"})
    client.post("/api/v1/auth/login", json={"email": email, "password": "definitely-wrong"})

    entry = _latest("auth.login.failed")
    assert entry is not None
    assert entry.actor_id is None, "there is no authenticated identity to attribute a failed login to"


def test_job_creation_is_audited_with_the_tenant() -> None:
    token = _register()
    job_id = client.post(
        "/api/v1/generations/images",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "an audited job"},
    ).json()["id"]

    entry = _latest("job.created")
    assert entry is not None
    assert entry.resource_type == "job"
    assert entry.resource_id == job_id
    assert entry.workspace_id, "the row says whose job it is"


def test_job_cancellation_is_audited() -> None:
    token = _register()
    job_id = client.post(
        "/api/v1/generations/images",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "cancel and audit"},
    ).json()["id"]
    client.post(f"/api/v1/jobs/{job_id}/cancel", headers={"Authorization": f"Bearer {token}"})

    entry = _latest("job.cancelled")
    assert entry is not None
    assert entry.resource_id == job_id


def test_an_asset_download_is_audited(monkeypatch, tmp_path) -> None:
    from app.storage import storage

    monkeypatch.setattr(storage, "local_root", tmp_path)
    token = _register()
    upload = client.post(
        "/api/v1/assets/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("audited.png", b"pixels", "image/png")},
    )
    assert upload.status_code == 201
    key = upload.json()["object_key"]
    assert client.get(f"/api/v1/assets/download/{key}", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    entry = _latest("asset.downloaded")
    assert entry is not None
    assert entry.resource_type == "asset"
    assert entry.resource_id == key


def test_a_persona_identity_revision_is_audited_with_the_claimed_actor() -> None:
    token = _register()
    response = client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise",
        headers={"Authorization": f"Bearer {token}"},
        json={"actor": "test-actor", "reason": "audit coverage", "lora_path": "weights/audit.safetensors"},
    )
    assert response.status_code == 200, response.text

    entry = _latest("persona.identity.revised")
    assert entry is not None
    detail = json.loads(entry.detail)
    assert detail["actor"] == "test-actor"
    assert entry.resource_id == "CHAR_PETRICK"


def test_the_audit_logger_emits_a_structured_line(caplog) -> None:
    token = _register()
    with caplog.at_level("INFO", logger="brobond.audit"):
        client.post(
            "/api/v1/generations/images",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "structured line"},
        )
    lines = [record.getMessage() for record in caplog.records if "audit" in record.getMessage()]
    assert lines, "the structured log line is the trail for deployments without a queryable database"
    payload = json.loads(lines[-1])
    assert payload["audit"] is True
    assert payload["action"] == "job.created"


def test_audit_rows_are_append_only_for_the_application() -> None:
    """Structural guard: nothing in the application updates or deletes AuditLog rows."""

    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "backend" / "app"
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "audit":
                        offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"audit rows must never be reassigned: {offenders}"
