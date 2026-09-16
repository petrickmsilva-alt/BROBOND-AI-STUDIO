"""V3.1 — Relationship Engine: vocabulary, traversal, phrasing, CharacterGraph.

The engine is stdlib-only over the `GraphStore` protocol, so every test here
runs against an in-memory stub — no database, no FastAPI. The repository
adapter that binds the engine to a workspace is pinned in
`test_graph_repository.py`; the HTTP surface in `test_graph_api.py`.
"""
from __future__ import annotations

import pytest

from app.graph.relationship_engine import (
    MAX_PHRASES_PER_NODE,
    MAX_TRAVERSAL_DEPTH,
    MIN_TRAVERSAL_DEPTH,
    RELATION_ALIASES,
    RELATION_DISPLAY_EN,
    RELATION_DISPLAY_PT,
    RELATION_INVERSES,
    RELATIONS,
    CharacterGraph,
    GraphEdgeView,
    GraphNodeView,
    RelationshipEngine,
    RelationshipError,
    Subgraph,
    describe_edge,
    inverse_of,
    normalize_direction,
    normalize_relation,
)


def _node(
    node_id: str,
    name: str,
    entity_type: str = "character",
    aliases: tuple[str, ...] = (),
    slug: str | None = None,
) -> GraphNodeView:
    return GraphNodeView(
        id=node_id,
        workspace_id="ws-test",
        entity_type=entity_type,
        name=name,
        slug=slug or name.lower().replace(" ", "-"),
        attributes={},
        aliases=aliases,
    )


def _edge(edge_id: str, source_id: str, target_id: str, relation: str) -> GraphEdgeView:
    return GraphEdgeView(
        id=edge_id,
        workspace_id="ws-test",
        source_id=source_id,
        target_id=target_id,
        relation=relation,
    )


class _StubStore:
    """In-memory `GraphStore`: nodes by id, edges filtered per direction."""

    def __init__(self, nodes: list[GraphNodeView], edges: list[GraphEdgeView]) -> None:
        self._nodes = {node.id: node for node in nodes}
        self._edges = list(edges)

    def get_node(self, node_id: str) -> GraphNodeView | None:
        return self._nodes.get(node_id)

    def out_edges(self, node_id: str) -> list[GraphEdgeView]:
        return [edge for edge in self._edges if edge.source_id == node_id]

    def in_edges(self, node_id: str) -> list[GraphEdgeView]:
        return [edge for edge in self._edges if edge.target_id == node_id]

    def list_nodes(self) -> list[GraphNodeView]:
        return list(self._nodes.values())


def _cycle_store() -> _StubStore:
    nodes = [_node("a", "Alpha"), _node("b", "Beta"), _node("c", "Gamma")]
    edges = [
        _edge("e-ab", "a", "b", "drives"),
        _edge("e-bc", "b", "c", "owns"),
        _edge("e-ca", "c", "a", "uses"),
    ]
    return _StubStore(nodes, edges)


# ------------------------------------------------------------------ vocabulary


def test_the_sixteen_canonical_relations() -> None:
    assert len(RELATIONS) == 16
    assert set(RELATIONS) == {
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
    }


def test_every_relation_has_a_unique_inverse() -> None:
    assert set(RELATION_INVERSES) == set(RELATIONS)
    assert len(set(RELATION_INVERSES.values())) == len(RELATIONS)
    assert RELATION_INVERSES["collaborates_with"] == "collaborates_with"


def test_aliases_cover_the_brief_verbs_and_stay_canonical() -> None:
    assert RELATION_ALIASES["dirige"] == "drives"
    assert RELATION_ALIASES["veste"] == "wears"
    assert RELATION_ALIASES["pertence"] == "belongs_to"
    assert RELATION_ALIASES["localizado"] == "located_at"
    assert RELATION_ALIASES["localizada"] == "located_at"
    assert set(RELATION_ALIASES.values()) <= set(RELATIONS)


def test_display_tables_cover_every_relation() -> None:
    assert set(RELATION_DISPLAY_PT) == set(RELATIONS)
    assert set(RELATION_DISPLAY_EN) == set(RELATIONS)
    assert RELATION_DISPLAY_PT["drives"] == "dirige"
    assert RELATION_DISPLAY_EN["located_at"] == "is located at"


def test_traversal_bounds() -> None:
    assert (MIN_TRAVERSAL_DEPTH, MAX_TRAVERSAL_DEPTH) == (1, 3)
    assert MAX_PHRASES_PER_NODE == 25


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("drives", "drives"),
        ("Dirige", "drives"),
        ("  VESTE  ", "wears"),
        ("pertence a", "belongs_to"),
        ("Fica em", "located_at"),
        ("LOCALIZADA EM", "located_at"),
        ("colabora_com", "collaborates_with"),
    ],
)
def test_normalize_relation(raw: str, expected: str) -> None:
    assert normalize_relation(raw) == expected


@pytest.mark.parametrize("raw", ["teleports", "", "drive fast", "dirigir"])
def test_normalize_relation_rejects_unknown(raw: str) -> None:
    with pytest.raises(RelationshipError):
        normalize_relation(raw)


