"""Initial schema: existing tables, jobs and audit_log.

Revision ID: 0001
Revises:
Create Date: 2026-09-15

PR002. This migration is the baseline. It creates the seven tables the
application was already managing with `Base.metadata.create_all` plus the two
tables PR002 introduces (`jobs`, `audit_log`).

It is written to be idempotent against databases that the pre-PR0002
bootstrap already created: each `create_table` is skipped when the table
exists, and `training_runs.workspace_id` is added only to legacy schemas that
received the old manual `ALTER TABLE`. A fresh database and a legacy database
end at the same schema — which is what lets `create_all` be retired in favour
of `alembic upgrade head` without forcing anyone to drop their dev database.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    if "workspaces" not in existing:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        )

    if "projects" not in existing:
        op.create_table(
            "projects",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        )
        op.create_index(op.f("ix_projects_workspace_id"), "projects", ["workspace_id"])

    if "assets" not in existing:
        op.create_table(
            "assets",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("object_key", sa.String(length=500), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        )
        op.create_index(op.f("ix_assets_workspace_id"), "assets", ["workspace_id"])

    if "training_runs" not in existing:
        op.create_table(
            "training_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("persona_id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("progress", sa.Integer(), nullable=False),
            sa.Column("log", sa.Text(), nullable=False),
            sa.Column("output_asset_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_training_runs_persona_id"), "training_runs", ["persona_id"])
        op.create_index(op.f("ix_training_runs_workspace_id"), "training_runs", ["workspace_id"])
    else:
        # Legacy schemas created by the pre-PR002 bootstrap got the column via
        # a manual ALTER TABLE; fresh schemas already have it.
        columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("training_runs")}
        if "workspace_id" not in columns:
            op.add_column("training_runs", sa.Column("workspace_id", sa.String(length=36), nullable=True))
            op.create_index(op.f("ix_training_runs_workspace_id"), "training_runs", ["workspace_id"])

    if "knowledge_entries" not in existing:
        op.create_table(
            "knowledge_entries",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("category", sa.String(length=40), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("title", sa.String(length=180), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=120), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_knowledge_entries_category"), "knowledge_entries", ["category"])
        op.create_index(op.f("ix_knowledge_entries_code"), "knowledge_entries", ["code"], unique=True)

    # PR002: jobs leave the process-local dict and become rows.
    if "jobs" not in existing:
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=True),
            sa.Column("type", sa.String(length=16), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("parameters", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("output_url", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_jobs_workspace_id"), "jobs", ["workspace_id"])
        op.create_index(op.f("ix_jobs_status"), "jobs", ["status"])

    # PR002: the audit trail for critical actions (Bible §16).
    if "audit_log" not in existing:
        op.create_table(
            "audit_log",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("actor_id", sa.String(length=36), nullable=True),
            sa.Column("action", sa.String(length=40), nullable=False),
            sa.Column("resource_type", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("resource_id", sa.String(length=64), nullable=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"])
        op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"])


def downgrade() -> None:
    for table in ("audit_log", "jobs", "knowledge_entries", "training_runs", "assets", "projects", "workspaces", "users"):
        op.drop_table(table)
