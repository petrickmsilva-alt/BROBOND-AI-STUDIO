"""V3.1 — Cinematic Knowledge Graph (application layer).

Persists and reasons about the studio's cinematic knowledge — Character,
Brand, Campaign, Location, Vehicle, Wardrobe and Prop, every type relatable —
so that memory becomes relational knowledge. The Core's `MemoryResolver`
reaches this package only through the `KnowledgeContextSource` protocol
wired in `app.main`; nothing here imports the Core, FastAPI or any provider.
"""

from .graph_models import (
    ENTITY_TYPES,
    GLOBAL_WORKSPACE_ID,
    GraphNode,
    GraphRelationship,
)
from .graph_repository import (
    GraphConflictError,
    GraphNotFoundError,
    GraphRepository,
    GraphRepositoryError,
    GraphValidationError,
    graph_repo,
)
from .relationship_engine import (
    CANONICAL_NODES,
    CANONICAL_RELATIONSHIPS,
    RELATION_VOCABULARY,
    RelationshipEngine,
    ResolvedRelationship,
    display_label,
    relationship_vocabulary,
    reverse_relation,
)
from .semantic_query import SemanticMatch, SemanticQuery, normalize, query_tokens

__all__ = [
    "CANONICAL_NODES",
    "CANONICAL_RELATIONSHIPS",
    "ENTITY_TYPES",
    "GLOBAL_WORKSPACE_ID",
    "GraphConflictError",
    "GraphNode",
    "GraphNotFoundError",
    "GraphRelationship",
    "GraphRepository",
    "GraphRepositoryError",
    "GraphValidationError",
    "RELATION_VOCABULARY",
    "RelationshipEngine",
    "ResolvedRelationship",
    "SemanticMatch",
    "SemanticQuery",
    "display_label",
    "graph_repo",
    "normalize",
    "query_tokens",
    "relationship_vocabulary",
    "reverse_relation",
]
