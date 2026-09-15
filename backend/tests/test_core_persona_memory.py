"""ETAPA 4 — Persona Memory Engine.

Covers the part ETAPA 2 could not: history that actually persists, attributed
governance, episode snapshots that survive later revisions, and the fact that
the engine and the spec builder read the *same* ledger.
"""
import pytest

from app.core.contracts import PersonaMemory, PersonaStatus
from app.core.generation_spec_builder import GenerationSpecBuilder
from app.core.memory_resolver import SEED_PERSONAS, MemoryError_, MemoryResolver
from app.core.persona_memory import (
    IDENTITY_DEFINITION_FIELDS,
    PersonaLedger,
    PersonaMemoryEngine,
    PersonaNotFound,
)


@pytest.fixture()
def engine() -> PersonaMemoryEngine:
    """A fixed clock keeps history assertions deterministic."""

    ticks = iter([f"2026-01-{day:02d}T00:00:00+00:00" for day in range(1, 29)])
    return PersonaMemoryEngine(ledger=PersonaLedger(clock=lambda: next(ticks)))


# --------------------------------------------------------------------- ledger


def test_the_ledger_starts_from_the_canonical_seeds(engine) -> None:
    assert [persona.persona_id for persona in engine.catalog()] == ["CHAR_PETRICK", "CHAR_JEFFERSON"]


def test_history_is_append_only_and_revisions_are_monotonic(engine) -> None:
    engine.revise("CHAR_PETRICK", actor="diretor", reason="corte", authorized=True, hair="shaved")
    engine.revise("CHAR_PETRICK", actor="diretor", reason="barba", authorized=True, beard="full beard")
    history = engine.history("CHAR_PETRICK")
    assert [entry.revision for entry in history] == [1, 2, 3]
    assert [entry.version for entry in history] == [1, 2, 3]


def test_administrative_changes_do_not_bump_the_identity_version(engine) -> None:
    engine.revise("CHAR_PETRICK", actor="ml", reason="publicado", lora_path="weights/petrick-v1.safetensors")
    history = engine.history("CHAR_PETRICK")
    assert history[-1].action == "updated", "a LoRA path is not an identity change"
    assert history[-1].version == 1, "identity version must not move for an administrative edit"
    assert engine.resolve("CHAR_PETRICK").lora_path == "weights/petrick-v1.safetensors"


def test_previous_identity_versions_stay_retrievable(engine) -> None:
    engine.revise("CHAR_PETRICK", actor="diretor", reason="ep2", authorized=True, eyes="green eyes")
    assert engine.resolve("CHAR_PETRICK", version=1).eyes == "dark brown eyes"
    assert engine.resolve("CHAR_PETRICK", version=2).eyes == "green eyes"
    assert engine.resolve("CHAR_PETRICK", version=99) is None


def test_fetch_version_returns_the_state_the_character_presented(engine) -> None:
    """Administrative edits and approval share one identity version.

    Several ledger revisions can carry the same version, so `fetch_version`
    must return the last one — the state the character actually presented.
    """

    engine.create(persona_id="CHAR_NOVA", name="Nova", actor="produtor")
    engine.revise("CHAR_NOVA", actor="ml", reason="publicado", lora_path="weights/nova.safetensors")
    engine.revise("CHAR_NOVA", actor="diretor", reason="identidade", authorized=True, age=32)
    engine.approve("CHAR_NOVA", actor="cto")

    assert [entry.version for entry in engine.history("CHAR_NOVA")] == [1, 1, 2, 2]
    version_one = engine.resolve("CHAR_NOVA", version=1)
    assert version_one.status is PersonaStatus.PLANNED, "as it stood at version 1"
    assert version_one.lora_path == "weights/nova.safetensors", "the latest revision of that version"
    assert engine.resolve("CHAR_NOVA", version=2).status is PersonaStatus.APPROVED


