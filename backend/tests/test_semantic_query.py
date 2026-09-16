"""V3.1 — Semantic Query: deterministic tiered search over the graph.

Pins every scoring tier (100/95/80/75/70/55/40/30), the +5 entity bonus, the
limit bounds and the stable tie-breaks against an in-memory node list — the
same data shape the workspace-bound store serves. Accent- and case-folding is
covered through Goiânia/Jaqueta queries, not mocked away.
"""
from __future__ import annotations

import pytest

from app.graph.relationship_engine import GraphNodeView
from app.graph.semantic_query import (
    MAX_QUERY_LIMIT,
    SCORE_ALIAS_PREFIX,
    SCORE_ENTITY_BONUS,
    SCORE_EXACT_ALIAS,
    SCORE_EXACT_NAME,
    SCORE_NAME_PREFIX,
    SCORE_TOKENS_IN_NAME,
    SCORE_TOKENS_IN_PROFILE,
    SCORE_TOKEN_IN_ALIAS_ATTRS,
    SCORE_TOKEN_SUBSTRING_NAME,
    QueryMatch,
    SemanticQuery,
    normalize_text,
    tokenize,
)


def _node(
    node_id: str,
    name: str,
    entity_type: str,
    aliases: tuple[str, ...] = (),
    attributes: dict | None = None,
) -> GraphNodeView:
    return GraphNodeView(
        id=node_id,
        workspace_id="ws-test",
        entity_type=entity_type,
        name=name,
        slug=name.lower().replace(" ", "-"),
        attributes=dict(attributes or {}),
        aliases=aliases,
    )


def _corpus() -> list[GraphNodeView]:
    return [
        _node(
            "ram",
            "RAM",
            "vehicle",
            ("RAM 3500",),
            {"color": "branca", "model": "3500 Laramie", "kind": "pickup"},
        ),
        _node("showroom", "Showroom", "location", (), {"city": "Goiania", "kind": "showroom"}),
        _node("goiania", "Goiânia", "location", (), {"state": "GO", "kind": "city"}),
        _node("petrick", "Petrick", "character", ("Petrick Martins",)),
        _node(
            "jacket",
            "Legacy Jacket",
            "wardrobe",
            ("Jaqueta Legacy",),
            {"category": "jacket", "color": "preta"},
        ),
        _node("legacy", "Legacy", "brand", ("Legacy Collection",), {"segment": "moda masculina"}),
        _node("brobond", "BroBond", "brand", (), {"segment": "estudio cinematografico"}),
        _node("camera", "Vintage Camera", "prop", (), {"kind": "camera", "era": "analogica"}),
    ]


class _ListStore:
    def __init__(self, nodes: list[GraphNodeView]) -> None:
        self._nodes = nodes

    def list_nodes(self) -> list[GraphNodeView]:
        return list(self._nodes)


@pytest.fixture()
def search() -> SemanticQuery:
    return SemanticQuery(_ListStore(_corpus()))


def test_tier_constants() -> None:
    assert (
        SCORE_EXACT_NAME,
        SCORE_EXACT_ALIAS,
        SCORE_NAME_PREFIX,
        SCORE_ALIAS_PREFIX,
        SCORE_TOKENS_IN_NAME,
        SCORE_TOKENS_IN_PROFILE,
        SCORE_TOKEN_SUBSTRING_NAME,
        SCORE_TOKEN_IN_ALIAS_ATTRS,
    ) == (100, 95, 80, 75, 70, 55, 40, 30)
    assert SCORE_ENTITY_BONUS == 5
    assert MAX_QUERY_LIMIT == 50


def test_normalize_text_folds_accents_and_case() -> None:
    assert normalize_text("Goiânia") == "goiania"
    assert normalize_text("  RAM 3500 ") == "  ram 3500 "


def test_tokenize_splits_on_non_alphanumerics() -> None:
    assert tokenize("RAM branca!") == ("ram", "branca")
    assert tokenize("3500 Laramie") == ("3500", "laramie")
    assert tokenize("!!!") == ()


def test_exact_name_scores_100(search: SemanticQuery) -> None:
    (match,) = search.query("Showroom")
    assert match.node.id == "showroom"
    assert match.score == 100
    assert match.matched_fields == ("name",)


def test_exact_alias_scores_95(search: SemanticQuery) -> None:
    (match,) = search.query("RAM 3500")
    assert match.node.id == "ram"
    assert match.score == 95
    assert match.matched_fields == ("alias",)