def test_relationship_errors_are_value_errors() -> None:
    assert issubclass(RelationshipError, ValueError)


def test_inverse_of_accepts_aliases() -> None:
    assert inverse_of("drives") == "driven_by"
    assert inverse_of("dirige") == "driven_by"
    assert inverse_of("localizado") == "hosts"
    with pytest.raises(RelationshipError):
        inverse_of("teleports")


@pytest.mark.parametrize(
    ("source", "relation", "target", "lang", "expected"),
    [
        ("Petrick", "dirige", "RAM", "pt", "Petrick dirige RAM"),
        ("Petrick", "drives", "RAM", "en", "Petrick drives RAM"),
        ("Showroom", "localizado", "Goiânia", "pt", "Showroom fica em Goiânia"),
        ("Showroom", "located_at", "Goiânia", "en", "Showroom is located at Goiânia"),
        ("Legacy", "pertence", "BroBond", "pt", "Legacy pertence a BroBond"),
    ],
)
def test_describe_edge(source: str, relation: str, target: str, lang: str, expected: str) -> None:
    assert describe_edge(source, relation, target, lang) == expected


def test_describe_edge_rejects_bad_language_and_relation() -> None:
    with pytest.raises(RelationshipError):
        describe_edge("Petrick", "drives", "RAM", "fr")
    with pytest.raises(RelationshipError):
        describe_edge("Petrick", "teleports", "RAM")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("out", "out"),
        ("outgoing", "out"),
        ("in", "in"),
        ("incoming", "in"),
        ("both", "both"),
        ("all", "both"),
        ("  BOTH ", "both"),
    ],
)
def test_normalize_direction(raw: str, expected: str) -> None:
    assert normalize_direction(raw) == expected


@pytest.mark.parametrize("raw", ["sideways", "", "up"])
def test_normalize_direction_rejects_unknown(raw: str) -> None:
    with pytest.raises(RelationshipError):
        normalize_direction(raw)


# ------------------------------------------------------------------ traversal


def test_neighbors_of_an_unknown_node_is_empty() -> None:
    subgraph = RelationshipEngine(_cycle_store()).neighbors("nope")
    assert subgraph.center is None
    assert subgraph.nodes == ()
    assert subgraph.edges == ()


@pytest.mark.parametrize("depth", [0, 4, 99])
def test_neighbors_rejects_depth_out_of_range(depth: int) -> None:
    with pytest.raises(RelationshipError):
        RelationshipEngine(_cycle_store()).neighbors("a", depth=depth)


def test_neighbors_depth_one_both_directions() -> None:
    subgraph = RelationshipEngine(_cycle_store()).neighbors("b", depth=1, direction="both")
    assert subgraph.center is not None and subgraph.center.id == "b"
    assert [node.name for node in subgraph.nodes] == ["Alpha", "Beta", "Gamma"]
    assert [edge.relation for edge in subgraph.edges] == ["drives", "owns"]


def test_neighbors_out_only() -> None:
    subgraph = RelationshipEngine(_cycle_store()).neighbors("b", depth=1, direction="out")
    assert {node.id for node in subgraph.nodes} == {"b", "c"}
    assert [edge.relation for edge in subgraph.edges] == ["owns"]


def test_neighbors_in_only() -> None:
    subgraph = RelationshipEngine(_cycle_store()).neighbors("b", depth=1, direction="in")
    assert {node.id for node in subgraph.nodes} == {"a", "b"}
    assert [edge.relation for edge in subgraph.edges] == ["drives"]


def test_neighbors_depth_two_crosses_hops() -> None:
    subgraph = RelationshipEngine(_cycle_store()).neighbors("a", depth=2, direction="out")
    assert {node.id for node in subgraph.nodes} == {"a", "b", "c"}
    # Out-only from Alpha reaches Beta then Gamma; the Gamma→Alpha edge
    # needs a third hop (or the `both` direction) to be walked.
    assert [edge.relation for edge in subgraph.edges] == ["drives", "owns"]


def test_neighbors_is_cycle_safe_at_max_depth() -> None:
    subgraph = RelationshipEngine(_cycle_store()).neighbors("a", depth=3, direction="both")
    assert {node.id for node in subgraph.nodes} == {"a", "b", "c"}
    assert len(subgraph.edges) == 3


def test_neighbors_skips_dangling_edges() -> None:
    store = _StubStore([_node("b", "Beta")], [_edge("e-ghost", "b", "ghost", "uses")])
    subgraph = RelationshipEngine(store).neighbors("b")
    assert [node.id for node in subgraph.nodes] == ["b"]
    assert subgraph.edges == ()


def test_neighbors_is_deterministic() -> None:
    engine = RelationshipEngine(_cycle_store())
    assert engine.neighbors("a", depth=2) == engine.neighbors("a", depth=2)


# ------------------------------------------------------------------- phrasing


def test_phrases_for_an_unknown_node_is_empty() -> None:
    assert RelationshipEngine(_cycle_store()).phrases_for("nope") == ()


