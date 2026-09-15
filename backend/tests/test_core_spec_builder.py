"""GenerationSpecBuilder: the composition root, and the precedence rules."""
import pytest

from app.core.contracts import GENERATION_SPEC_FIELDS, GenerationKind, GenerationSpec
from app.core.generation_spec_builder import GenerationSpecBuilder
from app.core.memory_resolver import MemoryResolver
from app.core.prompt_compiler import PromptCompiler
from app.core.shot_resolver import ShotResolver
from app.core.style_resolver import StyleResolver


@pytest.fixture()
def builder() -> GenerationSpecBuilder:
    return GenerationSpecBuilder(
        memory=MemoryResolver(),
        styles=StyleResolver(),
        shots=ShotResolver(),
        compiler=PromptCompiler(),
    )


def test_the_result_is_a_generation_spec_with_every_mandatory_field(builder: GenerationSpecBuilder) -> None:
    spec = builder.build(prompt="a black t-shirt on concrete")
    assert isinstance(spec, GenerationSpec)
    for field_name in GENERATION_SPEC_FIELDS:
        assert hasattr(spec, field_name), f"spec is missing {field_name}"


def test_persona_memory_is_consulted_automatically(builder: GenerationSpecBuilder) -> None:
    spec = builder.build(prompt="a portrait", persona_id="CHAR_PETRICK")
    assert spec.persona_id == "CHAR_PETRICK"
    assert "Petrick Martins" in spec.prompt_compiled
    assert "athletic build" in spec.prompt_compiled


def test_an_unknown_persona_is_dropped_instead_of_inventing_identity(builder: GenerationSpecBuilder) -> None:
    spec = builder.build(prompt="a portrait", persona_id="CHAR_NOBODY")
    assert spec.persona_id is None
    assert "Petrick" not in spec.prompt_compiled


def test_a_planned_persona_never_drives_a_generation(builder: GenerationSpecBuilder) -> None:
    spec = builder.build(prompt="a portrait", persona_id="CHAR_JEFFERSON")
    assert spec.persona_id is None
    assert "Jefferson" not in spec.prompt_compiled


def test_anonymous_generation_is_still_valid(builder: GenerationSpecBuilder) -> None:
    spec = builder.build(prompt="a portrait")
    assert spec.persona_id is None
    assert spec.prompt_compiled


def test_the_original_prompt_is_preserved_but_never_sent_raw(builder: GenerationSpecBuilder) -> None:
    spec = builder.build(prompt="a red car")
    assert spec.prompt_original == "a red car"
    assert spec.prompt_compiled != "a red car"
    assert spec.prompt_compiled.startswith("a red car")


def test_style_supplies_fps_when_the_caller_does_not(builder: GenerationSpecBuilder) -> None:
    result = builder.build_traced(prompt="x", style="marvel-trailer")
    assert result.spec.fps == 24
    assert result.trace.sources["fps"] == "style:marvel-trailer"


def test_an_explicit_fps_beats_the_style(builder: GenerationSpecBuilder) -> None:
    result = builder.build_traced(prompt="x", style="marvel-trailer", fps=30)
    assert result.spec.fps == 30
    assert result.trace.sources["fps"] == "request"


def test_shot_beats_style_for_lens_and_camera(builder: GenerationSpecBuilder) -> None:
    result = builder.build_traced(prompt="x", style="john-wick", shot="SH122")
    assert result.spec.lens.startswith("135mm")
    assert "detail insert" in result.spec.camera
    assert result.trace.sources["lens"] == "shot"
    assert result.trace.sources["camera"] == "shot"


def test_style_fills_lens_when_there_is_no_shot(builder: GenerationSpecBuilder) -> None:
    result = builder.build_traced(prompt="x", style="imax-hero")
    assert "40mm" in result.spec.lens
    assert result.trace.sources["lens"] == "style"


