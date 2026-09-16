"""V3.1 — Semantic Query: a human phrase in, complete entities out.

The two examples the sprint names are pinned here:

    "RAM branca" -> the complete Vehicle (attributes + relationships)
    "Showroom"   -> the Location

Run against a private in-memory database seeded with the canonical catalog.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from app.db import Base
from app.graph import GraphRepository, RelationshipEngine, SemanticQuery, normalize, query_tokens


@pytest.fixture()
def repo() -> GraphRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    repo = GraphRepository(sessionmaker(bind=engine, autoflush=False, autocommit=False))
    RelationshipEngine(repo).seed_canonical()
    return repo


@pytest.fixture()
def query(repo: GraphRepository) -> SemanticQuery:
    return SemanticQuery(repo)


# ----------------------------------------------------------------- normalise

def test_normalize_strips_case_and_accents() -> None:
    assert normalize("Goiânia") == "goiania"
    assert normalize("  RAM   BRANCA ") == "ram branca"
    assert normalize(None) == ""


def test_query_tokens_drop_stopwords_and_duplicates() -> None:
    assert query_tokens("a RAM branca de Goiânia") == ["ram", "branca", "goiania"]
    assert query_tokens("   ") == []
    assert query_tokens("ram ram ram") == ["ram"]
    assert len(query_tokens(" ".join(f"w{i}" for i in range(20)))) == 8, "long phrases are capped"


# ------------------------------------------------------------- the examples

def test_ram_branca_returns_the_complete_vehicle(query: SemanticQuery) -> None:
    results = query.search("ws-1", "RAM branca", limit=3)
    assert len(results) == 1, f"only the vehicle should match: {[r.node.name for r in results]}"
    top = results[0]
    assert top.node.entity_type == "vehicle"
    assert top.node.name == "RAM"
    assert top.node.attributes == {"modelo": "RAM 1500", "cor": "branca"}
    assert "attributes" in top.matched_fields
    # "complete": every relationship around the vehicle comes along
    others = {v.other.name for v in top.relationships}
    assert others == {"Petrick Martins"}
    petrick_edge = top.relationships[0]
    assert petrick_edge.direction == "incoming"
    assert petrick_edge.reverse_relation_type == "é dirigido por"


def test_showroom_returns_the_location(query: SemanticQuery) -> None:
    results = query.search("ws-1", "Showroom", limit=3)
    assert results, "an exact name must match"
    top = results[0]
    assert top.node.entity_type == "location"
    assert top.node.name == "Showroom"
    assert "name" in top.matched_fields
    assert {v.other.name for v in top.relationships} == {"Goiânia", "Legacy"}


def test_goiania_matches_with_or_without_the_accent(query: SemanticQuery) -> None:
    with_accent = query.search("ws-1", "Goiânia")
    without_accent = query.search("ws-1", "goiania")
    assert with_accent and with_accent[0].node.name == "Goiânia"
    assert without_accent and without_accent[0].node.name == "Goiânia"
    assert with_accent[0].score == without_accent[0].score, "accent insensitivity is deterministic"


def test_the_full_entity_name_wins_over_attribute_noise(query: SemanticQuery) -> None:
    results = query.search("ws-1", "Legacy")
    # the campaign "Legacy" is a full-name hit; the jacket only mentions it
    assert results[0].node.name == "Legacy"
    assert results[0].node.entity_type == "campaign"


def test_an_unknown_phrase_returns_nothing_instead_of_a_guess(query: SemanticQuery) -> None:
    assert query.search("ws-1", "xyzzy frobnicator") == []
    assert query.search("ws-1", "   ") == []
    assert query.search("ws-1", "a o de e") == [], "glue words alone are not a query"


def test_the_entity_type_filter_restricts_the_search(repo: GraphRepository, query: SemanticQuery) -> None:
    repo.create_node("ws-1", "vehicle", "RAM 2500", attributes={"cor": "branca"})
    all_results = query.search("ws-1", "RAM branca", limit=5)
    vehicle_only = query.search("ws-1", "RAM branca", entity_type="vehicle", limit=5)
    assert all(node.node.entity_type == "vehicle" for node in vehicle_only)
    assert vehicle_only[0].score >= all_results[0].score
    assert len(all_results) >= 1


def test_workspace_nodes_participate_in_the_search(repo: GraphRepository, query: SemanticQuery) -> None:
    repo.create_node("ws-1", "vehicle", "Chevrolet S10", attributes={"cor": "branca"})
    results = query.search("ws-1", "S10 branca", limit=5)
    assert results[0].node.name == "Chevrolet S10"
    assert "attributes" in results[0].matched_fields


def test_the_search_never_sees_another_workspaces_nodes(repo: GraphRepository, query: SemanticQuery) -> None:
    repo.create_node("ws-2", "vehicle", "Fluxoinductor X9", attributes={"cor": "branca"})
    assert query.search("ws-1", "Fluxoinductor") == []
    assert [m.node.name for m in query.search("ws-2", "Fluxoinductor")] == ["Fluxoinductor X9"]


def test_a_name_prefix_scores_below_an_exact_name(query: SemanticQuery) -> None:
    results = query.search("ws-1", "Goia", limit=5)
    assert results and results[0].node.name == "Goiânia"
    exact = query.search("ws-1", "Goiânia", limit=1)
    assert exact[0].score > results[0].score


def test_a_phrase_inside_a_name_scores_below_the_prefix(query: SemanticQuery) -> None:
    results = query.search("ws-1", "iani", limit=5)
    assert results and results[0].node.name == "Goiânia"
    prefix = query.search("ws-1", "Goia", limit=1)
    assert prefix[0].score > results[0].score


def test_an_attribute_key_is_a_match_too(query: SemanticQuery) -> None:
    results = query.search("ws-1", "modelo", limit=5)
    assert results, "the RAM's 'modelo' attribute key must be searchable"
    ram = next(m for m in results if m.node.name == "RAM")
    assert "attributes" in ram.matched_fields


def test_scores_are_ranked_best_first(query: SemanticQuery) -> None:
    results = query.search("ws-1", "branca", limit=10)
    scores = [match.score for match in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0].node.name == "RAM", "the white RAM is the defining 'branca' in the catalog"


def test_matches_carry_their_complete_relationships_in_both_directions(repo: GraphRepository, query: SemanticQuery) -> None:
    petrick_id = repo.find_character_by_external_ref("CHAR_PETRICK").id
    results = query.search("ws-1", "Petrick Martins", limit=1)
    assert len(results) == 1
    directions = {view.direction for view in results[0].relationships}
    assert directions == {"outgoing"}, "Petrick's canonical edges are all outgoing"
    assert len(results[0].relationships) == 4
    # and the reverse reading of one edge, from the other end
    ram_results = query.search("ws-1", "RAM 1500", limit=1)
    assert ram_results
    assert ram_results[0].relationships[0].direction == "incoming"
    assert ram_results[0].relationships[0].reverse_relation_type == "é dirigido por"
    assert ram_results[0].relationships[0].other.id == petrick_id