def test_fetch_returns_the_latest_identity_so_existing_callers_are_unaffected(engine) -> None:
    engine.revise("CHAR_PETRICK", actor="diretor", reason="ep2", authorized=True, eyes="green eyes")
    assert engine.ledger.fetch("CHAR_PETRICK").eyes == "green eyes"


def test_search_sees_current_identities_only(engine) -> None:
    engine.revise("CHAR_PETRICK", actor="diretor", reason="renomeado", authorized=True, name="Petrick M.")
    assert len(engine.ledger.search("petrick")) == 1, "history must not leak into search"
    assert engine.ledger.search("petrick")[0].name == "Petrick M."


# ----------------------------------------------------------------- governance


def test_a_new_character_is_planned_until_approved(engine) -> None:
    entry = engine.create(persona_id="CHAR_NOVA", name="Nova", actor="produtor")
    assert entry.persona.status is PersonaStatus.PLANNED
    assert engine.is_generable("CHAR_NOVA") is False, "registering a character must not make it generable"


def test_identity_change_without_authorization_is_rejected(engine) -> None:
    with pytest.raises(MemoryError_, match="requires explicit authorization"):
        engine.revise("CHAR_PETRICK", actor="estagiario", reason="achei melhor", eyes="green eyes")
    assert len(engine.history("CHAR_PETRICK")) == 1, "a rejected change must not be recorded"


def test_authorized_identity_change_is_recorded_with_actor_and_reason(engine) -> None:
    entry = engine.revise("CHAR_PETRICK", actor="diretor", reason="novo arco em EP2", authorized=True, hair="shaved")
    assert entry.actor == "diretor"
    assert entry.reason == "novo arco em EP2"
    assert entry.changed == ("hair",)
    assert entry.action == "revised"


def test_a_revision_that_changes_nothing_is_rejected(engine) -> None:
    with pytest.raises(MemoryError_, match="changes nothing"):
        engine.revise("CHAR_PETRICK", actor="diretor", reason="repetido", authorized=True, eyes="dark brown eyes")


def test_unknown_fields_are_rejected(engine) -> None:
    with pytest.raises(MemoryError_, match="unknown persona fields"):
        engine.revise("CHAR_PETRICK", actor="diretor", reason="x", eye_color="green")


def test_unknown_persona_raises_a_404_shaped_error(engine) -> None:
    for call in (
        lambda: engine.revise("CHAR_NOBODY", actor="x", reason="y", hair="z"),
        lambda: engine.approve("CHAR_NOBODY", actor="x"),
        lambda: engine.retire("CHAR_NOBODY", actor="x", reason="y"),
        lambda: engine.remember("CHAR_NOBODY", episode_id="EP01"),
    ):
        with pytest.raises(PersonaNotFound):
            call()
    assert issubclass(PersonaNotFound, MemoryError_), "existing handlers must keep working"


def test_duplicate_registration_is_rejected(engine) -> None:
    with pytest.raises(MemoryError_, match="already exists"):
        engine.create(persona_id="CHAR_PETRICK", name="Outro", actor="x")


# ------------------------------------------------------------------ approval


def test_approval_refuses_an_undefined_identity(engine) -> None:
    """CHAR_JEFFERSON stays planned: approval certifies an identity, never invents one."""

    jefferson = engine.resolve("CHAR_JEFFERSON")
    assert all(not getattr(jefferson, name) for name in IDENTITY_DEFINITION_FIELDS)
    with pytest.raises(MemoryError_, match="approval requires definition"):
        engine.approve("CHAR_JEFFERSON", actor="cto")
    assert engine.is_generable("CHAR_JEFFERSON") is False
    assert engine.identity_phrase("CHAR_JEFFERSON") == ""


def test_approval_of_a_defined_character_makes_it_generable(engine) -> None:
    engine.create(persona_id="CHAR_NOVA", name="Nova", actor="produtor")
    engine.revise(
        "CHAR_NOVA",
        actor="diretor",
        reason="identidade definida",
        authorized=True,
        age=32,
        hair="curly black hair",
        eyes="amber eyes",
    )
    entry = engine.approve("CHAR_NOVA", actor="cto", reason="aprovado para EP1")
    assert entry.action == "approved"
    assert entry.actor == "cto"
    assert engine.is_generable("CHAR_NOVA") is True
    assert "Nova" in engine.identity_phrase("CHAR_NOVA")


