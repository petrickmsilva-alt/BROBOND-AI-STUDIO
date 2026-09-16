"""V3.2 — Character Continuity Engine: persistence models.

Two tables hold the whole continuity state, so every lock type persists
through one code path with no per-type plumbing:

* ``continuity_locks`` — one row per (workspace, persona, campaign,
  episode, lock_type). ``payload`` is a JSON document in a ``Text`` column,
  the same SQLite/Postgres-portable convention ``persona_wardrobe.metadata``
  uses (PR003). Episode ``0`` is the campaign default every episode
  inherits unless it carries its own override; real episodes start at 1.
* ``continuity_episodes`` — one row per (workspace, persona, campaign,
  episode): the frozen snapshot the resolver produced when the episode was
  created. Later lock writes never reach back into it.

Conventions inherited from the codebase: ``String(36)`` uuid primary keys,
``workspace_id`` as an indexed plain reference (no DB-level foreign keys),
naive-UTC timestamps.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .identity_lock import ContinuityValidationError


#: The five V3.2 lock types (``BROBOND STUDIO V3 — MASTER ARCHITECTURE``,
#: §ROADMAP V3.2: Face/Outfit/Voice/Location/Vehicle locks). Lowercase
#: canonical form; user input is normalised onto it.
LOCK_TYPES: tuple[str, ...] = (
    "identity",
    "wardrobe",
    "location",
    "vehicle",
    "voice",
)

#: Campaign id used when the caller passes none or a blank.
DEFAULT_CAMPAIGN: str = "default"

#: Episode scope stored for a campaign default (real episodes start at 1).
DEFAULT_EPISODE: int = 0


def normalize_lock_type(value: str) -> str:
    """Return the canonical lock type for user input, or raise 422-style."""

    token = value.strip().casefold() if isinstance(value, str) else ""
    if token not in LOCK_TYPES:
        raise ContinuityValidationError(
            f"unknown lock type: {value!r} (expected one of: {', '.join(LOCK_TYPES)})"
        )
    return token


def dumps_payload(payload: dict) -> str:
    """Serialise a lock payload or episode snapshot, rejecting non-JSON loudly."""

    if not isinstance(payload, dict):
        raise ContinuityValidationError("payload must be an object")
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise ContinuityValidationError(f"payload is not JSON-serialisable: {error}") from error


def loads_payload(raw: str | None) -> dict:
    """Parse a stored payload, defensively (a corrupt row reads as empty)."""

    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the repository convention."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


class ContinuityLock(Base):
    """One frozen lock, owned by exactly one workspace."""

    __tablename__ = "continuity_locks"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "persona_id",
            "campaign_id",
            "episode",
            "lock_type",
            name="uq_continuity_locks_scope",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    persona_id: Mapped[str] = mapped_column(String(120), index=True)
    campaign_id: Mapped[str] = mapped_column(String(120), index=True)
    episode: Mapped[int] = mapped_column(Integer, default=DEFAULT_EPISODE)
    lock_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()


class ContinuityEpisode(Base):
    """One frozen episode snapshot, owned by exactly one workspace."""

    __tablename__ = "continuity_episodes"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "persona_id",
            "campaign_id",
            "episode",
            name="uq_continuity_episodes_scope",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    persona_id: Mapped[str] = mapped_column(String(120), index=True)
    campaign_id: Mapped[str] = mapped_column(String(120), index=True)
    episode: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    notes: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column()
