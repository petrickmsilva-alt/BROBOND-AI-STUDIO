"""V3.1 — GraphRepository: workspace-scoped persistence over the real tables.

Every test owns a fresh ``ws-<uuid>`` workspace against the shared test
database (the same isolation the persona/job suites use): cross-workspace
reads behave as 404s, slugs collide only within a tenant, and the
demonstration seed is idempotent. Vocabulary normalisation is pinned here at
the persistence boundary; the HTTP mapping (409/422) lives in
`test_graph_api.py`.
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app.graph.graph_models import GraphValidationError
from app.graph.graph_repository import (
    GraphRepositoryError,
    character_graph_for,
    edge_view,
    graph_repo,
    node_view,
    relationship_engine_for,
    semantic_query_for,
)
from app.graph.relationship_engine import RELATIONS, RelationshipError


@pytest.fixture()
def ws() -> str:
    return f"ws-{uuid4().hex}"


def _node(workspace_id: str, name: str | None = None, entity_type: str = "character", **kwargs):
    return graph_repo.create_node(
        workspace_id,
        name=name if name is not None else f"Node {uuid4().hex[:8]}",
        entity_type=entity_type,
        **kwargs,
    )


# --------------------------------------------------------------------- nodes


def test_create_and_read_back(ws: str) -> None:
    row = graph_repo.create_node(
        ws,
        name="  Petrick  ",
        entity_type="Character",
        attributes={"role": "Founder"},
        aliases=["Petrick Martins"],
    )
    assert row.id and row.workspace_id == ws
    assert row.name == "Petrick"
    assert row.entity_type == "character"
    assert row.slug == "petrick"
    assert isinstance(row.created_at, datetime) and isinstance(row.updated_at, datetime)

    read = graph_repo.get_node(row.id, ws)
    assert read is not None
    assert (read.name, read.slug) == ("Petrick", row.slug)
    fetched = node_view(read)
    assert fetched.attributes == {"role": "Founder"}
    assert fetched.aliases == ("Petrick Martins",)


@pytest.mark.parametrize("name", ["", "   "])
def test_create_rejects_blank_names(ws: str, name: str) -> None:
    with pytest.raises(GraphValidationError):
        _node(ws, name=name)


def test_create_rejects_unknown_entity_types(ws: str) -> None:
    with pytest.raises(GraphValidationError):
        _node(ws, entity_type="starship")


def test_create_honours_explicit_slugs_and_falls_back_on_blank(ws: str) -> None:
    assert _node(ws, name="Alpha", slug="custom-slug").slug == "custom-slug"
    assert _node(ws, name="Beta", slug="   ").slug == "beta"


def test_slugs_collide_only_within_a_workspace(ws: str) -> None:
    _node(ws, name="Duplicado")
    with pytest.raises(GraphRepositoryError):
        _node(ws, name="Duplicado")
    other = f"ws-{uuid4().hex}"
    assert _node(other, name="Duplicado").slug == "duplicado"


def test_get_node_scoping(ws: str) -> None:
    row = _node(ws)
    assert graph_repo.get_node("missing", ws) is None
    assert graph_repo.get_node("", ws) is None
    assert graph_repo.get_node(row.id, f"ws-{uuid4().hex}") is None
    assert graph_repo.get_node(row.id) is not None


def test_find_by_slug(ws: str) -> None:
    row = _node(ws, name="Findable", slug="find-me")
    assert graph_repo.find_by_slug("find-me", ws) is not None
    assert graph_repo.find_by_slug("find-me", ws).id == row.id
    assert graph_repo.find_by_slug("absent", ws) is None
    assert graph_repo.find_by_slug("", ws) is None
    assert graph_repo.find_by_slug("find-me", f"ws-{uuid4().hex}") is None


def test_list_nodes_orders_by_name_then_id(ws: str) -> None:
    _node(ws, name="bravo")
    _node(ws, name="Alpha")
    _node(ws, name="charlie")
    assert [row.name for row in graph_repo.list_nodes(ws)] == ["Alpha", "bravo", "charlie"]


def test_list_nodes_filters_by_entity_type(ws: str) -> None:
    _node(ws, name="Pet")
    _node(ws, name="Car", entity_type="vehicle")
    rows = graph_repo.list_nodes(ws, entity_type="VEHICLE")
    assert [row.name for row in rows] == ["Car"]
    with pytest.raises(GraphValidationError):
        graph_repo.list_nodes(ws, entity_type="starship")


def test_list_nodes_paginates(ws: str) -> None:
    for name in ("a", "b", "c", "d", "e"):
        _node(ws, name=name)
    assert [row.name for row in graph_repo.list_nodes(ws, limit=2, offset=1)] == ["b", "c"]
    assert len(graph_repo.list_nodes(ws, limit=0)) == 1
    assert len(graph_repo.list_nodes(ws, limit=999)) == 5
    assert [row.name for row in graph_repo.list_nodes(ws, offset=-5, limit=1)] == ["a"]


def test_update_node_replaces_fields_wholesale(ws: str) -> None:
    row = _node(ws, name="Old", attributes={"keep": False}, aliases=["Oldie"])
    updated = graph_repo.update_node(
        row.id,
        ws,
        {"name": "  New  ", "entity_type": "Brand", "attributes": {"fresh": True}, "aliases": ["Newbie"]},
    )
    assert updated is not None
    assert (updated.name, updated.entity_type) == ("New", "brand")
    assert updated.slug == row.slug, "the slug is immutable"
    view = node_view(updated)
    assert view.attributes == {"fresh": True}
    assert view.aliases == ("Newbie",)


def test_update_node_ignores_unknown_keys(ws: str) -> None:
    row = _node(ws, name="Stable")
    updated = graph_repo.update_node(row.id, ws, {"bogus": 1})
    assert updated is not None and updated.name == "Stable"


def test_update_node_missing_or_foreign(ws: str) -> None:
    assert graph_repo.update_node("missing", ws, {"name": "x"}) is None
    row = _node(ws)
    assert graph_repo.update_node(row.id, f"ws-{uuid4().hex}", {"name": "x"}) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "   "},
        {"entity_type": "starship"},
        {"attributes": ["not", "an", "object"]},
        {"aliases": "not-a-list"},
        {"aliases": ["ok", 2]},
    ],
)
def test_update_node_validates(ws: str, changes: dict) -> None:
    row = _node(ws)
    with pytest.raises(GraphValidationError):
        graph_repo.update_node(row.id, ws, changes)


def test_delete_node_removes_incident_edges_both_ways(ws: str) -> None:
    source = _node(ws, name="Source")
    center = _node(ws, name="Center")
    target = _node(ws, name="Target")
    graph_repo.create_edge(ws, source_id=source.id, target_id=center.id, relation="uses")
    graph_repo.create_edge(ws, source_id=center.id, target_id=target.id, relation="owns")
    assert graph_repo.delete_node(center.id, ws) is True
    assert graph_repo.get_node(center.id, ws) is None
    assert graph_repo.list_edges(ws) == []
    assert graph_repo.get_node(source.id, ws) is not None
    assert graph_repo.get_node(target.id, ws) is not None


def test_delete_node_missing_or_foreign(ws: str) -> None:
    assert graph_repo.delete_node("missing", ws) is False
    row = _node(ws)
    assert graph_repo.delete_node(row.id, f"ws-{uuid4().hex}") is False
    assert graph_repo.get_node(row.id, ws) is not None


# --------------------------------------------------------------------- edges


def test_create_edge_normalises_the_relation(ws: str) -> None:
    source = _node(ws, name="Petrick")
    target = _node(ws, name="RAM", entity_type="vehicle")
    edge = graph_repo.create_edge(ws, source_id=source.id, target_id=target.id, relation="dirige")
    assert edge.relation == "drives"
    assert edge.workspace_id == ws


def test_create_edge_rejects_unknown_relations(ws: str) -> None:
    source = _node(ws)
    target = _node(ws)
    with pytest.raises(RelationshipError):
        graph_repo.create_edge(ws, source_id=source.id, target_id=target.id, relation="teleports")


def test_create_edge_rejects_self_loops(ws: str) -> None:
    row = _node(ws)
    with pytest.raises(GraphValidationError):
        graph_repo.create_edge(ws, source_id=row.id, target_id=row.id, relation="uses")


@pytest.mark.parametrize("endpoint", ["source_id", "target_id"])
def test_create_edge_requires_workspace_endpoints(ws: str, endpoint: str) -> None:
    row = _node(ws)
    foreign = _node(f"ws-{uuid4().hex}")
    kwargs = {"source_id": row.id, "target_id": row.id}
    kwargs[endpoint] = foreign.id
    with pytest.raises(GraphRepositoryError):
        graph_repo.create_edge(ws, relation="uses", **kwargs)
    kwargs[endpoint] = "missing"
    with pytest.raises(GraphRepositoryError):
        graph_repo.create_edge(ws, relation="uses", **kwargs)


def test_create_edge_rejects_duplicates(ws: str) -> None:
    source = _node(ws)
    target = _node(ws)
    graph_repo.create_edge(ws, source_id=source.id, target_id=target.id, relation="uses")
    with pytest.raises(GraphRepositoryError):
        graph_repo.create_edge(ws, source_id=source.id, target_id=target.id, relation="usa")


def test_list_edges_filters_and_orders(ws: str) -> None:
    first = _node(ws, name="First")
    second = _node(ws, name="Second")
    third = _node(ws, name="Third")
    one = graph_repo.create_edge(ws, source_id=first.id, target_id=second.id, relation="uses")
    two = graph_repo.create_edge(ws, source_id=second.id, target_id=third.id, relation="owns")
    assert [edge.id for edge in graph_repo.list_edges(ws)] == [one.id, two.id]
    assert [edge.id for edge in graph_repo.list_edges(ws, source_id=second.id)] == [two.id]
    assert [edge.id for edge in graph_repo.list_edges(ws, target_id=second.id)] == [one.id]
    assert [edge.id for edge in graph_repo.list_edges(ws, relation="usa")] == [one.id]
    assert len(graph_repo.list_edges(ws, limit=1)) == 1
    assert len(graph_repo.list_edges(ws, limit=0)) == 1
    with pytest.raises(RelationshipError):
        graph_repo.list_edges(ws, relation="teleports")


def test_delete_edge(ws: str) -> None:
    source = _node(ws)
    target = _node(ws)
    edge = graph_repo.create_edge(ws, source_id=source.id, target_id=target.id, relation="uses")
    assert graph_repo.delete_edge(edge.id, f"ws-{uuid4().hex}") is False
    assert graph_repo.delete_edge("missing", ws) is False
    assert graph_repo.delete_edge(edge.id, ws) is True
    assert graph_repo.delete_edge(edge.id, ws) is False
    assert graph_repo.get_node(source.id, ws) is not None
    assert graph_repo.get_node(target.id, ws) is not None


def test_directional_edge_reads(ws: str) -> None:
    source = _node(ws, name="Source")
    target = _node(ws, name="Target")
    edge = graph_repo.create_edge(ws, source_id=source.id, target_id=target.id, relation="uses")
    assert [row.id for row in graph_repo.out_edges(source.id, ws)] == [edge.id]
    assert graph_repo.out_edges(target.id, ws) == []
    assert [row.id for row in graph_repo.in_edges(target.id, ws)] == [edge.id]
    assert graph_repo.in_edges(source.id, ws) == []


# ---------------------------------------------------------------------- views


def test_views_carry_iso_timestamps(ws: str) -> None:
    row = _node(ws, name="Timed", attributes={"a": 1}, aliases=["T"])
    node = node_view(row)
    assert datetime.fromisoformat(node.created_at) <= datetime.fromisoformat(node.updated_at)
    assert isinstance(node.attributes, dict) and isinstance(node.aliases, tuple)
    edge = edge_view(
        graph_repo.create_edge(ws, source_id=row.id, target_id=_node(ws).id, relation="uses")
    )
    assert datetime.fromisoformat(edge.created_at)


# ----------------------------------------------------------------------- seed


def test_seed_demo_loads_the_brief_graph(ws: str) -> None:
    report = graph_repo.seed_demo(ws)
    assert report == {"created_nodes": 9, "created_edges": 11, "skipped_nodes": 0, "skipped_edges": 0}
    kinds = {row.entity_type for row in graph_repo.list_nodes(ws)}
    assert kinds == {"character", "brand", "campaign", "location", "vehicle", "wardrobe", "prop"}
    relations = {row.relation for row in graph_repo.list_edges(ws)}
    assert relations <= set(RELATIONS)
    assert {"drives", "wears", "belongs_to", "located_at"} <= relations


def test_seed_demo_is_idempotent(ws: str) -> None:
    graph_repo.seed_demo(ws)
    assert graph_repo.seed_demo(ws) == {
        "created_nodes": 0,
        "created_edges": 0,
        "skipped_nodes": 9,
        "skipped_edges": 11,
    }


def test_seed_demo_reuses_pre_existing_slugs(ws: str) -> None:
    _node(ws, name="Custom Petrick", slug="petrick")
    report = graph_repo.seed_demo(ws)
    assert (report["created_nodes"], report["skipped_nodes"]) == (8, 1)
    assert (report["created_edges"], report["skipped_edges"]) == (11, 0)


# --------------------------------------------------------------- constructors


def test_workspace_constructors_bind_the_engine_search_and_characters(ws: str) -> None:
    graph_repo.seed_demo(ws)
    petrick = graph_repo.find_by_slug("petrick", ws)
    assert petrick is not None
    subgraph = relationship_engine_for(ws).neighbors(petrick.id)
    assert subgraph.center is not None and len(subgraph.nodes) == 5
    matches = semantic_query_for(ws).query("RAM branca")
    assert matches and matches[0].node.name == "RAM"
    context = character_graph_for(ws).context("Petrick")
    assert context is not None and len(context.phrases) == 4
