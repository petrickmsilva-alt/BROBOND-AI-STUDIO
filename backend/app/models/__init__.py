"""Core persistence models. Media binaries stay in MinIO; DB stores metadata.

PR004-prep (Repository Pattern directive): the package form lets each model
live in its own module. `JobRow` moved to `models/job.py` — the job table is
owned by the job persistence layer (`repositories/*_job_repository.py`).
Every name is re-exported here, so `from app.models import X` is unchanged
for all existing call sites.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

from .job import JobRow  # noqa: F401  (re-export, owned by models/job.py)
  # noqa: F401  (re-export, owned by models/job.py)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    owner: Mapped[User] = relationship(back_populates="workspaces")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32))
    object_key: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrainingRun(Base):
    __tablename__ = "training_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    persona_id: Mapped[str] = mapped_column(String(36), index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(default=0)
    log: Mapped[str] = mapped_column(Text, default="Training queued")
    output_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)




class AuditLog(Base):
    """PR002: the audit trail for critical actions (Bible §16).

    Append-only by convention: nothing in the application updates or deletes
    these rows. `actor_id` is the acting user (or NULL for anonymous/failed
    attempts), `detail` carries a JSON document when an action has more to say
    than its name (e.g. which persona was revised).
    """

    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    resource_type: Mapped[str] = mapped_column(String(40), default="")
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    category: Mapped[str] = mapped_column(String(40), index=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(120), default="core")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Persona(Base):
    """PR003: a persisted persona profile (the product view of a persona).

    The Core's `PersonaMemory` (identity for prompts) is DERIVED from this row
    at read time (`PersonaRepository.to_memory`); the row is the source of
    truth and lives in PostgreSQL, never in process memory. `slug` is unique
    per workspace (a persona may be addressed by name within it). Child rows
    (images, wardrobe, revisions) are plain indexed `persona_id` references —
    the repository removes them explicitly, matching this repo's
    SQLite/Postgres-portable convention (no DB-level foreign keys).
    """

    __tablename__ = "personas"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_personas_workspace_slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), index=True)
    age: Mapped[int] = mapped_column(default=0)
    height: Mapped[float] = mapped_column(default=0.0)
    body_type: Mapped[str] = mapped_column(String(80), default="")
    skin_tone: Mapped[str] = mapped_column(String(80), default="")
    hair: Mapped[str] = mapped_column(String(120), default="")
    beard: Mapped[str] = mapped_column(String(120), default="")
    eyes: Mapped[str] = mapped_column(String(80), default="")
    voice: Mapped[str] = mapped_column(String(120), default="")
    default_style: Mapped[str] = mapped_column(String(160), default="")
    lora_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PersonaImage(Base):
    """PR003: a persona's reference to a stored asset.

    The persona only REFERENCES existing assets (upload stays in the Asset
    flow). `asset_id` is intentionally not a DB foreign key: the legacy
    training flow (ETAPA 16 contract) creates personas whose reference ids
    are filled in before the assets exist; the dedicated `/images` endpoint
    validates existence at the API level.
    """

    __tablename__ = "persona_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    persona_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_id: Mapped[str] = mapped_column(String(36))
    image_type: Mapped[str] = mapped_column(String(32), default="reference")
    order_index: Mapped[int] = mapped_column(default=0)


class PersonaWardrobe(Base):
    """PR003: one wardrobe entry. `metadata` is a JSON document (Text, the
    same SQLite/Postgres-portable convention `audit_log.detail` uses)."""

    __tablename__ = "persona_wardrobe"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    persona_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80), default="")
    metadata_json: Mapped[str] = mapped_column("metadata", Text, default="{}")


class PersonaIdentityRevision(Base):
    """PR003: an append-only history row for every identity change.

    Created on creation (revision 1) and on every PATCH that touches the
    identity fields; `notes` is a JSON document describing what changed.
    Never updated, never deleted — the persona's continuity story.
    """

    __tablename__ = "persona_identity_revision"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    persona_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
