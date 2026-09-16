"""V3.1 — Cinematic Knowledge Graph.

Memory becomes relational knowledge: seven entity types (Character, Brand,
Campaign, Location, Vehicle, Wardrobe, Prop) in one node table, one directed
edge table over a closed relation vocabulary, deterministic semantic search,
and a character-centred facade (``CharacterGraph``) that the MemoryResolver
consumes as context — without touching ``GenerationSpec``.

Layering (same rule as ``repositories/``): ``relationship_engine.py`` and
``semantic_query.py`` are framework-free and reason over store protocols;
``graph_repository.py`` is the only module that touches SQLAlchemy.
"""
from .graph_models import (
    ENTITY_TYPES,
    GraphEdge,
    GraphNode,
    GraphValidationError,
    normalize_entity_type,
)
from .graph_repository import (
    GraphRepository,
    GraphRepositoryError,
    RepositoryGraphStore,
    character_graph_for,
    edge_view,
    graph_repo,
    node_view,
    relationship_engine_for,
    semantic_query_for,
)
from .relationship_engine import (
    RELATION_ALIASES,
    RELATION_DISPLAY_EN,
    RELATION_DISPLAY_PT,
    RELATION_INVERSES,
    RELATIONS,
    CharacterContext,
    CharacterGraph,
    CharacterRelation,
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
from .semantic_query import (
    QueryMatch,
    SemanticQuery,
    normalize_text,
    tokenize,
)

__all__ = [
    "ENTITY_TYPES",
    "RELATION_ALIASES",
    "RELATION_DISPLAY_EN",
    "RELATION_DISPLAY_PT",
    "RELATION_INVERSES",
    "RELATIONS",
    "CharacterContext",
    "CharacterGraph",
    "CharacterRelation",
    "GraphEdge",
    "GraphEdgeView",
    "GraphNode",
    "GraphNodeView",
    "GraphRepository",
    "GraphRepositoryError",
    "GraphValidationError",
    "QueryMatch",
    "RelationshipEngine",
    "RelationshipError",
    "RepositoryGraphStore",
    "SemanticQuery",
    "Subgraph",
    "character_graph_for",
    "describe_edge",
    "edge_view",
    "graph_repo",
    "inverse_of",
    "node_view",
    "normalize_direction",
    "normalize_entity_type",
    "normalize_relation",
    "normalize_text",
    "relationship_engine_for",
    "semantic_query_for",
    "tokenize",
]
