"""Character Continuity Engine tables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-16

V3.2. Absolute continuity across scenes, episodes and campaigns:

* ``continuity_locks`` — one row per (workspace, persona, campaign,
  episode, lock_type). ``payload`` is a JSON document in a Text column (the
  portable convention ``persona_wardrobe.metadata`` uses); ``episode`` 0 is
  the campaign default every episode inherits unless it carries its own
  override (real episodes start at 1); re-locking the same scope replaces
  the payload and bumps ``version``.
* ``continuity_episodes`` — one row per (workspace, persona, campaign,
  episode): the frozen resolver snapshot taken when the episode was
  created. Later lock writes never reach back into it.

Idempotency: every ``create_table``/``create_index`` is skipped when the
object exists, exactly like 0001/0002/0003. ``downgrade`` is a documented
no-op: the Developer Bible (section 2) forbids dropping historical tables,
and continuity rows are product data that must never be destroyed by a
rollback.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()

    if "continuity_locks" not in existing:
        op.create_table(
            "continuity_locks",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("persona_id", sa.String(length=120), nullable=False),
            sa.Column("campaign_id", sa.String(length=120), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("lock_type", sa.String(length=32), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("fingerprint", sa.String(length=32), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "workspace_id",
                "persona_id",
                "campaign_id",
                "episode",
                "lock_type",
                name="uq_continuity_locks_scope",
            ),
        )
        op.create_index(op.f("ix_continuity_locks_workspace_id"), "continuity_locks", ["workspace_id"])
        op.create_index(op.f("ix_continuity_locks_persona_id"), "continuity_locks", ["persona_id"])
        op.create_index(op.f("ix_continuity_locks_campaign_id"), "continuity_locks", ["campaign_id"])
        op.create_index(op.f("ix_continuity_locks_lock_type"), "continuity_locks", ["lock_type"])

    if "continuity_episodes" not in existing:
        op.create_table(
            "continuity_episodes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("persona_id", sa.String(length=120), nullable=False),
            sa.Column("campaign_id", sa.String(length=120), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "workspace_id",
                "persona_id",
                "campaign_id",
                "episode",
                name="uq_continuity_episodes_scope",
            ),
        )
        op.create_index(op.f("ix_continuity_episodes_workspace_id"), "continuity_episodes", ["workspace_id"])
        op.create_index(op.f("ix_continuity_episodes_persona_id"), "continuity_episodes", ["persona_id"])
        op.create_index(op.f("ix_continuity_episodes_campaign_id"), "continuity_episodes", ["campaign_id"])


def downgrade() -> None:
    # Developer Bible, section 2 (Regra de Ouro): historical tables are never
    # dropped. Continuity rows are product data; a rollback must not destroy
    # them. The tables are inert while the application code is rolled back.
    return None
