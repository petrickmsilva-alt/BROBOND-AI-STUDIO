"""V3.1 — Cinematic Knowledge Graph: GraphRepository.

The single persistence boundary of the graph, following the PR003/PR004
repository convention: short-lived `SessionLocal` per call, a module-level
`graph_repo` singleton wired in at the composition root (`app.main`), and the
routes translate its rows into schemas.

Scope model:

* canonical catalog rows live in ``workspace_id = "global"`` and are visible
  to every workspace (never mutable through the workspace surface);
* a workspace view = canonical rows + the workspace's own rows, with the
  workspace row winning a ``(entity_type, name)`` collision, so a workspace
  may specialize an entity without forking the catalog;
* relationships belong to the workspace that created them; a relationship is
  visible in a view when its workspace is the caller's or it is canonical.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from .graph_models import GLOBAL_WORKSPACE_ID, ENTITY_TYPES, GraphNode, GraphRelationship


class GraphRepositoryError(Exception):
    """Base error for graph persistence failures."""


class GraphNotFoundError(GraphRepositoryError):
    """The requested row does not exist (or is not visible to the workspace)."""


class GraphConflictError(GraphRepositoryError):
    """The write collides with an existing row, or touches read-only data.

    `code` tells the route which HTTP status fits: "read-only" for the
    canonical catalog (403), everything else is a duplicate/collision (409).
    """

    def __init__(self, message: str, code: str = "conflict") -> None:
        super().__init__(message)
        self.code = code


class GraphValidationError(GraphRepositoryError):
    """The payload violates the graph's shape rules before any persistence."""


