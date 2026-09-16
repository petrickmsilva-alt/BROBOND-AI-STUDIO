"""V3.1 — Cinematic Knowledge Graph: Relationship Engine.

Owns the domain rules on top of the persistence boundary:

* the relation vocabulary (``dirige``, ``veste``, ``pertence``, ``localizado``,
  ``aparece_em``, ``usa``, ``faz_parte_de``) with a human-readable display
  label and the **reverse** label, which is what makes every relationship
  bidirectional: one stored row, two readings;
* write validation (no self-loops, both ends must exist, duplicates refused);
* bidirectional neighbour views (outgoing and incoming, each labelled from the
  reader's side);
* a bounded BFS ``shortest_path`` so the UI can show how two entities connect;
* the canonical BROBOND catalog ("CharacterGraph" of the V3.1 deliverable):
  Petrick drives the white RAM, wears the Legacy Jacket, appears in the Legacy
  campaign; Legacy belongs to BroBond; the Showroom is located in Goiânia.

The engine never imports the Core and never produces prompt text — it is
knowledge, not direction. The Core's `MemoryResolver` reaches it only through
the `KnowledgeContextSource` protocol (see `app.main`).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .graph_models import GLOBAL_WORKSPACE_ID, GraphNode, GraphRelationship
from .graph_repository import GraphConflictError, GraphNotFoundError, GraphRepository, GraphValidationError

#: relation_type -> (display label read from the source side, reverse label
#: read from the target side, typical (source_types, target_types)).
#: `typical` is a *hint* for the UI, never an enforcement: V3.1 makes every
#: entity type relatable to every other, so any pair is legal.
RELATION_VOCABULARY: dict[str, tuple[str, str, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    "dirige": ("dirige", "é dirigido por", (("character",), ("vehicle",))),
    "veste": ("veste", "é vestida por", (("character",), ("wardrobe",))),
    "pertence": ("pertence a", "possui", (("campaign", "wardrobe", "location", "vehicle", "prop"), ("brand", "campaign"))),
    "localizado": ("localizado em", "contém", (("location",), ("location",))),
    "aparece_em": ("aparece em", "apresenta", (("character",), ("campaign", "location"))),
    "usa": ("usa", "é usado por", (("character",), ("prop", "vehicle"))),
    "faz_parte_de": ("faz parte de", "compõe", (("wardrobe", "prop", "campaign"), ("campaign", "brand"))),
}

#: Fallback pair for any user-supplied relation type outside the vocabulary:
#: the edge is stored, and both readings stay honest ("relacionado a").
GENERIC_RELATION: tuple[str, str] = ("relacionado a", "relacionado a")


def reverse_relation(relation_type: str) -> str:
    """The label an edge reads with when it is traversed backwards."""

    return RELATION_VOCABULARY.get(relation_type, GENERIC_RELATION)[1]


def display_label(relation_type: str) -> str:
    """The label an edge reads with from the source side."""

    return RELATION_VOCABULARY.get(relation_type, GENERIC_RELATION)[0]


def relationship_vocabulary() -> list[dict[str, object]]:
    """The curated vocabulary, for the UI's relation picker."""

    return [
        {
            "type": type_,
            "display_label": display_label(type_),
            "reverse_relation": reverse_relation(type_),
            "typical": {"source": source, "target": target},
        }
        for type_, (_, _, (source, target)) in RELATION_VOCABULARY.items()
    ]


@dataclass(frozen=True)
class ResolvedRelationship:
    """A relationship row plus its two endpoint nodes and the reverse label.

    `direction` is relative to the node the view was requested for:
    "outgoing" when the node is the source, "incoming" when it is the target.
    """

    relationship: GraphRelationship
    source: GraphNode
    target: GraphNode
    direction: str

    @property
    def reverse_relation_type(self) -> str:
        return reverse_relation(self.relationship.relation_type)

    @property
    def other(self) -> GraphNode:
        return self.source if self.direction == "incoming" else self.target