def test_an_explicit_camera_beats_the_shot(builder: GenerationSpecBuilder) -> None:
    result = builder.build_traced(prompt="x", shot="SH001", camera="locked off wide")
    assert result.spec.camera == "locked off wide"
    assert result.trace.sources["camera"] == "request"


def test_lighting_comes_from_the_style(builder: GenerationSpecBuilder) -> None:
    result = builder.build_traced(prompt="x", style="neo-tokyo")
    assert "neon practicals" in result.spec.lighting
    assert result.trace.sources["lighting"] == "style"


def test_style_falls_back_to_the_persona_default(builder: GenerationSpecBuilder) -> None:
    result = builder.build_traced(prompt="x", persona_id="CHAR_PETRICK")
    assert result.spec.style_id == "cinematic-realism"
    assert result.trace.style_source == "persona:CHAR_PETRICK"


def test_an_unknown_style_never_borrows_another_look(builder: GenerationSpecBuilder) -> None:
    result = builder.build_traced(prompt="x", style="not-in-the-library")
    assert result.spec.style_id == "brobond-neutral"
    assert result.trace.style_source == "unknown-fallback-neutral"


def test_the_default_style_is_the_brobond_baseline(builder: GenerationSpecBuilder) -> None:
    assert builder.build(prompt="x").style_id == "cinematic-realism"


def test_lora_resolution_prefers_the_request_then_the_persona(builder: GenerationSpecBuilder) -> None:
    assert builder.build(prompt="x", lora="explicit.safetensors").lora == "explicit.safetensors"
    assert builder.build(prompt="x", persona_id="CHAR_PETRICK").lora is None


def test_negative_prompt_always_carries_the_brobond_guard(builder: GenerationSpecBuilder) -> None:
    assert "plastic skin" in builder.build(prompt="x").negative_prompt


def test_video_kind_is_carried_through(builder: GenerationSpecBuilder) -> None:
    spec = builder.build(prompt="x", kind="video", duration=10, fps=30)
    assert spec.kind is GenerationKind.VIDEO
    assert spec.duration == 10
    assert spec.fps == 30


def test_project_user_and_seed_are_carried_through(builder: GenerationSpecBuilder) -> None:
    spec = builder.build(prompt="x", project_id="p-1", user_id="w-1", seed=42, controlnet="depth")
    assert (spec.project_id, spec.user_id, spec.seed, spec.controlnet) == ("p-1", "w-1", 42, "depth")


def test_every_spec_gets_a_unique_traceable_id(builder: GenerationSpecBuilder) -> None:
    first, second = builder.build(prompt="x"), builder.build(prompt="x")
    assert first.spec_id != second.spec_id
    assert first.schema_version == second.schema_version


def test_the_trace_explains_every_contested_field(builder: GenerationSpecBuilder) -> None:
    trace = builder.build_traced(prompt="x", style="john-wick", shot="SH001").trace.to_dict()
    assert trace["style_id"] == "john-wick"
    assert trace["shot_code"] == "SH001"
    assert trace["shot_applied"] is True
    assert set(trace["sources"]) >= {"camera", "lens", "lighting", "motion", "fps", "lora"}


def test_the_builder_works_with_stub_collaborators() -> None:
    """Independence check: the builder needs no database and no real resolvers."""

    class StubMemory:
        def resolve(self, persona_id):
            return None

        def resolve_by_name(self, name):
            return None

        def catalog(self):
            return []

        def is_generable(self, persona_id):
            return False

        def identity_phrase(self, persona):
            return ""

        def voice_phrase(self, persona):
            return ""

        def default_style(self, persona):
            return ""

        def lora_path(self, persona):
            return None

        def revise(self, persona, *, authorized, **changes):
            return persona

        def snapshot(self, persona):
            return {}

    spec = GenerationSpecBuilder(memory=StubMemory()).build(prompt="stubbed build")
    assert spec.prompt_compiled.startswith("stubbed build")