def test_approving_twice_is_rejected(engine) -> None:
    with pytest.raises(MemoryError_, match="already approved"):
        engine.approve("CHAR_PETRICK", actor="cto")


def test_retirement_keeps_history_and_stops_generation(engine) -> None:
    entry = engine.retire("CHAR_PETRICK", actor="produtor", reason="fim do arco")
    assert entry.action == "retired"
    assert engine.is_generable("CHAR_PETRICK") is False
    assert engine.identity_phrase("CHAR_PETRICK") == "", "a retired character must not emit an identity block"
    assert len(engine.history("CHAR_PETRICK")) == 2
    assert engine.resolve("CHAR_PETRICK", version=1).status is PersonaStatus.RETIRED


# ----------------------------------------------------------- episode memory


def test_an_episode_keeps_its_original_snapshot(engine) -> None:
    """The CHARACTER_LIBRARY rule, made true rather than aspirational."""

    engine.remember("CHAR_PETRICK", episode_id="EP01")
    engine.revise("CHAR_PETRICK", actor="diretor", reason="novo look", authorized=True, eyes="green eyes")
    engine.remember("CHAR_PETRICK", episode_id="EP02")

    assert engine.recall("EP01", "CHAR_PETRICK").eyes == "dark brown eyes"
    assert engine.recall("EP02", "CHAR_PETRICK").eyes == "green eyes"
    assert engine.resolve("CHAR_PETRICK").eyes == "green eyes"


def test_recall_without_a_snapshot_is_none_not_a_guess(engine) -> None:
    assert engine.recall("EP99", "CHAR_PETRICK") is None


def test_remember_returns_the_snapshot_payload(engine) -> None:
    snapshot = engine.remember("CHAR_PETRICK", episode_id="EP01")
    assert snapshot["persona_id"] == "CHAR_PETRICK"
    assert snapshot["snapshot_of_version"] == 1
    assert snapshot["eyes"] == "dark brown eyes"


def test_episode_cast_lists_every_character_used(engine) -> None:
    engine.remember("CHAR_PETRICK", episode_id="EP01")
    engine.remember("CHAR_JEFFERSON", episode_id="EP01")
    engine.remember("CHAR_PETRICK", episode_id="EP02")
    assert {persona.persona_id for persona in engine.episode_cast("EP01")} == {"CHAR_PETRICK", "CHAR_JEFFERSON"}
    assert [persona.persona_id for persona in engine.episode_cast("EP02")] == ["CHAR_PETRICK"]


def test_continuity_reports_drift_between_episodes(engine) -> None:
    engine.remember("CHAR_PETRICK", episode_id="EP01")
    engine.revise("CHAR_PETRICK", actor="diretor", reason="novo look", authorized=True, eyes="green eyes")
    engine.remember("CHAR_PETRICK", episode_id="EP02")

    report = engine.continuity("CHAR_PETRICK", ["EP01", "EP02"])
    assert report["consistent"] is False
    assert report["distinct_identities"] == 2
    assert report["identity_phrases"]["EP01"] != report["identity_phrases"]["EP02"]


def test_continuity_is_true_when_the_identity_held(engine) -> None:
    engine.remember("CHAR_PETRICK", episode_id="EP01")
    engine.remember("CHAR_PETRICK", episode_id="EP02")
    report = engine.continuity("CHAR_PETRICK", ["EP01", "EP02"])
    assert report["consistent"] is True
    assert report["distinct_identities"] == 1


def test_continuity_distinguishes_missing_from_consistent(engine) -> None:
    engine.remember("CHAR_PETRICK", episode_id="EP01")
    report = engine.continuity("CHAR_PETRICK", ["EP01", "EP02"])
    assert report["consistent"] is False, "a missing record is not evidence of consistency"
    assert report["episodes_without_snapshot"] == ["EP02"]


