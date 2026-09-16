"""PR002 — the Alembic migration, verified against a real database.

The schema moved from `Base.metadata.create_all` plus a hand-written
`ALTER TABLE` to a versioned migration. These tests run `alembic upgrade
head` against a throwaway SQLite database and check the three properties that
matter in production:

* a fresh database comes up with every table the application needs, including
  the two PR002 introduces (`jobs`, `audit_log`);
* the upgrade is idempotent, so the API bootstrap can retry it safely;
* a legacy database — created by the pre-PR002 bootstrap, whose
  `training_runs` lacks `workspace_id` — upgrades in place instead of forcing
  a drop.

The URL is the application's own `settings.database_url`, pointed at the temp
file: the same `env.py` the CLI and the API bootstrap use, so what is tested
is exactly what runs.
"""
from __future__ import annotations

import pathlib
import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture()
def temp_database(monkeypatch, tmp_path):
    """Point the application settings at a scratch SQLite file and return its path."""

    from app.core.config import settings

    db_file = tmp_path / "migration.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_file}")
    return db_file


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def _tables(path) -> set[str]:
    engine = create_engine(f"sqlite:///{path}", pool_pre_ping=True)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_fresh_database_gets_the_full_schema(temp_database) -> None:
    command.upgrade(_alembic_config(), "head")

    tables = _tables(temp_database)
    for expected in (
        "users", "workspaces", "projects", "assets", "training_runs",
        "knowledge_entries", "jobs", "audit_log", "alembic_version",
        # V3.1 (migration 0003): the Cinematic Knowledge Graph tables.
        "graph_nodes", "graph_edges",
    ):
        assert expected in tables, f"{expected} missing from a fresh schema"


def test_the_upgrade_is_idempotent(temp_database) -> None:
    config = _alembic_config()
    command.upgrade(config, "head")
    before = _tables(temp_database)
    # A second run must not raise and must not change the schema.
    command.upgrade(config, "head")
    assert _tables(temp_database) == before


def test_a_legacy_database_upgrades_in_place(temp_database) -> None:
    """A database the old bootstrap created, missing `training_runs.workspace_id`."""

    connection = sqlite3.connect(temp_database)
    try:
        connection.execute(
            """CREATE TABLE training_runs (
                id VARCHAR(36) PRIMARY KEY,
                persona_id VARCHAR(36) NOT NULL,
                status VARCHAR(32) NOT NULL,
                progress INTEGER NOT NULL,
                log TEXT NOT NULL,
                output_asset_id VARCHAR(36),
                created_at DATETIME NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE users (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                name VARCHAR(120) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at DATETIME NOT NULL
            )"""
        )
        connection.commit()
    finally:
        connection.close()

    # Pre-state: the column really is absent.
    engine = create_engine(f"sqlite:///{temp_database}")
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("training_runs")}
        assert "workspace_id" not in columns
    finally:
        engine.dispose()

    command.upgrade(_alembic_config(), "head")

    engine = create_engine(f"sqlite:///{temp_database}")
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("training_runs")}
        assert "workspace_id" in columns, "the legacy column was not added"
        # And the new tables appeared alongside.
        names = set(inspect(engine).get_table_names())
        assert {"jobs", "audit_log", "graph_nodes", "graph_edges"} <= names
    finally:
        engine.dispose()


def test_downgrade_removes_the_schema(temp_database) -> None:
    command.upgrade(_alembic_config(), "head")
    command.downgrade(_alembic_config(), "base")
    tables = _tables(temp_database)
    for gone in ("users", "workspaces", "projects", "assets", "training_runs", "knowledge_entries", "jobs", "audit_log"):
        assert gone not in tables, f"{gone} should have been dropped"


def test_the_migration_is_the_initial_revision() -> None:
    """There is exactly one baseline revision, and it has no parent."""

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "initial_migration", ROOT / "alembic" / "versions" / "0001_initial_schema.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision is None
    assert module.revision == "0001"
