"""PromptCompiler: raw text never reaches a model on its own."""
import pytest

from app.core.contracts import PromptBlocks
from app.core.prompt_compiler import DROP_PRIORITY, PromptCompiler, PromptCompilerError


@pytest.fixture()
def compiler() -> PromptCompiler:
    return PromptCompiler()


def test_raw_prompt_is_never_emitted_alone(compiler: PromptCompiler) -> None:
    compiled = compiler.build("a red car")
    assert compiled.prompt != "a red car"
    assert compiled.prompt.startswith("a red car")
    assert compiler.output_block in compiled.prompt


def test_blocks_are_emitted_in_the_mandated_order(compiler: PromptCompiler) -> None:
    compiled = compiler.compile(
        PromptBlocks(
            subject="subj",
            persona="pers",
            environment="env",
            action="act",
            camera="cam",
            lens="lens",
            light="light",
            color="color",
            motion="mot",
            style="style",
            continuity="cont",
            output="out",
        )
    )
    # Exact equality, not substring positions: single-letter markers collide
    # ("CO" matches inside "COLOUR") and would pass a wrong order.
    assert compiled.prompt == (
        "subj, pers, env, act, cam, lens, light, color, mot, style, cont, out"
    )


def test_backward_compatible_enhance_keeps_the_brobond_signature(compiler: PromptCompiler) -> None:
    """The pre-Core `/api/v1/prompts/enhance` contract must survive."""

    enhanced = compiler.enhance("man walking")
    assert "cinematic composition" in enhanced
    assert "cinematic" in enhanced
    assert len(compiler.tokenize(enhanced)) > 3


def test_enhance_defaults_match_the_pre_core_prompt_enhancer(compiler: PromptCompiler) -> None:
    assert compiler.default_style == "cinematic realism"
    enhanced = compiler.enhance("subject")
    assert "cinematic realism" in enhanced
    assert "medium shot, 85mm lens, shallow depth of field" in enhanced


def test_persona_and_camera_land_in_their_own_blocks(compiler: PromptCompiler) -> None:
    compiled = compiler.build("a man", persona="Petrick Martins", camera="low angle tracking")
    assert "Petrick Martins" in compiled.prompt
    assert "low angle tracking" in compiled.prompt


def test_negative_prompt_always_carries_the_style_guide_guard(compiler: PromptCompiler) -> None:
    compiled = compiler.build("a man")
    assert "plastic skin" in compiled.negative_prompt
    assert "oversharpened" in compiled.negative_prompt


def test_caller_negative_terms_are_merged_and_deduplicated(compiler: PromptCompiler) -> None:
    compiled = compiler.build("a man", negative_prompt="extra fingers, plastic skin")
    assert compiled.negative_prompt.count("plastic skin") == 1
    assert compiled.negative_prompt.count("extra fingers") == 1
    assert compiled.negative_prompt.index("extra fingers") < compiled.negative_prompt.index("plastic skin")


def test_negative_guard_can_be_disabled(compiler: PromptCompiler) -> None:
    assert compiler.compile_negative("blurry", include_guard=False) == "blurry"


def test_empty_subject_is_rejected(compiler: PromptCompiler) -> None:
    with pytest.raises(PromptCompilerError):
        compiler.build("   ")


def test_oversized_prompt_is_trimmed_and_the_trim_is_reported() -> None:
    compiler = PromptCompiler()
    compiler.max_prompt_chars = 120
    compiled = compiler.build(
        "subject",
        environment="a very long environment description that will not fit in the budget",
        motion="a very long motion description that also will not fit in the budget",
    )
    assert len(compiled.prompt) <= 120
    assert compiled.dropped, "trimming must be reported, never silent"
    # The invariant is that trimming follows the declared priority order.
    priorities = [DROP_PRIORITY.index(name) for name in compiled.dropped]
    assert priorities == sorted(priorities), f"trim ignored priority: {compiled.dropped}"
    assert "subject" not in compiled.dropped, "the subject is never dropped"
    assert compiled.prompt == "subject"


def test_whitespace_and_trailing_dots_are_normalised(compiler: PromptCompiler) -> None:
    # Collapses runs of whitespace and strips a trailing dot, matching the
    # pre-Core PromptEnhancer (`prompt.strip().rstrip(".")`).
    assert PromptCompiler.normalize("  a   messy  prompt. ") == "a messy prompt"
    assert PromptCompiler.normalize("") == ""
    assert PromptCompiler.normalize("no trailing dot") == "no trailing dot"


def test_tokenize_splits_on_clause_boundaries(compiler: PromptCompiler) -> None:
    assert PromptCompiler.tokenize("a, b,  c ") == ("a", "b", "c")


def test_compilation_is_deterministic(compiler: PromptCompiler) -> None:
    first = compiler.build("a man", style="luxury-fashion")
    second = compiler.build("a man", style="luxury-fashion")
    assert first.prompt == second.prompt
    assert first.negative_prompt == second.negative_prompt
