"""V3.1: repository over the knowledge-graph tables.

The single persistence boundary for the Cinematic Knowledge Graph, following
the convention ``repositories/persona_repository.py`` (PR003) established:

* short-lived ``SessionLocal`` sessions per call, rows detached before the
  session closes, module-level ``graph_repo`` singleton for the API layer;
* every read and write is workspace-scoped — a foreign id behaves as a 404,
  never a 403, so tenant ids are not enumerable;
* child cleanup is explicit: deleting a node removes its incident edges in
  both directions first (no DB-level foreign keys, same portable rule);
* the relation vocabulary is enforced before persistence
  (``normalize_relation``), so the table only ever holds canonical terms.

The engine (``relationship_engine.py``) and the search (``semantic_query.py``)
stay framework-free; ``RepositoryGraphStore`` below is the adapter that binds
them to one workspace, and ``relationship_engine_for`` / ``semantic_query_for`` /
``character_graph_for`` are the constructors the routes use.
"""
from __future__ import annotations

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from .graph_models import (
    GraphEdge,
    GraphNode,
    GraphValidationError,
    dumps_aliases,
    dumps_attributes,
    loads_aliases,
    loads_attributes,
    normalize_entity_type,
    slugify,
    utcnow,
)
from .relationship_engine import (
    CharacterGraph,
    GraphEdgeView,
    GraphNodeView,
    RelationshipEngine,
    normalize_relation,
)
from .semantic_query import SemanticQuery


class GraphRepositoryError(Exception):
    """Raised when a write cannot proceed (slug taken, edge duplicated)."""


