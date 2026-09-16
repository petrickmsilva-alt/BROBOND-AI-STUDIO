"""V3.1 — ETAPA 5: the Memory Resolver gains the graph as context.

Three floors, from pure Core to HTTP:

1. the Core floor — `MemoryResolver.knowledge_context` with and without an
   injected `KnowledgeContextSource`; without one it is exactly what it was
   before V3.1 (None, no behaviour change at all);
2. the contract floor — a `GenerationSpec` compiled with a wired graph is
   identical to one compiled without it: the enrichment is context, and the
   spec's 19 fields do not move;
3. the HTTP floor — `/api/v1/core/personas/{persona_id}/knowledge-context`
   exposes what the resolver holds.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.contracts import KnowledgeContext, KnowledgeEntity, KnowledgeRelation
from app.core.memory_resolver import MemoryResolver
from app.core.prompt_compiler import PromptCompiler
from app.core.style_resolver import StyleResolver
from app.main import app, memory_resolver, spec_builder

client = TestClient(app)

_REGISTER = client.post(
    "/api/v1/auth/register",
    json={
        "email": f"graph-memory-{uuid4()}@example.com",
        "name": "Graph Memory",
        "password": "strong-pass-123",
    },
)
assert _REGISTER.status_code == 201, _REGISTER.text
HEADERS = {"Authorization": f"Bearer {_REGISTER.json()['access_token']}"}


# ----------------------------------------------------------------- the Core

class _StubKnowledgeSource:
    def __init__(self, context: KnowledgeContext | None) -> None:
        self._context = context
        self.calls: list[str] = []

    def context_for(self, persona_id: str) -> KnowledgeContext | None:
        self.calls.append(persona_id)
        return self._context


def _stub_context() -> KnowledgeContext:
    return KnowledgeContext(
        persona_id="CHAR_PETRICK",
        character=KnowledgeEntity(entity_type="character", name="Petrick Martins", attributes=(("idade", "50"),)),
        relationships=(
            KnowledgeRelation(
                direction="outgoing",
                relation_type="dirige",
                reverse_relation_type="é dirigido por",
                other=KnowledgeEntity(entity_type="vehicle", name="RAM", attributes=(("cor", "branca"),)),
            ),
        ),
        entity_count=1,
        phrase="Petrick Martins dirige RAM.",
    )


def test_a_resolver_without_a_knowledge_source_is_unchanged() -> None:
    resolver = MemoryResolver()
    assert resolver.knowledge_context("CHAR_PETRICK") is None
    assert resolver.knowledge_context(None) is None
    assert resolver.knowledge_context("") is None


def test_a_wired_resolver_returns_the_graph_context() -> None:
    stub = _StubKnowledgeSource(_stub_context())
    resolver = MemoryResolver(knowledge=stub)
    context = resolver.knowledge_context("CHAR_PETRICK")
    assert context is not None
    assert context.phrase == "Petrick Martins dirige RAM."
    assert context.entity_count == 1
    assert context.relationships[0].other.name == "RAM"
    assert stub.calls == ["CHAR_PETRICK"]


def test_knowledge_context_never_leaks_into_the_generation_spec() -> None:
    """The sprint rule: 'Sem alterar GenerationSpec. Apenas enriquecer contexto.'

    Both specs are compiled with fresh, identically-seeded resolvers so the
    only difference in the experiment is the injected knowledge source (the
    app-level builder is deliberately avoided: other test files mutate the
    shared persona ledger it reads, which is not the variable under test).
    """

    from app.core.generation_spec_builder import GenerationSpecBuilder

    kwargs = dict(prompt="Petrick with the white RAM", persona_id="CHAR_PETRICK", provider="mock")
    with_graph = GenerationSpecBuilder(
        memory=MemoryResolver(knowledge=_StubKnowledgeSource(_stub_context())),
        styles=StyleResolver(),
        compiler=PromptCompiler(),
    ).build_traced(**kwargs).spec
    without_graph = GenerationSpecBuilder(
        memory=MemoryResolver(),
        styles=StyleResolver(),
        compiler=PromptCompiler(),
    ).build_traced(**kwargs).spec
    a, b = with_graph.to_dict(), without_graph.to_dict()
    assert a["spec_id"] != b["spec_id"], "spec_id is unique per build by design"
    a.pop("spec_id")
    b.pop("spec_id")
    assert a == b, "the spec must be byte-identical whether or not the graph is wired"
    assert "knowledge" not in a and "graph_context" not in a


def test_identity_phrase_is_not_enriched_by_the_graph() -> None:
    """The PERSONA block keeps its exact shape; the context lives beside it."""

    resolver = MemoryResolver(knowledge=_StubKnowledgeSource(_stub_context()))
    persona = resolver.resolve("CHAR_PETRICK")
    assert "RAM" not in resolver.identity_phrase(persona)
    assert resolver.identity_phrase(persona).startswith("Petrick Martins")


# ------------------------------------------------------------------ the HTTP

def test_the_context_route_requires_identity() -> None:
    assert client.get("/api/v1/core/personas/CHAR_PETRICK/knowledge-context").status_code == 401


def test_petrick_has_a_complete_context_over_http() -> None:
    body = client.get("/api/v1/core/personas/CHAR_PETRICK/knowledge-context", headers=HEADERS)
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["persona_id"] == "CHAR_PETRICK"
    assert payload["character"]["entity_type"] == "character"
    assert payload["character"]["name"] == "Petrick Martins"
    assert payload["entity_count"] == 4
    assert "dirige RAM" in payload["phrase"]
    relation_types = {relation["relation_type"] for relation in payload["relationships"]}
    assert relation_types == {"dirige", "veste", "aparece_em", "usa"}
    for relation in payload["relationships"]:
        assert relation["direction"] == "outgoing"
        assert relation["other"]["name"]
        assert relation["display_label"]
    ram = next(r for r in payload["relationships"] if r["relation_type"] == "dirige")
    assert ram["other"]["attributes"]["cor"] == "branca"


def test_a_planned_character_resolves_with_an_empty_context() -> None:
    body = client.get("/api/v1/core/personas/CHAR_JEFFERSON/knowledge-context", headers=HEADERS)
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["character"]["name"] == "Jefferson"
    assert payload["relationships"] == []
    assert payload["entity_count"] == 0
    assert "no relationships" in payload["phrase"]


def test_an_unknown_persona_is_404() -> None:
    assert client.get("/api/v1/core/personas/CHAR_NOBODY/knowledge-context", headers=HEADERS).status_code == 404


def test_the_resolver_itself_is_wired_in_the_application() -> None:
    """The composition root really injected the graph source (not just a fake)."""

    context = memory_resolver.knowledge_context("CHAR_PETRICK")
    assert context is not None
    assert context.character is not None
    assert context.character.name == "Petrick Martins"
    assert context.entity_count >= 4


def test_the_bridge_degrades_to_none_for_personas_outside_the_catalog(monkeypatch) -> None:
    """A persona the catalog does not know must read as 'no context', not a 500."""

    from app import main

    monkeypatch.setattr(main.graph_repo, "find_character_by_external_ref", lambda persona_id: None)
    assert memory_resolver.knowledge_context("SOME_WORKSPACE_PERSONA") is None
    response = client.get("/api/v1/core/personas/CHAR_PETRICK/knowledge-context", headers=HEADERS)
    assert response.status_code == 404, "the route reports absence, it does not crash"
