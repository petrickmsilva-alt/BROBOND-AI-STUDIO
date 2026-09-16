"""PR009 — REAL AI CONNECTORS (ETAPA 8).

Covers the five new guarantees, each with the component that owns it:

* Retry    — `providers/retry_policy.py` (states retryable/fatal/timeout/backoff,
             at most 3 attempts)
* Timeout  — `providers/timeout_manager.py` (Flux 90s, Wan 300s, ENV-tunable)
* Fallback — `providers/generation_executor.py` (unavailable -> Registry ->
             MockProvider, reason recorded on the Job, batch never lost)
* Health   — `ProviderHealth.last_health_at` stamped by the registry
* Executor — Flux/Wan real connectors receive only `GenerationSpec`
             (text-to-image / image-to-image / text-to-video / image-to-video,
             seed, negative_prompt, lora, aspect_ratio, duration, fps,
             motion_strength)
"""
from __future__ import annotations

import inspect
import json
import sys
import time
import types as types_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core.contracts import GenerationKind, GenerationSpec
from app.main import app
from app.providers import flux_provider as flux_module
from app.providers import wan_provider as wan_module
from app.providers.base_provider import (
    BaseProvider,
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
    ProviderJob,
    ProviderNotFound,
    ProviderTimeoutError,
    ProviderUnavailable,
    ProviderUnsupported,
)
from app.providers.flux_provider import (
    FLUX_MODES,
    MODE_IMAGE_TO_IMAGE,
    MODE_TEXT_TO_IMAGE,
    FluxProvider,
    flux_pipeline_arguments,
    flux_request_from_spec,
    resolve_flux_mode,
)
from app.providers.generation_executor import GenerationExecution, GenerationExecutor
from app.providers.mock_provider import MockProvider
from app.providers.provider_registry import (
    ProviderRegistration,
    ProviderRegistry,
    create_default_registry,
)
from app.providers.retry_policy import (
    MAX_ATTEMPTS,
    RetryDecision,
    RetryEngine,
    RetryPolicy,
    RetryState,
)
from app.providers.telemetry import (
    ERROR_FATAL,
    ERROR_GENERATION,
    ERROR_NOT_REGISTERED,
    ERROR_TIMEOUT,
    ERROR_UNAVAILABLE,
    ERROR_UNSUPPORTED,
    ProviderTelemetryRecord,
    TelemetryStore,
)
from app.providers.timeout_manager import TimeoutManager
from app.providers.wan_provider import (
    MODE_IMAGE_TO_VIDEO,
    MODE_TEXT_TO_VIDEO,
    WAN_MODES,
    HunyuanProvider,
    WanProvider,
    hunyuan_frame_count,
    wan_frame_count,
    wan_pipeline_arguments,
)

client = TestClient(app)


def spec(**overrides) -> GenerationSpec:
    base = {
        "prompt_original": "human brief",
        "prompt_compiled": "compiled cinematic prompt",
        "provider": "mock",
        "kind": GenerationKind.IMAGE,
        "duration": 5,
        "fps": 24,
    }
    base.update(overrides)
    return GenerationSpec(**base)


def fast_engine() -> RetryEngine:
    """Retry engine whose backoff is observed, never slept."""

    return RetryEngine(RetryPolicy(), sleeper=lambda _seconds: None)


def registry_with(*providers: BaseProvider, kinds=()) -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(
            ProviderRegistration(
                provider_id=provider.provider_id,
                label=provider.label,
                factory=lambda model_id=None, _provider=provider: _provider,
                default_for=kinds,
            )
        )
    return registry


class ScriptedProvider(BaseProvider):
    """Test double whose generate_image follows a script of outcomes."""

    provider_id = "scripted"
    label = "Scripted"
    version = "scripted-v1"

    def __init__(self, script: list, *, provider_id: str = "scripted") -> None:
        self.provider_id = provider_id
        self.script = list(script)
        self.calls = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_resolution="1024",
            supports_video=True,
            supports_image=True,
            supports_lora=True,
            supports_upscale=False,
            supports_seed=True,
            supports_negative_prompt=True,
        )

    def generate_image(self, spec_: GenerationSpec, output_dir) -> ProviderAsset:
        return self._next(spec_, output_dir, "image", "png")

    def generate_video(self, spec_: GenerationSpec, output_dir) -> ProviderAsset:
        return self._next(spec_, output_dir, "video", "mp4")

    def _next(self, spec_: GenerationSpec, output_dir, kind: str, extension: str) -> ProviderAsset:
        self.calls += 1
        outcome = self.script.pop(0) if self.script else "ok"
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome == "ok":
            path = Path(output_dir) / f"{spec_.spec_id}.{extension}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"scripted")
            if kind == "image":
                return ProviderAsset(str(path), kind, self.provider_id, width=64, height=64)
            return ProviderAsset(
                str(path), kind, self.provider_id, duration_seconds=spec_.duration, fps=spec_.fps
            )
        raise AssertionError(f"unknown script outcome {outcome!r}")

    def upscale(self, spec_: GenerationSpec, asset_path, output_dir) -> ProviderAsset:
        raise ProviderUnsupported("scripted does not upscale")

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            id=self.provider_id,
            label=self.label,
            status="ready",
            latency_ms=0.0,
            version=self.version,
            capabilities=self.capabilities(),
        )

    def estimate(self, spec_: GenerationSpec) -> ProviderEstimate:
        return ProviderEstimate(self.provider_id, spec_.kind.value, 0.1)


# ---------------------------------------------------------------------------
# ETAPA 3 — Retry engine
# ---------------------------------------------------------------------------


def test_retry_states_are_the_four_the_pr_declares() -> None:
    assert {state.value for state in RetryState} == {"retryable", "fatal", "timeout", "backoff"}


