"""V3.1 — Cinematic Knowledge Graph: model helpers and vocabulary.

Pins the domain vocabulary shared by the repository, the engine and the
routes: the seven entity types, slug generation, JSON (de)serialisation and
the naive-UTC timestamps. Framework-free assertions only — persistence
behaviour lives in `test_graph_repository.py`.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.graph.graph_models import (
    ENTITY_TYPES,
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


def test_the_seven_entity_types() -> None:
    assert set(ENTITY_TYPES) == {
        "character",
        "brand",
        "campaign",
        "location",
        "vehicle",
        "wardrobe",
        "prop",
    }
    assert len(ENTITY_TYPES) == 7
    assert all(token == token.lower() for token in ENTITY_TYPES)


def test_validation_errors_are_value_errors() -> None:
    assert issubclass(GraphValidationError, ValueError)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("character", "character"),
        ("Character", "character"),
        ("  VEHICLE ", "vehicle"),
        ("Wardrobe", "wardrobe"),
    ],
)
def test_normalize_entity_type(raw: str, expected: str) -> None:
    assert normalize_entity_type(raw) == expected


@pytest.mark.parametrize("raw", ["starship", "", "  ", "characters", "car"])
def test_normalize_entity_type_rejects_unknown(raw: str) -> None:
    with pytest.raises(GraphValidationError):
        normalize_entity_type(raw)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Petrick Martins", "petrick-martins"),
        ("  RAM 3500!! ", "ram-3500"),
        ("Legacy Jacket", "legacy-jacket"),
        ("Goiânia", "goi-nia"),
        ("", "node"),
        ("!!!", "node"),
    ],
)
def test_slugify(name: str, expected: str) -> None:
    assert slugify(name) == expected


def test_slugify_truncates_and_is_deterministic() -> None:
    assert len(slugify("x" * 200)) == 180
    assert slugify("Showroom Goiânia") == slugify("Showroom Goiânia")


def test_attributes_round_trip() -> None:
    payload = {"color": "branca", "nested": {"year": 2026}, "tags": ["a", "b"]}
    assert loads_attributes(dumps_attributes(payload)) == payload


def test_dumps_attributes_rejects_non_objects() -> None:
    with pytest.raises(GraphValidationError):
        dumps_attributes(["not", "an", "object"])  # type: ignore[arg-type]


def test_dumps_attributes_rejects_non_serialisable_values() -> None:
    with pytest.raises(GraphValidationError):
        dumps_attributes({"handler": object()})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, {}),
        ("", {}),
        ("{not json", {}),
        ("[1, 2]", {}),
        ('"just a string"', {}),
        ("42", {}),
        ('{"color": "branca"}', {"color": "branca"}),
    ],
)
def test_loads_attributes_is_defensive(raw: str | None, expected: dict) -> None:
    assert loads_attributes(raw) == expected


def test_aliases_round_trip_and_clean_whitespace() -> None:
    assert loads_aliases(dumps_aliases([" Petrick Martins ", "", "  ", "RAM"])) == [
        "Petrick Martins",
        "RAM",
    ]


@pytest.mark.parametrize("raw", ["nope", {"a": 1}, ["ok", 2], [None]])
def test_dumps_aliases_rejects_non_string_lists(raw: object) -> None:
    with pytest.raises(GraphValidationError):
        dumps_aliases(raw)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ("", []),
        ("[broken", []),
        ('{"a": 1}', []),
        ('"lone"', []),
        ('["a", 1, null, "b"]', ["a", "b"]),
    ],
)
def test_loads_aliases_is_defensive(raw: str | None, expected: list) -> None:
    assert loads_aliases(raw) == expected


def test_utcnow_is_naive_utc() -> None:
    stamp = utcnow()
    assert isinstance(stamp, datetime)
    assert stamp.tzinfo is None


def test_table_and_column_names() -> None:
    assert GraphNode.__tablename__ == "graph_nodes"
    assert GraphEdge.__tablename__ == "graph_edges"
    node_columns = set(GraphNode.__table__.c.keys())
    assert {"attributes", "aliases"} <= node_columns
    assert "attributes_json" not in node_columns
    edge_columns = set(GraphEdge.__table__.c.keys())
    assert {"source_id", "target_id", "relation"} <= edge_columns
