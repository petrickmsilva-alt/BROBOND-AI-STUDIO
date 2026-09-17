"""PR009.4.1 — Database health guard.

Covers the guard itself (online, offline, timeout), the health endpoint's
503 contract and the readiness deploy gates, with `app.core.database_guard`
at 100% statement coverage.
"""
import time

import pytest
from fastapi.testclient import TestClient

from app.core.database_guard import (
    DEFAULT_TIMEOUT_SECONDS,
    UNAVAILABLE_MESSAGE,
    DatabaseGuard,
    database_guard,
)
from app.main import app

client = TestClient(app)


# ------------------------------------------------------------------ the guard


def test_guard_passes_when_the_database_is_online():
    """The suite's SQLite database answers SELECT 1: verify() returns None."""

    assert DatabaseGuard().verify() is None
    assert DatabaseGuard().ping() is True


def test_guard_raises_postgresql_unavailable_when_the_database_is_offline():
    """A connection that cannot be established is the PR's RuntimeError."""

    offline = DatabaseGuard(
        database_url="postgresql+psycopg://nobody:wrong@127.0.0.1:1/brobond",
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    )
    with pytest.raises(RuntimeError, match=UNAVAILABLE_MESSAGE):
        offline.verify()
    assert offline.ping() is False


def test_guard_enforces_the_wall_clock_timeout(monkeypatch):
    """A probe that hangs past the deadline collapses into the same error.

    The hang is simulated at the `_select_one` layer so the test needs no
    firewalled host: the guard must abandon the worker and answer within
    its own deadline, not the hang's.
    """

    guard = DatabaseGuard(timeout_seconds=0.1)
    monkeypatch.setattr(DatabaseGuard, "_select_one", lambda self: time.sleep(5))

    started = time.monotonic()
    with pytest.raises(RuntimeError, match=UNAVAILABLE_MESSAGE):
        guard.verify()
    assert time.monotonic() - started < 2, "the guard waited for the hung probe"


def test_guard_defaults_are_the_pr_contract():
    guard = DatabaseGuard()
    assert guard.timeout_seconds == DEFAULT_TIMEOUT_SECONDS == 5.0
    assert UNAVAILABLE_MESSAGE == "PostgreSQL unavailable"


def test_guard_follows_settings_when_no_url_is_injected(monkeypatch):
    """The singleton reads `settings.database_url` at call time, not import time."""

    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://u:p@h:5432/db")
    assert database_guard.database_url == "postgresql+psycopg://u:p@h:5432/db"
    assert database_guard.provider() == "postgresql"


def test_guard_provider_names_sqlite_in_development():
    assert DatabaseGuard(database_url="sqlite:///./brobond.db").provider() == "sqlite"


# ------------------------------------------------------------- health endpoint


def test_health_reports_database_connected_when_online():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["provider"] in {"postgresql", "sqlite"}


def test_health_answers_503_never_200_when_the_database_is_down(monkeypatch):
    monkeypatch.setattr(database_guard, "ping", lambda: False)

    for path in ("/api/v1/health", "/health"):
        response = client.get(path)
        assert response.status_code == 503, f"{path} must never answer 200 with a dead database"
        body = response.json()
        assert body["status"] == "unavailable"
        assert body["database"] == "disconnected"


# ---------------------------------------------------------- readiness endpoint


def test_readiness_reports_the_three_deploy_gates_true():
    """Database up, migrations at head, local storage writable: all green."""

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["database"] is True
    assert body["migrations"] is True
    assert body["storage"] is True


def test_readiness_turns_database_false_and_503_when_the_guard_fails(monkeypatch):
    monkeypatch.setattr(database_guard, "ping", lambda: False)

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 503, "a broken deploy must not read as ready"
    assert response.json()["database"] is False


def test_readiness_turns_migrations_false_when_the_schema_is_behind(monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(main_module, "_migrations_ready", lambda: False)

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 503
    assert response.json()["migrations"] is False


def test_readiness_turns_storage_false_when_the_backend_rejects_writes(monkeypatch):
    from app import main as main_module

    monkeypatch.setattr(main_module, "_storage_ready", lambda: False)

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 503
    assert response.json()["storage"] is False


def test_migrations_check_is_false_on_an_empty_database(tmp_path, monkeypatch):
    """A database without `alembic_version` is by definition not at head."""

    from sqlalchemy import create_engine

    from app import main as main_module
    from app import db as db_module

    empty_engine = create_engine(f"sqlite:///{tmp_path/'empty.db'}")
    monkeypatch.setattr(db_module, "engine", empty_engine)

    assert main_module._migrations_ready() is False


def test_storage_check_probes_the_s3_bucket_when_storage_is_enabled(monkeypatch):
    """With `storage_enabled` the probe is `head_bucket`, not a local write."""

    from app import main as main_module
    from app.core.config import settings

    calls: list[str] = []

    class FakeClient:
        def head_bucket(self, Bucket: str) -> None:
            calls.append(Bucket)

    monkeypatch.setattr(settings, "storage_enabled", True)
    monkeypatch.setattr(main_module.storage, "client", FakeClient())
    assert main_module._storage_ready() is True
    assert calls == [settings.minio_bucket]

    class DeadClient:
        def head_bucket(self, Bucket: str) -> None:
            raise ConnectionError("bucket gone")

    monkeypatch.setattr(main_module.storage, "client", DeadClient())
    assert main_module._storage_ready() is False