# ---------------------------------------------------------------------- drift


def test_drift_names_what_changed_and_when(engine) -> None:
    engine.revise("CHAR_PETRICK", actor="diretor", reason="ep2", authorized=True, eyes="green eyes")
    engine.revise("CHAR_PETRICK", actor="diretor", reason="ep3", authorized=True, hair="shaved")
    engine.revise("CHAR_PETRICK", actor="ml", reason="publicado", lora_path="weights/v2.safetensors")

    report = engine.drift("CHAR_PETRICK")
    assert report["identity_versions"] == [1, 2, 3]
    assert report["changed_fields"] == {"eyes": [2], "hair": [3]}, "administrative edits are not identity drift"
    assert report["identity_changed"] is True
    assert report["revisions"] == 4, "the ledger still records every entry"


def test_drift_of_an_untouched_character_reports_no_change(engine) -> None:
    report = engine.drift("CHAR_JEFFERSON")
    assert report["changed_fields"] == {}
    assert report["identity_changed"] is False


# --------------------------------------------------------------- composition


def test_the_engine_delegates_vocabulary_instead_of_reimplementing_it(engine) -> None:
    """One definition of each rule: the engine must not fork ETAPA 2's wording."""

    resolver = MemoryResolver(engine.ledger)
    persona = engine.resolve("CHAR_PETRICK")
    assert engine.identity_phrase("CHAR_PETRICK") == resolver.identity_phrase(persona)
    assert engine.default_style("CHAR_PETRICK") == resolver.default_style(persona)
    assert engine.lora_path("CHAR_PETRICK") == resolver.lora_path(persona)


def test_the_ledger_satisfies_the_persona_source_protocol(engine) -> None:
    from app.core.contracts import PersonaSource

    assert isinstance(engine.ledger, PersonaSource)


def test_seeds_are_not_duplicated_by_the_ledger() -> None:
    """A fourth copy of the character library would be a drift risk."""

    assert PersonaLedger().fetch("CHAR_PETRICK") == next(p for p in SEED_PERSONAS if p.persona_id == "CHAR_PETRICK")
    jefferson = PersonaLedger().fetch("CHAR_JEFFERSON")
    assert jefferson.status is PersonaStatus.PLANNED
    assert all(not getattr(jefferson, name) for name in IDENTITY_DEFINITION_FIELDS)


def test_an_approved_persona_reaches_a_generation_spec() -> None:
    """The payoff of sharing one ledger: governance feeds generation.

    A character defined and approved through the engine becomes usable by
    GenerationSpecBuilder with no extra wiring.
    """

    ledger = PersonaLedger()
    engine = PersonaMemoryEngine(ledger=ledger)
    builder = GenerationSpecBuilder(memory=MemoryResolver(ledger))

    engine.create(persona_id="CHAR_NOVA", name="Nova", actor="produtor")
    before = builder.build_traced(prompt="a portrait", persona_id="CHAR_NOVA")
    assert before.trace.persona_applied is False, "a planned character must not reach the prompt"

    engine.revise(
        "CHAR_NOVA",
        actor="diretor",
        reason="identidade",
        authorized=True,
        age=32,
        hair="curly black hair",
        eyes="amber eyes",
    )
    engine.approve("CHAR_NOVA", actor="cto")

    after = builder.build_traced(prompt="a portrait", persona_id="CHAR_NOVA")
    assert after.trace.persona_applied is True
    assert "Nova" in after.spec.prompt_compiled
    assert after.spec.persona_id == "CHAR_NOVA"


def test_a_revised_identity_changes_the_compiled_prompt() -> None:
    ledger = PersonaLedger()
    engine = PersonaMemoryEngine(ledger=ledger)
    builder = GenerationSpecBuilder(memory=MemoryResolver(ledger))

    first = builder.build_traced(prompt="a portrait", persona_id="CHAR_PETRICK").spec.prompt_compiled
    engine.revise("CHAR_PETRICK", actor="diretor", reason="ep2", authorized=True, eyes="green eyes")
    second = builder.build_traced(prompt="a portrait", persona_id="CHAR_PETRICK").spec.prompt_compiled

    assert "dark brown eyes" in first
    assert "green eyes" in second


