"""Job -> GenerationSpec translation.

The adapter is the only place that knows both `app.schemas.Job` and the Core,
so these tests pin exactly what crosses that boundary.
"""
import pytest

from app.core.contracts import GENERATION_SPEC_FIELDS, GenerationKind, GenerationSpec
from app.schemas import GenerationType, Job
from app.spec_adapter import (
    DEFAULT_IMAGE_PROVIDER,
    DEFAULT_VIDEO_PROVIDER,
    compile_job,
    job_kind,
    resolve_model_id,
    spec_from_job,
)


def _image_job(**parameters) -> Job:
    return Job(
        type=GenerationType.IMAGE,
        prompt=parameters.pop("prompt", "a cinematic portrait"),
        parameters={"model": "flux-dev", **parameters},
    )


def _video_job(**parameters) -> Job:
    return Job(
        type=GenerationType.VIDEO,
        prompt=parameters.pop("prompt", "a slow dolly-in"),
        parameters={"mode": "text-to-video", **parameters},
    )


# --------------------------------------------------------------------- the kind


def test_image_jobs_are_classified_as_image() -> None:
    assert job_kind(_image_job()) is GenerationKind.IMAGE
    assert compile_job(_image_job()).spec.kind is GenerationKind.IMAGE


def test_video_jobs_are_classified_as_video() -> None:
    """`str()` of a `str, Enum` member is "GenerationType.VIDEO", not "video".

    Comparing the stringified enum silently classified every video job as an
    image, so this is pinned explicitly.
    """

    assert str(GenerationType.VIDEO) != "video"
    assert job_kind(_video_job()) is GenerationKind.VIDEO
    assert compile_job(_video_job()).spec.kind is GenerationKind.VIDEO


def test_a_plain_string_kind_is_also_accepted() -> None:
    class Duck:
        type = "video"
        prompt = "x"
        parameters: dict = {}

    assert job_kind(Duck()) is GenerationKind.VIDEO


# -------------------------------------------------------------------- the spec


def test_the_result_is_a_full_generation_spec() -> None:
    spec = spec_from_job(_image_job())
    assert isinstance(spec, GenerationSpec)
    for field_name in GENERATION_SPEC_FIELDS:
        assert hasattr(spec, field_name)


def test_the_prompt_is_compiled_and_the_original_is_kept() -> None:
    spec = spec_from_job(_image_job(prompt="a red car"))
    assert spec.prompt_original == "a red car"
    assert spec.prompt_compiled != "a red car"
    assert spec.prompt_compiled.startswith("a red car")


def test_image_sampling_parameters_travel_inside_the_spec() -> None:
    spec = spec_from_job(
        _image_job(aspect_ratio="1:1", resolution="2048", steps=36, seed=7, guidance_scale=8.0, ip_adapter_scale=0.4, controlnet="depth")
    )
    assert spec.aspect_ratio == "1:1"
    assert spec.resolution == 2048, "resolution arrives as a string and must be coerced"
    assert spec.steps == 36
    assert spec.seed == 7
    assert spec.guidance_scale == 8.0
    assert spec.ip_adapter_scale == 0.4
    assert spec.controlnet == "depth"


def test_video_timing_parameters_travel_inside_the_spec() -> None:
    spec = spec_from_job(_video_job(duration_seconds=10, fps=24, aspect_ratio="9:16"))
    assert spec.duration == 10.0
    assert spec.fps == 24
    assert spec.aspect_ratio == "9:16"
    assert spec.mode == "text-to-video"


def test_video_switches_travel_inside_the_spec() -> None:
    spec = spec_from_job(_video_job(cinematic_mode=False, slow_motion=True, native_audio=True))
    assert spec.cinematic_mode is False
    assert spec.slow_motion is True
    assert spec.native_audio is True


def test_the_workspace_becomes_the_owning_principal() -> None:
    assert spec_from_job(_image_job(workspace_id="ws-42")).user_id == "ws-42"
    assert spec_from_job(_image_job()).user_id is None


def test_a_neutral_camera_motion_does_not_override_the_style() -> None:
    """`camera_motion="static"` is the request default, not a direction."""

    styled = spec_from_job(_video_job(camera_motion="static")).camera
    assert styled, "the style's own camera motion must survive"
    assert spec_from_job(_video_job(camera_motion="orbit left")).camera == "orbit left"


def test_style_persona_and_shot_are_forwarded_when_present() -> None:
    spec = spec_from_job(_image_job(style="john-wick", persona_id="CHAR_PETRICK", shot="SH001"))
    assert spec.style_id == "john-wick"
    assert spec.persona_id == "CHAR_PETRICK"
    assert "Petrick Martins" in spec.prompt_compiled


def test_without_a_style_the_core_uses_its_own_default() -> None:
    assert spec_from_job(_image_job()).style_id == "cinematic-realism"


def test_a_lora_selected_on_the_request_is_carried_as_an_identifier() -> None:
    """The worker validates ownership and swaps in the resolved path."""

    assert spec_from_job(_image_job(lora_id="asset-1")).lora == "asset-1"


def test_an_empty_job_still_produces_a_valid_spec() -> None:
    spec = spec_from_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    assert spec.prompt_compiled
    assert spec.aspect_ratio == "16:9"
    assert spec.negative_prompt


def test_the_resolution_trace_is_available() -> None:
    result = compile_job(_image_job(style="john-wick"))
    assert result.trace.style_id == "john-wick"
    assert result.trace.sources


# ------------------------------------------------------------------- provider id


@pytest.mark.parametrize(
    "value,fallback,expected",
    [
        ("flux-dev", "fb", "black-forest-labs/FLUX.1-dev"),
        ("org/some-repo", "fb", "org/some-repo"),
        ("flux-1.1-pro-ultra", "fb", "fb"),
        ("", "fb", "fb"),
        (None, "fb", "fb"),
    ],
)
def test_resolve_model_id_never_invents_a_repository(value, fallback, expected) -> None:
    assert resolve_model_id(value, fallback) == expected


def test_the_worker_needs_no_fallback_because_the_adapter_already_resolved_it() -> None:
    assert spec_from_job(_image_job()).provider == "black-forest-labs/FLUX.1-dev"
    assert spec_from_job(_video_job()).provider == DEFAULT_VIDEO_PROVIDER
    assert resolve_model_id(None, DEFAULT_IMAGE_PROVIDER) == DEFAULT_IMAGE_PROVIDER
