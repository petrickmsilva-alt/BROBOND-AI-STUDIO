"""V3.1 — Cinematic Knowledge Graph: persistence models.

Two tables hold the whole graph, so every entity type relates to every other
type with no per-type plumbing:

* ``graph_nodes`` — one row per entity (Character, Brand, Campaign, Location,
  Vehicle, Wardrobe, Prop). ``attributes``/``aliases`` are JSON documents in
  ``Text`` columns, the same SQLite/Postgres-portable convention
  ``persona_wardrobe.metadata`` uses (PR003).
* ``graph_edges`` — one directed row per relation (``source -> relation ->
  target``). The relation stores the canonical vocabulary term; traversal in
  both directions is the engine's job, not a second row.

Conventions inherited from the codebase: ``String(36)`` uuid primary keys,
``workspace_id`` as an indexed plain reference (no DB-level foreign keys),
``slug`` unique per workspace for stable addressing, naive-UTC timestamps.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


#: The seven V3.1 entity types (``BROBOND STUDIO V3 — MASTER ARCHITECTURE``,
#: §ROADMAP V3). Lowercase canonical form; user input is normalised onto it.
ENTITY_TYPES: tuple[str, ...] = (
    "character",
    "brand",
    "campaign",
    "location",
    "vehicle",
    "wardrobe",
    "prop",
)


class GraphValidationError(ValueError):
    """Raised when graph input violates the domain vocabulary."""


def normalize_entity_type(value: str) -> str:
    """Return the canonical entity type for user input, or raise 422-style."""

    token = value.strip().casefold()
    if token not in ENTITY_TYPES:
        raise GraphValidationError(
            f"unknown entity type: {value!r} (expected one of: {', '.join(ENTITY_TYPES)})"
        )
    return token


def slugify(name: str) -> str:
    """Stable, workspace-unique-friendly slug from a node name."""

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:180] or "node"


def dumps_attributes(attributes: dict) -> str:
    """Serialise node attributes, rejecting non-JSON values loudly."""

    if not isinstance(attributes, dict):
        raise GraphValidationError("attributes must be an object")
    try:
        return json.dumps(attributes, ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise GraphValidationError(f"attributes are not JSON-serialisable: {error}") from error


def loads_attributes(raw: str | None) -> dict:
    """Parse stored attributes, defensively (a corrupt row reads as empty)."""

    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def dumps_aliases(aliases: list[str]) -> str:
    """Serialise node aliases, normalising whitespace and dropping empties."""

    if not isinstance(aliases, list) or any(not isinstance(item, str) for item in aliases):
        raise GraphValidationError("aliases must be a list of strings")
    cleaned = [item.strip() for item in aliases]
    return json.dumps([item for item in cleaned if item], ensure_ascii=False)


def loads_aliases(raw: str | None) -> list[str]:
    """Parse stored aliases, defensively (a corrupt row reads as no aliases)."""

    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the repository convention."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


class GraphNode(Base):
    """One knowledge-graph entity, owned by exactly one workspace."""

    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_graph_nodes_workspace_slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), index=True)
    attributes_json: Mapped[str] = mapped_column("attributes", Text, default="{}")
    aliases_json: Mapped[str] = mapped_column("aliases", Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class GraphEdge(Base):
    """One directed relation between two nodes of the same workspace.

    Edges reference nodes by plain indexed ids (no DB foreign key): node
    deletion removes incident edges explicitly in the repository, the same
    rule persona children follow. The ``(workspace, source, target,
    relation)`` unique constraint makes a relation idempotent — creating it
    twice is a conflict, not a duplicate.
    """

    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_id",
            "target_id",
            "relation",
            name="uq_graph_edges_endpoint_relation",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    relation: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