def test_a_retired_character_stops_reaching_the_prompt() -> None:
    ledger = PersonaLedger()
    engine = PersonaMemoryEngine(ledger=ledger)
    builder = GenerationSpecBuilder(memory=MemoryResolver(ledger))

    assert builder.build_traced(prompt="x", persona_id="CHAR_PETRICK").trace.persona_applied is True
    engine.retire("CHAR_PETRICK", actor="produtor", reason="fim do arco")
    assert builder.build_traced(prompt="x", persona_id="CHAR_PETRICK").trace.persona_applied is False


def test_fetch_revision_reads_a_specific_ledger_entry(engine) -> None:
    engine.revise("CHAR_PETRICK", actor="diretor", reason="ep2", authorized=True, eyes="green eyes")
    assert engine.ledger.fetch_revision("CHAR_PETRICK", 1).eyes == "dark brown eyes"
    assert engine.ledger.fetch_revision("CHAR_PETRICK", 2).eyes == "green eyes"
    assert engine.ledger.fetch_revision("CHAR_PETRICK", 99) is None
    assert engine.ledger.fetch_revision("CHAR_NOBODY", 1) is None


def test_resolving_no_persona_is_none_not_an_error(engine) -> None:
    assert engine.resolve(None) is None
    assert engine.resolve("") is None
    assert engine.identity_phrase(None) == ""
    assert engine.voice_phrase(None) == ""
    assert engine.default_style(None) == ""
    assert engine.lora_path(None) is None
    assert engine.is_generable(None) is False


def test_voice_is_reported_only_for_a_character_that_has_one(engine) -> None:
    assert engine.voice_phrase("CHAR_PETRICK") == "", "no seed character has a defined voice"
    engine.create(persona_id="CHAR_NOVA", name="Nova", actor="produtor")
    engine.revise("CHAR_NOVA", actor="diretor", reason="voz", authorized=True, voice="low, unhurried")
    assert engine.voice_phrase("CHAR_NOVA") == "Nova voice: low, unhurried"


def test_the_persona_source_protocol_is_structural_not_nominal() -> None:
    """Any object with fetch/search can back the resolver — this is the PostgreSQL seam."""

    class Minimal:
        def fetch(self, persona_id):
            return SEED_PERSONAS[0] if persona_id == "CHAR_PETRICK" else None

        def search(self, query=""):
            return list(SEED_PERSONAS)

    resolver = MemoryResolver(Minimal())
    assert resolver.resolve("CHAR_PETRICK").name == "Petrick Martins"
    assert len(resolver.catalog()) == 2


def test_a_persona_is_resolved_at_the_version_an_episode_used() -> None:
    ledger = PersonaLedger()
    engine = PersonaMemoryEngine(ledger=ledger)
    builder = GenerationSpecBuilder(memory=MemoryResolver(ledger))

    engine.remember("CHAR_PETRICK", episode_id="EP01")
    engine.revise("CHAR_PETRICK", actor="diretor", reason="ep2", authorized=True, eyes="green eyes")

    ep01 = engine.recall("EP01", "CHAR_PETRICK")
    prompt_ep01 = builder.build_traced(prompt="a portrait", persona_id="CHAR_PETRICK").spec.prompt_compiled
    assert "green eyes" in prompt_ep01, "current identity is what a new generation uses"
    assert engine.memory.identity_phrase(ep01).endswith("dark brown eyes"), "EP01 keeps its own memory"


def test_persona_memory_is_a_value_object(engine) -> None:
    persona = engine.resolve("CHAR_PETRICK")
    assert isinstance(persona, PersonaMemory)
    with pytest.raises(Exception):
        persona.name = "outro"  # type: ignore[misc]