def test_the_attempt_ceiling_is_three_and_enforced() -> None:
    assert MAX_ATTEMPTS == 3
    assert RetryPolicy(max_attempts=3).max_attempts == 3
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=4)
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ProviderTimeoutError("deadline"), RetryState.TIMEOUT),
        (TimeoutError(), RetryState.TIMEOUT),
        (ConnectionError(), RetryState.TIMEOUT),
        (ProviderUnsupported("nope"), RetryState.FATAL),
        (ValueError("bad spec"), RetryState.FATAL),
        (TypeError("bad call"), RetryState.FATAL),
        (KeyError("missing"), RetryState.FATAL),
        (ProviderNotFound("gone"), RetryState.RETRYABLE),
        (ProviderUnavailable("down"), RetryState.RETRYABLE),
        (RuntimeError("CUDA exploded"), RetryState.RETRYABLE),
        (OSError("disk"), RetryState.RETRYABLE),
    ],
)
def test_classification_maps_errors_onto_states(error, expected) -> None:
    assert RetryPolicy().classify(error) is expected


def test_a_first_try_success_spends_one_attempt_and_no_decisions() -> None:
    outcome = fast_engine().attempt(lambda: "asset")
    assert outcome.success is True
    assert outcome.result == "asset"
    assert outcome.attempts == 1
    assert outcome.decisions == ()
    assert outcome.final_state is None


def test_a_transient_failure_is_retried_after_backoff() -> None:
    slept: list[float] = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return "asset"

    engine = RetryEngine(RetryPolicy(base_delay_seconds=0.5), sleeper=slept.append)
    outcome = engine.attempt(flaky)

    assert outcome.success is True
    assert outcome.attempts == 2
    states = [decision.state for decision in outcome.decisions]
    assert states == [RetryState.RETRYABLE, RetryState.BACKOFF]
    assert slept == [0.5]
    assert outcome.decisions[0].reason == "transient"
    assert outcome.decisions[1].reason == "backoff before attempt 2"


def test_three_failures_exhaust_the_budget_and_raise_from_run() -> None:
    def always_broken():
        raise RuntimeError("still broken")

    engine = fast_engine()
    outcome = engine.attempt(always_broken)

    assert outcome.success is False
    assert outcome.attempts == 3
    error_states = [d.state for d in outcome.decisions if d.state is not RetryState.BACKOFF]
    assert error_states == [RetryState.RETRYABLE] * 3
    backoffs = [d for d in outcome.decisions if d.state is RetryState.BACKOFF]
    assert len(backoffs) == 2, "no backoff after the final attempt"
    assert outcome.final_state is RetryState.RETRYABLE
    with pytest.raises(RuntimeError, match="still broken"):
        engine.run(always_broken)


def test_a_fatal_error_stops_on_the_first_attempt_with_no_backoff() -> None:
    def broken_spec():
        raise ValueError("image-to-image without reference")

    outcome = fast_engine().attempt(broken_spec)

    assert outcome.success is False
    assert outcome.attempts == 1
    assert [d.state for d in outcome.decisions] == [RetryState.FATAL]
    assert outcome.final_state is RetryState.FATAL


def test_timeouts_are_their_own_state_but_still_retryable() -> None:
    calls = {"n": 0}

    def slow_then_fast():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderTimeoutError("deadline exceeded")
        return "asset"

    outcome = fast_engine().attempt(slow_then_fast)
    assert outcome.success is True
    assert outcome.decisions[0].state is RetryState.TIMEOUT


def test_backoff_grows_geometrically_and_is_capped() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, backoff_factor=2.0, max_delay_seconds=1.5)
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(2) == 1.5  # 2.0 capped
    assert policy.delay_for(3) == 1.5


def test_the_decision_hook_sees_every_step() -> None:
    seen: list[RetryDecision] = []
    engine = RetryEngine(RetryPolicy(), sleeper=lambda _s: None, on_decision=seen.append)

    def twice_broken():
        if len([d for d in seen if d.state is RetryState.RETRYABLE]) < 2:
            raise RuntimeError("boom")
        return "ok"

    assert engine.run(twice_broken) == "ok"
    assert [d.state for d in seen] == [
        RetryState.RETRYABLE,
        RetryState.BACKOFF,
        RetryState.RETRYABLE,
        RetryState.BACKOFF,
    ]


def test_retry_decision_serialises() -> None:
    decision = RetryDecision(RetryState.BACKOFF, 1, 3, 0.25, "backoff before attempt 2")
    assert decision.to_dict() == {
        "state": "backoff",
        "attempt": 1,
        "max_attempts": 3,
        "delay_seconds": 0.25,
        "reason": "backoff before attempt 2",
    }
    assert decision.is_last_attempt is False


# ---------------------------------------------------------------------------
# ETAPA 4 — Timeout manager
# ---------------------------------------------------------------------------


def test_flux_wan_and_default_deadlines_are_90_300_and_120() -> None:
    manager = TimeoutManager()
    assert manager.seconds_for("flux-dev") == 90.0
    assert manager.seconds_for("flux") == 90.0
    assert manager.seconds_for("wan-2.1-t2v") == 300.0
    assert manager.seconds_for("wan") == 300.0
    assert manager.seconds_for("hunyuan-video") == 300.0
    assert manager.seconds_for("mock") == 120.0
    assert manager.seconds_for(None) == 120.0
    assert manager.seconds_for("never-heard-of") == 120.0


def test_the_deadlines_are_configurable_via_env(monkeypatch) -> None:
    monkeypatch.setenv("BROBOND_PROVIDER_TIMEOUT_FLUX_SECONDS", "45")
    monkeypatch.setenv("BROBOND_PROVIDER_TIMEOUT_WAN_SECONDS", "600")
    monkeypatch.setenv("BROBOND_PROVIDER_TIMEOUT_DEFAULT_SECONDS", "33")
    fresh = Settings()
    assert fresh.provider_timeout_flux_seconds == 45.0
    assert fresh.provider_timeout_wan_seconds == 600.0
    assert fresh.provider_timeout_default_seconds == 33.0

    monkeypatch.setattr(settings, "provider_timeout_flux_seconds", 45.0)
    manager = TimeoutManager()
    assert manager.seconds_for("flux-dev") == 45.0


def test_timeout_overrides_win_over_settings() -> None:
    manager = TimeoutManager(overrides={"flux-dev": 7.5}, default_seconds=9.0)
    assert manager.seconds_for("flux-dev") == 7.5
    assert manager.seconds_for("anything-else") == 9.0


def test_run_returns_the_result_inside_the_deadline() -> None:
    assert TimeoutManager().run("mock", lambda: "done", seconds=1.0) == "done"


