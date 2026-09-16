"""Cinematic Knowledge Graph tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

V3.1. Memory becomes relational knowledge:

* ``graph_nodes`` — one row per entity (character/brand/campaign/location/
  vehicle/wardrobe/prop). ``attributes``/``aliases`` are JSON documents in
  Text columns (the portable convention ``persona_wardrobe.metadata`` uses);
  ``slug`` is unique per workspace for stable addressing.
* ``graph_edges`` — one directed row per relation (source -> relation ->
  target). No DB-level foreign keys (same portable rule as the persona
  children): node deletion removes incident edges explicitly. The
  ``(workspace, source, target, relation)`` unique constraint makes a
  relation idempotent.

Idempotency: every ``create_table``/``create_index`` is skipped when the
object exists, exactly like 0001/0002. ``downgrade`` is a documented no-op:
the Developer Bible (section 2) forbids dropping historical tables, and
graph rows are product data that must never be destroyed by a rollback.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    if "graph_nodes" not in existing:
        op.create_table(
            "graph_nodes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("entity_type", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("slug", sa.String(length=180), nullable=False),
            sa.Column("attributes", sa.Text(), nullable=False),
            sa.Column("aliases", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "slug", name="uq_graph_nodes_workspace_slug"),
        )
        op.create_index(op.f("ix_graph_nodes_workspace_id"), "graph_nodes", ["workspace_id"])
        op.create_index(op.f("ix_graph_nodes_entity_type"), "graph_nodes", ["entity_type"])
        op.create_index(op.f("ix_graph_nodes_slug"), "graph_nodes", ["slug"])

    if "graph_edges" not in existing:
        op.create_table(
            "graph_edges",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("source_id", sa.String(length=36), nullable=False),
            sa.Column("target_id", sa.String(length=36), nullable=False),
            sa.Column("relation", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "workspace_id",
                "source_id",
                "target_id",
                "relation",
                name="uq_graph_edges_endpoint_relation",
            ),
        )
        op.create_index(op.f("ix_graph_edges_workspace_id"), "graph_edges", ["workspace_id"])
        op.create_index(op.f("ix_graph_edges_source_id"), "graph_edges", ["source_id"])
        op.create_index(op.f("ix_graph_edges_target_id"), "graph_edges", ["target_id"])


def downgrade() -> None:
    # Developer Bible, section 2 (Regra de Ouro): historical tables are never
    # dropped. Graph rows are product data; a rollback must not destroy
    # them. The tables are inert while the application code is rolled back.
    return None
