"""V3.1 — Relationship Engine: vocabulary, traversal and phrasing.

Framework-free (stdlib only): the engine reasons over the ``GraphStore``
protocol and never imports SQLAlchemy. ``graph_repository.py`` is the only
module that binds it to the database, mirroring how the Core depends on
repository-backed protocols instead of the stores themselves.

Three responsibilities:

* **vocabulary** — the closed relation set (``RELATIONS``), the alias map
  (``RELATION_ALIASES``, including the Portuguese verbs from the V3.1 brief:
  ``dirige``/``veste``/``pertence``/``localizado``) and the inverse map that
  makes every relation readable in both directions;
* **traversal** — ``RelationshipEngine.neighbors`` walks the graph breadth
  first, cycle-safe, with a deterministic order (peers sorted by name, then
  relation), in ``out``/``in``/``both`` directions;
* **phrasing** — ``describe_edge`` renders one edge as a sentence
  (``Petrick dirige RAM``). Phrases always use the active voice from the
  edge's true source, so incoming relations never need gendered participles.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Protocol


class RelationshipError(ValueError):
    """Raised when a relation name is outside the engine vocabulary."""


#: The sixteen canonical relations. Stored on every edge; user input in any
#: alias form is normalised onto these before persistence.
RELATIONS: tuple[str, ...] = (
    "drives",
    "wears",
    "owns",
    "belongs_to",
    "located_at",
    "part_of",
    "features",
    "produces",
    "manages",
    "collaborates_with",
    "inspired_by",
    "uses",
    "designed_by",
    "styled_by",
    "filmed_at",
    "appears_in",
)

#: Inverse label per canonical relation. Every value is unique, so the map is
#: reversible; ``collaborates_with`` is symmetric by nature.
RELATION_INVERSES: dict[str, str] = {
    "drives": "driven_by",
    "wears": "worn_by",
    "owns": "owned_by",
    "belongs_to": "includes",
    "located_at": "hosts",
    "part_of": "contains",
    "features": "featured_in",
    "produces": "produced_by",
    "manages": "managed_by",
    "collaborates_with": "collaborates_with",
    "inspired_by": "inspires",
    "uses": "used_by",
    "designed_by": "designed",
    "styled_by": "styled",
    "filmed_at": "location_of",
    "appears_in": "shows",
}

#: Alias (normalised token) -> canonical relation. Covers the Portuguese
#: verbs from the V3.1 brief plus the obvious English inflections.
RELATION_ALIASES: dict[str, str] = {
    "dirige": "drives",
    "drive": "drives",
    "driving": "drives",
    "pilota": "drives",
    "pilot": "drives",
    "veste": "wears",
    "wear": "wears",
    "wearing": "wears",
    "vestindo": "wears",
    "traja": "wears",
    "pertence": "belongs_to",
    "pertence_a": "belongs_to",
    "possui": "owns",
    "own": "owns",
    "dono_de": "owns",
    "dona_de": "owns",
    "localizado": "located_at",
    "localizado_em": "located_at",
    "localizada": "located_at",
    "localizada_em": "located_at",
    "located_in": "located_at",
    "fica_em": "located_at",
    "parte_de": "part_of",
    "member_of": "part_of",
    "apresenta": "features",
    "feature": "features",
    "produz": "produces",
    "produce": "produces",
    "gerencia": "manages",
    "manage": "manages",
    "colabora_com": "collaborates_with",
    "se_inspira_em": "inspired_by",
    "inspirado_por": "inspired_by",
    "inspirado_em": "inspired_by",
    "usa": "uses",
    "use": "uses",
    "using": "uses",
    "utiliza": "uses",
    "tem_design_de": "designed_by",
    "tem_styling_de": "styled_by",
    "tem_locacao_em": "filmed_at",
    "aparece_em": "appears_in",
}

#: Active-voice Portuguese rendering per canonical relation. Every form is
#: gender-invariable on purpose (``fica em``, ``se inspira em``), so a phrase
#: about any entity is always grammatical.
RELATION_DISPLAY_PT: dict[str, str] = {
    "drives": "dirige",
    "wears": "veste",
    "owns": "possui",
    "belongs_to": "pertence a",
    "located_at": "fica em",
    "part_of": "é parte de",
    "features": "apresenta",
    "produces": "produz",
    "manages": "gerencia",
    "collaborates_with": "colabora com",
    "inspired_by": "se inspira em",
    "uses": "usa",
    "designed_by": "tem design de",
    "styled_by": "tem styling de",
    "filmed_at": "tem locação em",
    "appears_in": "aparece em",
}

#: Active-voice English rendering per canonical relation.
RELATION_DISPLAY_EN: dict[str, str] = {
    "drives": "drives",
    "wears": "wears",
    "owns": "owns",
    "belongs_to": "belongs to",
    "located_at": "is located at",
    "part_of": "is part of",
    "features": "features",
    "produces": "produces",
    "manages": "manages",
    "collaborates_with": "collaborates with",
    "inspired_by": "is inspired by",
    "uses": "uses",
    "designed_by": "is designed by",
    "styled_by": "is styled by",
    "filmed_at": "was filmed at",
    "appears_in": "appears in",
}

#: Traversal depths the API allows. Three hops bound the worst case while
#: still answering "who connects this campaign to that city?".
MIN_TRAVERSAL_DEPTH = 1
MAX_TRAVERSAL_DEPTH = 3

#: Phrase budget for one node: context enrichment must stay a summary.
MAX_PHRASES_PER_NODE = 25


def _token(value: str) -> str:
    """Normalise free text for vocabulary lookup (accents/space/case-free)."""

    folded = "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )
    runs = "".join(char if char.isalnum() else " " for char in folded.casefold()).split()
    return "_".join(runs)


def normalize_relation(value: str) -> str:
    """Return the canonical relation for canonical or alias input.

    Raises ``RelationshipError`` (a ``ValueError``, mapped to 422 at the API
    boundary) for anything outside the vocabulary — an unknown verb is a
    client error, never a silent free-text edge.
    """

    token = _token(value)
    if token in RELATIONS:
        return token
    canonical = RELATION_ALIASES.get(token)
    if canonical is None:
        raise RelationshipError(
            f"unknown relation: {value!r} (expected one of: {', '.join(RELATIONS)})"
        )
    return canonical


def inverse_of(relation: str) -> str:
    """Return the inverse label, accepting canonical or alias input."""

    return RELATION_INVERSES[normalize_relation(relation)]


def describe_edge(source_name: str, relation: str, target_name: str, lang: str = "pt") -> str:
    """Render one edge as a sentence (``Petrick dirige RAM``).

    The relation accepts aliases; ``lang`` is ``pt`` (default, the studio's
    working language) or ``en``. Anything else is a ``RelationshipError``.
    """

    canonical = normalize_relation(relation)
    displays = {"pt": RELATION_DISPLAY_PT, "en": RELATION_DISPLAY_EN}
    table = displays.get(lang.casefold())
    if table is None:
        raise RelationshipError(f"unknown phrase language: {lang!r} (expected 'pt' or 'en')")
    return f"{source_name} {table[canonical]} {target_name}"


@dataclass(frozen=True)
class GraphNodeView:
    """Detached, framework-free view of one node (engine in/out vocabulary)."""

    id: str
    workspace_id: str
    entity_type: str
    name: str
    slug: str
    attributes: dict = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "slug": self.slug,
            "attributes": dict(self.attributes),
            "aliases": list(self.aliases),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class GraphEdgeView:
    """Detached, framework-free view of one directed edge."""

    id: str
    workspace_id: str
    source_id: str
    target_id: str
    relation: str
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "created_at": self.created_at,
        }


class GraphStore(Protocol):
    """What the engine needs from any backing store (workspace-bound)."""

    def get_node(self, node_id: str) -> GraphNodeView | None:
        ...

    def out_edges(self, node_id: str) -> list[GraphEdgeView]:
        ...

    def in_edges(self, node_id: str) -> list[GraphEdgeView]:
        ...

    def list_nodes(self) -> list[GraphNodeView]:
        ...


@dataclass(frozen=True)
class Subgraph:
    """A traversal result: the centre plus its reachable neighbourhood."""

    center: GraphNodeView | None
    nodes: tuple[GraphNodeView, ...]
    edges: tuple[GraphEdgeView, ...]


def normalize_direction(direction: str) -> str:
    """Canonical traversal direction (``out``/``in``/``both``)."""

    token = direction.strip().casefold()
    aliases = {"out": "out", "outgoing": "out", "in": "in", "incoming": "in", "both": "both", "all": "both"}
    if token not in aliases:
        raise RelationshipError(
            f"unknown direction: {direction!r} (expected 'out', 'in' or 'both')"
        )
    return aliases[token]


class RelationshipEngine:
    """Breadth-first traversal and phrasing over a ``GraphStore``."""

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def neighbors(
        self, node_id: str, *, depth: int = 1, direction: str = "both"
    ) -> Subgraph:
        """Walk ``depth`` hops from ``node_id`` in ``direction``.

        Cycle-safe (visited set), deterministic (peers ordered by name, then
        relation) and total: an unknown node yields an empty subgraph with a
        ``None`` centre instead of raising, so the route decides the 404.
        """

        oriented = normalize_direction(direction)
        if not MIN_TRAVERSAL_DEPTH <= depth <= MAX_TRAVERSAL_DEPTH:
            raise RelationshipError(
                f"depth {depth} out of range "
                f"({MIN_TRAVERSAL_DEPTH}..{MAX_TRAVERSAL_DEPTH})"
            )
        center = self._store.get_node(node_id)
        if center is None:
            return Subgraph(center=None, nodes=(), edges=())
        seen: dict[str, GraphNodeView] = {center.id: center}
        edges: dict[str, GraphEdgeView] = {}
        frontier: list[str] = [center.id]
        for _ in range(depth):
            stepped: list[str] = []
            for current in frontier:
                for edge in self._incident(current, oriented):
                    peer_id = edge.target_id if edge.source_id == current else edge.source_id
                    peer = self._store.get_node(peer_id)
                    if peer is None:
                        # A store that drops a node without its edges: skip the
                        # dangling edge rather than failing the whole walk.
                        continue
                    edges.setdefault(edge.id, edge)
                    if peer.id not in seen:
                        seen[peer.id] = peer
                        stepped.append(peer.id)
            frontier = sorted(stepped)
            if not frontier:
                break
        ordered = sorted(seen.values(), key=lambda node: (node.name.casefold(), node.id))
        ordered_edges = sorted(
            edges.values(), key=lambda edge: (edge.relation, edge.source_id, edge.target_id)
        )
        return Subgraph(center=center, nodes=tuple(ordered), edges=tuple(ordered_edges))

    def phrases_for(self, node_id: str, *, lang: str = "pt") -> tuple[str, ...]:
        """Depth-1 context phrases for a node, active voice, sorted, capped."""

        subgraph = self.neighbors(node_id, depth=1, direction="both")
        if subgraph.center is None:
            return ()
        by_id = {node.id: node for node in subgraph.nodes}
        phrases = sorted(
            {
                describe_edge(
                    by_id[edge.source_id].name, edge.relation, by_id[edge.target_id].name, lang
                )
                for edge in subgraph.edges
                if edge.source_id in by_id and edge.target_id in by_id
            }
        )
        return tuple(phrases[:MAX_PHRASES_PER_NODE])

    def _incident(self, node_id: str, direction: str) -> list[GraphEdgeView]:
        outgoing = self._store.out_edges(node_id) if direction in ("out", "both") else []
        incoming = self._store.in_edges(node_id) if direction in ("in", "both") else []
        return list(outgoing) + list(incoming)


@dataclass(frozen=True)
class CharacterRelation:
    """One relation of a character, with the peer and its phrase."""

    relation: str
    direction: str  # "out" (character -> peer) or "in" (peer -> character)
    peer: GraphNodeView
    phrase: str


@dataclass(frozen=True)
class CharacterContext:
    """Everything the graph knows about one character (V3.1 CharacterGraph)."""

    node: GraphNodeView
    relations: tuple[CharacterRelation, ...]
    phrases: tuple[str, ...]
    relation_counts: dict[str, int]


class CharacterGraph:
    """Character-centred facade: identity plus wardrobe, vehicles, places."""

    def __init__(self, store: GraphStore, engine: RelationshipEngine | None = None) -> None:
        self._store = store
        self._engine = engine or RelationshipEngine(store)

    def find_character(self, name: str) -> GraphNodeView | None:
        """Find a ``character`` node by name, slug or alias (accent-free)."""

        needle = _token(name).replace("_", " ")
        if not needle:
            return None
        for node in sorted(self._store.list_nodes(), key=lambda item: item.name.casefold()):
            if node.entity_type != "character":
                continue
            candidates = [node.name, node.slug.replace("-", " "), *node.aliases]
            if any(_token(candidate).replace("_", " ") == needle for candidate in candidates):
                return node
        return None

    def context(self, name: str, *, lang: str = "pt") -> CharacterContext | None:
        """Full character context, or ``None`` when no character matches."""

        node = self.find_character(name)
        if node is None:
            return None
        subgraph = self._engine.neighbors(node.id, depth=1, direction="both")
        by_id = {item.id: item for item in subgraph.nodes}
        relations: list[CharacterRelation] = []
        for edge in subgraph.edges:
            peer_id = edge.target_id if edge.source_id == node.id else edge.source_id
            peer = by_id.get(peer_id)
            if peer is None:
                # Dangling edge in a degraded store: skip it, keep the rest.
                continue
            source = by_id[edge.source_id]
            target = by_id[edge.target_id]
            relations.append(
                CharacterRelation(
                    relation=edge.relation,
                    direction="out" if edge.source_id == node.id else "in",
                    peer=peer,
                    phrase=describe_edge(source.name, edge.relation, target.name, lang),
                )
            )
        relations.sort(key=lambda item: (item.peer.name.casefold(), item.relation))
        phrases = tuple(sorted({item.phrase for item in relations})[:MAX_PHRASES_PER_NODE])
        counts: dict[str, int] = {}
        for item in relations:
            counts[item.relation] = counts.get(item.relation, 0) + 1
        return CharacterContext(node=node, relations=tuple(relations), phrases=phrases, relation_counts=counts)
