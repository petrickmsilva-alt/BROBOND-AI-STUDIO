"""V3.1 — Semantic Query: deterministic, dependency-free graph search.

``SemanticQuery`` answers "RAM branca" with the Vehicle node and "Showroom"
with the Location node — no embedding model, no LLM, no network. Matching is
accent- and case-insensitive token scoring over names, aliases and attribute
keys/values, with explicit tiers so a ranking is explainable
(``matched_fields`` says which fields contributed).

Tiers (first match wins, highest score first):

* 100 — query equals the node name (``Showroom``);
* 95 — query equals one alias;
* 80 — the name starts with the query;
* 75 — one alias starts with the query;
* 70 — every query token appears in the name;
* 55 — every query token appears across name/aliases/attributes
  (``RAM branca``: ``ram`` in the name, ``branca`` in ``attributes.color``);
* 40 — one query token is a substring of the name;
* 30 — one query token is found in aliases or attributes.

An explicit ``entity_type`` filter adds a +5 bonus (capped at 100) instead of
just filtering, so ``query("ram", entity_type="vehicle")`` ranks the Vehicle
above a same-named Character. Ties break by name, then id: the order is
stable across processes and restarts.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Protocol

from .relationship_engine import GraphNodeView


SCORE_EXACT_NAME = 100
SCORE_EXACT_ALIAS = 95
SCORE_NAME_PREFIX = 80
SCORE_ALIAS_PREFIX = 75
SCORE_TOKENS_IN_NAME = 70
SCORE_TOKENS_IN_PROFILE = 55
SCORE_TOKEN_SUBSTRING_NAME = 40
SCORE_TOKEN_IN_ALIAS_ATTRS = 30
SCORE_ENTITY_BONUS = 5
MAX_SCORE = 100
MAX_QUERY_LIMIT = 50


def normalize_text(value: str) -> str:
    """Casefolded, accent-free text for comparison (``Goiânia`` -> ``goiania``)."""

    folded = "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )
    return folded.casefold()


def tokenize(value: str) -> tuple[str, ...]:
    """Split normalised text into ``[a-z0-9]`` token runs."""

    return tuple("".join(char if char.isalnum() else " " for char in normalize_text(value)).split())


@dataclass(frozen=True)
class QueryMatch:
    """One ranked hit: the node, its score and the fields that matched."""

    node: GraphNodeView
    score: int
    matched_fields: tuple[str, ...]


class NodeSearchStore(Protocol):
    """What semantic search needs from any backing store (workspace-bound)."""

    def list_nodes(self) -> list[GraphNodeView]:
        ...


class SemanticQuery:
    """Ranked search over a workspace's nodes (see module docstring)."""

    def __init__(self, store: NodeSearchStore) -> None:
        self._store = store

    def query(
        self, text: str, *, entity_type: str | None = None, limit: int = 10
    ) -> tuple[QueryMatch, ...]:
        """Search nodes, best match first. A blank query matches nothing."""

        needle = normalize_text(text).strip()
        tokens = tokenize(text)
        if not needle or not tokens:
            return ()
        wanted = entity_type.strip().casefold() if entity_type else None
        bounded = max(1, min(limit, MAX_QUERY_LIMIT))
        matches: list[QueryMatch] = []
        for node in self._store.list_nodes():
            if wanted is not None and node.entity_type.casefold() != wanted:
                continue
            scored = _score(node, needle, tokens)
            if scored is None:
                continue
            score, fields = scored
            if wanted is not None:
                score = min(MAX_SCORE, score + SCORE_ENTITY_BONUS)
            matches.append(QueryMatch(node=node, score=score, matched_fields=fields))
        matches.sort(key=lambda item: (-item.score, item.node.name.casefold(), item.node.id))
        return tuple(matches[:bounded])


def _profile(node: GraphNodeView) -> tuple[str, tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Normalised (name, aliases, attribute token runs) for one node."""

    return (
        normalize_text(node.name),
        tuple(normalize_text(alias) for alias in node.aliases),
        {normalize_text(str(key)): tokenize(str(value)) for key, value in node.attributes.items()},
    )


def _score(
    node: GraphNodeView, needle: str, tokens: tuple[str, ...]
) -> tuple[int, tuple[str, ...]] | None:
    name, aliases, attributes = _profile(node)
    if needle == name:
        return SCORE_EXACT_NAME, ("name",)
    if needle in aliases:
        return SCORE_EXACT_ALIAS, ("alias",)
    if name.startswith(needle):
        return SCORE_NAME_PREFIX, ("name",)
    if any(alias.startswith(needle) for alias in aliases):
        return SCORE_ALIAS_PREFIX, ("alias",)
    wanted = set(tokens)
    name_tokens = set(tokenize(node.name))
    if wanted <= name_tokens:
        return SCORE_TOKENS_IN_NAME, ("name",)
    pool: dict[str, set[str]] = {"name": name_tokens}
    for alias in node.aliases:
        pool.setdefault("alias", set()).update(tokenize(alias))
    for key, words in attributes.items():
        pool.setdefault(f"attributes.{key}", set()).update(words)
        pool[f"attributes.{key}"].update(key.split())
    if wanted <= set().union(*pool.values()):
        holding = sorted(field for field, words in pool.items() if wanted & words)
        return SCORE_TOKENS_IN_PROFILE, tuple(holding)
    if any(token in name for token in wanted):
        return SCORE_TOKEN_SUBSTRING_NAME, ("name",)
    if any(token in alias for token in wanted for alias in aliases):
        return SCORE_TOKEN_IN_ALIAS_ATTRS, ("alias",)
    for key in sorted(attributes):
        if any(token in word for token in wanted for word in attributes[key]):
            return SCORE_TOKEN_IN_ALIAS_ATTRS, (f"attributes.{key}",)
    return None
