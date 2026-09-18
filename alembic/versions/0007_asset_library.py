"""Cinematic Asset Studio — library metadata table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18

PR013 — V4.0.1. The Assets module gains its library layer:

* ``asset_metadata`` — the 1:1 companion row of an ``assets`` row holding
  everything the grid and the preview need that ``assets`` was never asked
  to carry: content type, byte size and sha256 of the stored file, probed
  resolution and duration, the derivative thumbnail key, attribution
  (project / persona / provider / seed), searchable tags and the
  before/after pairing. Rows are minted by
  ``backend/app/assets/library_service.py`` at upload time; assets written
  by other flows simply have no companion row, and the library shows them
  with ``has_metadata = False``.

The ``assets`` table itself is untouched: uploads, renders, conditioning
and exports keep writing exactly the rows they wrote before this PR.

Idempotency: ``create_table``/``create_index`` are skipped when the object
exists, exactly like 0001–0006. ``downgrade`` is a documented no-op: the
Developer Bible (section 2) forbids dropping historical tables, and
library metadata is product data that must never be destroyed by a
rollback.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    existing_tables = set(inspector.get_table_names())

    if "asset_metadata" not in existing_tables:
        op.create_table(
            "asset_metadata",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("asset_id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("thumbnail_key", sa.String(length=500), nullable=True),
            sa.Column("project", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("persona", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("provider", sa.String(length=80), nullable=False, server_default="upload"),
            sa.Column("seed", sa.Integer(), nullable=True),
            sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="upload"),
            sa.Column("before_asset_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_asset_metadata_asset_id"), "asset_metadata", ["asset_id"], unique=True)
        op.create_index(op.f("ix_asset_metadata_workspace_id"), "asset_metadata", ["workspace_id"])


def downgrade() -> None:
    """Documented no-op — library metadata is product data (Bible section 2)."""
