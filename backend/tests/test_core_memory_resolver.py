"""MemoryResolver: identity is permanent, versioned and never silently changed."""
import pytest

from app.core.contracts import PersonaMemory, PersonaStatus
from app.core.memory_resolver import MemoryError_, MemoryResolver, SeedPersonaSource


@pytest.fixture()
def memory() -> MemoryResolver:
    return MemoryResolver()


def test_canonical_persona_is_resolved_from_the_knowledge_base(memory: MemoryResolver) -> None:
    persona = memory.resolve("CHAR_PETRICK")
    assert persona is not None
    assert persona.name == "Petrick Martins"
    assert persona.age == 50
    assert persona.height_m == 1.85
    assert persona.status is PersonaStatus.APPROVED


def test_planned_character_has_no_invented_identity(memory: MemoryResolver) -> None:
    jefferson = memory.resolve("CHAR_JEFFERSON")
    assert jefferson is not None
    assert jefferson.status is PersonaStatus.PLANNED
    assert jefferson.age is None
    assert jefferson.hair == ""
    assert memory.identity_phrase(jefferson) == ""


def test_unknown_and_absent_personas_resolve_to_none(memory: MemoryResolver) -> None:
    assert memory.resolve("CHAR_NOBODY") is None
    assert memory.resolve(None) is None
    assert memory.resolve("") is None


def test_only_approved_identities_may_drive_a_generation(memory: MemoryResolver) -> None:
    assert memory.is_generable("CHAR_PETRICK") is True
    assert memory.is_generable("CHAR_JEFFERSON") is False
    assert memory.is_generable(None) is False


def test_identity_phrase_carries_the_persistent_traits(memory: MemoryResolver) -> None:
    phrase = memory.identity_phrase(memory.resolve("CHAR_PETRICK"))
    for trait in ("Petrick Martins", "50 years old", "1.85m tall", "athletic build", "short beard", "dark brown eyes"):
        assert trait in phrase


def test_identity_can_be_looked_up_by_name(memory: MemoryResolver) -> None:
    assert memory.resolve_by_name("Petrick").persona_id == "CHAR_PETRICK"
    assert memory.resolve_by_name("ninguém") is None
    assert memory.resolve_by_name(None) is None


def test_unauthorized_identity_change_is_refused(memory: MemoryResolver) -> None:
    persona = memory.resolve("CHAR_PETRICK")
    with pytest.raises(MemoryError_):
        memory.revise(persona, authorized=False, hair="shaved")
    with pytest.raises(MemoryError_):
        memory.revise(persona, authorized=False, eyes="blue")


def test_authorized_identity_change_opens_a_new_version(memory: MemoryResolver) -> None:
    persona = memory.resolve("CHAR_PETRICK")
    revised = memory.revise(persona, authorized=True, hair="shaved")
    assert revised.hair == "shaved"
    assert revised.version == persona.version + 1
    # The original snapshot is untouched, so published episodes keep their look.
    assert persona.hair == "tied back"
    assert persona.version == 1


def test_administrative_fields_do_not_require_authorization(memory: MemoryResolver) -> None:
    persona = memory.resolve("CHAR_PETRICK")
    revised = memory.revise(persona, authorized=False, lora_path="persona-v2.safetensors")
    assert revised.lora_path == "persona-v2.safetensors"
    assert revised.version == persona.version


def test_unknown_field_is_rejected(memory: MemoryResolver) -> None:
    with pytest.raises(MemoryError_):
        memory.revise(memory.resolve("CHAR_PETRICK"), authorized=True, eye_color="green")


def test_no_op_change_does_not_bump_the_version(memory: MemoryResolver) -> None:
    persona = memory.resolve("CHAR_PETRICK")
    assert memory.revise(persona, authorized=True, hair=persona.hair).version == persona.version


def test_snapshot_records_the_version_it_came_from(memory: MemoryResolver) -> None:
    snapshot = memory.snapshot(memory.resolve("CHAR_PETRICK"))
    assert snapshot["snapshot_of_version"] == 1
    assert snapshot["name"] == "Petrick Martins"


def test_lora_is_never_hardcoded(memory: MemoryResolver) -> None:
    assert memory.lora_path(memory.resolve("CHAR_PETRICK")) is None
    assert memory.lora_path(None) is None


def test_a_custom_source_can_replace_the_seed_source() -> None:
    class OnePersona:
        def fetch(self, persona_id: str) -> PersonaMemory | None:
            return PersonaMemory(persona_id="X", name="Custom") if persona_id == "X" else None

        def search(self, query: str = "") -> list[PersonaMemory]:
            return [PersonaMemory(persona_id="X", name="Custom")]

    resolver = MemoryResolver(source=OnePersona())
    assert resolver.resolve("X").name == "Custom"
    assert resolver.resolve("CHAR_PETRICK") is None


def test_seed_source_is_writeable_for_the_api_layer() -> None:
    source = SeedPersonaSource()
    source.register(PersonaMemory(persona_id="CHAR_NEW", name="New Character"))
    assert MemoryResolver(source=source).resolve("CHAR_NEW").name == "New Character"


def test_default_style_comes_from_memory(memory: MemoryResolver) -> None:
    assert memory.default_style(memory.resolve("CHAR_PETRICK")) == "cinematic realism"
    assert memory.default_style(None) == ""
