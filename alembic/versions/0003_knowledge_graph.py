"""Cinematic Knowledge Graph tables (V3.1).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

V3.1 turns persona memory into relational knowledge:

* ``knowledge_graph_nodes``          — Character, Brand, Campaign, Location,
  Vehicle, Wardrobe, Prop; every type relatable to every other
* ``knowledge_graph_relationships``  — directed, typed edges ("Petrick ->
  dirige -> RAM"); the reverse direction is derived, never stored twice

Canonical, brand-level rows live in ``workspace_id = 'global'`` (visible to
every workspace, read-only); workspace rows specialize or extend the catalog.

Idempotency: every ``create_table``/``create_index`` is skipped when the
object exists, exactly like 0001/0002 — a fresh database and an upgraded one
end at the same schema. ``downgrade`` is a documented no-op: the Developer
Bible (section 2) forbids dropping historical tables, and graph data is
product data that must never be destroyed by a rollback.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table: str) -> set[str]:
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    existing = _existing_tables()

    if "knowledge_graph_nodes" not in existing:
        op.create_table(
            "knowledge_graph_nodes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("entity_type", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("attributes_json", sa.Text(), nullable=False),
            sa.Column("external_ref", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "entity_type", "name", name="uq_graph_nodes_ws_type_name"),
        )
        op.create_index(op.f("ix_knowledge_graph_nodes_workspace_id"), "knowledge_graph_nodes", ["workspace_id"])
        op.create_index(op.f("ix_knowledge_graph_nodes_entity_type"), "knowledge_graph_nodes", ["entity_type"])
        op.create_index(op.f("ix_knowledge_graph_nodes_name"), "knowledge_graph_nodes", ["name"])
        op.create_index(op.f("ix_knowledge_graph_nodes_external_ref"), "knowledge_graph_nodes", ["external_ref"])

    if "knowledge_graph_relationships" not in existing:
        op.create_table(
            "knowledge_graph_relationships",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("source_node_id", sa.String(length=36), nullable=False),
            sa.Column("target_node_id", sa.String(length=36), nullable=False),
            sa.Column("relation_type", sa.String(length=60), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "source_node_id", "relation_type", "target_node_id", name="uq_graph_rel_ws_source_type_target"),
        )
        op.create_index(op.f("ix_knowledge_graph_relationships_workspace_id"), "knowledge_graph_relationships", ["workspace_id"])
        op.create_index(op.f("ix_knowledge_graph_relationships_source_node_id"), "knowledge_graph_relationships", ["source_node_id"])
        op.create_index(op.f("ix_knowledge_graph_relationships_target_node_id"), "knowledge_graph_relationships", ["target_node_id"])
        op.create_index(op.f("ix_knowledge_graph_relationships_relation_type"), "knowledge_graph_relationships", ["relation_type"])


def downgrade() -> None:
    # Documented no-op, same rule as 0001/0002: the Developer Bible forbids
    # dropping historical tables, and knowledge graph rows are product data.
    return None