class GraphRepository:
    """CRUD + relational reads for the cinematic knowledge graph.

    `session_factory` is injectable so tests bind a private in-memory
    database instead of the shared one (the same seam PR004-prep gave the
    job repositories).
    """

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------- sessions

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Short-lived session, committed on success (the PR002 convention).

        `expire_on_commit` is off because the repository hands ORM objects to
        the route layer *after* the session closes: with the default, the
        commit would expire every attribute and the first attribute read
        outside the session would raise `DetachedInstanceError`.
        """

        db = self._session_factory()
        db.expire_on_commit = False
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ----------------------------------------------------------------- nodes

    def create_node(
        self,
        workspace_id: str,
        entity_type: str,
        name: str,
        description: str = "",
        attributes: dict[str, object] | None = None,
        external_ref: str | None = None,
    ) -> GraphNode:
        if entity_type not in ENTITY_TYPES:
            raise GraphValidationError(f"unknown entity_type: {entity_type}")
        node = GraphNode(
            workspace_id=workspace_id,
            entity_type=entity_type,
            name=name.strip(),
            description=description,
            external_ref=external_ref,
        )
        node.attributes = attributes or {}
        with self.session() as db:
            db.add(node)
            try:
                db.flush()
            except Exception as exc:
                raise GraphConflictError(
                    f"an {entity_type} named {node.name!r} already exists in this workspace"
                ) from exc
            db.refresh(node)
            return node

    def get_node(self, node_id: str) -> GraphNode | None:
        with self.session() as db:
            return db.get(GraphNode, node_id)

    def find_character_by_external_ref(self, external_ref: str) -> GraphNode | None:
        """The canonical character linked to a persona id (None when absent).

        The catalog is the resolver's bridge, so this looks in the global
        workspace only: workspace-private character rows are product data, not
        canonical identity.
        """

        with self.session() as db:
            return db.scalar(
                select(GraphNode).where(
                    GraphNode.workspace_id == GLOBAL_WORKSPACE_ID,
                    GraphNode.entity_type == "character",
                    GraphNode.external_ref == external_ref,
                )
            )

    def list_nodes(self, workspace_id: str | None = None, entity_type: str | None = None, q: str | None = None) -> list[GraphNode]:
        """Nodes visible to a workspace (canonical + own); None lists the catalog only."""

        statement = select(GraphNode)
        if workspace_id is None:
            statement = statement.where(GraphNode.workspace_id == GLOBAL_WORKSPACE_ID)
        else:
            statement = statement.where(GraphNode.workspace_id.in_((GLOBAL_WORKSPACE_ID, workspace_id)))
        return self._filtered(statement, entity_type, q)

    def _filtered(self, statement, entity_type: str | None, q: str | None) -> list[GraphNode]:
        if entity_type:
            statement = statement.where(GraphNode.entity_type == entity_type)
        if q:
            pattern = f"%{q}%"
            statement = statement.where(
                (GraphNode.name.ilike(pattern))
                | (GraphNode.description.ilike(pattern))
                | (GraphNode.attributes_json.ilike(pattern))
            )
        with self.session() as db:
            return list(db.scalars(statement.order_by(GraphNode.entity_type, GraphNode.name)).all())

    def update_node(
        self,
        workspace_id: str,
        node_id: str,
        name: str | None = None,
        description: str | None = None,
        attributes: dict[str, object] | None = None,
        external_ref: str | None = None,
    ) -> GraphNode:
        """Patch a workspace-owned node; canonical rows are read-only."""

        with self.session() as db:
            node = db.get(GraphNode, node_id)
            if node is None:
                raise GraphNotFoundError(f"node {node_id} not found")
            if node.workspace_id == GLOBAL_WORKSPACE_ID:
                raise GraphConflictError("canonical nodes are read-only", code="read-only")
            if node.workspace_id != workspace_id:
                raise GraphNotFoundError(f"node {node_id} not found")
            if name is not None:
                node.name = name.strip()
            if description is not None:
                node.description = description
            if attributes is not None:
                node.attributes = attributes
            if external_ref is not None:
                node.external_ref = external_ref
            try:
                db.flush()
            except Exception as exc:
                raise GraphConflictError("the updated name collides with an existing node") from exc
            db.refresh(node)
            return node

    def delete_node(self, workspace_id: str, node_id: str) -> None:
        """Remove a workspace-owned node and every relationship touching it."""

        with self.session() as db:
            node = db.get(GraphNode, node_id)
            if node is None:
                raise GraphNotFoundError(f"node {node_id} not found")
            if node.workspace_id == GLOBAL_WORKSPACE_ID:
                raise GraphConflictError("canonical nodes are read-only", code="read-only")
            if node.workspace_id != workspace_id:
                raise GraphNotFoundError(f"node {node_id} not found")
            db.execute(
                sa_delete(GraphRelationship).where(
                    (GraphRelationship.source_node_id == node_id)
                    | (GraphRelationship.target_node_id == node_id),
                    GraphRelationship.workspace_id == workspace_id,
                )
            )
            db.delete(node)
            db.flush()

    # --------------------------------------------------------- relationships

    def create_relationship(
        self,
        workspace_id: str,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        description: str = "",
    ) -> GraphRelationship:
        relationship = GraphRelationship(
            workspace_id=workspace_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation_type=relation_type,
            description=description,
        )
        with self.session() as db:
            db.add(relationship)
            try:
                db.flush()
            except Exception as exc:
                raise GraphConflictError(
                    f"{relation_type!r} between these nodes already exists in this workspace"
                ) from exc
            db.refresh(relationship)
            return relationship

    def get_relationship(self, relationship_id: str) -> GraphRelationship | None:
        with self.session() as db:
            return db.get(GraphRelationship, relationship_id)

    def list_relationships(
        self,
        workspace_id: str,
        relation_type: str | None = None,
        source_node_id: str | None = None,
        target_node_id: str | None = None,
    ) -> list[GraphRelationship]:
        statement = select(GraphRelationship).where(
            GraphRelationship.workspace_id.in_((GLOBAL_WORKSPACE_ID, workspace_id))
        )
        if relation_type:
            statement = statement.where(GraphRelationship.relation_type == relation_type)
        if source_node_id:
            statement = statement.where(GraphRelationship.source_node_id == source_node_id)
        if target_node_id:
            statement = statement.where(GraphRelationship.target_node_id == target_node_id)
        with self.session() as db:
            return list(db.scalars(statement.order_by(GraphRelationship.relation_type)).all())

    def relationships_for_node(self, node_id: str, workspace_id: str | None = None) -> list[GraphRelationship]:
        """Every edge touching the node, both directions, scoped to a workspace.

        Canonical nodes are shared, so their adjacency is the union of the
        canonical edges and the requesting workspace's edges — never the
        edges of other workspaces (tenant isolation).
        """

        statement = select(GraphRelationship).where(
            (GraphRelationship.source_node_id == node_id) | (GraphRelationship.target_node_id == node_id)
        )
        if workspace_id is not None:
            statement = statement.where(GraphRelationship.workspace_id.in_((GLOBAL_WORKSPACE_ID, workspace_id)))
        with self.session() as db:
            return list(db.scalars(statement).all())

    def delete_relationship(self, relationship_id: str) -> None:
        with self.session() as db:
            relationship = db.get(GraphRelationship, relationship_id)
            if relationship is None:
                raise GraphNotFoundError(f"relationship {relationship_id} not found")
            db.delete(relationship)
            db.flush()

    # ------------------------------------------------------------------- view

    def workspace_view(self, workspace_id: str) -> tuple[list[GraphNode], list[GraphRelationship]]:
        """The graph a workspace sees: canonical + own, workspace wins ties.

        A workspace row with the same ``(entity_type, name)`` as a canonical
        one *specializes* the entity, so the canonical copy is hidden behind
        it — the catalog stays single-source per entity address.
        """

        by_address: dict[tuple[str, str], GraphNode] = {}
        for node in self.list_nodes(workspace_id=workspace_id):
            key = (node.entity_type, node.name.casefold())
            current = by_address.get(key)
            if current is None or (
                current.workspace_id == GLOBAL_WORKSPACE_ID and node.workspace_id != GLOBAL_WORKSPACE_ID
            ):
                by_address[key] = node
        nodes = list(by_address.values())
        visible_ids = {node.id for node in nodes}
        relationships = [
            row
            for row in self.list_relationships(workspace_id)
            if row.source_node_id in visible_ids and row.target_node_id in visible_ids
        ]
        return nodes, relationships


#: The module-level singleton the composition root (`app.main`) wires in —
#: the same convention as `repositories/persona_repository.py::persona_repo`.
graph_repo = GraphRepository()
