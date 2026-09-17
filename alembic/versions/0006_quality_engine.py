"""Quality AI Engine tables and columns.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17

V3.4. A render gains an honest, persistent verdict:

* ``quality_reports`` — one row per engine run over one asset: overall
  score (0–100), status band (retry / manual_review / approved /
  masterpiece), the recommendation flags, the full report document
  (criteria, issues, strengths, suggestions, facts) and the engine version
  that produced it. Append-only: re-assessing appends, it never rewrites an
  old opinion;
* four columns on ``assets`` (ETAPA 6) — ``quality_score``,
  ``quality_status``, ``quality_report``, ``quality_version`` — the latest
  verdict denormalised so the Asset Library can badge and filter without a
  join. All nullable: NULL means "never assessed", which is a different
  fact from any score.

Idempotency: every ``create_table``/``create_index``/``add_column`` is
skipped when the object exists, exactly like 0001–0005. ``downgrade`` is a
documented no-op: the Developer Bible (section 2) forbids dropping
historical tables, and quality verdicts are product data that must never be
destroyed by a rollback.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    existing_tables = set(inspector.get_table_names())

    if "quality_reports" not in existing_tables:
        op.create_table(
            "quality_reports",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("asset_id", sa.String(length=36), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("overall_score", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("retry_recommended", sa.Integer(), nullable=False),
            sa.Column("upscale_recommended", sa.Integer(), nullable=False),
            sa.Column("report_json", sa.Text(), nullable=False),
            sa.Column("engine_version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_quality_reports_workspace_id"), "quality_reports", ["workspace_id"])
        op.create_index(op.f("ix_quality_reports_asset_id"), "quality_reports", ["asset_id"])

    asset_columns = {column["name"] for column in inspector.get_columns("assets")}
    if "quality_score" not in asset_columns:
        op.add_column("assets", sa.Column("quality_score", sa.Integer(), nullable=True))
    if "quality_status" not in asset_columns:
        op.add_column("assets", sa.Column("quality_status", sa.String(length=32), nullable=True))
    if "quality_report" not in asset_columns:
        op.add_column("assets", sa.Column("quality_report", sa.Text(), nullable=True))
    if "quality_version" not in asset_columns:
        op.add_column("assets", sa.Column("quality_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Documented no-op — quality history is product data (Bible section 2)."""
