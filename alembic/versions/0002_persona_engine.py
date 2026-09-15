"""Persona Memory Engine tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15

PR003. Personas leave the in-memory `PersonaLedger` (which only ever knew the
seed characters) and become rows in PostgreSQL:

* ``personas``                    — the profile (identity + wardrobe + LoRA ref)
* ``persona_images``              — reference to existing stored assets
* ``persona_wardrobe``            — wardrobe entries (metadata is a JSON doc)
* ``persona_identity_revision``   — append-only history of identity changes

The spec also lists ``knowledge_entries``: it already exists since the 0001
baseline (idempotently guarded there), so this migration only touches the
four persona tables.

Idempotency: every ``create_table``/``create_index`` is skipped when the
object exists, exactly like 0001 — a fresh database and an upgraded one end
at the same schema. ``downgrade`` is a documented no-op: the Developer
Bible (section 2) forbids dropping historical tables, and persona data is
product data that must never be destroyed by a rollback.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table: str) -> set[str]:
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    existing = _existing_tables()

    if "personas" not in existing:
        op.create_table(
            "personas",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("slug", sa.String(length=140), nullable=False),
            sa.Column("age", sa.Integer(), nullable=False),
            sa.Column("height", sa.Float(), nullable=False),
            sa.Column("body_type", sa.String(length=80), nullable=False),
            sa.Column("skin_tone", sa.String(length=80), nullable=False),
            sa.Column("hair", sa.String(length=120), nullable=False),
            sa.Column("beard", sa.String(length=120), nullable=False),
            sa.Column("eyes", sa.String(length=80), nullable=False),
            sa.Column("voice", sa.String(length=120), nullable=False),
            sa.Column("default_style", sa.String(length=160), nullable=False),
            sa.Column("lora_id", sa.String(length=36), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "slug", name="uq_personas_workspace_slug"),
        )
        op.create_index(op.f("ix_personas_workspace_id"), "personas", ["workspace_id"])
        op.create_index(op.f("ix_personas_slug"), "personas", ["slug"])
        op.create_index(op.f("ix_personas_lora_id"), "personas", ["lora_id"])

    if "persona_images" not in existing:
        op.create_table(
            "persona_images",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("persona_id", sa.String(length=36), nullable=False),
            sa.Column("asset_id", sa.String(length=36), nullable=False),
            sa.Column("image_type", sa.String(length=32), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False),
        )
        op.create_index(op.f("ix_persona_images_persona_id"), "persona_images", ["persona_id"])

    if "persona_wardrobe" not in existing:
        op.create_table(
            "persona_wardrobe",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("persona_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=False),
            sa.Column("metadata", sa.Text(), nullable=False),
        )
        op.create_index(op.f("ix_persona_wardrobe_persona_id"), "persona_wardrobe", ["persona_id"])

    if "persona_identity_revision" not in existing:
        op.create_table(
            "persona_identity_revision",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("persona_id", sa.String(length=36), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("created_by", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_persona_identity_revision_persona_id"), "persona_identity_revision", ["persona_id"])


def downgrade() -> None:
    # Developer Bible, section 2 (Regra de Ouro): historical tables are never
    # dropped. Persona rows are product data; a rollback must not destroy
    # them. The tables are inert while the application code is rolled back.
    return None
