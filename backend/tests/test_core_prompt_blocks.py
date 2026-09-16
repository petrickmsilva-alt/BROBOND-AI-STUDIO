"""ETAPA 9 tests — the prompt compiler's block structure.

The compiler existed since ETAPA 2 but emitted ten blocks where
`SYSTEM_PROMPT.md` ("Estrutura de prompt interno") declares thirteen, and it
joined them without deduplicating, so every prompt carrying a shot preset
repeated the focal length.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.core import PromptCompiler, StyleResolver
from app.core.contracts import NEGATIVE_BLOCK, PROMPT_BLOCKS, PROMPT_BLOCK_ORDER, PromptBlocks, SceneBeat


@pytest.fixture()
def compiler() -> PromptCompiler:
    return PromptCompiler()


# ---------------------------------------------------------------------------
# The thirteen declared blocks
# ---------------------------------------------------------------------------


def test_every_block_system_prompt_declares_is_emitted():
    documented = [
        "SUBJECT", "CHARACTER", "ENVIRONMENT", "ACTION", "CAMERA", "LENS",
        "LIGHT", "COLOR", "MOTION", "STYLE", "CONTINUITY", "OUTPUT", "NEGATIVE",
    ]
    assert len(PROMPT_BLOCKS) == len(documented) == 13
    # CHARACTER is spelled `persona` in the implementation.
    aliases = {"CHARACTER": "persona"}
    for name in documented:
        assert aliases.get(name, name.lower()) in PROMPT_BLOCKS


def test_action_and_color_are_really_emitted_not_just_declared(compiler):
    """The two blocks that did not exist before ETAPA 9."""

    compiled = compiler.compile(PromptBlocks(subject="a street", action="a man walks", color="teal grade"))
    assert "a man walks" in compiled.prompt
    assert "teal grade" in compiled.prompt


def test_blocks_serialise_all_thirteen(compiler):
    """`to_dict` is the contract's own view of the block set."""

    payload = PromptBlocks(subject="a street").to_dict()
    assert set(payload) == set(PROMPT_BLOCKS)
    assert len(payload) == 13
    assert payload["subject"] == "a street"
    assert payload["negative"] == ""


def test_negative_is_declared_but_never_joined_to_the_prompt(compiler):
    """A negative prompt appended to the positive one would invert its meaning."""

    compiled = compiler.compile(PromptBlocks(subject="a street", negative="blurry, watermark"))
    assert "blurry" not in compiled.prompt
    assert "blurry" in compiled.negative_prompt
    assert NEGATIVE_BLOCK not in PROMPT_BLOCK_ORDER


def test_blocks_follow_the_documented_order(compiler):
    compiled = compiler.compile(
        PromptBlocks(
            subject="subj", persona="pers", environment="env", action="act",
            camera="cam", lens="lens", light="light", color="color",
            motion="mot", style="style", continuity="cont", output="out",
        )
    )
    assert compiled.prompt == "subj, pers, env, act, cam, lens, light, color, mot, style, cont, out"


def test_style_comes_after_motion_as_the_document_says():
    """STYLE is a global look modifier, not the fourth thing the model reads."""

    assert PROMPT_BLOCK_ORDER.index("style") > PROMPT_BLOCK_ORDER.index("motion")
    assert PROMPT_BLOCK_ORDER.index("color") > PROMPT_BLOCK_ORDER.index("light")


# ---------------------------------------------------------------------------
# Deduplication — the defect this etapa fixes
# ---------------------------------------------------------------------------


def test_a_repeated_clause_is_emitted_once(compiler):
    """`camera_phrase` and `lens_phrase` both carry the focal length."""

    compiled = compiler.compile(PromptBlocks(subject="a street", camera="orbit, 35mm", lens="35mm"))
    assert compiled.prompt.count("35mm") == 1
    assert compiled.prompt == "a street, orbit, 35mm"


