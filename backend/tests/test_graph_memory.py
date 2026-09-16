"""V3.1 ETAPA 5 — MemoryResolver graph enrichment without touching identity.

`context_phrases` is the only new seam: a resolver composed with a
`GraphContextSource` serves relation phrases for a persona, while every
pre-V3.1 construction (no source) resolves exactly as before. These tests pin
both halves — the enrichment paths and the untouched identity paths — plus
the `GraphContext` contract vocabulary and the workspace-bound adapter the
character-context route composes per request.
"""
from __future__ import annotations

from uuid import uuid4

from app.core.contracts import GraphContext, GraphContextSource, PersonaMemory
from app.core.memory_resolver import MemoryResolver
from app.graph.graph_repository import graph_repo
from app.main import _GraphContextSource


class _MapPersonaSource:
    def __init__(self, personas: list[PersonaMemory]) -> None:
        self._by_id = {persona.persona_id: persona for persona in personas}

    def register(self, persona: PersonaMemory) -> PersonaMemory:
        self._by_id[persona.persona_id] = persona
        return persona

    def fetch(self, persona_id: str) -> PersonaMemory | None:
        return self._by_id.get(persona_id)

    def search(self, query: str = "") -> list[PersonaMemory]:
        if not query:
            return list(self._by_id.values())
        needle = query.strip().casefold()
        return [persona for persona in self._by_id.values() if needle in persona.name.casefold()]


class _MapContextSource:
    def __init__(self, contexts: dict[str, GraphContext]) -> None:
        self._contexts = dict(contexts)

    def get_context(self, subject: str) -> GraphContext | None:
        return self._contexts.get(subject)


def _resolver(contexts: dict[str, GraphContext] | None = None) -> MemoryResolver:
    personas = [PersonaMemory(persona_id="P1", name="Petrick"), PersonaMemory(persona_id="P2", name="Ghost")]
    source = _MapPersonaSource(personas)
    if contexts is None:
        return MemoryResolver(source=source)
    return MemoryResolver(source=source, context_source=_MapContextSource(contexts))


def test_context_phrases_serve_graph_enrichment() -> None:
    resolver = _resolver({"Petrick": GraphContext(subject="Petrick", phrases=("Petrick dirige RAM",), relation_count=1)})
    assert resolver.context_phrases("P1") == ("Petrick dirige RAM",)


def test_context_phrases_without_a_source_is_empty() -> None:
    assert _resolver().context_phrases("P1") == ()


def test_context_phrases_without_a_persona_is_empty() -> None:
    resolver = _resolver({"Petrick": GraphContext(subject="Petrick", phrases=("Petrick dirige RAM",))})
    assert resolver.context_phrases("unknown-id") == ()
    assert resolver.context_phrases(None) == ()
    assert resolver.context_phrases("") == ()


def test_context_phrases_without_graph_coverage_is_empty() -> None:
    resolver = _resolver({"Petrick": GraphContext(subject="Petrick", phrases=("Petrick dirige RAM",))})
    assert resolver.context_phrases("P2") == ()


def test_identity_resolution_ignores_the_context_source() -> None:
    plain = _resolver()
    enriched = _resolver({"Petrick": GraphContext(subject="Petrick", phrases=("Petrick dirige RAM",))})
    assert enriched.resolve("P1") == plain.resolve("P1")
    assert enriched.resolve_by_name("Petrick") == plain.resolve_by_name("Petrick")
    assert enriched.resolve_persona("P1") == plain.resolve_persona("P1")


def test_a_default_resolver_carries_no_enrichment() -> None:
    assert MemoryResolver().context_phrases("CHAR_PETRICK") == ()


def test_graph_context_vocabulary() -> None:
    context = GraphContext(subject="Petrick", phrases=("Petrick dirige RAM",), relation_count=1)
    assert context.to_dict() == {
        "subject": "Petrick",
        "phrases": ["Petrick dirige RAM"],
        "relation_count": 1,
    }
    assert context.is_empty is False
    assert GraphContext(subject="Nobody").is_empty is True
    assert GraphContext(subject="Nobody").to_dict()["phrases"] == []


def test_graph_context_source_is_runtime_checkable() -> None:
    assert isinstance(_MapContextSource({}), GraphContextSource)


def test_the_route_adapter_reads_one_workspace() -> None:
    workspace_id = f"ws-{uuid4().hex}"
    graph_repo.seed_demo(workspace_id)
    source = _GraphContextSource(workspace_id)
    context = source.get_context("Petrick")
    assert context is not None
    assert context.subject == "Petrick"
    assert len(context.phrases) == 4
    assert context.relation_count == 4
    assert "Petrick dirige RAM" in context.phrases
    assert source.get_context("Nobody") is None
