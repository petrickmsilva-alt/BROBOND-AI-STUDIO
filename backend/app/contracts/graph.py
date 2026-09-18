"""Knowledge Graph contracts — what the graph knows about a subject.

Vocabulary only: a subject, the relation phrases that describe it and how
many relations produced them. `GenerationSpec` is untouched by this — the
phrases are enrichment for a caller that asks, never an implicit rewrite.

PR010.0 froze this vocabulary. It was moved here verbatim from
`app/core/contracts.py`, which now re-exports it: the objects are the *same*
objects, so `app.core.contracts.GraphContext is app.contracts.GraphContext`. A module
that needs this vocabulary imports it; it never restates it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

@dataclass(frozen=True)
class GraphContext:
    """V3.1: what the Knowledge Graph knows about one subject.

    Vocabulary only: the subject's display name, the relation phrases that
    describe it (``Petrick dirige RAM``) and how many relations produced
    them. ``GenerationSpec`` is untouched by this contract — the phrases are
    enrichment for callers that ask, never an implicit prompt rewrite.
    """

    subject: str
    phrases: tuple[str, ...] = ()
    relation_count: int = 0

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "phrases": list(self.phrases),
            "relation_count": self.relation_count,
        }

    @property
    def is_empty(self) -> bool:
        return not self.phrases

@runtime_checkable
class GraphContextSource(Protocol):
    """Where graph context is read from (V3.1).

    Kept separate from ``PersonaSource``/``PersonaProfileSource`` on purpose:
    those are the identity contracts (frozen), this one is the relational
    view. ``MemoryResolver`` takes it as an optional third injection, so
    every existing construction keeps working unchanged. The Core still never
    touches SQL: the API layer plugs the graph-backed source in.
    """

    def get_context(self, subject: str) -> GraphContext | None:
        ...