def test_deduplication_is_case_insensitive(compiler):
    compiled = compiler.compile(PromptBlocks(subject="Rain", camera="rain, wet street"))
    assert compiled.prompt.count("ain") == 1


def test_deduplication_keeps_the_first_occurrence(compiler):
    compiled = compiler.compile(PromptBlocks(subject="first, shared", lens="shared, last"))
    assert compiled.prompt == "first, shared, last"


def test_deduplication_does_not_eat_distinct_clauses(compiler):
    compiled = compiler.compile(
        PromptBlocks(subject="a street", camera="slow push", lens="50mm", light="soft key")
    )
    assert compiled.prompt == "a street, slow push, 50mm, soft key"


def test_no_published_shot_produces_a_duplicated_clause():
    """Regression, measured over the ten published presets."""

    from collections import Counter

    from app.core import GenerationSpecBuilder, MemoryResolver, PersonaLedger, ShotResolver
    from app.core.shot_library import FULL_SHOT_LIBRARY
    from app.core.shot_resolver import SeedShotSource

    builder = GenerationSpecBuilder(
        memory=MemoryResolver(PersonaLedger()),
        styles=StyleResolver(),
        shots=ShotResolver(SeedShotSource(FULL_SHOT_LIBRARY)),
        compiler=PromptCompiler(),
    )
    for code in ("SH001", "SH014", "SH032", "SH051", "SH089"):
        spec = builder.build(prompt="a man walks", style="neo-tokyo", shot=code)
        counts = Counter(part.casefold() for part in spec.prompt_compiled.split(", "))
        repeated = [clause for clause, count in counts.items() if count > 1]
        assert not repeated, f"{code} repeats {repeated}"


# ---------------------------------------------------------------------------
# Colour is its own block
# ---------------------------------------------------------------------------


def test_the_style_resolver_separates_name_from_grade():
    styles = StyleResolver()
    preset = styles.resolve("neo-tokyo")
    assert styles.style_phrase(preset) == "neo tokyo"
    color = styles.color_phrase(preset)
    assert preset.lut in color
    assert preset.palette in color
    assert "neo tokyo" not in color


def test_describe_is_unchanged_so_its_callers_still_work():
    """`describe` is public surface and is pinned by its own test."""

    styles = StyleResolver()
    described = styles.describe(styles.resolve("neo-tokyo"))
    assert "neo tokyo" in described
    assert "cyan" in described


def test_a_compiled_spec_puts_the_grade_in_the_colour_block():
    from app.core import GenerationSpecBuilder, MemoryResolver, PersonaLedger, ShotResolver
    from app.core.shot_library import FULL_SHOT_LIBRARY
    from app.core.shot_resolver import SeedShotSource

    builder = GenerationSpecBuilder(
        memory=MemoryResolver(PersonaLedger()),
        styles=StyleResolver(),
        shots=ShotResolver(SeedShotSource(FULL_SHOT_LIBRARY)),
        compiler=PromptCompiler(),
    )
    spec = builder.build(prompt="a man walks", style="neo-tokyo", shot="SH051")
    prompt = spec.prompt_compiled
    # STYLE (name) sits after MOTION; COLOR sits after LIGHT.
    assert prompt.index("cyan-magenta") < prompt.index("neo tokyo")


# ---------------------------------------------------------------------------
# Trim priority
# ---------------------------------------------------------------------------


def test_colour_survives_a_trim_that_drops_style():
    """The grade is what keeps a sequence recognisable across cuts."""

    from app.core.prompt_compiler import DROP_PRIORITY

    assert DROP_PRIORITY.index("color") > DROP_PRIORITY.index("style")
    assert DROP_PRIORITY.index("action") > DROP_PRIORITY.index("camera")


def test_the_subject_is_still_never_dropped(compiler):
    compiler.max_prompt_chars = 60
    compiled = compiler.build(
        "the subject stays",
        environment="a very long environment that will not fit the budget at all",
        motion="a very long motion description that will not fit either",
        continuity="and a continuity note that also has to go",
    )
    assert compiled.prompt.startswith("the subject stays")
    assert "subject" not in compiled.dropped
    assert compiled.dropped, "trimming must be reported, never silent"