def test_run_raises_provider_timeout_when_the_deadline_expires() -> None:
    with pytest.raises(ProviderTimeoutError, match="exceeded its 0.05s deadline"):
        TimeoutManager().run("flux-dev", lambda: time.sleep(0.3), seconds=0.05)


def test_run_propagates_provider_errors_untouched() -> None:
    def broken():
        raise RuntimeError("GPU fell over")

    with pytest.raises(RuntimeError, match="GPU fell over"):
        TimeoutManager().run("flux-dev", broken, seconds=1.0)


def test_a_zero_deadline_disables_the_guard() -> None:
    calls = {"n": 0}

    def quick():
        calls["n"] += 1
        return "direct"

    assert TimeoutManager().run("mock", quick, seconds=0) == "direct"
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# ETAPA 6 — Telemetry
# ---------------------------------------------------------------------------


def _record(**overrides) -> ProviderTelemetryRecord:
    base = {
        "provider_id": "mock",
        "requested_provider_id": "mock",
        "spec_id": "spec-1",
        "kind": "image",
        "success": True,
        "error_code": None,
        "latency_ms": 12.0,
        "queue_time_ms": 2.0,
        "render_time_ms": 10.0,
    }
    base.update(overrides)
    return ProviderTelemetryRecord(**base)


def test_the_telemetry_record_carries_every_field_the_pr_names() -> None:
    payload = _record().to_dict()
    assert {
        "provider_id",
        "latency_ms",
        "queue_time_ms",
        "render_time_ms",
        "success",
        "error_code",
    } <= set(payload)
    assert payload["at"], "records carry their own timestamp"


def test_the_store_keeps_newest_first_and_respects_the_cap() -> None:
    store = TelemetryStore(limit=2)
    store.record(_record(spec_id="a"))
    store.record(_record(spec_id="b"))
    store.record(_record(spec_id="c"))

    recent = store.recent(10)
    assert [record.spec_id for record in recent] == ["c", "b"]
    assert len(store) == 2
    assert store.recent(1)[0].spec_id == "c"
    assert store.recent(0) == ()
    store.clear()
    assert len(store) == 0


def test_the_jsonl_sink_persists_each_record(tmp_path) -> None:
    log = tmp_path / "telemetry" / "records.jsonl"
    store = TelemetryStore(log_path=log)
    store.record(_record(spec_id="one"))
    store.record(_record(spec_id="two", success=False, error_code=ERROR_TIMEOUT))

    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [entry["spec_id"] for entry in lines] == ["one", "two"]
    assert lines[1]["success"] is False
    assert lines[1]["error_code"] == "timeout"
    assert store.log_path == log