def test_name_prefix_scores_80(search: SemanticQuery) -> None:
    matches = search.query("ra")
    assert matches[0].node.id == "ram"
    assert matches[0].score == 80


def test_alias_prefix_scores_75(search: SemanticQuery) -> None:
    matches = search.query("jaqueta l")
    assert matches[0].node.id == "jacket"
    assert matches[0].score == 75


def test_reordered_name_tokens_score_70(search: SemanticQuery) -> None:
    matches = search.query("jacket legacy")
    assert matches[0].node.id == "jacket"
    assert matches[0].score == 70
    assert matches[0].matched_fields == ("name",)


def test_tokens_across_profile_score_55_with_fields(search: SemanticQuery) -> None:
    matches = search.query("RAM branca")
    assert matches[0].node.id == "ram"
    assert matches[0].score == 55
    assert matches[0].matched_fields == ("alias", "attributes.color", "name")
    assert [match.score for match in matches] == sorted(
        (match.score for match in matches), reverse=True
    )


def test_name_substring_scores_40(search: SemanticQuery) -> None:
    (match,) = search.query("etr")
    assert match.node.id == "petrick"
    assert match.score == 40


def test_partial_alias_token_scores_30(search: SemanticQuery) -> None:
    (match,) = search.query("350")
    assert match.node.id == "ram"
    assert match.score == 30
    assert match.matched_fields == ("alias",)


def test_partial_attribute_token_scores_30_with_key(search: SemanticQuery) -> None:
    (match,) = search.query("branc")
    assert match.node.id == "ram"
    assert match.score == 30
    assert match.matched_fields == ("attributes.color",)


def test_queries_are_accent_insensitive(search: SemanticQuery) -> None:
    matches = search.query("goiania")
    assert [(match.node.id, match.score) for match in matches] == [
        ("goiania", 100),  # exact name, accent-folded
        ("showroom", 55),  # the city attribute holds the same token
    ]
    matches = search.query("JAQUETA LEGACY")
    assert [(match.node.id, match.score) for match in matches] == [
        ("jacket", 95),  # exact alias, case-folded
        ("legacy", 40),  # the shared `legacy` token, substring tier
    ]


@pytest.mark.parametrize("text", ["", "   ", "!!!", "zzzqqq"])
def test_blank_punctuation_and_unknown_queries_match_nothing(
    search: SemanticQuery, text: str
) -> None:
    assert search.query(text) == ()


def test_entity_filter_restricts_and_adds_a_bonus(search: SemanticQuery) -> None:
    (match,) = search.query("legacy jacket", entity_type="brand")
    assert match.node.id == "legacy"
    assert match.score == 45  # substring 40 + bonus 5


def test_entity_bonus_is_capped_at_100(search: SemanticQuery) -> None:
    (match,) = search.query("Showroom", entity_type="location")
    assert match.score == 100


def test_entity_filter_is_case_insensitive(search: SemanticQuery) -> None:
    (match,) = search.query("ram branca", entity_type="VEHICLE")
    assert match.node.id == "ram"


def test_unknown_entity_filter_matches_nothing(search: SemanticQuery) -> None:
    assert search.query("ram", entity_type="starship") == ()


def test_limit_bounds() -> None:
    many = [_node(f"n-{index:02d}", f"Node {index:02d}", "prop") for index in range(60)]
    search = SemanticQuery(_ListStore(many))
    assert len(search.query("node", limit=999)) == MAX_QUERY_LIMIT
    assert len(search.query("node", limit=0)) == 1
    assert len(search.query("node", limit=3)) == 3


def test_ties_break_by_name_then_id() -> None:
    twins = [
        _node("twin-b", "Twin", "prop"),
        _node("twin-a", "Twin", "prop"),
    ]
    matches = SemanticQuery(_ListStore(twins)).query("twin")
    assert [(match.node.id, match.score) for match in matches] == [("twin-a", 100), ("twin-b", 100)]


def test_ranking_is_deterministic(search: SemanticQuery) -> None:
    first = search.query("legacy")
    second = search.query("legacy")
    assert [(match.node.id, match.score) for match in first] == [
        (match.node.id, match.score) for match in second
    ]


def test_match_shape() -> None:
    node = _node("ram", "RAM", "vehicle")
    match = QueryMatch(node=node, score=100, matched_fields=("name",))
    assert match.node is node
    assert match.score == 100
    assert match.matched_fields == ("name",)
