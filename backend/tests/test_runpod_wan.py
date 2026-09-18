"""PR011 — ETAPA 7: the RunPod Wan connector, against a mocked cluster.

Same shape as `test_runpod_flux.py`: a real submit/poll/download lifecycle
against `FakeRunPod`, no network, no wall time.

The rule this file guards hardest is ETAPA 3's: **camera motion reaches the
cluster without the connector ever touching the Storyboard**. The Director
plans the move, the spec carries it as `motion` + `motion_strength`, and the
connector translates those two fields into the worker's vocabulary. There is a
source-level assertion at the bottom that no storyboard import appears here.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from gpu_fakes import PIXEL_PNG_BASE64, PIXEL_PNG_BYTES, FakeClock, FakeRunPod, NeverFinishes, gpu_client

from app.core.contracts import GenerationKind, GenerationSpec
from app.providers.base_provider import ProviderUnavailable, ProviderUnsupported
from app.providers.runpod_wan_provider import (
    CAMERA_MOTIONS,
    MAX_DURATION_SECONDS,
    MAX_FPS,
    MIN_DURATION_SECONDS,
    MIN_FPS,
    MODE_IMAGE_TO_VIDEO,
    MODE_TEXT_TO_VIDEO,
    RUNPOD_WAN_MODEL_ID,
    RUNPOD_WAN_PROVIDER_ID,
    RUNPOD_WAN_VRAM,
    RunPodWanProvider,
    dimensions_for_ratio,
    resolve_camera_motion,
    resolve_wan_mode,
    wan_request_from_spec,
)

VIDEO_OUTPUT = {"video": PIXEL_PNG_BASE64}


def spec(**overrides) -> GenerationSpec:
    fields = {
        "prompt_original": "a car on a coastal road",
        "prompt_compiled": "a car on a coastal road, golden hour, anamorphic",
        "negative_prompt": "blurry",
        "aspect_ratio": "16:9",
        "duration": 5.0,
        "fps": 24,
        "seed": 11,
        "motion": "slow push in",
        "motion_strength": 0.8,
        "kind": GenerationKind.VIDEO,
        "mode": MODE_TEXT_TO_VIDEO,
        "provider": RUNPOD_WAN_PROVIDER_ID,
    }
    fields.update(overrides)
    return GenerationSpec(**fields)


def provider(fake: FakeRunPod | None = None, **client_kwargs) -> tuple[RunPodWanProvider, FakeRunPod]:
    cluster = fake or FakeRunPod(polls_before_done=1, output=dict(VIDEO_OUTPUT))
    return RunPodWanProvider(client=gpu_client(cluster, FakeClock(), **client_kwargs)), cluster


def reference(tmp_path: Path) -> str:
    path = tmp_path / "first-frame.png"
    path.write_bytes(PIXEL_PNG_BYTES)
    return str(path)


# ---------------------------------------------------------------------------
# Identity and capabilities
# ---------------------------------------------------------------------------


def test_the_connector_identifies_itself() -> None:
    connector, _ = provider()

    assert connector.provider_id == "runpod-wan"
    assert connector.model_id == RUNPOD_WAN_MODEL_ID
    assert connector.vram == RUNPOD_WAN_VRAM
    assert connector.output_suffix == ".mp4"


def test_capabilities_claim_video_only_and_keep_the_public_shape() -> None:
    capabilities = RunPodWanProvider().capabilities()

    assert capabilities.supports_video is True
    assert capabilities.supports_image is False
    assert capabilities.supports_upscale is False
    assert capabilities.supports_seed is True
    assert capabilities.supports(GenerationKind.VIDEO) is True
    assert capabilities.supports(GenerationKind.IMAGE) is False


@pytest.mark.parametrize("mode", [MODE_TEXT_TO_VIDEO, MODE_IMAGE_TO_VIDEO])
def test_both_etapa_3_modes_are_supported(mode: str) -> None:
    assert RunPodWanProvider.supports_mode(mode) is True


def test_an_image_mode_is_not_claimed() -> None:
    assert RunPodWanProvider.supports_mode("inpaint") is False


def test_the_connector_declares_what_it_cannot_honour() -> None:
    assert "resolution" in RunPodWanProvider.UNSUPPORTED_SPEC_FIELDS
    assert "motion" in RunPodWanProvider.CONSUMED_SPEC_FIELDS
    assert not (RunPodWanProvider.CONSUMED_SPEC_FIELDS & RunPodWanProvider.UNSUPPORTED_SPEC_FIELDS)


# ---------------------------------------------------------------------------
# Duration, fps, seed
# ---------------------------------------------------------------------------


def test_duration_and_fps_produce_the_frame_count() -> None:
    request = wan_request_from_spec(spec(duration=4.0, fps=16))

    assert request.duration == 4.0
    assert request.fps == 16
    assert request.frames == 64
    assert request.clamped is False


@pytest.mark.parametrize(
    ("duration", "expected"),
    [(0.1, MIN_DURATION_SECONDS), (5.0, 5.0), (30.0, MAX_DURATION_SECONDS)],
)
def test_duration_is_clamped_to_what_the_endpoint_accepts(duration: float, expected: float) -> None:
    """Clamped and recorded, not rejected: a whole batch must not die over it."""

    request = wan_request_from_spec(spec(duration=duration))

    assert request.duration == expected
    assert request.clamped is (duration != expected)


@pytest.mark.parametrize(("fps", "expected"), [(4, MIN_FPS), (24, 24), (120, MAX_FPS)])
def test_fps_is_clamped_too(fps: int, expected: int) -> None:
    assert wan_request_from_spec(spec(fps=fps)).fps == expected


def test_the_clamp_is_recorded_in_the_asset_metadata(tmp_path) -> None:
    connector, _ = provider()

    asset = connector.generate_video(spec(duration=30.0), tmp_path)

    assert (asset.metadata or {})["clamped"] is True
    assert asset.duration_seconds == MAX_DURATION_SECONDS


def test_the_seed_is_forwarded_and_omitted_when_absent(tmp_path) -> None:
    connector, fake = provider()

    connector.generate_video(spec(seed=99), tmp_path)
    assert fake.submitted[0]["seed"] == 99

    connector.generate_video(spec(seed=None), tmp_path)
    assert "seed" not in fake.submitted[1]


# ---------------------------------------------------------------------------
# Camera motion — without the Storyboard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("motion", "token"),
    [
        ("slow push in", "push_in"),
        ("dolly in", "push_in"),
        ("pull back", "pull_out"),
        ("pan left", "pan_left"),
        ("tilt up", "tilt_up"),
        ("orbit", "orbit"),
        ("handheld", "handheld"),
        ("", "static"),
    ],
)
def test_director_motion_translates_to_the_worker_vocabulary(motion: str, token: str) -> None:
    assert resolve_camera_motion(spec(motion=motion)) == token


def test_motion_matching_ignores_case_and_padding() -> None:
    assert resolve_camera_motion(spec(motion="  Pan Right  ")) == "pan_right"


def test_an_unmapped_move_passes_through_instead_of_being_dropped() -> None:
    """A new Director move reaches the cluster before this table learns it."""

    assert resolve_camera_motion(spec(motion="whip pan")) == "whip pan"


def test_a_persona_lora_is_forwarded(tmp_path) -> None:
    connector, fake = provider()

    connector.generate_video(spec(lora="weights/petrick.safetensors"), tmp_path)

    assert fake.submitted[0]["lora"] == "weights/petrick.safetensors"


def test_the_request_is_serialisable_for_telemetry_and_tests() -> None:
    payload = wan_request_from_spec(spec()).to_dict()

    assert payload["camera_motion"] == "push_in"
    assert payload["frames"] == 120
    assert payload["clamped"] is False


def test_camera_motion_and_strength_reach_the_payload(tmp_path) -> None:
    connector, fake = provider()

    connector.generate_video(spec(motion="crane up", motion_strength=0.25), tmp_path)

    assert fake.submitted[0]["camera_motion"] == "crane_up"
    assert fake.submitted[0]["motion_strength"] == 0.25


def test_the_camera_table_maps_onto_known_tokens_only() -> None:
    assert CAMERA_MOTIONS[""] == "static"
    assert set(CAMERA_MOTIONS.values()) <= {
        "static",
        "push_in",
        "pull_out",
        "pan_left",
        "pan_right",
        "tilt_up",
        "tilt_down",
        "orbit",
        "crane_up",
        "handheld",
        "tracking",
    }


# ---------------------------------------------------------------------------
# Modes and dimensions
# ---------------------------------------------------------------------------


def test_the_image_default_mode_is_read_as_text_to_video() -> None:
    assert resolve_wan_mode(spec(mode="text-to-image")) == MODE_TEXT_TO_VIDEO


@pytest.mark.parametrize(
    ("ratio", "size"),
    [("16:9", (1280, 720)), ("9:16", (720, 1280)), ("1:1", (960, 960)), ("21:9", (1280, 720))],
)
def test_dimensions_follow_the_aspect_ratio_with_a_safe_default(ratio, size) -> None:
    assert dimensions_for_ratio(ratio) == size


def test_text_to_video_sends_no_reference(tmp_path) -> None:
    connector, fake = provider()

    connector.generate_video(spec(), tmp_path)

    assert "image" not in fake.submitted[0]
    assert fake.submitted[0]["mode"] == MODE_TEXT_TO_VIDEO


def test_image_to_video_uploads_the_first_frame(tmp_path) -> None:
    connector, fake = provider()

    connector.generate_video(
        spec(mode=MODE_IMAGE_TO_VIDEO, reference_path=reference(tmp_path)), tmp_path
    )

    assert fake.submitted[0]["image"].startswith("data:image/png;base64,")


def test_image_to_video_without_a_frame_is_a_fatal_value_error(tmp_path) -> None:
    connector, fake = provider()

    with pytest.raises(ValueError, match="reference_path"):
        connector.generate_video(spec(mode=MODE_IMAGE_TO_VIDEO), tmp_path)
    assert fake.calls == []


# ---------------------------------------------------------------------------
# The full lifecycle
# ---------------------------------------------------------------------------


def test_generate_video_submits_polls_downloads_and_writes_an_mp4(tmp_path) -> None:
    connector, fake = provider(FakeRunPod(polls_before_done=2, output=dict(VIDEO_OUTPUT)))

    asset = connector.generate_video(spec(), tmp_path)

    assert fake.paths == ["/run", "/status/job-1", "/status/job-1", "/status/job-1"]
    written = Path(asset.path)
    assert written.suffix == ".mp4"
    assert written.read_bytes() == PIXEL_PNG_BYTES
    assert asset.kind == "video"
    assert asset.duration_seconds == 5.0
    assert asset.fps == 24


def test_the_metadata_traces_the_job_and_the_move(tmp_path) -> None:
    connector, _ = provider()

    metadata = connector.generate_video(spec(), tmp_path).metadata or {}

    assert metadata["job_id"] == "job-1"
    assert metadata["camera_motion"] == "push_in"
    assert metadata["num_frames"] == 120
    assert metadata["vram"] == RUNPOD_WAN_VRAM
    assert "rp-test-key" not in repr(metadata)


def test_a_video_url_result_is_downloaded(tmp_path) -> None:
    connector, _ = provider(
        FakeRunPod(polls_before_done=0, output={"video_url": "https://cdn.example.test/job-1.mp4"})
    )

    assert Path(connector.generate_video(spec(), tmp_path).path).read_bytes() == PIXEL_PNG_BYTES


# ---------------------------------------------------------------------------
# Failure translation
# ---------------------------------------------------------------------------


def test_an_unconfigured_cluster_is_unavailable(tmp_path) -> None:
    connector = RunPodWanProvider(client=gpu_client(FakeRunPod(), api_key="", endpoint=""))

    with pytest.raises(ProviderUnavailable, match="BROBOND_RUNPOD_ENDPOINT"):
        connector.generate_video(spec(), tmp_path)


def test_a_failed_render_becomes_provider_unavailable(tmp_path) -> None:
    connector, _ = provider(
        FakeRunPod(polls_before_done=0, final_status="FAILED", error="worker crashed")
    )

    with pytest.raises(ProviderUnavailable, match="worker crashed"):
        connector.generate_video(spec(), tmp_path)


def test_a_long_render_that_never_finishes_is_cancelled_and_reported(tmp_path) -> None:
    connector, fake = provider(NeverFinishes(), timeout=6.0, poll_interval=2.0)

    with pytest.raises(ProviderUnavailable, match="did not finish"):
        connector.generate_video(spec(), tmp_path)
    assert fake.cancelled == ["job-1"]


def test_image_and_upscale_are_refused_rather_than_faked(tmp_path) -> None:
    connector, _ = provider()

    with pytest.raises(ProviderUnsupported, match="image generation"):
        connector.generate_image(spec(kind=GenerationKind.IMAGE), tmp_path)
    with pytest.raises(ProviderUnsupported, match="upscale"):
        connector.upscale(spec(), tmp_path / "x.mp4", tmp_path)


# ---------------------------------------------------------------------------
# Health and estimates
# ---------------------------------------------------------------------------


def test_health_is_ready_when_the_cluster_answers() -> None:
    connector, _ = provider()

    report = connector.health()

    assert report.status == "ready"
    assert report.capabilities.supports_video is True
    assert "rp-test-key" not in repr(report.to_dict())


def test_health_is_unavailable_when_unconfigured() -> None:
    connector = RunPodWanProvider(client=gpu_client(FakeRunPod(), api_key="", endpoint=""))

    assert connector.health().status == "unavailable"


def test_the_estimate_scales_with_the_clamped_duration() -> None:
    connector, _ = provider()

    assert connector.estimate(spec(duration=3.0)).estimated_seconds == 60.0
    assert connector.estimate(spec(duration=30.0)).estimated_seconds == 200.0
    assert connector.estimate(spec()).kind == "video"


# ---------------------------------------------------------------------------
# Architecture guards
# ---------------------------------------------------------------------------


def test_the_connector_receives_only_the_spec() -> None:
    assert list(inspect.signature(RunPodWanProvider.generate_video).parameters) == [
        "self",
        "spec",
        "output_dir",
    ]


def test_the_connector_never_touches_the_storyboard() -> None:
    """ETAPA 3, enforced at source level and not only by convention."""

    source = Path("backend/app/providers/runpod_wan_provider.py").read_text(encoding="utf-8")
    for banned in (
        "from ..core.storyboard_engine",
        "from ..core.director",
        "import storyboard",
        "StoryboardState",
        "SceneBeat",
        "ShotPlan",
    ):
        assert banned not in source, f"{banned!r} would couple execution to planning"


def test_the_connector_never_speaks_http() -> None:
    source = Path("backend/app/providers/runpod_wan_provider.py").read_text(encoding="utf-8")
    for banned in ("import httpx", "Authorization", "status_code", "await "):
        assert banned not in source
