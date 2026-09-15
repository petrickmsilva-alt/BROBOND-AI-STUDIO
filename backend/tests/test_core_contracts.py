"""Contracts of BROBOND CORE: the GenerationSpec shape is the product's spine."""
import dataclasses

from app.core.contracts import (
    GENERATION_SPEC_FIELDS,
    NEGATIVE_BLOCK,
    PROMPT_BLOCKS,
    PROMPT_BLOCK_ORDER,
    SPEC_SCHEMA_VERSION,
    GenerationKind,
    GenerationSpec,
    PersonaStatus,
    PromptBlocks,
)

#: The 19 mandatory fields required by ETAPA 3, restated here on purpose: this
#: test must fail if the contract and the mission drift apart.
MANDATORY = {
    "project_id",
    "user_id",
    "persona_id",
    "style_id",
    "prompt_original",
    "prompt_compiled",
    "negative_prompt",
    "camera",
    "lens",
    "lighting",
    "motion",
    "weather",
    "aspect_ratio",
    "fps",
    "duration",
    "provider",
    "seed",
    "lora",
    "controlnet",
}


def test_generation_spec_declares_every_mandatory_field() -> None:
    declared = {f.name for f in dataclasses.fields(GenerationSpec)}
    assert MANDATORY <= declared, f"missing mandatory fields: {sorted(MANDATORY - declared)}"


def test_mandatory_field_list_is_the_single_source_of_truth() -> None:
    assert set(GENERATION_SPEC_FIELDS) == MANDATORY
    assert len(GENERATION_SPEC_FIELDS) == 19


def test_generation_spec_is_immutable_and_serialisable() -> None:
    spec = GenerationSpec(prompt_original="raw", prompt_compiled="compiled")
    assert spec.schema_version == SPEC_SCHEMA_VERSION
    payload = spec.to_dict()
    assert payload["kind"] == "image"
    assert payload["prompt_original"] == "raw"
    try:
        spec.prompt_compiled = "mutated"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - a mutable spec would break reproducibility
        raise AssertionError("GenerationSpec must be frozen")


def test_spec_trace_is_short_and_stable() -> None:
    spec = GenerationSpec(prompt_original="a", prompt_compiled="b", style_id="john-wick", provider="flux-dev")
    assert spec.trace().endswith(":flux-dev:john-wick")


def test_prompt_block_order_matches_the_mandate() -> None:
    """SYSTEM_PROMPT.md declares thirteen blocks; assert all thirteen, in order.

    Until ETAPA 9 only ten were emitted: ACTION and COLOR did not exist and
    STYLE sat fourth instead of after MOTION. `CHARACTER` is spelled `persona`.
    """

    documented = (
        "subject",      # SUBJECT
        "persona",      # CHARACTER
        "environment",  # ENVIRONMENT
        "action",       # ACTION
        "camera",       # CAMERA
        "lens",         # LENS
        "light",        # LIGHT
        "color",        # COLOR
        "motion",       # MOTION
        "style",        # STYLE
        "continuity",   # CONTINUITY (documented BROBOND extra)
        "output",       # OUTPUT
    )
    assert PROMPT_BLOCK_ORDER == documented, f"out of order: {PROMPT_BLOCK_ORDER}"
    assert PROMPT_BLOCK_ORDER[0] == "subject"
    assert PROMPT_BLOCK_ORDER[-1] == "output"


def test_the_thirteenth_block_is_negative_and_stays_out_of_the_prompt() -> None:
    """NEGATIVE is declared but must never be appended to the positive prompt."""

    assert len(PROMPT_BLOCKS) == 13
    assert PROMPT_BLOCKS[-1] == NEGATIVE_BLOCK
    assert NEGATIVE_BLOCK not in PROMPT_BLOCK_ORDER


def test_prompt_blocks_drop_empty_entries_in_order() -> None:
    blocks = PromptBlocks(subject="s", style="", camera="c")
    assert blocks.ordered() == [("subject", "s"), ("camera", "c")]


def test_generation_kind_covers_image_and_video() -> None:
    assert GenerationKind.IMAGE.value == "image"
    assert GenerationKind.VIDEO.value == "video"


def test_persona_status_distinguishes_planned_from_approved() -> None:
    assert PersonaStatus.PLANNED.value == "planned"
    assert PersonaStatus.APPROVED.value == "approved"
