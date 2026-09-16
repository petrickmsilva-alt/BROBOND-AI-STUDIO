"""V3.1 — GraphRepository: the persistence boundary of the knowledge graph.

Unit-level: the repository is bound to a private in-memory database through
the injectable session factory, so nothing here touches the shared bootstrap
database and test order is irrelevant.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import uuid4

import pytest

from app.db import Base
from app.graph import (
    GLOBAL_WORKSPACE_ID,
    GraphConflictError,
    GraphNotFoundError,
    GraphRepository,
    GraphValidationError,
    RelationshipEngine,
)


@pytest.fixture()
def repo() -> GraphRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return GraphRepository(factory)


@pytest.fixture()
def seeded_repo(repo: GraphRepository) -> GraphRepository:
    RelationshipEngine(repo).seed_canonical()
    return repo


def test_create_node_round_trips_all_fields(repo: GraphRepository) -> None:
    node = repo.create_node(
        "ws-1",
        "vehicle",
        "  Hilux  ",
        description="pickup of the test",
        attributes={"cor": "preta", "ano": "2024"},
        external_ref="EXT_1",
    )
    assert node.name == "Hilux", "the name is trimmed on write"
    fetched = repo.get_node(node.id)
    assert fetched is not None
    assert fetched.to_dict() == {
        "id": node.id,
        "workspace_id": "ws-1",
        "entity_type": "vehicle",
        "name": "Hilux",
        "description": "pickup of the test",
        "attributes": {"cor": "preta", "ano": "2024"},
        "external_ref": "EXT_1",
        "is_canonical": False,
        "created_at": fetched.created_at.isoformat(),
        "updated_at": fetched.updated_at.isoformat(),
    }


def test_create_node_refuses_an_unknown_entity_type(repo: GraphRepository) -> None:
    with pytest.raises(GraphValidationError, match="unknown entity_type"):
        repo.create_node("ws-1", "spaceship", "Starship")


def test_create_node_refuses_a_duplicate_address(repo: GraphRepository) -> None:
    repo.create_node("ws-1", "vehicle", "RAM")
    with pytest.raises(GraphConflictError, match="already exists"):
        repo.create_node("ws-1", "vehicle", "RAM")
    # the same name in another type is a different entity and is allowed
    other = repo.create_node("ws-1", "wardrobe", "RAM")
    assert other.entity_type == "wardrobe"


def test_the_same_name_is_unique_per_workspace(repo: GraphRepository) -> None:
    repo.create_node("ws-1", "vehicle", "RAM")
    assert repo.create_node("ws-2", "vehicle", "RAM").workspace_id == "ws-2"


def test_update_node_patches_only_the_given_fields(repo: GraphRepository) -> None:
    node = repo.create_node("ws-1", "prop", "Camera", attributes={"marca": "Canon"})
    updated = repo.update_node("ws-1", node.id, description="hero prop", external_ref="EXT_CAM")
    assert updated.description == "hero prop"
    assert updated.name == "Camera"
    assert updated.attributes == {"marca": "Canon"}
    assert updated.external_ref == "EXT_CAM"


def test_update_node_replaces_the_attribute_bag(repo: GraphRepository) -> None:
    node = repo.create_node("ws-1", "prop", "Camera", attributes={"marca": "Canon"})
    updated = repo.update_node("ws-1", node.id, attributes={"modelo": "5D"})
    assert updated.attributes == {"modelo": "5D"}


def test_update_node_reports_unknown_and_foreign_nodes_as_not_found(repo: GraphRepository) -> None:
    node = repo.create_node("ws-1", "prop", "Camera")
    with pytest.raises(GraphNotFoundError):
        repo.update_node("ws-1", "no-such-id")
    with pytest.raises(GraphNotFoundError):
        repo.update_node("ws-2", node.id)


def test_update_node_refuses_a_name_collision(repo: GraphRepository) -> None:
    repo.create_node("ws-1", "vehicle", "RAM")
    other = repo.create_node("ws-1", "vehicle", "Truck")
    with pytest.raises(GraphConflictError):
        repo.update_node("ws-1", other.id, name="RAM")


def test_canonical_nodes_are_read_only(repo: GraphRepository) -> None:
    RelationshipEngine(repo).seed_canonical()
    node = repo.find_character_by_external_ref("CHAR_PETRICK")
    assert node is not None
    with pytest.raises(GraphConflictError) as update_error:
        repo.update_node(GLOBAL_WORKSPACE_ID, node.id, description="hacked")
    assert update_error.value.code == "read-only"
    with pytest.raises(GraphConflictError) as delete_error:
        repo.delete_node(GLOBAL_WORKSPACE_ID, node.id)
    assert delete_error.value.code == "read-only"
    assert repo.get_node(node.id) is not None, "the canonical row survived both attempts"


def test_delete_node_removes_the_node_and_every_edge_touching_it(repo: GraphRepository) -> None:
    a = repo.create_node("ws-1", "character", "Anna")
    b = repo.create_node("ws-1", "vehicle", "Onix")
    repo.create_relationship("ws-1", a.id, b.id, "dirige")
    repo.create_relationship("ws-1", b.id, a.id, "é dirigido por")
    repo.delete_node("ws-1", a.id)
    assert repo.get_node(a.id) is None
    assert repo.relationships_for_node(b.id, "ws-1") == []


def test_delete_node_refuses_unknown_and_foreign_nodes(repo: GraphRepository) -> None:
    node = repo.create_node("ws-1", "prop", "Camera")
    with pytest.raises(GraphNotFoundError):
        repo.delete_node("ws-1", "no-such-id")
    with pytest.raises(GraphNotFoundError):
        repo.delete_node("ws-2", node.id)
    assert repo.get_node(node.id) is not None


def test_relationship_round_trips_and_refuses_duplicates(repo: GraphRepository) -> None:
    a = repo.create_node("ws-1", "character", "Anna")
    b = repo.create_node("ws-1", "vehicle", "Onix")
    row = repo.create_relationship("ws-1", a.id, b.id, "dirige", description="protagonista")
    fetched = repo.get_relationship(row.id)
    assert fetched is not None
    assert fetched.to_dict()["source_node_id"] == a.id
    assert fetched.description == "protagonista"
    assert fetched.to_dict()["is_canonical"] is False
    with pytest.raises(GraphConflictError, match="already exists"):
        repo.create_relationship("ws-1", a.id, b.id, "dirige")
    # the reverse edge is a different relationship and is allowed
    reverse = repo.create_relationship("ws-1", b.id, a.id, "dirige")
    assert reverse.id != row.id


def test_list_nodes_filters_by_type_and_text(repo: GraphRepository) -> None:
    repo.create_node("ws-1", "vehicle", "RAM", attributes={"cor": "branca"})
    repo.create_node("ws-1", "location", "Showroom", description="flagship")
    assert [n.name for n in repo.list_nodes(workspace_id="ws-1", entity_type="vehicle")] == ["RAM"]
    assert [n.name for n in repo.list_nodes(workspace_id="ws-1", q="flagship")] == ["Showroom"]
    assert [n.name for n in repo.list_nodes(workspace_id="ws-1", q="branca")] == ["RAM"]
    assert repo.list_nodes(workspace_id="ws-2") == []


def test_list_nodes_never_leaks_another_workspaces_rows(repo: GraphRepository) -> None:
    repo.create_node("ws-1", "vehicle", "Secret Car")
    assert all(n.workspace_id in (GLOBAL_WORKSPACE_ID, "ws-2") for n in repo.list_nodes(workspace_id="ws-2"))


def test_list_relationships_filters(repo: GraphRepository) -> None:
    a = repo.create_node("ws-1", "character", "Anna")
    b = repo.create_node("ws-1", "vehicle", "Onix")
    c = repo.create_node("ws-1", "location", "Garage")
    r1 = repo.create_relationship("ws-1", a.id, b.id, "dirige")
    r2 = repo.create_relationship("ws-1", b.id, c.id, "localizado")
    assert [r.id for r in repo.list_relationships("ws-1", relation_type="dirige")] == [r1.id]
    assert [r.id for r in repo.list_relationships("ws-1", source_node_id=b.id)] == [r2.id]
    assert [r.id for r in repo.list_relationships("ws-1", target_node_id=c.id)] == [r2.id]


def test_relationships_for_node_returns_both_directions_scoped(repo: GraphRepository) -> None:
    RelationshipEngine(repo).seed_canonical()
    petrick = repo.find_character_by_external_ref("CHAR_PETRICK")
    ram = repo.list_nodes(entity_type="vehicle", q="RAM")[0]
    petrick_edges = repo.relationships_for_node(petrick.id, "ws-1")
    assert {row.source_node_id for row in petrick_edges} == {petrick.id}
    assert len(petrick_edges) == 4, "Petrick's four canonical edges"
    assert all(row.workspace_id == GLOBAL_WORKSPACE_ID for row in petrick_edges)
    # the canonical RAM is shared: ws-1 sees only Petrick's edge on it, while
    # ws-9 — which added its own edge to the same canonical node — sees both.
    # Tenancy: ws-1 must never read ws-9's edges.
    other_ws = "ws-9"
    stranger = repo.create_node(other_ws, "character", "Stranger")
    repo.create_relationship(other_ws, stranger.id, ram.id, "dirige")
    ws1_view = repo.relationships_for_node(ram.id, "ws-1")
    assert [r.source_node_id for r in ws1_view] == [petrick.id]
    ws9_view = repo.relationships_for_node(ram.id, other_ws)
    assert {r.source_node_id for r in ws9_view} == {petrick.id, stranger.id}


def test_delete_relationship(repo: GraphRepository) -> None:
    a = repo.create_node("ws-1", "character", "Anna")
    b = repo.create_node("ws-1", "vehicle", "Onix")
    row = repo.create_relationship("ws-1", a.id, b.id, "dirige")
    repo.delete_relationship(row.id)
    assert repo.get_relationship(row.id) is None
    with pytest.raises(GraphNotFoundError):
        repo.delete_relationship("no-such-id")


def test_workspace_view_merges_canonical_and_own(repo: GraphRepository) -> None:
    RelationshipEngine(repo).seed_canonical()
    repo.create_node("ws-1", "vehicle", "Fusion", attributes={"cor": "vermelha"})
    nodes, relationships = repo.workspace_view("ws-1")
    names = {(n.entity_type, n.name) for n in nodes}
    assert ("vehicle", "Fusion") in names
    assert ("character", "Petrick Martins") in names
    assert ("vehicle", "RAM") in names
    # every relationship endpoint is visible in the view
    visible_ids = {n.id for n in nodes}
    assert all(r.source_node_id in visible_ids and r.target_node_id in visible_ids for r in relationships)


def test_workspace_view_gives_the_workspace_row_priority_on_ties(repo: GraphRepository) -> None:
    RelationshipEngine(repo).seed_canonical()
    specialization = repo.create_node("ws-1", "location", "Showroom", description="my showroom")
    nodes, _ = repo.workspace_view("ws-1")
    showrooms = [n for n in nodes if (n.entity_type, n.name) == ("location", "Showroom")]
    assert len(showrooms) == 1
    assert showrooms[0].id == specialization.id
    assert showrooms[0].workspace_id == "ws-1"


def test_seed_canonical_is_idempotent(repo: GraphRepository) -> None:
    engine = RelationshipEngine(repo)
    created_first = engine.seed_canonical()
    assert created_first > 0
    assert engine.seed_canonical() == 0, "a second boot creates nothing"
    assert len(repo.list_nodes()) == 9
    assert len(repo.list_relationships(GLOBAL_WORKSPACE_ID)) == 8


def test_canonical_catalog_covers_the_sprint_examples(seeded_repo: GraphRepository) -> None:
    """The four relationships the sprint names must exist, word for word."""

    edges = {(r.source_node_id, r.relation_type, r.target_node_id) for r in seeded_repo.list_relationships(GLOBAL_WORKSPACE_ID)}
    by_name = {n.name: n.id for n in seeded_repo.list_nodes()}
    assert (by_name["Petrick Martins"], "dirige", by_name["RAM"]) in edges
    assert (by_name["Petrick Martins"], "veste", by_name["Legacy Jacket"]) in edges
    assert (by_name["Legacy"], "pertence", by_name["BroBond"]) in edges
    assert (by_name["Showroom"], "localizado", by_name["Goiânia"]) in edges


def test_the_model_attribute_bag_survives_a_bad_payload(repo: GraphRepository) -> None:
    from app.graph.graph_models import GraphNode

    broken = GraphNode(workspace_id="ws-1", entity_type="prop", name="X")
    broken.attributes_json = "not-json"
    assert broken.attributes == {}
    broken.attributes = {"a": 1}
    assert broken.attributes == {"a": "1"}, "attributes are stored as strings"


def test_every_entity_type_of_v31_is_usable(repo: GraphRepository) -> None:
    for entity_type in ("character", "brand", "campaign", "location", "vehicle", "wardrobe", "prop"):
        node = repo.create_node(f"ws-{uuid4()}", entity_type, "Everything")
        assert node.entity_type == entity_type


def test_dangling_relationships_are_skipped_not_crashing(repo: GraphRepository) -> None:
    """A row left dangling by out-of-band maintenance must be skipped, not a 500."""

    a = repo.create_node("ws-1", "character", "Anna")
    b = repo.create_node("ws-1", "vehicle", "Onix")
    c = repo.create_node("ws-1", "location", "Garage")
    repo.create_relationship("ws-1", a.id, b.id, "dirige")
    repo.create_relationship("ws-1", c.id, b.id, "aparece_em")
    with repo.session() as db:
        from app.graph.graph_models import GraphNode

        db.delete(db.get(GraphNode, b.id))  # bypasses the cascade, on purpose
    engine = RelationshipEngine(repo)
    assert engine.neighbors("ws-1", a.id) == [], "the dangling edge is invisible"
    from app.graph import SemanticQuery

    results = SemanticQuery(repo).search("ws-1", "Garage")
    assert len(results) == 1 and results[0].node.name == "Garage"
    assert results[0].relationships == (), "the dangling edge does not ship with the match"
