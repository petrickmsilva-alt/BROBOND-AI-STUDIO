"""V3.1 — Cinematic Knowledge Graph: persistence models.

Two tables, both on the `Base` metadata (registered through `app.models`, the
same way `models/job.py` is):

* ``knowledge_graph_nodes``         — the entities (Character, Brand, Campaign,
  Location, Vehicle, Wardrobe, Prop) — every type is relatable to every other;
* ``knowledge_graph_relationships`` — the directed, typed edges between them
  ("Petrick -> dirige -> RAM"). One row per (workspace, source, type, target):
  the reverse direction is derived, never duplicated (bidirectional views are
  computed by the Relationship Engine).

Workspace scoping follows the Persona Engine precedent (PR003): canonical,
brand-level knowledge (the BROBOND catalog: Petrick, Legacy, RAM, BroBond,
Showroom, Goiânia) lives in a special ``global`` workspace that every
workspace's view includes; user-created nodes and relationships are owned by
the caller's workspace. The Core never sees these rows — it knows only the
frozen `KnowledgeContext` vocabulary in `core/contracts.py`.
"""
from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

#: The sentinel workspace that owns the canonical (read-only) catalog.
GLOBAL_WORKSPACE_ID = "global"

#: The seven entity types of V3.1 — every one of them is relatable.
ENTITY_TYPES: tuple[str, ...] = (
    "character",
    "brand",
    "campaign",
    "location",
    "vehicle",
    "wardrobe",
    "prop",
)


def _utcnow() -> datetime:
    return datetime.utcnow()


class GraphNode(Base):
    """One entity in the cinematic knowledge graph."""

    __tablename__ = "knowledge_graph_nodes"
    __table_args__ = (
        # (workspace, type, name) is the entity's address: "the RAM vehicle"
        # is unique per workspace; the same name may exist in two types.
        UniqueConstraint("workspace_id", "entity_type", "name", name="uq_graph_nodes_ws_type_name"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    #: A free-form attribute bag as a JSON document (Text, the portable
    #: convention of `audit_log.detail` / `persona_wardrobe.metadata`).
    attributes_json: Mapped[str] = mapped_column(Text, default="{}")
    #: Stable link to an external identity (e.g. the ledger's "CHAR_PETRICK")
    #: so the Memory Resolver can find the character row for a persona id.
    external_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    @property
    def attributes(self) -> dict[str, str]:
        try:
            parsed = json.loads(self.attributes_json or "{}")
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in parsed.items()} if isinstance(parsed, dict) else {}

    @attributes.setter
    def attributes(self, value: dict[str, object]) -> None:
        self.attributes_json = json.dumps(value or {}, ensure_ascii=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "description": self.description,
            "attributes": self.attributes,
            "external_ref": self.external_ref,
            "is_canonical": self.workspace_id == GLOBAL_WORKSPACE_ID,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class GraphRelationship(Base):
    """A directed, typed edge: ``source --relation_type--> target``.

    The reverse reading (``target <--reverse_relation_type-- source``) is
    derived by the Relationship Engine from the relation vocabulary — storing
    both directions would double every write and double every delete.
    """

    __tablename__ = "knowledge_graph_relationships"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_node_id",
            "relation_type",
            "target_node_id",
            name="uq_graph_rel_ws_source_type_target",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    source_node_id: Mapped[str] = mapped_column(String(36), index=True)
    target_node_id: Mapped[str] = mapped_column(String(36), index=True)
    relation_type: Mapped[str] = mapped_column(String(60), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation_type": self.relation_type,
            "description": self.description,
            "is_canonical": self.workspace_id == GLOBAL_WORKSPACE_ID,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
