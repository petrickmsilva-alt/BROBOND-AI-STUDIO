"""V3.1 — Relationship Engine: validation, bidirectional views, paths, seed.

Unit-level against a private in-memory database (the repository's injectable
session factory), so these tests never touch the shared bootstrap database.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from app.db import Base
from app.graph import (
    GLOBAL_WORKSPACE_ID,
    GraphConflictError,
    GraphNotFoundError,
    GraphRepository,
    GraphValidationError,
    RelationshipEngine,
    display_label,
    relationship_vocabulary,
    reverse_relation,
)


@pytest.fixture()
def repo() -> GraphRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return GraphRepository(sessionmaker(bind=engine, autoflush=False, autocommit=False))


@pytest.fixture()
def engine(repo: GraphRepository) -> RelationshipEngine:
    return RelationshipEngine(repo)


@pytest.fixture()
def cast(repo: GraphRepository) -> dict[str, str]:
    """petrick -> dirige -> ram, petrick -> veste -> jacket, jacket -> faz_parte_de -> legacy."""

    petrick = repo.create_node("ws-1", "character", "Petrick")
    ram = repo.create_node("ws-1", "vehicle", "RAM")
    jacket = repo.create_node("ws-1", "wardrobe", "Jacket")
    legacy = repo.create_node("ws-1", "campaign", "Legacy")
    return {"petrick": petrick.id, "ram": ram.id, "jacket": jacket.id, "legacy": legacy.id}


# --------------------------------------------------------------------- rules

def test_reverse_labels_come_from_the_vocabulary(engine: RelationshipEngine) -> None:
    assert reverse_relation("dirige") == "é dirigido por"
    assert reverse_relation("pertence") == "possui"
    assert reverse_relation("localizado") == "contém"
    assert reverse_relation("invented_type") == "relacionado a", "unknown types stay honest"
    assert display_label("pertence") == "pertence a"
    assert display_label("invented_type") == "relacionado a"


def test_the_vocabulary_is_exposed_for_the_ui(engine: RelationshipEngine) -> None:
    entries = relationship_vocabulary()
    types = {entry["type"] for entry in entries}
    assert {"dirige", "veste", "pertence", "localizado", "aparece_em", "usa", "faz_parte_de"} <= types
    for entry in entries:
        assert entry["display_label"]
        assert entry["reverse_relation"]


def test_connect_normalises_the_relation_type(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    row = engine.connect("ws-1", cast["petrick"], cast["ram"], "  Dirige  ")
    assert row.relation_type == "dirige"


def test_connect_refuses_an_empty_relation_type(engine: RelationshipEngine, cast: dict[str, str]) -> None:
    with pytest.raises(GraphValidationError, match="required"):
        engine.connect("ws-1", cast["petrick"], cast["ram"], "   ")


def test_connect_refuses_an_overlong_relation_type(engine: RelationshipEngine, cast: dict[str, str]) -> None:
    with pytest.raises(GraphValidationError, match="60 characters"):
        engine.connect("ws-1", cast["petrick"], cast["ram"], "x" * 61)


def test_connect_refuses_a_self_loop(engine: RelationshipEngine, cast: dict[str, str]) -> None:
    with pytest.raises(GraphValidationError, match="itself"):
        engine.connect("ws-1", cast["petrick"], cast["petrick"], "dirige")


def test_connect_refuses_unknown_and_foreign_endpoints(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    with pytest.raises(GraphNotFoundError):
        engine.connect("ws-1", "no-such-node", cast["ram"], "dirige")
    # every petrick/ram node belongs to ws-1: ws-2 may not connect them
    stranger = repo.create_node("ws-2", "character", "Stranger")
    with pytest.raises(GraphNotFoundError):
        engine.connect("ws-2", stranger.id, cast["petrick"], "dirige")


def test_connect_refuses_a_duplicate_edge(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    first = engine.connect("ws-1", cast["petrick"], cast["ram"], "dirige")
    with pytest.raises(GraphConflictError, match="already exists"):
        engine.connect("ws-1", cast["petrick"], cast["ram"], "dirige")
    assert repo.get_relationship(first.id) is not None


def test_a_workspace_may_relate_its_own_node_to_a_canonical_one(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    RelationshipEngine(repo).seed_canonical()
    ram = repo.find_character_by_external_ref("CHAR_PETRICK")  # canonical petrick
    row = engine.connect("ws-1", cast["petrick"], ram.id, "dirige")
    assert row.workspace_id == "ws-1"


def test_every_entity_type_is_relatable_to_every_other(repo: GraphRepository, engine: RelationshipEngine) -> None:
    """'Todas relacionáveis': no pair of types is refused."""

    types = ("character", "brand", "campaign", "location", "vehicle", "wardrobe", "prop")
    nodes = {
        entity_type: repo.create_node("ws-1", entity_type, f"Node {entity_type}").id
        for entity_type in types
    }
    for source_type in types:
        for target_type in types:
            if source_type == target_type:
                continue
            row = engine.connect("ws-1", nodes[source_type], nodes[target_type], f"rel_{source_type}_{target_type}")
            assert row.id
    assert len(repo.list_relationships("ws-1")) == 6 * 7


# -------------------------------------------------------------------- views

def test_neighbors_are_bidirectional_and_labelled_from_the_readers_side(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    engine.connect("ws-1", cast["petrick"], cast["ram"], "dirige")
    engine.connect("ws-1", cast["petrick"], cast["jacket"], "veste")
    engine.connect("ws-1", cast["petrick"], cast["legacy"], "aparece_em")
    engine.connect("ws-1", cast["jacket"], cast["legacy"], "faz_parte_de")

    petrick_views = engine.neighbors("ws-1", cast["petrick"])
    by_direction = {}
    for view in petrick_views:
        by_direction.setdefault(view.direction, []).append(view)
    outgoing = {v.other.name: v for v in by_direction["outgoing"]}
    assert set(outgoing) == {"RAM", "Jacket", "Legacy"}
    assert outgoing["RAM"].relationship.relation_type == "dirige"
    # reading the same edges from the other side flips the label
    ram_views = engine.neighbors("ws-1", cast["ram"])
    assert len(ram_views) == 1
    assert ram_views[0].direction == "incoming"
    assert ram_views[0].reverse_relation_type == "é dirigido por"
    assert ram_views[0].other.name == "Petrick"
    legacy_views = {v.other.name: v for v in engine.neighbors("ws-1", cast["legacy"])}
    assert legacy_views["Petrick"].direction == "incoming"
    assert legacy_views["Petrick"].reverse_relation_type == "apresenta"
    assert legacy_views["Jacket"].reverse_relation_type == "compõe"


def test_neighbors_direction_filter(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    engine.connect("ws-1", cast["petrick"], cast["ram"], "dirige")
    engine.connect("ws-1", cast["legacy"], cast["petrick"], "apresenta")
    outgoing = engine.neighbors("ws-1", cast["petrick"], direction="outgoing")
    incoming = engine.neighbors("ws-1", cast["petrick"], direction="incoming")
    assert {v.other.name for v in outgoing} == {"RAM"}
    assert {v.other.name for v in incoming} == {"Legacy"}


def test_neighbors_refuse_unknown_and_foreign_nodes(engine: RelationshipEngine, cast: dict[str, str]) -> None:
    with pytest.raises(GraphNotFoundError):
        engine.neighbors("ws-1", "no-such-node")
    with pytest.raises(GraphNotFoundError):
        engine.neighbors("ws-2", cast["petrick"])


def test_shortest_path_finds_the_route(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    engine.connect("ws-1", cast["petrick"], cast["ram"], "dirige")
    engine.connect("ws-1", cast["petrick"], cast["jacket"], "veste")
    engine.connect("ws-1", cast["jacket"], cast["legacy"], "faz_parte_de")
    path = engine.shortest_path("ws-1", cast["ram"], cast["legacy"])
    assert path == [cast["ram"], cast["petrick"], cast["jacket"], cast["legacy"]]
    assert engine.shortest_path("ws-1", cast["ram"], cast["ram"]) == [cast["ram"]]


def test_shortest_path_respects_the_depth_budget(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    """ram -> petrick -> jacket -> legacy is three hops; the budget must hold."""

    engine.connect("ws-1", cast["petrick"], cast["ram"], "dirige")
    engine.connect("ws-1", cast["petrick"], cast["jacket"], "veste")
    engine.connect("ws-1", cast["jacket"], cast["legacy"], "faz_parte_de")
    assert engine.shortest_path("ws-1", cast["ram"], cast["legacy"], max_depth=1) is None
    assert engine.shortest_path("ws-1", cast["ram"], cast["legacy"], max_depth=2) is None
    assert engine.shortest_path("ws-1", cast["ram"], cast["legacy"], max_depth=3) is not None


def test_shortest_path_never_crosses_tenants(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    engine.connect("ws-1", cast["petrick"], cast["ram"], "dirige")
    stranger = repo.create_node("ws-2", "character", "Stranger")
    repo.create_relationship("ws-2", stranger.id, cast["ram"], "dirige")
    assert engine.shortest_path("ws-1", cast["ram"], stranger.id) is None


def test_context_for_character_returns_the_footprint(engine: RelationshipEngine, repo: GraphRepository, cast: dict[str, str]) -> None:
    engine.connect("ws-1", cast["petrick"], cast["ram"], "dirige")
    footprint = engine.context_for_character(cast["petrick"])
    assert footprint is not None
    assert footprint["node"].id == cast["petrick"]
    assert [view.other.name for view in footprint["relationships"]] == ["RAM"]
    assert engine.context_for_character("no-such-node") is None


# --------------------------------------------------------------------- seed

def test_seed_creates_the_full_canonical_catalog(engine: RelationshipEngine, repo: GraphRepository) -> None:
    created = engine.seed_canonical()
    assert created == 9 + 8, "nine nodes and eight relationships"
    assert engine.seed_canonical() == 0
    petrick = repo.find_character_by_external_ref("CHAR_PETRICK")
    assert petrick is not None
    assert petrick.attributes["estilo"] == "cinematic realism"
    views = engine.neighbors(GLOBAL_WORKSPACE_ID, petrick.id)
    assert {v.other.name for v in views} == {"RAM", "Legacy Jacket", "Legacy", "Vintage Radio"}


def test_seed_leaves_existing_rows_untouched(engine: RelationshipEngine, repo: GraphRepository) -> None:
    engine.seed_canonical()
    petrick_id = repo.find_character_by_external_ref("CHAR_PETRICK").id
    engine.seed_canonical()
    again = repo.find_character_by_external_ref("CHAR_PETRICK")
    assert again.id == petrick_id, "idempotency: the same row, not a twin"


def test_seed_skips_a_relationship_pointing_at_a_missing_node(
    engine: RelationshipEngine, monkeypatch
) -> None:
    """A catalog row lost to out-of-band maintenance is skipped, not fatal."""

    from app.graph import relationship_engine

    assert engine.seed_canonical() == 17, "fresh catalog: nine nodes, eight edges"
    monkeypatch.setattr(
        relationship_engine,
        "CANONICAL_RELATIONSHIPS",
        (("Ghost", "Petrick Martins", "usa", ""),),
    )
    assert engine.seed_canonical() == 0, "the ghost edge is skipped; nothing is created"