def test_a_broken_sink_never_takes_telemetry_down(tmp_path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("file in the way of the directory")
    store = TelemetryStore(log_path=blocker / "inside" / "records.jsonl")

    entry = store.record(_record())

    assert len(store) == 1, "the in-memory record still happened"
    assert entry is not None


def test_the_error_code_taxonomy_is_machine_readable() -> None:
    codes = {
        ERROR_TIMEOUT,
        ERROR_UNAVAILABLE,
        ERROR_UNSUPPORTED,
        ERROR_GENERATION,
        ERROR_NOT_REGISTERED,
        ERROR_FATAL,
    }
    assert len(codes) == 6
    assert all(isinstance(code, str) and code for code in codes)


# ---------------------------------------------------------------------------
# Flux real connector (ETAPA 1)
# ---------------------------------------------------------------------------


def test_flux_modes_cover_text_and_image_to_image() -> None:
    assert FLUX_MODES == (MODE_TEXT_TO_IMAGE, MODE_IMAGE_TO_IMAGE)
    assert resolve_flux_mode(spec(mode="image-to-image")) == MODE_IMAGE_TO_IMAGE
    assert resolve_flux_mode(spec(mode="text-to-image")) == MODE_TEXT_TO_IMAGE
    # A spec carrying the video default still renders its prompt as an image.
    assert resolve_flux_mode(spec(mode="text-to-video")) == MODE_TEXT_TO_IMAGE


def test_the_flux_request_is_built_only_from_the_spec_and_never_the_raw_prompt() -> None:
    request = flux_request_from_spec(
        spec(aspect_ratio="9:16", resolution=2048, seed=11, lora="loras/x.safetensors", negative_prompt="blurry")
    )
    assert request.prompt == "compiled cinematic prompt"
    assert "human brief" not in request.to_dict().values(), "prompt_original must never reach the connector"
    assert request.seed == 11
    assert request.lora == "loras/x.safetensors"
    assert request.negative_prompt == "blurry"
    assert (request.width, request.height) == (1152, 2048)
    assert request.reference_path is None


def test_flux_image_to_image_carries_the_reference_and_refuses_to_invent_one(tmp_path) -> None:
    source = tmp_path / "reference.png"
    source.write_bytes(b"png-bytes")
    request = flux_request_from_spec(spec(mode="image-to-image", reference_path=str(source)))
    assert request.mode == MODE_IMAGE_TO_IMAGE
    assert request.reference_path == str(source)

    provider = FluxProvider()
    with pytest.raises(ValueError, match="reference_path"):
        provider.generate_image(spec(mode="image-to-image"), tmp_path)


def test_flux_pipeline_arguments_map_every_supported_control(monkeypatch) -> None:
    monkeypatch.setattr(flux_module, "generator_for", lambda seed: ("generator", seed))
    request = flux_request_from_spec(spec(seed=7, steps=40, guidance_scale=3.5, negative_prompt="text"))
    arguments = flux_pipeline_arguments(request)

    assert arguments["prompt"] == "compiled cinematic prompt"
    assert arguments["negative_prompt"] == "text"
    assert arguments["generator"] == ("generator", 7)
    assert arguments["num_inference_steps"] == 40
    assert arguments["guidance_scale"] == 3.5
    assert "image" not in arguments


def test_flux_image_to_image_arguments_load_the_reference_image(tmp_path, monkeypatch) -> None:
    from PIL import Image

    monkeypatch.setattr(flux_module, "generator_for", lambda seed: None)
    source = tmp_path / "ref.png"
    Image.new("RGB", (64, 32), color=(255, 0, 0)).save(source)

    request = flux_request_from_spec(spec(mode="image-to-image", reference_path=str(source)))
    arguments = flux_pipeline_arguments(request)

    assert arguments["image"].size == (64, 32)


def fake_flux_pipeline(seen: dict):
    class FakePipeline:
        def __call__(self, **kwargs):
            seen["kwargs"] = kwargs

            def save(path):
                Path(path).write_bytes(b"flux-render")

            return SimpleNamespace(images=[SimpleNamespace(save=save, size=(1024, 576))])

    return FakePipeline()


def test_flux_generate_image_runs_the_spec_through_the_pipeline(tmp_path, monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(flux_module, "generator_for", lambda seed: ("generator", seed))
    provider = FluxProvider(
        model_id="org/checkpoint", pipeline_loader=lambda model_id, mode: fake_flux_pipeline(seen)
    )

    asset = provider.generate_image(
        spec(provider="flux-dev", seed=7, lora=None, aspect_ratio="16:9"), tmp_path
    )

    assert asset.kind == "image"
    assert asset.provider_id == "flux-dev"
    assert (asset.width, asset.height) == (1024, 576)
    assert Path(asset.path).read_bytes() == b"flux-render"
    assert seen["kwargs"]["prompt"] == "compiled cinematic prompt"
    assert asset.metadata["mode"] == "text-to-image"
    assert asset.metadata["model_id"] == "org/checkpoint"


def test_flux_load_refuses_without_diffusers_and_reports_it_in_health() -> None:
    provider = FluxProvider()
    with pytest.raises(RuntimeError, match="Diffusers GPU dependencies"):
        provider._pipeline_for(MODE_TEXT_TO_IMAGE)

    report = provider.health()
    assert report.status in {"ready", "unavailable"}
    assert report.last_health_at, "health reports carry their timestamp"
    assert report.capabilities.supports_image is True
    with pytest.raises(ProviderUnavailable, match="video generation"):
        provider.generate_video(spec(kind=GenerationKind.VIDEO), "nowhere")
    with pytest.raises(ProviderUnavailable, match="upscale"):
        provider.upscale(spec(), "nowhere", "nowhere")
    assert provider.estimate(spec()).estimated_seconds > 0


def test_no_flux_entrypoint_accepts_a_prompt_string_or_a_parameters_dict() -> None:
    for method in (FluxProvider.generate_image, FluxProvider.generate_video, FluxProvider.upscale):
        parameters = inspect.signature(method).parameters
        assert "prompt" not in parameters
        assert "parameters" not in parameters
    source = Path("backend/app/providers/flux_provider.py").read_text(encoding="utf-8")
    assert "prompt_original" not in source, "the raw prompt must never reach the connector"


# ---------------------------------------------------------------------------
# Wan real connector (ETAPA 2)
# ---------------------------------------------------------------------------


def test_wan_modes_cover_text_and_image_to_video() -> None:
    assert WAN_MODES == (MODE_TEXT_TO_VIDEO, MODE_IMAGE_TO_VIDEO)


def test_wan_frame_counts_follow_the_4n_plus_1_rule_and_hunyuan_does_not() -> None:
    clip = spec(fps=24, duration=5)
    assert wan_frame_count(clip) == 121
    assert hunyuan_frame_count(clip) == 120
    odd = spec(fps=30, duration=2)
    assert wan_frame_count(odd) % 4 == 1
    assert hunyuan_frame_count(odd) == 60
    assert wan_frame_count(spec(fps=1, duration=0.2)) >= 1


def test_the_wan_request_carries_duration_fps_motion_and_seed() -> None:
    provider = WanProvider()
    request = provider.request_from_spec(
        spec(kind=GenerationKind.VIDEO, duration=6, fps=16, motion_strength=0.4, seed=3, aspect_ratio="9:16")
    )
    assert request.mode == MODE_TEXT_TO_VIDEO
    assert request.prompt == "compiled cinematic prompt"
    assert request.duration == 6.0
    assert request.fps == 16
    assert request.motion_strength == 0.4
    assert request.seed == 3
    assert (request.width, request.height) == (480, 832)
    assert "human brief" not in request.to_dict().values()


def test_wan_pipeline_arguments_include_motion_strength_and_never_steps(monkeypatch) -> None:
    monkeypatch.setattr(wan_module, "generator_for", lambda seed: None)
    request = WanProvider().request_from_spec(spec(kind=GenerationKind.VIDEO, motion_strength=0.7))
    arguments = wan_pipeline_arguments(request, frame_count=121)

    assert arguments["motion_strength"] == 0.7
    assert arguments["num_frames"] == 121
    assert arguments["prompt"] == "compiled cinematic prompt"
    assert "num_inference_steps" not in arguments
    assert "image" not in arguments


def test_wan_image_to_video_requires_and_loads_the_reference(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wan_module, "generator_for", lambda seed: None)
    provider = WanProvider()
    request = provider.request_from_spec(
        spec(kind=GenerationKind.VIDEO, mode="image-to-video", reference_path=str(tmp_path / "x.png"))
    )
    assert request.reference_path is not None

    with pytest.raises(ValueError, match="reference_path"):
        provider.generate_video(spec(kind=GenerationKind.VIDEO, mode="image-to-video"), tmp_path)


def _install_fake_imageio(monkeypatch, written: dict) -> None:
    def fake_imwrite(target, frames, fps=None, codec=None):
        written["fps"] = fps
        written["codec"] = codec
        Path(target).write_bytes(b"wan-render")

    module = types_module.ModuleType("imageio.v3")
    module.imwrite = fake_imwrite
    parent = types_module.ModuleType("imageio")
    parent.v3 = module
    monkeypatch.setitem(sys.modules, "imageio", parent)
    monkeypatch.setitem(sys.modules, "imageio.v3", module)


def test_wan_generate_video_encodes_at_the_spec_fps(tmp_path, monkeypatch) -> None:
    written: dict = {}
    _install_fake_imageio(monkeypatch, written)
    seen: dict = {}

    class FakePipeline:
        def __call__(self, **kwargs):
            seen["kwargs"] = kwargs
            return SimpleNamespace(frames=[[object()]])

    monkeypatch.setattr(wan_module, "generator_for", lambda seed: None)
    provider = WanProvider(pipeline_loader=lambda model_id, class_name: FakePipeline())

    asset = provider.generate_video(
        spec(provider="wan-2.1-t2v", kind=GenerationKind.VIDEO, fps=24, duration=5), tmp_path
    )

    assert asset.kind == "video"
    assert asset.duration_seconds == 5.0
    assert asset.fps == 24
    assert written == {"fps": 24, "codec": "libx264"}
    assert Path(asset.path).read_bytes() == b"wan-render"
    assert seen["kwargs"]["num_frames"] == 121
    assert asset.metadata["num_frames"] == 121
    assert asset.metadata["mode"] == MODE_TEXT_TO_VIDEO


def test_wan_image_to_video_uses_the_i2v_pipeline(tmp_path, monkeypatch) -> None:
    from PIL import Image

    written: dict = {}
    _install_fake_imageio(monkeypatch, written)
    seen: dict = {}

    class FakePipeline:
        def __call__(self, **kwargs):
            seen["kwargs"] = kwargs
            return SimpleNamespace(frames=[[object()]])

    loaded: dict = {}

    def loader(model_id, class_name):
        loaded["class"] = class_name
        return FakePipeline()

    monkeypatch.setattr(wan_module, "generator_for", lambda seed: None)
    source = tmp_path / "frame.png"
    Image.new("RGB", (32, 32)).save(source)
    provider = WanProvider(pipeline_loader=loader)

    asset = provider.generate_video(
        spec(kind=GenerationKind.VIDEO, mode="image-to-video", reference_path=str(source)), tmp_path
    )

    assert loaded["class"] == "WanImageToVideoPipeline"
    assert seen["kwargs"]["image"].size == (32, 32)
    assert asset.metadata["mode"] == MODE_IMAGE_TO_VIDEO


def test_hunyuan_keeps_its_own_frame_rule_steps_and_refuses_image_to_video(tmp_path) -> None:
    provider = HunyuanProvider()
    clip = spec(kind=GenerationKind.VIDEO, fps=24, duration=5, steps=40)
    assert provider.frame_count(clip) == 120

    arguments = provider.pipeline_arguments(provider.request_from_spec(clip), frame_count=120)
    assert arguments["num_inference_steps"] == 40

    assert "generate_video" not in WanProvider.__dict__, "Wan and Hunyuan share one implementation"
    assert "generate_video" not in HunyuanProvider.__dict__
    with pytest.raises(ProviderUnsupported, match="image-to-video"):
        provider.generate_video(spec(kind=GenerationKind.VIDEO, mode="image-to-video"), tmp_path)
    with pytest.raises(ProviderUnavailable, match="image generation"):
        provider.generate_image(spec(), tmp_path)
    report = provider.health()
    assert report.last_health_at


def test_the_wan_connector_fields_are_declared_not_implicit() -> None:
    import dataclasses

    declared = {field.name for field in dataclasses.fields(GenerationSpec)}
    assert WanProvider.CONSUMED_SPEC_FIELDS <= declared
    assert HunyuanProvider.CONSUMED_SPEC_FIELDS <= declared
    assert not (WanProvider.CONSUMED_SPEC_FIELDS & WanProvider.UNSUPPORTED_SPEC_FIELDS)
    assert "motion_strength" in WanProvider.CONSUMED_SPEC_FIELDS
    assert "steps" in HunyuanProvider.CONSUMED_SPEC_FIELDS
    assert "steps" not in WanProvider.CONSUMED_SPEC_FIELDS


# ---------------------------------------------------------------------------
# ETAPA 5 — Fallback chain in the executor
# ---------------------------------------------------------------------------


def test_a_missing_provider_falls_back_and_registers_the_reason(tmp_path) -> None:
    registry = registry_with(MockProvider())
    store = TelemetryStore()
    executor = GenerationExecutor(registry, retry_engine=fast_engine(), telemetry_store=store)

    execution = executor.execute(spec(provider="ghost"), tmp_path, job_id="job-ghost")

    assert execution.asset.kind == "image"
    assert execution.job.status == "complete"
    assert execution.job.fallback is True
    assert execution.job.fallback_from == "ghost"
    assert "not registered" in (execution.job.fallback_reason or "")
    assert execution.job.attempts == 0, "no attempt was spent on a provider that does not exist"
    record = store.recent(1)[0]
    assert record.provider_id == "mock"
    assert record.requested_provider_id == "ghost"
    assert record.error_code == ERROR_NOT_REGISTERED
    assert record.success is True


def test_a_kind_mismatch_falls_back_with_the_reason(tmp_path) -> None:
    registry = create_default_registry()
    store = TelemetryStore()
    executor = GenerationExecutor(registry, retry_engine=fast_engine(), telemetry_store=store)

    execution = executor.execute(
        spec(provider="flux-dev", kind=GenerationKind.VIDEO), tmp_path
    )

    assert execution.job.fallback is True
    assert execution.asset.kind == "video"
    assert "cannot generate video" in (execution.job.fallback_reason or "")
    assert store.recent(1)[0].error_code == ERROR_UNAVAILABLE


def test_retryable_failures_exhaust_the_budget_then_fall_back(tmp_path) -> None:
    broken = ScriptedProvider([RuntimeError("x")] * 3)
    registry = registry_with(broken, MockProvider())
    store = TelemetryStore()
    executor = GenerationExecutor(registry, retry_engine=fast_engine(), telemetry_store=store)

    execution = executor.execute(spec(provider="scripted"), tmp_path, job_id="job-flaky")

    assert broken.calls == 3, "the whole attempt budget is spent before falling back"
    assert execution.job.fallback is True
    assert execution.job.provider_id == "mock"
    assert execution.job.fallback_from == "scripted"
    assert "failed after 3 attempts" in (execution.job.fallback_reason or "")
    record = store.recent(1)[0]
    assert record.error_code == ERROR_GENERATION
    assert record.attempts == 3
    assert record.fallback_reason == execution.job.fallback_reason


def test_a_transient_failure_that_recovers_never_touches_the_fallback(tmp_path) -> None:
    flaky = ScriptedProvider([RuntimeError("once"), "ok"])
    registry = registry_with(flaky, MockProvider())
    store = TelemetryStore()
    executor = GenerationExecutor(registry, retry_engine=fast_engine(), telemetry_store=store)

    execution = executor.execute(spec(provider="scripted"), tmp_path)

    assert flaky.calls == 2
    assert execution.job.fallback is False
    assert execution.job.provider_id == "scripted"
    assert execution.job.attempts == 2
    record = store.recent(1)[0]
    assert record.success is True
    assert record.error_code is None
    assert record.fallback is False


def test_timeouts_fall_back_with_the_timeout_reason(tmp_path) -> None:
    class SlowProvider(ScriptedProvider):
        def generate_image(self, spec_, output_dir):
            time.sleep(0.2)
            return super().generate_image(spec_, output_dir)

    slow = SlowProvider(["ok"] * 3, provider_id="slow-image")
    registry = registry_with(slow, MockProvider())
    store = TelemetryStore()
    executor = GenerationExecutor(
        registry,
        retry_engine=fast_engine(),
        timeout_manager=TimeoutManager(overrides={"slow-image": 0.05}, default_seconds=0.05),
        telemetry_store=store,
    )

    execution = executor.execute(spec(provider="slow-image"), tmp_path)

    assert execution.job.fallback is True
    assert "timed out" in (execution.job.fallback_reason or "")
    assert "0.05s" in (execution.job.fallback_reason or "")
    record = store.recent(1)[0]
    assert record.error_code == ERROR_TIMEOUT
    assert record.attempts == 3


def test_fatal_errors_propagate_but_leave_a_telemetry_trail(tmp_path) -> None:
    fatal = ScriptedProvider([ProviderUnsupported("scripted cannot do that")])
    registry = registry_with(fatal, MockProvider())
    store = TelemetryStore()
    executor = GenerationExecutor(registry, retry_engine=fast_engine(), telemetry_store=store)

    with pytest.raises(ProviderUnsupported, match="cannot do that"):
        executor.execute(spec(provider="scripted"), tmp_path)

    assert fatal.calls == 1, "fatal errors are never retried"
    record = store.recent(1)[0]
    assert record.success is False
    assert record.error_code == ERROR_UNSUPPORTED
    assert record.fallback is False


def test_disabling_fallback_lets_retryable_failures_fail(tmp_path) -> None:
    broken = ScriptedProvider([RuntimeError("boom")] * 3)
    registry = registry_with(broken, MockProvider())
    executor = GenerationExecutor(
        registry, retry_engine=fast_engine(), telemetry_store=TelemetryStore(), fallback_enabled=False
    )

    with pytest.raises(RuntimeError, match="boom"):
        executor.execute(spec(provider="scripted"), tmp_path)


def test_the_fallback_chain_itself_can_fail_loudly(tmp_path) -> None:
    broken = ScriptedProvider([RuntimeError("boom")] * 3)
    registry = registry_with(broken)  # no mock registered
    executor = GenerationExecutor(registry, retry_engine=fast_engine(), telemetry_store=TelemetryStore())

    with pytest.raises(ProviderUnavailable, match="could not take over"):
        executor.execute(spec(provider="scripted"), tmp_path)


def test_the_batch_is_never_lost_when_a_provider_dies(tmp_path, monkeypatch) -> None:
    """Render-level proof of ETAPA 5: every scene completes through the fallback."""

    from app.render.render_batch import RenderBatchStore
    from app.render.render_orchestrator import RenderOrchestrator
    from app.render.progress import RenderProgressHub
    from app.render.scene_renderer import SceneRenderInput
    from app.render.asset_pipeline import RenderAssetPipeline
    from app.storage import StorageService

    # Two scenes x three attempts each: every call the batch makes must die.
    dying = ScriptedProvider([RuntimeError("GPU gone")] * 6, provider_id="dying")
    registry = registry_with(dying, MockProvider())
    executor = GenerationExecutor(registry, retry_engine=fast_engine(), telemetry_store=TelemetryStore())

    monkeypatch.setattr(settings, "local_media_dir", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "storage_enabled", False)
    orchestrator = RenderOrchestrator(
        executor=executor,
        pipeline=RenderAssetPipeline(storage=StorageService(), staging_dir=tmp_path / "staging"),
        store=RenderBatchStore(),
        hub=RenderProgressHub(),
    )
    batch = orchestrator.create_batch(
        [
            SceneRenderInput(scene_number=1, title="Abertura", objective="estabelecer o mundo"),
            SceneRenderInput(scene_number=2, title="Produto", objective="mostrar o produto"),
        ],
        workspace_id="workspace-fallback",
        project_id="project-fallback",
        provider="dying",
    )

    import asyncio

    finished = asyncio.run(orchestrator.run_batch(batch.batch_id))

    assert finished is not None
    assert finished.status == "completed", "the batch survives a dead provider"
    assert all(scene.status == "completed" for scene in finished.scenes)
    assert all((scene.job or {}).get("fallback") is True for scene in finished.scenes)
    assert all("GPU gone" in ((scene.job or {}).get("fallback_reason") or "") for scene in finished.scenes)


# ---------------------------------------------------------------------------
# Executor + telemetry wiring
# ---------------------------------------------------------------------------


def test_the_happy_path_records_one_clean_telemetry_entry(tmp_path) -> None:
    store = TelemetryStore()
    executor = GenerationExecutor(
        registry_with(MockProvider()), retry_engine=fast_engine(), telemetry_store=store
    )

    execution = executor.execute(spec(provider="mock"), tmp_path, job_id="job-1")

    assert isinstance(execution, GenerationExecution)
    assert execution.job.status == "complete"
    assert execution.job.attempts == 1
    assert execution.job.telemetry is not None
    record = store.recent(1)[0]
    assert record.provider_id == "mock"
    assert record.requested_provider_id == "mock"
    assert record.success is True
    assert record.error_code is None
    assert record.latency_ms >= 0
    assert record.queue_time_ms >= 0
    assert record.render_time_ms >= 0
    assert record.job_id == "job-1"
    assert execution.to_dict()["telemetry"]["provider_id"] == "mock"


def test_the_job_contract_keeps_the_pr007_shape_plus_pr009_fields(tmp_path) -> None:
    store = TelemetryStore()
    executor = GenerationExecutor(
        registry_with(MockProvider()), retry_engine=fast_engine(), telemetry_store=store
    )
    execution = executor.execute(spec(provider="mock"), tmp_path)
    payload = execution.job.to_dict()

    assert {"id", "status", "provider_id", "asset", "estimate", "attempts", "fallback"} <= set(payload)
    assert payload["fallback"] is False
    assert payload["fallback_reason"] is None
    # And the plain constructor still works positionally for legacy callers.
    legacy = ProviderJob(
        "job", "complete", "mock", execution.asset, ProviderEstimate("mock", "image", 0.1)
    )
    assert legacy.attempts == 1
    assert legacy.fallback is False


# ---------------------------------------------------------------------------
# Health (ETAPA 7) + API
# ---------------------------------------------------------------------------


def test_registry_health_stamps_latency_and_the_last_health_instant() -> None:
    registry = registry_with(MockProvider())
    rows = registry.health_all()
    assert len(rows) == 1
    assert rows[0].latency_ms >= 0
    assert rows[0].last_health_at, "health_all stamps the instant it measured"


def test_the_providers_endpoint_exposes_availability_version_and_last_health() -> None:
    body = client.get("/api/v1/providers").json()
    by_label = {row["label"]: row for row in body}
    assert {"Flux", "Wan", "Mock"} <= set(by_label)
    for row in body:
        assert "available" in row
        assert "last_health_at" in row
        assert row["available"] == (row["status"] == "ready")
    assert by_label["Mock"]["available"] is True
    assert by_label["Mock"]["last_health_at"]


def test_the_real_test_endpoint_runs_the_full_path_on_mock() -> None:
    body = client.post("/api/v1/providers/mock/test").json()
    assert body["provider_id"] == "mock"
    assert body["executed_provider_id"] == "mock"
    assert body["success"] is True
    assert body["fallback"] is False
    assert body["asset_kind"] == "image"
    assert body["asset_bytes"] > 0
    assert body["attempts"] >= 1
    assert body["latency_ms"] >= 0


def test_the_real_test_endpoint_falls_back_honestly_for_gpu_providers() -> None:
    """No CUDA in CI: Flux is tested, misses its deadline budget, and the mock
    takes over — with the reason visible, exactly as the UI will show it."""

    body = client.post("/api/v1/providers/flux-dev/test").json()
    assert body["provider_id"] == "flux-dev"
    assert body["success"] is True, "the test run must still produce an asset"
    assert body["fallback"] is True
    assert body["executed_provider_id"] == "mock"
    assert body["fallback_reason"], "the fallback reason is the point of the feature"
    assert body["attempts"] == 3
    assert body["asset_kind"] == "image"

    video = client.post("/api/v1/providers/wan-2.1-t2v/test").json()
    assert video["kind"] == "video"
    assert video["fallback"] is True
    assert video["asset_kind"] == "video"


def test_the_real_test_endpoint_refuses_to_invent_an_unknown_provider_shape() -> None:
    body = client.post("/api/v1/providers/never-registered/test").json()
    assert body["success"] is True
    assert body["fallback"] is True
    assert "not registered" in (body["fallback_reason"] or "")


def test_the_telemetry_endpoint_returns_newest_first_with_the_saved_fields() -> None:
    client.post("/api/v1/providers/mock/test")
    body = client.get("/api/v1/providers/telemetry", params={"limit": 5}).json()
    assert isinstance(body, list) and body
    entry = body[0]
    for field in (
        "provider_id",
        "requested_provider_id",
        "latency_ms",
        "queue_time_ms",
        "render_time_ms",
        "success",
        "error_code",
        "attempts",
        "fallback",
    ):
        assert field in entry
    timestamps = [item["at"] for item in body]
    assert timestamps == sorted(timestamps, reverse=True)

    clamped = client.get("/api/v1/providers/telemetry", params={"limit": 0}).json()
    assert len(clamped) <= 1


# ---------------------------------------------------------------------------
# Loader runtime paths (fake GPU environment, ETAPA 16 pattern)
# ---------------------------------------------------------------------------


@pytest.fixture()
def gpu_like_env(monkeypatch):
    """Fake `torch` + `diffusers` so the real loaders run without hardware."""

    state: dict = {}

    class FakePipelineClass:
        @classmethod
        def from_pretrained(cls, model_id, torch_dtype=None):
            state["model_id"] = model_id
            pipeline = SimpleNamespace(
                enable_model_cpu_offload=lambda: state.update(offloaded=True),
                to=lambda device: state.update(device=device),
            )
            state["pipeline"] = pipeline
            return pipeline

    torch_fake = SimpleNamespace(
        bfloat16="bfloat16",
        cuda=SimpleNamespace(is_available=lambda: True),
        Generator=lambda device: SimpleNamespace(manual_seed=lambda seed: ("gen", seed)),
    )
    monkeypatch.setitem(sys.modules, "torch", torch_fake)
    monkeypatch.setitem(
        sys.modules,
        "diffusers",
        SimpleNamespace(
            FluxPipeline=FakePipelineClass,
            FluxImg2ImgPipeline=FakePipelineClass,
            WanPipeline=FakePipelineClass,
            WanImageToVideoPipeline=FakePipelineClass,
        ),
    )
    return state


def test_the_flux_loader_builds_cuda_pipelines_and_caches_per_mode(gpu_like_env) -> None:
    provider = FluxProvider(model_id="org/flux-checkpoint")
    t2i = provider._pipeline_for(MODE_TEXT_TO_IMAGE)
    assert provider._pipeline_for(MODE_TEXT_TO_IMAGE) is t2i, "the pipeline is cached, not rebuilt"
    assert gpu_like_env["offloaded"] is True
    assert gpu_like_env["model_id"] == "org/flux-checkpoint"

    i2i = provider._pipeline_for(MODE_IMAGE_TO_IMAGE)
    assert i2i is not None
    assert provider._pipeline_mode == MODE_IMAGE_TO_IMAGE

    report = provider.health()
    assert report.status == "ready", "with CUDA available the connector reports ready"
    assert report.loaded is True


def test_the_flux_loader_refuses_a_missing_pipeline_class_and_missing_cuda(monkeypatch) -> None:
    torch_fake = SimpleNamespace(bfloat16="bfloat16", cuda=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "torch", torch_fake)
    monkeypatch.setitem(sys.modules, "diffusers", SimpleNamespace(FluxPipeline=object))

    with pytest.raises(RuntimeError, match="CUDA GPU is required"):
        FluxProvider()._pipeline_for(MODE_TEXT_TO_IMAGE)

    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(bfloat16="bfloat16", cuda=SimpleNamespace(is_available=lambda: True))
    )
    with pytest.raises(RuntimeError, match="no FluxImg2ImgPipeline"):
        FluxProvider()._pipeline_for(MODE_IMAGE_TO_IMAGE)


def test_the_video_loader_moves_the_pipeline_to_cuda(gpu_like_env) -> None:
    loader = wan_module.VideoPipelineLoader()
    loader("org/wan-checkpoint", "WanPipeline")
    assert gpu_like_env["device"] == "cuda"
    assert gpu_like_env["model_id"] == "org/wan-checkpoint"

    with pytest.raises(RuntimeError, match="no NoSuchPipeline"):
        loader("org/wan-checkpoint", "NoSuchPipeline")


def test_the_wan_connector_reports_a_missing_encoder(monkeypatch, tmp_path) -> None:
    class FakePipeline:
        def __call__(self, **kwargs):
            return SimpleNamespace(frames=[[object()]])

    monkeypatch.setattr(wan_module, "generator_for", lambda seed: None)
    monkeypatch.setitem(sys.modules, "imageio", None)
    monkeypatch.setitem(sys.modules, "imageio.v3", None)
    provider = WanProvider(pipeline_loader=lambda model_id, class_name: FakePipeline())

    with pytest.raises(RuntimeError, match="imageio"):
        provider.generate_video(spec(kind=GenerationKind.VIDEO), tmp_path)


# ---------------------------------------------------------------------------
# Small contract guards
# ---------------------------------------------------------------------------


def test_provider_asset_validates_its_required_fields() -> None:
    with pytest.raises(ValueError, match="path"):
        ProviderAsset("", "image", "mock")
    with pytest.raises(ValueError, match="provider_id"):
        ProviderAsset("/tmp/x.png", "image", "")


def test_reference_loader_and_registry_edge_cases() -> None:
    from app.providers.common import load_reference_image

    with pytest.raises(ValueError, match="reference_path"):
        load_reference_image(None)

    bare = ProviderRegistry()
    with pytest.raises(ProviderNotFound):
        bare.get(None)

    from app.providers import provider_registry as universal

    universal.register(
        ProviderRegistration(provider_id="pr009-probe", label="Probe", factory=lambda model_id=None: MockProvider())
    )
    try:
        assert universal.get("pr009-probe").provider_id == "mock"
    finally:
        # Registration is global; leave the default registry exactly as found.
        universal.DEFAULT_REGISTRY._registrations.pop("pr009-probe", None)
        universal.DEFAULT_REGISTRY._order.remove("pr009-probe")

    with pytest.raises(ProviderUnsupported):
        wan_module.WanProvider().upscale(spec(), "/tmp/x.png", "/tmp")


def test_the_mock_upscale_survives_a_missing_source(tmp_path) -> None:
    asset = MockProvider().upscale(spec(), tmp_path / "missing.png", tmp_path)
    assert Path(asset.path).read_bytes()


def test_registry_module_functions_keep_the_default_registry_reachable() -> None:
    from app.providers import provider_registry as universal

    assert universal.get("mock").provider_id == "mock"
    assert {provider.label for provider in universal.list()} >= {"Flux", "Wan", "Mock"}
    assert universal.defaults() == {"image": "flux-dev", "video": "wan-2.1-t2v"}
    assert {row.id for row in universal.health_all()} >= {"mock", "flux-dev", "wan-2.1-t2v"}


def test_retry_policy_helpers_round_out_the_engine() -> None:
    from app.providers.retry_policy import default_retry_engine

    policy = RetryPolicy()
    assert policy.is_retryable(RuntimeError("x")) is True
    assert policy.is_retryable(ProviderTimeoutError("x")) is True
    assert policy.is_retryable(ValueError("x")) is False
    assert isinstance(default_retry_engine(), RetryEngine)


def test_telemetry_edge_cases() -> None:
    from app.providers.telemetry import default_telemetry_store, records_to_payloads, reset_default_telemetry_store

    with pytest.raises(ValueError):
        TelemetryStore(limit=0)

    store = TelemetryStore()
    entry = store.record(_record())
    assert records_to_payloads([entry])[0]["provider_id"] == "mock"

    reset_default_telemetry_store()
    first = default_telemetry_store()
    reset_default_telemetry_store()
    second = default_telemetry_store()
    assert first is not second, "reset drops the cached store so settings are re-read"


def test_unavailable_errors_get_the_unavailable_verdict(tmp_path) -> None:
    unavailable = ScriptedProvider([ProviderUnavailable("model weights missing")] * 3)
    registry = registry_with(unavailable, MockProvider())
    store = TelemetryStore()
    executor = GenerationExecutor(registry, retry_engine=fast_engine(), telemetry_store=store)

    execution = executor.execute(spec(provider="scripted"), tmp_path)

    assert execution.job.fallback is True
    assert "unavailable after 3 attempts" in (execution.job.fallback_reason or "")
    assert store.recent(1)[0].error_code == ERROR_UNAVAILABLE


# ---------------------------------------------------------------------------
# Architecture guards
# ---------------------------------------------------------------------------


def test_connectors_receive_only_the_spec() -> None:
    for method in (
        FluxProvider.generate_image,
        WanProvider.generate_video,
        HunyuanProvider.generate_video,
    ):
        parameters = list(inspect.signature(method).parameters)
        assert parameters == ["self", "spec", "output_dir"]


def test_the_default_registry_still_registers_flux_wan_mock_and_hunyuan() -> None:
    registry = create_default_registry()
    labels = {provider.label for provider in registry.list()}
    assert {"Flux", "Wan", "Mock", "Hunyuan"} <= labels
    assert registry.defaults() == {"image": "flux-dev", "video": "wan-2.1-t2v"}


def test_the_executor_still_knows_no_provider_brands() -> None:
    source = Path("backend/app/providers/generation_executor.py").read_text(encoding="utf-8")
    for banned in ("FLUX", "Wan2", "Hunyuan", "flux-dev", "wan-2.1"):
        assert banned not in source