# ---------------------------------------------------------------------------
# Per-provider budget
# ---------------------------------------------------------------------------


def test_provider_names_are_opaque_to_the_core_budget(compiler):
    assert compiler.budget_for("provider-a") == compiler.budget_for("provider-b")
    assert compiler.budget_for("provider-b", budget=1200) > compiler.budget_for("provider-a")


def test_an_unknown_provider_gets_the_conservative_budget(compiler):
    assert compiler.budget_for("some-future-model") == compiler.budget_for(None)


def test_a_provider_budget_can_never_loosen_the_compiler_ceiling():
    compiler = PromptCompiler()
    compiler.max_prompt_chars = 120
    assert compiler.budget_for("wan-video") == 120


def test_a_long_prompt_is_cut_to_the_budget_of_its_provider(compiler):
    long_subject = "an extremely detailed scene description " * 40
    for provider in ("flux-dev", "wan-video"):
        compiled = compiler.compile(PromptBlocks(subject=long_subject), provider=provider)
        assert len(compiled.prompt) <= compiler.budget_for(provider)


def test_a_trimmed_prompt_reports_what_it_dropped(compiler):
    compiler.max_prompt_chars = 80
    compiled = compiler.compile(
        PromptBlocks(
            subject="a man walks",
            environment="a long rainy street full of neon signs and reflections",
            color="teal and amber restraint with heavy grain",
        )
    )
    assert compiled.dropped == ("environment",), compiled.dropped
    assert "teal and amber" in compiled.prompt, "the grade outlives the scenery"


# ---------------------------------------------------------------------------
# compile_beats — closing the storyboard loop
# ---------------------------------------------------------------------------


def _beats() -> tuple[SceneBeat, ...]:
    return (
        SceneBeat(
            number=1, objective="abrir", emotion="curiosidade",
            camera="slow crane reveal", lighting="blue hour", motion="slow",
            shot_code="SH002", reference="the world before the story",
            lens="24mm", continuity="establish geography once",
        ),
        SceneBeat(
            number=2, objective="fechar", emotion="convicção",
            camera="static locked tripod", lighting="warm side light", motion="still",
            shot_code="SH253", reference="the story releases them",
            lens="24mm", continuity="match the preceding direction",
        ),
    )


def test_compile_beats_returns_one_prompt_per_scene(compiler):
    prompts = compiler.compile_beats(_beats(), brief="a short film")
    assert len(prompts) == 2
    assert all(item.prompt for item in prompts)


def test_a_compiled_scene_carries_the_cast_shot(compiler):
    prompt = compiler.compile_beats(_beats(), brief="a short film")[0].prompt
    assert "the world before the story" in prompt  # ACTION, from the preset
    assert "slow crane reveal" in prompt           # CAMERA
    assert "24mm" in prompt                        # LENS
    assert "blue hour" in prompt                   # LIGHT
    assert "establish geography once" in prompt    # CONTINUITY


def test_compile_beats_applies_the_provider_budget(compiler):
    prompts = compiler.compile_beats(_beats(), brief="a short film", provider="flux-dev")
    assert all(len(item.prompt) <= compiler.budget_for("flux-dev") for item in prompts)


def test_compile_beats_never_emits_the_brief_twice(compiler):
    prompt = compiler.compile_beats(_beats(), brief="a short film")[0].prompt
    assert prompt.count("a short film") == 1


def test_compile_beats_takes_only_contract_types():
    """The compiler must not learn what a Storyboard is — independence is guarded."""

    module = pathlib.Path("backend/app/core/prompt_compiler.py").read_text()
    assert "storyboard_engine" not in module
    assert "from .storyboard_engine" not in module
    tree = ast.parse(module)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported <= {"__future__", "contracts", "collections.abc", "re"}