def node_view(row: GraphNode) -> GraphNodeView:
    """Map a node row onto the engine's detached view."""

    return GraphNodeView(
        id=row.id,
        workspace_id=row.workspace_id,
        entity_type=row.entity_type,
        name=row.name,
        slug=row.slug,
        attributes=loads_attributes(row.attributes_json),
        aliases=tuple(loads_aliases(row.aliases_json)),
        # Non-nullable columns with defaults: always populated on persisted rows.
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def edge_view(row: GraphEdge) -> GraphEdgeView:
    """Map an edge row onto the engine's detached view."""

    return GraphEdgeView(
        id=row.id,
        workspace_id=row.workspace_id,
        source_id=row.source_id,
        target_id=row.target_id,
        relation=row.relation,
        created_at=row.created_at.isoformat(),
    )


def _detach(db: Session, row):
    """Return a detached row whose attributes are fully loaded.

    ``db.commit()`` expires the instance by default; refreshing before
    expunging loads every column into memory, so the caller can keep using
    the row after the session closes without a DetachedInstanceError.
    """

    db.refresh(row)
    db.expunge(row)
    return row


class GraphRepository:
    """CRUD + traversal reads for graph nodes and edges (workspace-scoped)."""

    # ----------------------------------------------------------------- nodes

    def create_node(
        self,
        workspace_id: str,
        *,
        name: str,
        entity_type: str,
        attributes: dict | None = None,
        aliases: list[str] | None = None,
        slug: str | None = None,
    ) -> GraphNode:
        """Create a node. The slug defaults from the name and is unique."""

        cleaned_name = name.strip()
        if not cleaned_name:
            raise GraphValidationError("name must not be blank")
        kind = normalize_entity_type(entity_type)
        node_slug = (slug or "").strip() or slugify(cleaned_name)
        stored_attributes = dumps_attributes(dict(attributes or {}))
        stored_aliases = dumps_aliases(list(aliases or []))
        with SessionLocal() as db:
            taken = db.scalar(
                select(GraphNode.id).where(
                    GraphNode.workspace_id == workspace_id, GraphNode.slug == node_slug
                )
            )
            if taken:
                raise GraphRepositoryError(
                    f"slug '{node_slug}' already exists in this workspace"
                )
            row = GraphNode(
                workspace_id=workspace_id,
                entity_type=kind,
                name=cleaned_name,
                slug=node_slug,
                attributes_json=stored_attributes,
                aliases_json=stored_aliases,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            db.add(row)
            db.commit()
            return _detach(db, row)

    def get_node(self, node_id: str, workspace_id: str | None = None) -> GraphNode | None:
        if not node_id:
            return None
        with SessionLocal() as db:
            row = db.get(GraphNode, node_id)
            if row is None:
                return None
            if workspace_id is not None and row.workspace_id != workspace_id:
                return None
            return _detach(db, row)

    def find_by_slug(self, slug: str, workspace_id: str) -> GraphNode | None:
        if not slug:
            return None
        with SessionLocal() as db:
            row = db.scalar(
                select(GraphNode).where(
                    GraphNode.workspace_id == workspace_id, GraphNode.slug == slug
                )
            )
            return _detach(db, row) if row else None

    def list_nodes(
        self,
        workspace_id: str,
        *,
        entity_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GraphNode]:
        kind = normalize_entity_type(entity_type) if entity_type else None
        bounded = max(1, min(limit, 200))
        start = max(0, offset)
        with SessionLocal() as db:
            statement = (
                select(GraphNode)
                .where(GraphNode.workspace_id == workspace_id)
                .order_by(func.lower(GraphNode.name), GraphNode.id)
                .limit(bounded)
                .offset(start)
            )
            if kind is not None:
                statement = statement.where(GraphNode.entity_type == kind)
            return [_detach(db, row) for row in db.scalars(statement).all()]

    def update_node(
        self,
        node_id: str,
        workspace_id: str,
        changes: dict[str, object],
    ) -> GraphNode | None:
        """Apply a partial update. ``attributes``/``aliases`` replace wholesale.

        Unknown keys are ignored (the API layer validates the shape first);
        the slug is immutable, like the persona slug (PR003). Returns ``None``
        when the node does not exist in the workspace.
        """

        with SessionLocal() as db:
            row = db.get(GraphNode, node_id)
            if row is None or row.workspace_id != workspace_id:
                return None
            if "name" in changes:
                cleaned = str(changes["name"]).strip()
                if not cleaned:
                    raise GraphValidationError("name must not be blank")
                row.name = cleaned
            if "entity_type" in changes:
                row.entity_type = normalize_entity_type(str(changes["entity_type"]))
            if "attributes" in changes:
                value = changes["attributes"]
                if not isinstance(value, dict):
                    raise GraphValidationError("attributes must be an object")
                row.attributes_json = dumps_attributes(dict(value))
            if "aliases" in changes:
                value = changes["aliases"]
                if not isinstance(value, list):
                    raise GraphValidationError("aliases must be a list of strings")
                row.aliases_json = dumps_aliases(list(value))
            row.updated_at = utcnow()
            db.commit()
            return _detach(db, row)

    def delete_node(self, node_id: str, workspace_id: str) -> bool:
        """Remove a node and its incident edges in both directions."""

        with SessionLocal() as db:
            row = db.get(GraphNode, node_id)
            if row is None or row.workspace_id != workspace_id:
                return False
            db.execute(
                sa_delete(GraphEdge).where(
                    GraphEdge.workspace_id == workspace_id,
                    ((GraphEdge.source_id == node_id) | (GraphEdge.target_id == node_id)),
                )
            )
            db.delete(row)
            db.commit()
            return True

    # ----------------------------------------------------------------- edges

    def create_edge(
        self,
        workspace_id: str,
        *,
        source_id: str,
        target_id: str,
        relation: str,
    ) -> GraphEdge:
        """Create one directed edge between two nodes of the workspace.

        Both endpoints must exist in the workspace (a missing endpoint raises
        ``GraphRepositoryError`` and the route maps it to 404); the relation
        is normalised to the canonical vocabulary; self-loops and duplicates
        are refused.
        """

        canonical = normalize_relation(relation)
        if source_id == target_id:
            raise GraphValidationError("an edge cannot loop back onto its own node")
        with SessionLocal() as db:
            for endpoint in (source_id, target_id):
                row = db.get(GraphNode, endpoint)
                if row is None or row.workspace_id != workspace_id:
                    raise GraphRepositoryError(f"unknown node in this workspace: {endpoint}")
            duplicate = db.scalar(
                select(GraphEdge.id).where(
                    GraphEdge.workspace_id == workspace_id,
                    GraphEdge.source_id == source_id,
                    GraphEdge.target_id == target_id,
                    GraphEdge.relation == canonical,
                )
            )
            if duplicate:
                raise GraphRepositoryError("this relation already exists between the two nodes")
            edge = GraphEdge(
                workspace_id=workspace_id,
                source_id=source_id,
                target_id=target_id,
                relation=canonical,
                created_at=utcnow(),
            )
            db.add(edge)
            db.commit()
            return _detach(db, edge)

    def list_edges(
        self,
        workspace_id: str,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
        relation: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[GraphEdge]:
        canonical = normalize_relation(relation) if relation else None
        bounded = max(1, min(limit, 500))
        start = max(0, offset)
        with SessionLocal() as db:
            statement = (
                select(GraphEdge)
                .where(GraphEdge.workspace_id == workspace_id)
                .order_by(GraphEdge.created_at, GraphEdge.id)
                .limit(bounded)
                .offset(start)
            )
            if source_id is not None:
                statement = statement.where(GraphEdge.source_id == source_id)
            if target_id is not None:
                statement = statement.where(GraphEdge.target_id == target_id)
            if canonical is not None:
                statement = statement.where(GraphEdge.relation == canonical)
            return [_detach(db, row) for row in db.scalars(statement).all()]

    def delete_edge(self, edge_id: str, workspace_id: str) -> bool:
        with SessionLocal() as db:
            row = db.get(GraphEdge, edge_id)
            if row is None or row.workspace_id != workspace_id:
                return False
            db.delete(row)
            db.commit()
            return True

    def out_edges(self, node_id: str, workspace_id: str) -> list[GraphEdge]:
        return self.list_edges(workspace_id, source_id=node_id, limit=500)

    def in_edges(self, node_id: str, workspace_id: str) -> list[GraphEdge]:
        return self.list_edges(workspace_id, target_id=node_id, limit=500)

    # ------------------------------------------------------------------- seed

    def seed_demo(self, workspace_id: str) -> dict[str, int]:
        """Load the V3.1 demonstration graph, idempotently.

        The Petrick/RAM/Legacy/Showroom/Goiânia graph from the brief, written
        through the same validated path as the API (the seed phrases use
        alias verbs — ``dirige``/``veste``/``pertence``/``localizado`` — so a
        seeded workspace also proves normalisation end to end). Existing slugs
        and relations are skipped, never duplicated.
        """

        created_nodes = 0
        skipped_nodes = 0
        for spec in _DEMO_NODES:
            if self.find_by_slug(spec["slug"], workspace_id) is not None:
                skipped_nodes += 1
                continue
            self.create_node(
                workspace_id,
                name=spec["name"],
                entity_type=spec["entity_type"],
                attributes=dict(spec.get("attributes", {})),
                aliases=list(spec.get("aliases", [])),
                slug=spec["slug"],
            )
            created_nodes += 1
        created_edges = 0
        skipped_edges = 0
        by_slug = {
            row.slug: row
            for row in self.list_nodes(workspace_id, limit=200)
            if row.slug in _DEMO_SLUGS
        }
        for source_slug, relation, target_slug in _DEMO_EDGES:
            # Direct indexing is safe: the node loop above guarantees every
            # demo slug exists (pre-existing or just created).
            source = by_slug[source_slug]
            target = by_slug[target_slug]
            try:
                self.create_edge(
                    workspace_id,
                    source_id=source.id,
                    target_id=target.id,
                    relation=relation,
                )
            except GraphRepositoryError:
                skipped_edges += 1
            else:
                created_edges += 1
        return {
            "created_nodes": created_nodes,
            "created_edges": created_edges,
            "skipped_nodes": skipped_nodes,
            "skipped_edges": skipped_edges,
        }


#: The module-level singleton the API layer wires in (mirrors ``persona_repo``
#: from PR003).
graph_repo = GraphRepository()


class RepositoryGraphStore:
    """Workspace-bound ``GraphStore``/``NodeSearchStore`` over the repository."""

    def __init__(self, repository: GraphRepository, workspace_id: str) -> None:
        self._repository = repository
        self._workspace_id = workspace_id

    def get_node(self, node_id: str) -> GraphNodeView | None:
        row = self._repository.get_node(node_id, self._workspace_id)
        return node_view(row) if row is not None else None

    def out_edges(self, node_id: str) -> list[GraphEdgeView]:
        return [edge_view(row) for row in self._repository.out_edges(node_id, self._workspace_id)]

    def in_edges(self, node_id: str) -> list[GraphEdgeView]:
        return [edge_view(row) for row in self._repository.in_edges(node_id, self._workspace_id)]

    def list_nodes(self) -> list[GraphNodeView]:
        return [node_view(row) for row in self._repository.list_nodes(self._workspace_id, limit=200)]


def relationship_engine_for(workspace_id: str) -> RelationshipEngine:
    """A traversal engine bound to one workspace (routes use this)."""

    return RelationshipEngine(RepositoryGraphStore(graph_repo, workspace_id))


def semantic_query_for(workspace_id: str) -> SemanticQuery:
    """A semantic search bound to one workspace (routes use this)."""

    return SemanticQuery(RepositoryGraphStore(graph_repo, workspace_id))


def character_graph_for(workspace_id: str) -> CharacterGraph:
    """A character facade bound to one workspace (routes use this)."""

    return CharacterGraph(RepositoryGraphStore(graph_repo, workspace_id))


#: The demonstration graph: nine nodes across all seven entity types.
_DEMO_NODES: tuple[dict, ...] = (
    {
        "slug": "petrick",
        "name": "Petrick",
        "entity_type": "character",
        "aliases": ["Petrick Martins"],
        "attributes": {"role": "Founder & Director", "brand": "BroBond"},
    },
    {
        "slug": "ram",
        "name": "RAM",
        "entity_type": "vehicle",
        "aliases": ["RAM 3500"],
        "attributes": {"color": "branca", "model": "3500 Laramie", "kind": "pickup"},
    },
    {
        "slug": "legacy-jacket",
        "name": "Legacy Jacket",
        "entity_type": "wardrobe",
        "aliases": ["Jaqueta Legacy"],
        "attributes": {"category": "jacket", "color": "preta"},
    },
    {
        "slug": "legacy",
        "name": "Legacy",
        "entity_type": "brand",
        "aliases": ["Legacy Collection"],
        "attributes": {"segment": "moda masculina"},
    },
    {
        "slug": "brobond",
        "name": "BroBond",
        "entity_type": "brand",
        "aliases": ["BROBOND"],
        "attributes": {"segment": "estudio cinematografico"},
    },
    {
        "slug": "legacy-launch",
        "name": "Legacy Launch",
        "entity_type": "campaign",
        "aliases": [],
        "attributes": {"season": "2026", "goal": "lancamento da colecao Legacy"},
    },
    {
        "slug": "showroom",
        "name": "Showroom",
        "entity_type": "location",
        "aliases": [],
        "attributes": {"city": "Goiania", "state": "GO", "country": "BR", "kind": "showroom"},
    },
    {
        "slug": "goiania",
        "name": "Goiânia",
        "entity_type": "location",
        "aliases": [],
        "attributes": {"state": "GO", "country": "BR", "kind": "city"},
    },
    {
        "slug": "vintage-camera",
        "name": "Vintage Camera",
        "entity_type": "prop",
        "aliases": [],
        "attributes": {"kind": "camera", "era": "analogica"},
    },
)

_DEMO_SLUGS = frozenset(spec["slug"] for spec in _DEMO_NODES)

#: (source slug, relation — aliases welcome —, target slug).
_DEMO_EDGES: tuple[tuple[str, str, str], ...] = (
    ("petrick", "dirige", "ram"),
    ("petrick", "veste", "legacy-jacket"),
    ("legacy", "pertence", "brobond"),
    ("showroom", "localizado", "goiania"),
    ("legacy-launch", "features", "petrick"),
    ("legacy-launch", "filmed_at", "showroom"),
    ("legacy-jacket", "belongs_to", "legacy"),
    ("petrick", "manages", "legacy"),
    ("brobond", "produces", "legacy-launch"),
    ("vintage-camera", "appears_in", "legacy-launch"),
    ("showroom", "features", "ram"),
)
