"""PR002 — jobs survive the process boundary.

The audit's P0-2b: jobs lived in a process-local dict, so a Celery worker in
another process could never find what the API created, and a deploy dropped
the whole queue. The fix is a `jobs` table plus a repository (`JobStore`) that
both sides go through.

These tests simulate the second process the way it actually happens: a brand
new database session (the "other process" opens its own connection), and the
worker entry point `process_generation` called with just a job id — which is
exactly the contract a Celery task receives.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.events import hub
from app.main import app
from app.models import JobRow
from app.schemas import JobStatus

client = TestClient(app)


def _register() -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"persist-{uuid.uuid4()}@example.com",
            "name": "Persistence Test",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _row(job_id: str) -> JobRow | None:
    """A fresh session — the other process's view of the database."""

    with SessionLocal() as db:
        return db.get(JobRow, job_id)


def test_a_created_job_exists_for_another_process() -> None:
    token = _register()
    response = client.post(
        "/api/v1/generations/images",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "a job that must survive", "model": "flux-dev", "aspect_ratio": "9:16"},
    )
    assert response.status_code == 202
    body = response.json()

    row = _row(body["id"])
    assert row is not None, "the API created the job, but no other process can see it"
    assert row.status == "queued"
    assert row.type == "image"
    # The parameters cross the boundary as a JSON document the spec adapter reads.
    assert row.parameters is not None and "aspect_ratio" in row.parameters
    assert row.workspace_id, "a tenant's job carries its tenant"


def test_the_worker_runs_a_job_the_api_created(monkeypatch) -> None:
    """The Celery contract: one id in, state and events out, no shared memory."""

    from app.core.config import settings
    from app.queue import process_generation

    monkeypatch.setattr(settings, "inference_enabled", False)
    monkeypatch.setattr(settings, "storage_enabled", False)
    token = _register()
    job_id = client.post(
        "/api/v1/generations/images",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "orchestration run"},
    ).json()["id"]

    hub.events.clear()
    try:
        result = process_generation(job_id)
        assert result["status"] == "complete"

        row = _row(job_id)
        assert row.status == "complete", "the terminal state must be in the row, not in a dict"
        assert row.progress == 100
    finally:
        hub.events.clear()


def test_a_cancel_is_persisted_and_announced(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "inference_enabled", False)
    monkeypatch.setattr(settings, "storage_enabled", False)
    token = _register()
    job_id = client.post(
        "/api/v1/generations/images",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "cancel me"},
    ).json()["id"]

    hub.events.clear()
    try:
        response = client.post(f"/api/v1/jobs/{job_id}/cancel", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

        row = _row(job_id)
        assert row.status == "cancelled", "a cancel must reach the row, or a worker revives the job"
        events = hub.history(job_id)
        assert events and events[-1]["event"] == "cancelled", "the cancel must be announced to watchers"
        assert events[-1]["status"] == "cancelled"
    finally:
        hub.events.clear()


def test_the_queue_list_is_scoped_to_the_tenant() -> None:
    owner_token = _register()
    foreign_token = _register()
    owner_id = client.post(
        "/api/v1/generations/images",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"prompt": "mine"},
    ).json()["id"]
    client.post(
        "/api/v1/generations/images",
        headers={"Authorization": f"Bearer {foreign_token}"},
        json={"prompt": "theirs"},
    )

    seen = {job["id"] for job in client.get("/api/v1/queue", headers={"Authorization": f"Bearer {owner_token}"}).json()}
    assert owner_id in seen
    assert len(seen) == 1, "the queue is a tenant view, not the whole table"


def test_a_worker_that_starts_after_a_restart_finds_the_job(monkeypatch) -> None:
    """`process_generation` on a job created before this 'boot' (new session only)."""

    from app.core.config import settings
    from app.queue import process_generation

    monkeypatch.setattr(settings, "inference_enabled", False)
    monkeypatch.setattr(settings, "storage_enabled", False)
    token = _register()
    job_id = client.post(
        "/api/v1/generations/images",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "survive the restart"},
    ).json()["id"]

    # Simulate the boot boundary: nothing in this module holds the job in
    # memory — only the row does.
    result = process_generation(job_id)
    assert result["status"] == "complete"
