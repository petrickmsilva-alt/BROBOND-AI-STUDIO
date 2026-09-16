"""Campaign Builder tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-16

V3.3. One briefing becomes a complete campaign:

* ``campaigns`` — the campaign root (product, audience, platform, objective,
  status and the CTA seed that re-arms the deck on duplication);
* ``campaign_briefs`` — the frozen Brief Interpreter output, one per
  campaign, including the fields it had to default (``missing``);
* ``campaign_episodes`` — one row per timeline day (Dia 1..Dia 5), unique
  per (workspace, campaign, day);
* ``campaign_assets`` — one row per deliverable (Reel 9:16, Story, Shorts,
  Banner, Thumbnail, Feed 1:1, YouTube Cover), unique per (workspace,
  campaign, kind): each format is scheduled exactly once;
* ``campaign_exports`` — one row per Export Center ZIP (object key, file
  count, checksum, manifest).

Idempotency: every ``create_table``/``create_index`` is skipped when the
object exists, exactly like 0001/0002/0003/0004. ``downgrade`` is a
documented no-op: the Developer Bible (section 2) forbids dropping
historical tables, and campaigns are product data that must never be
destroyed by a rollback.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    if "campaigns" not in existing:
        op.create_table(
            "campaigns",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("product", sa.String(length=160), nullable=False),
            sa.Column("product_type", sa.String(length=80), nullable=False),
            sa.Column("audience", sa.String(length=160), nullable=False),
            sa.Column("platform", sa.String(length=80), nullable=False),
            sa.Column("objective", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("seed", sa.Integer(), nullable=False),
            sa.Column("primary_cta", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_campaigns_workspace_id"), "campaigns", ["workspace_id"])

    if "campaign_briefs" not in existing:
        op.create_table(
            "campaign_briefs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("campaign_id", sa.String(length=36), nullable=False),
            sa.Column("raw_text", sa.Text(), nullable=False),
            sa.Column("product", sa.String(length=160), nullable=False),
            sa.Column("product_type", sa.String(length=80), nullable=False),
            sa.Column("audience", sa.String(length=160), nullable=False),
            sa.Column("platform", sa.String(length=80), nullable=False),
            sa.Column("objective", sa.String(length=40), nullable=False),
            sa.Column("duration_seconds", sa.Integer(), nullable=False),
            sa.Column("cta", sa.String(length=200), nullable=False),
            sa.Column("missing_json", sa.Text(), nullable=False),
            sa.Column("matched_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "campaign_id", name="uq_campaign_briefs_campaign"),
        )
        op.create_index(op.f("ix_campaign_briefs_workspace_id"), "campaign_briefs", ["workspace_id"])
        op.create_index(op.f("ix_campaign_briefs_campaign_id"), "campaign_briefs", ["campaign_id"])

    if "campaign_episodes" not in existing:
        op.create_table(
            "campaign_episodes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("campaign_id", sa.String(length=36), nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("focus", sa.String(length=120), nullable=False),
            sa.Column("cta", sa.String(length=200), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "campaign_id", "day", name="uq_campaign_episodes_day"),
        )
        op.create_index(op.f("ix_campaign_episodes_workspace_id"), "campaign_episodes", ["workspace_id"])
        op.create_index(op.f("ix_campaign_episodes_campaign_id"), "campaign_episodes", ["campaign_id"])

    if "campaign_assets" not in existing:
        op.create_table(
            "campaign_assets",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("campaign_id", sa.String(length=36), nullable=False),
            sa.Column("day", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("label", sa.String(length=120), nullable=False),
            sa.Column("medium", sa.String(length=16), nullable=False),
            sa.Column("aspect_ratio", sa.String(length=16), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("cta", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("output_key", sa.String(length=500), nullable=True),
            sa.Column("thumbnail_key", sa.String(length=500), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("workspace_id", "campaign_id", "kind", name="uq_campaign_assets_kind"),
        )
        op.create_index(op.f("ix_campaign_assets_workspace_id"), "campaign_assets", ["workspace_id"])
        op.create_index(op.f("ix_campaign_assets_campaign_id"), "campaign_assets", ["campaign_id"])
        op.create_index(op.f("ix_campaign_assets_kind"), "campaign_assets", ["kind"])

    if "campaign_exports" not in existing:
        op.create_table(
            "campaign_exports",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("campaign_id", sa.String(length=36), nullable=False),
            sa.Column("object_key", sa.String(length=500), nullable=False),
            sa.Column("file_count", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("manifest_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_campaign_exports_workspace_id"), "campaign_exports", ["workspace_id"])
        op.create_index(op.f("ix_campaign_exports_campaign_id"), "campaign_exports", ["campaign_id"])


def downgrade() -> None:
    # Developer Bible, section 2 (Regra de Ouro): historical tables are never
    # dropped. Campaign rows are product data; a rollback must not destroy
    # them. The tables are inert while the application code is rolled back.
    return None
