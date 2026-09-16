"""V3.1 — Cinematic Knowledge Graph: Semantic Query.

Turns a human phrase into complete entities:

    "RAM branca"  ->  the full Vehicle (attributes + relationships)
    "Showroom"    ->  the Location

Deterministic by design — the same rule the Director Agent follows: no model
is loaded and none is faked; a transparent scoring function ranks the
workspace's visible nodes, and the top matches come back *complete* (entity
plus every relationship around it), not as name fragments.

Scoring (higher wins; ties break on entity type, then name, so results are
stable across runs):

* full query equals the name                     +100
* name starts with the full query                +55
* full query appears inside the name             +40
* full query appears inside the attribute bag    +25
* each query token in the name                   +12
* each query token in an attribute value         +15
* each query token in an attribute key           +6
* each query token in the description            +8

Tokens are normalised (casefold + accents stripped); a small stopword list
drops glue words ("a", "de", "o"...) that would otherwise match everything.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .graph_models import GraphNode
from .relationship_engine import ResolvedRelationship
from .graph_repository import GraphRepository

#: Glue words that carry no entity information in pt-BR/en.
_STOPWORDS = frozenset({"a", "o", "um", "uma", "e", "ou", "de", "do", "da", "dos", "das", "em", "no", "na", "para", "por", "com", "the", "of", "and"})

_TOKEN_CAP = 8  # a phrase longer than this is scanned by its first eight tokens


def normalize(text: str) -> str:
    """Casefold + strip accents, so "Goiânia" matches "goiania"."""

    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.casefold().split())


def query_tokens(query: str) -> list[str]:
    """The meaningful tokens of a phrase, in order, de-duplicated."""

    tokens: list[str] = []
    for token in normalize(query).split():
        if token in _STOPWORDS or token in tokens:
            continue
        tokens.append(token)
    return tokens[:_TOKEN_CAP]


@dataclass(frozen=True)
class SemanticMatch:
    """One ranked hit: the complete node, its score and what matched."""

    node: GraphNode
    score: int
    matched_fields: tuple[str, ...]
    relationships: tuple[ResolvedRelationship, ...]


def _score_node(node: GraphNode, query: str, tokens: list[str]) -> tuple[int, set[str]]:
    name = normalize(node.name)
    full_query = normalize(query)
    score = 0
    matched: set[str] = set()

    if full_query:
        if name == full_query:
            score += 100
            matched.add("name")
        elif name.startswith(full_query):
            score += 55
            matched.add("name")
        elif full_query in name:
            score += 40
            matched.add("name")

    attribute_text = " ".join(normalize(value) for value in node.attributes.values())
    key_text = " ".join(normalize(key) for key in node.attributes.keys())
    description = normalize(node.description)

    if full_query and full_query in attribute_text:
        score += 25
        matched.add("attributes")

    for token in tokens:
        if token in name:
            score += 12
            matched.add("name")
        if token in attribute_text:
            score += 15
            matched.add("attributes")
        elif token in key_text:
            score += 6
            matched.add("attributes")
        if token in description:
            score += 8
            matched.add("description")

    return score, matched


class SemanticQuery:
    """Ranks a workspace's visible nodes against a human phrase."""

    def __init__(self, repository: GraphRepository) -> None:
        self._repo = repository

    def search(
        self,
        workspace_id: str,
        query: str,
        entity_type: str | None = None,
        limit: int = 5,
    ) -> list[SemanticMatch]:
        """Complete entities for the phrase, best first. Empty when nothing
        scores — an unknown phrase must read as "no match", not a guess."""

        tokens = query_tokens(query)
        full_query = normalize(query)
        if not tokens and not full_query:
            return []
        scored: list[tuple[int, str, str, GraphNode, set[str]]] = []
        for node in self._repo.list_nodes(workspace_id=workspace_id, entity_type=entity_type):
            score, matched = _score_node(node, query, tokens)
            if score <= 0:
                continue
            scored.append((score, node.entity_type, node.name, node, matched))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [
            SemanticMatch(
                node=node,
                score=score,
                matched_fields=tuple(sorted(matched)),
                relationships=tuple(_neighbors_for(self._repo, node.id, workspace_id)),
            )
            for score, _entity_type, _name, node, matched in scored[: max(1, limit)]
        ]


def _neighbors_for(repo: GraphRepository, node_id: str, workspace_id: str) -> list[ResolvedRelationship]:
    """Bidirectional relationships of a match — the "complete entity" part.

    Scoped to the workspace (canonical edges included): a canonical node is
    shared, but its adjacency must never leak another workspace's edges.
    """

    resolved: list[ResolvedRelationship] = []
    for row in repo.relationships_for_node(node_id, workspace_id):
        source = repo.get_node(row.source_node_id)
        target = repo.get_node(row.target_node_id)
        if source is None or target is None:
            continue
        direction = "outgoing" if row.source_node_id == node_id else "incoming"
        resolved.append(ResolvedRelationship(row, source, target, direction))
    return resolved