def test_phrases_use_active_voice_from_the_true_source() -> None:
    store = _StubStore(
        [_node("p", "Petrick"), _node("r", "RAM", "vehicle"), _node("l", "Legacy", "brand")],
        [_edge("e1", "p", "r", "drives"), _edge("e2", "l", "p", "owns")],
    )
    phrases = RelationshipEngine(store).phrases_for("p")
    assert phrases == ("Legacy possui Petrick", "Petrick dirige RAM")


def test_phrases_support_english() -> None:
    store = _StubStore(
        [_node("p", "Petrick"), _node("r", "RAM", "vehicle")],
        [_edge("e1", "p", "r", "drives")],
    )
    assert RelationshipEngine(store).phrases_for("p", lang="en") == ("Petrick drives RAM",)


def test_phrases_are_capped_per_node() -> None:
    peers = [_node(f"peer-{index:02d}", f"Peer {index:02d}", "prop") for index in range(26)]
    edges = [_edge(f"edge-{index:02d}", "center", peer.id, "uses") for index, peer in enumerate(peers)]
    store = _StubStore([_node("center", "Center"), *peers], edges)
    phrases = RelationshipEngine(store).phrases_for("center")
    assert len(phrases) == MAX_PHRASES_PER_NODE
    assert phrases[0] == "Center usa Peer 00"
    assert "Center usa Peer 25" not in phrases


def test_view_serialisation() -> None:
    node = _node("n", "Petrick", aliases=("Petrick Martins",))
    assert node.to_dict() == {
        "id": "n",
        "workspace_id": "ws-test",
        "entity_type": "character",
        "name": "Petrick",
        "slug": "petrick",
        "attributes": {},
        "aliases": ["Petrick Martins"],
        "created_at": "",
        "updated_at": "",
    }
    edge = _edge("e", "n", "m", "drives")
    assert edge.to_dict() == {
        "id": "e",
        "workspace_id": "ws-test",
        "source_id": "n",
        "target_id": "m",
        "relation": "drives",
        "created_at": "",
    }


# ------------------------------------------------------------- CharacterGraph


def _character_store() -> _StubStore:
    nodes = [
        _node("petrick", "Petrick", aliases=("Petrick Martins",)),
        _node("jose", "José", slug="jose"),
        _node("jacket", "Legacy Jacket", "wardrobe", slug="legacy-jacket"),
        _node("showroom", "Showroom", "location"),
        _node("ram", "RAM", "vehicle"),
        _node("legacy", "Legacy", "brand"),
        _node("petrick-place", "Petrick", "location"),
    ]
    edges = [
        _edge("e1", "petrick", "ram", "drives"),
        _edge("e2", "legacy", "petrick", "owns"),
    ]
    return _StubStore(nodes, edges)


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("Petrick", "petrick"),
        ("petrick", "petrick"),
        ("Petrick Martins", "petrick"),
        ("jose", "jose"),
        ("José", "jose"),
    ],
)
def test_find_character_by_name_slug_or_alias(query: str, expected_id: str) -> None:
    found = CharacterGraph(_character_store()).find_character(query)
    assert found is not None and found.id == expected_id


@pytest.mark.parametrize("query", ["", "   ", "Showroom", "Legacy Jacket", "Nobody"])
def test_find_character_skips_non_characters_and_blanks(query: str) -> None:
    assert CharacterGraph(_character_store()).find_character(query) is None


def test_find_character_prefers_characters_over_places() -> None:
    found = CharacterGraph(_character_store()).find_character("Petrick")
    assert found is not None
    assert found.entity_type == "character"


def test_character_context() -> None:
    context = CharacterGraph(_character_store()).context("Petrick")
    assert context is not None
    assert context.node.id == "petrick"
    assert [(item.relation, item.direction, item.peer.name) for item in context.relations] == [
        ("owns", "in", "Legacy"),
        ("drives", "out", "RAM"),
    ]
    assert [item.phrase for item in context.relations] == [
        "Legacy possui Petrick",
        "Petrick dirige RAM",
    ]
    assert context.phrases == ("Legacy possui Petrick", "Petrick dirige RAM")
    assert context.relation_counts == {"owns": 1, "drives": 1}


def test_character_context_supports_english() -> None:
    context = CharacterGraph(_character_store()).context("Petrick", lang="en")
    assert context is not None
    assert context.phrases == ("Legacy owns Petrick", "Petrick drives RAM")


def test_character_context_of_an_unknown_name_is_none() -> None:
    assert CharacterGraph(_character_store()).context("Nobody") is None


def test_character_context_skips_dangling_peers() -> None:
    node = _node("petrick", "Petrick")

    class _DanglingEngine:
        def neighbors(self, node_id: str, *, depth: int = 1, direction: str = "both") -> Subgraph:
            assert (node_id, depth, direction) == ("petrick", 1, "both")
            return Subgraph(
                center=node,
                nodes=(node,),
                edges=(_edge("e-ghost", "petrick", "ghost", "uses"),),
            )

    context = CharacterGraph(_StubStore([node], []), _DanglingEngine()).context("Petrick")  # type: ignore[arg-type]
    assert context is not None
    assert context.relations == ()
    assert context.phrases == ()
    assert context.relation_counts == {}