class RelationshipEngine:
    """Validation and bidirectional views over the graph repository."""

    def __init__(self, repository: GraphRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------ writes

    def connect(
        self,
        workspace_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
        description: str = "",
    ) -> GraphRelationship:
        """Create ``source --relation_type--> target`` after validating it.

        Raises `GraphValidationError` (empty/self-loop/overlong type),
        `GraphNotFoundError` (an endpoint is not visible to the workspace) and
        `GraphConflictError` (the exact edge already exists in that workspace).
        """

        normalized = (relation_type or "").strip().lower().replace(" ", "_")
        if not normalized:
            raise GraphValidationError("relation_type is required")
        if len(normalized) > 60:
            raise GraphValidationError("relation_type must be at most 60 characters")
        if source_id == target_id:
            raise GraphValidationError("a node cannot relate to itself")
        _visible_node(self._repo.get_node(source_id), workspace_id)
        _visible_node(self._repo.get_node(target_id), workspace_id)
        return self._repo.create_relationship(
            workspace_id,
            source_id,
            target_id,
            normalized,
            description=description,
        )

    def disconnect(self, workspace_id: str, relationship_id: str) -> None:
        """Remove a relationship the workspace owns; canonical is read-only."""

        relationship = self._repo.get_relationship(relationship_id)
        if relationship is None:
            raise GraphNotFoundError(f"relationship {relationship_id} not found")
        if relationship.workspace_id != workspace_id:
            raise GraphConflictError("canonical relationships are read-only", code="read-only")
        self._repo.delete_relationship(relationship_id)

    # ------------------------------------------------------------------- reads

    def neighbors(self, workspace_id: str, node_id: str, direction: str = "both") -> list[ResolvedRelationship]:
        """Bidirectional view: outgoing and incoming edges of a node, each
        labelled from the node's side (``reverse_relation`` on incoming)."""

        node = _visible_node(self._repo.get_node(node_id), workspace_id)
        resolved: list[ResolvedRelationship] = []
        for row in self._repo.relationships_for_node(node.id, workspace_id):
            source = self._repo.get_node(row.source_node_id)
            target = self._repo.get_node(row.target_node_id)
            if source is None or target is None:
                continue  # dangling row (defensive): never a 500
            if row.source_node_id == node.id:
                view = ResolvedRelationship(row, source, target, "outgoing")
            else:
                view = ResolvedRelationship(row, source, target, "incoming")
            if direction in ("both", view.direction):
                resolved.append(view)
        return resolved

    def shortest_path(
        self,
        workspace_id: str,
        start_id: str,
        end_id: str,
        max_depth: int = 4,
    ) -> list[str] | None:
        """Bounded BFS over the *undirected* graph: how two entities connect.

        Returns the node ids of the route (inclusive of both ends), or None
        when no route exists within `max_depth` hops. The graph is small by
        design (catalog + workspace additions), so an explicit stack keeps it
        deterministic: neighbours in stored order, no randomness.
        """

        if start_id == end_id:
            return [start_id]
        adjacency: dict[str, list[str]] = {}
        node_ids = [node.id for node in self._repo.list_nodes(workspace_id=workspace_id)]
        for node_id in node_ids:
            for row in self._repo.relationships_for_node(node_id, workspace_id):
                other = row.target_node_id if row.source_node_id == node_id else row.source_node_id
                adjacency.setdefault(node_id, []).append(other)
        frontier: list[str] = [start_id]
        came_from: dict[str, str] = {start_id: start_id}
        depth = 0
        while frontier and depth < max_depth:
            next_frontier: list[str] = []
            for current in frontier:
                for other in adjacency.get(current, []):
                    if other in came_from:
                        continue
                    came_from[other] = current
                    if other == end_id:
                        route = [end_id]
                        while route[-1] != start_id:
                            route.append(came_from[route[-1]])
                        return list(reversed(route))
                    next_frontier.append(other)
            frontier = next_frontier
            depth += 1
        return None

    def context_for_character(self, node_id: str) -> dict[str, object] | None:
        """A node's knowledge footprint: itself + every relation around it.

        Consumed by the Memory Resolver adapter (`app.main`) to build the
        Core's frozen `KnowledgeContext`. Returns None for unknown nodes so
        the resolver degrades to "no context" instead of raising.
        """

        node = self._repo.get_node(node_id)
        if node is None:
            return None
        return {
            "node": node,
            "relationships": self.neighbors(node.workspace_id, node.id),
        }

    # -------------------------------------------------------------------- seed

    def seed_canonical(self) -> int:
        """Upsert the canonical BROBOND catalog into the global workspace.

        Idempotent: rows that already exist are left untouched, so the call
        can run on every boot (it does, next to `seed_knowledge`) and after
        a fresh database. Returns how many rows were created.
        """

        created = 0
        with self._repo.session() as db:
            for entity_type, name, description, attributes, external_ref in CANONICAL_NODES:
                existing = db.scalar(
                    select(GraphNode).where(
                        GraphNode.workspace_id == GLOBAL_WORKSPACE_ID,
                        GraphNode.entity_type == entity_type,
                        GraphNode.name == name,
                    )
                )
                if existing is not None:
                    continue
                node = GraphNode(
                    workspace_id=GLOBAL_WORKSPACE_ID,
                    entity_type=entity_type,
                    name=name,
                    description=description,
                    external_ref=external_ref,
                )
                node.attributes = attributes
                db.add(node)
                created += 1
            db.flush()
            for source_name, target_name, relation_type, description in CANONICAL_RELATIONSHIPS:
                source = _canonical_node(db, source_name)
                target = _canonical_node(db, target_name)
                if source is None or target is None:
                    continue
                exists = db.scalar(
                    select(GraphRelationship).where(
                        GraphRelationship.workspace_id == GLOBAL_WORKSPACE_ID,
                        GraphRelationship.source_node_id == source.id,
                        GraphRelationship.relation_type == relation_type,
                        GraphRelationship.target_node_id == target.id,
                    )
                )
                if exists is not None:
                    continue
                db.add(
                    GraphRelationship(
                        workspace_id=GLOBAL_WORKSPACE_ID,
                        source_node_id=source.id,
                        target_node_id=target.id,
                        relation_type=relation_type,
                        description=description,
                    )
                )
                created += 1
            db.commit()
        return created


def _canonical_node(db: Session, name: str) -> GraphNode | None:
    return db.scalar(select(GraphNode).where(GraphNode.workspace_id == GLOBAL_WORKSPACE_ID, GraphNode.name == name))


def _visible_node(node: GraphNode | None, workspace_id: str) -> GraphNode:
    """A node is visible to a workspace when it is canonical or its own."""

    if node is None:
        raise GraphNotFoundError("node not found")
    if node.workspace_id != GLOBAL_WORKSPACE_ID and node.workspace_id != workspace_id:
        raise GraphNotFoundError("node not found")
    return node


#: The canonical catalog: (entity_type, name, description, attributes, external_ref).
#: Petrick and Jefferson carry the ledger's persona ids in `external_ref`, so
#: the Memory Resolver can jump from a persona id to its character node.
CANONICAL_NODES: tuple[tuple[str, str, str, dict[str, str], str | None], ...] = (
    (
        "character",
        "Petrick Martins",
        "Canonical BROBOND persona — 50 years, 1.85m, athletic build, short beard, cinematic realism.",
        {"idade": "50", "altura": "1.85m", "estilo": "cinematic realism"},
        "CHAR_PETRICK",
    ),
    (
        "character",
        "Jefferson",
        "Planned character — identity to be defined and approved before generation.",
        {},
        "CHAR_JEFFERSON",
    ),
    (
        "brand",
        "BroBond",
        "The BROBOND brand — premium automotive and lifestyle storytelling.",
        {},
        None,
    ),
    (
        "campaign",
        "Legacy",
        "Coleção Legacy — warm side light, tactile materials, measured pace, emotional restraint.",
        {"colecao": "Legacy", "paleta": "warm"},
        None,
    ),
    (
        "location",
        "Showroom",
        "BroBond flagship showroom — symmetrical architecture, warm practicals.",
        {"estilo": "premium"},
        None,
    ),
    (
        "location",
        "Goiânia",
        "City where the flagship showroom is located.",
        {"estado": "GO"},
        None,
    ),
    (
        "vehicle",
        "RAM",
        "White RAM 1500 — hero vehicle of the Legacy campaign.",
        {"modelo": "RAM 1500", "cor": "branca"},
        None,
    ),
    (
        "wardrobe",
        "Legacy Jacket",
        "Signature jacket of the Legacy collection.",
        {"colecao": "Legacy"},
        None,
    ),
    (
        "prop",
        "Vintage Radio",
        "Lifestyle prop — 1970s tabletop radio.",
        {"era": "1970s"},
        None,
    ),
)

#: Canonical relationships: (source name, target name, relation_type, description).
CANONICAL_RELATIONSHIPS: tuple[tuple[str, str, str, str], ...] = (
    ("Petrick Martins", "RAM", "dirige", "Petrick drives the white RAM."),
    ("Petrick Martins", "Legacy Jacket", "veste", "Signature look of the collection."),
    ("Petrick Martins", "Legacy", "aparece_em", "Face of the Legacy campaign."),
    ("Petrick Martins", "Vintage Radio", "usa", "Lifestyle detail in showroom scenes."),
    ("Legacy", "BroBond", "pertence", "A coleção Legacy pertence à marca BroBond."),
    ("Legacy Jacket", "Legacy", "faz_parte_de", "O item-âncora da coleção."),
    ("Showroom", "Goiânia", "localizado", "O showroom fica em Goiânia."),
    ("Showroom", "Legacy", "aparece_em", "Cenário principal da coleção Legacy."),
)
