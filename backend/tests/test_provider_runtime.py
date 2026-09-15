"""ETAPA 16 tests — the provider runtime paths.

`providers/image.py` and `providers/video.py` sat at 70%/74% because the
uncovered lines are the ones that call diffusers. Those lines are not all
GPU-only in their *logic*: which pipeline class is asked for, what a missing
diffusers does, why ControlNet is refused, what the output file is named, and
what a failed encode reports are all decisions worth pinning. The tests inject a
stand-in pipeline for the parts that are decisions and assert the refusal for
the parts that are hardware.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from app.core.contracts import GenerationSpec


def _spec(**overrides) -> GenerationSpec:
    base = dict(prompt_original="a red car", prompt_compiled="a red car, cinematic realism")
    base.update(overrides)
    return GenerationSpec(**base)


class FakeImage:
    def __init__(self, saved: list) -> None:
        self.saved = saved

    def save(self, destination) -> None:
        self.saved.append(str(destination))
        Path(destination).write_bytes(b"\x89PNG fake")


class FakePipeline:
    """A stand-in whose `__call__` signature decides what gets filtered in."""

    def __init__(self, saved: list) -> None:
        self.saved = saved
        self.calls: list = []
        self.loaded: list = []
        self.adapters: list = []
        self.offloaded = False
        self.devices: list = []

    def __call__(self, prompt=None, height=None, width=None, num_inference_steps=None, **ignored):
        """Returns both shapes at once: image pipelines read `.images`, video `.frames`."""

        self.calls.append({"prompt": prompt, "height": height, "width": width, "steps": num_inference_steps})
        return types.SimpleNamespace(
            images=[FakeImage(self.saved)],
            frames=[[b"frame-0", b"frame-1"]],
        )

    def load_lora_weights(self, path, adapter_name) -> None:
        self.loaded.append((path, adapter_name))

    def set_adapters(self, names, adapter_weights) -> None:
        self.adapters.append((names, adapter_weights))

    def load_ip_adapter(self, *args, **kwargs) -> None:
        self.loaded.append(("ip-adapter", kwargs))

    def set_ip_adapter_scale(self, scale) -> None:
        self.adapters.append(("ip-scale", scale))

    def enable_model_cpu_offload(self) -> None:
        self.offloaded = True

    def to(self, device) -> None:
        self.devices.append(device)


@pytest.fixture()
def diffusers_env(monkeypatch):
    """Fake `torch` plus a diffusers namespace the video loader can query."""

    state: dict = {}

    class FakeFlux:
        @classmethod
        def from_pretrained(cls, model_id, torch_dtype=None):
            state["model_id"] = model_id
            state["dtype"] = torch_dtype
            pipeline = FakePipeline(state.setdefault("saved", []))
            state["pipeline"] = pipeline
            return pipeline

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(bfloat16="bfloat16", cuda=types.SimpleNamespace(is_available=lambda: True)))
    monkeypatch.setitem(sys.modules, "diffusers", types.SimpleNamespace(FluxPipeline=FakeFlux, WanPipeline=FakeFlux, HunyuanVideoPipeline=FakeFlux))
    return state


# ---------------------------------------------------------------------------
# FluxDiffusersProvider — loading
# ---------------------------------------------------------------------------


def test_a_missing_diffusers_is_reported_not_imported_at_module_load(monkeypatch) -> None:
    from app.providers.image import FluxDiffusersProvider

    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(RuntimeError, match="Diffusers GPU dependencies are not installed"):
        FluxDiffusersProvider()._load()


def test_load_builds_the_pipeline_once(diffusers_env) -> None:
    from app.providers.image import FluxDiffusersProvider

    provider = FluxDiffusersProvider(model_id="black-forest-labs/FLUX.1-dev")
    first = provider._load()
    second = provider._load()
    assert first is second, "the pipeline must be cached, not rebuilt per frame"
    assert diffusers_env["model_id"] == "black-forest-labs/FLUX.1-dev"
    assert first.offloaded is True, "a 24GB model must not sit wholly in VRAM"


def test_health_reports_the_machine_not_the_code(diffusers_env) -> None:
    """`available` is a claim about this host, never about correctness."""

    from app.providers.image import FluxDiffusersProvider

    provider = FluxDiffusersProvider()
    report = provider.health()
    assert report["loaded"] is False
    assert set(report) == {"available", "reason", "model_id", "loaded"}

    provider._load()
    assert provider.health()["loaded"] is True


def test_health_says_unavailable_without_cuda(monkeypatch) -> None:
    from app.providers.image import FluxDiffusersProvider

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False)))
    report = FluxDiffusersProvider().health()
    assert report["available"] is False
    assert report["reason"] == "CUDA GPU is required"


# ---------------------------------------------------------------------------
# FluxDiffusersProvider — conditioning
# ---------------------------------------------------------------------------


def test_controlnet_is_refused_with_the_reason(diffusers_env) -> None:
    """FLUX ControlNet needs `FluxControlPipeline`; this adapter loads `FluxPipeline`.

    The refusal has to name what is missing, or the operator cannot act on it.
    """

    from app.providers.image import FluxDiffusersProvider

    provider = FluxDiffusersProvider()
    pipeline = provider._load()
    with pytest.raises(RuntimeError, match=r"ControlNet 'canny' requires FluxControlPipeline"):
        provider._apply_conditioning(pipeline, _spec(controlnet="canny"))


def test_a_reference_image_applies_the_ip_adapter_at_the_spec_scale(diffusers_env, tmp_path) -> None:
    from app.providers.image import FluxDiffusersProvider

    reference = tmp_path / "face.png"
    reference.write_bytes(b"\x89PNG fake")

    provider = FluxDiffusersProvider()
    pipeline = provider._load()
    provider._apply_conditioning(pipeline, _spec(reference_path=str(reference), ip_adapter_scale=0.7))
    assert ("ip-scale", 0.7) in pipeline.adapters


def test_no_conditioning_touches_nothing(diffusers_env) -> None:
    from app.providers.image import FluxDiffusersProvider

    provider = FluxDiffusersProvider()
    pipeline = provider._load()
    provider._apply_conditioning(pipeline, _spec())
    assert pipeline.loaded == [] and pipeline.adapters == []


# ---------------------------------------------------------------------------
# FluxDiffusersProvider — generate
# ---------------------------------------------------------------------------


def test_generate_writes_one_file_named_by_spec_id(diffusers_env, tmp_path) -> None:
    """Two concurrent jobs must not overwrite one another's output."""

    from app.providers.image import FluxDiffusersProvider

    provider = FluxDiffusersProvider()
    spec = _spec(aspect_ratio="16:9", resolution=1024)
    output = provider.generate(spec, str(tmp_path / "nested"))

    assert Path(output.path).name == f"{spec.spec_id}.png"
    assert Path(output.path).is_file(), "the output directory must be created"
    # `resolution` is the *long* side, measured not assumed: 1024 gives 1024x576.
    assert (output.width, output.height) == (1024, 576)
    assert diffusers_env["pipeline"].calls[0]["prompt"] == spec.prompt_compiled


@pytest.mark.parametrize(
    "ratio,resolution,expected",
    [
        ("16:9", 1024, (1024, 576)),
        ("9:16", 1024, (576, 1024)),
        ("1:1", 1024, (1024, 1024)),
        ("16:9", 2048, (2048, 1152)),
    ],
)
def test_resolution_is_the_long_side(diffusers_env, tmp_path, ratio: str, resolution: int, expected: tuple) -> None:
    """The contract behind every "2K"/"4K" label in the product."""

    from app.providers.image import FluxDiffusersProvider

    output = FluxDiffusersProvider().generate(_spec(aspect_ratio=ratio, resolution=resolution), str(tmp_path))
    assert (output.width, output.height) == expected


def test_generate_applies_the_requested_lora(diffusers_env, tmp_path) -> None:
    from app.providers.common import PERSONA_ADAPTER_NAME
    from app.providers.image import FluxDiffusersProvider

    provider = FluxDiffusersProvider()
    provider.generate(_spec(lora="persona-abc"), str(tmp_path))
    assert ("persona-abc", PERSONA_ADAPTER_NAME) in diffusers_env["pipeline"].loaded


def test_generate_filters_kwargs_to_what_the_pipeline_accepts(diffusers_env, tmp_path) -> None:
    """Diffusers changes its signature between versions; hardcoding it breaks."""

    from app.providers.image import FluxDiffusersProvider

    provider = FluxDiffusersProvider()
    provider.generate(_spec(), str(tmp_path))
    call = diffusers_env["pipeline"].calls[0]
    assert "prompt" in call and "height" in call
    assert "negative_prompt" not in call, "FLUX is guidance-distilled and has no negative prompt"


def test_generate_reuses_a_pipeline_already_loaded(diffusers_env, tmp_path) -> None:
    from app.providers.image import FluxDiffusersProvider

    provider = FluxDiffusersProvider()
    provider._load()
    provider.generate(_spec(), str(tmp_path))
    provider.generate(_spec(), str(tmp_path))
    assert len(diffusers_env["pipeline"].calls) == 2


# ---------------------------------------------------------------------------
# Video providers — loading
# ---------------------------------------------------------------------------


def test_video_reports_a_missing_diffusers(monkeypatch) -> None:
    from app.providers.video import WanVideoProvider

    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(RuntimeError, match="Video GPU dependencies are not installed"):
        WanVideoProvider()._load()


def test_video_reports_a_diffusers_too_old_for_the_pipeline(monkeypatch) -> None:
    """An installed diffusers that lacks the pipeline class is a different failure."""

    from app.providers.video import WanVideoProvider

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(bfloat16="bf16", cuda=types.SimpleNamespace(is_available=lambda: True)))
    monkeypatch.setitem(sys.modules, "diffusers", types.SimpleNamespace())
    with pytest.raises(RuntimeError, match="has no WanPipeline; upgrade diffusers"):
        WanVideoProvider()._load()


def test_video_moves_the_pipeline_onto_the_gpu(diffusers_env) -> None:
    """Wan has no CPU offload, so the device move is the only option."""

    from app.providers.video import WanVideoProvider

    pipeline = WanVideoProvider()._load()
    assert pipeline.devices == ["cuda"]


def test_hunyuan_asks_for_its_own_pipeline_class(diffusers_env) -> None:
    """The two video adapters must not silently share one pipeline class."""

    from app.providers.video import HunyuanVideoProvider, WanVideoProvider

    assert HunyuanVideoProvider.PIPELINE_CLASS != WanVideoProvider.PIPELINE_CLASS
    assert HunyuanVideoProvider.PIPELINE_CLASS == "HunyuanVideoPipeline"


# ---------------------------------------------------------------------------
# Video providers — generate
# ---------------------------------------------------------------------------


@pytest.fixture()
def imageio_env(monkeypatch, tmp_path):
    state: dict = {}

    module = types.ModuleType("imageio.v3")

    def imwrite(destination, frames, fps=None, codec=None):
        state.update(destination=str(destination), fps=fps, codec=codec, frames=frames)
        Path(destination).write_bytes(b"fake mp4")

    module.imwrite = imwrite
    parent = types.ModuleType("imageio")
    parent.v3 = module
    monkeypatch.setitem(sys.modules, "imageio", parent)
    monkeypatch.setitem(sys.modules, "imageio.v3", module)
    return state


def test_video_generate_writes_one_file_named_by_spec_id(diffusers_env, imageio_env, tmp_path) -> None:
    from app.providers.video import WanVideoProvider

    provider = WanVideoProvider()
    spec = _spec(duration=5.0, fps=24)
    output = provider.generate(spec, str(tmp_path / "nested"))

    assert Path(output.path).name == f"{spec.spec_id}.mp4"
    assert Path(output.path).is_file()
    assert (output.duration_seconds, output.fps) == (5, 24)
    assert imageio_env["fps"] == 24
    assert imageio_env["codec"] == "libx264"


def test_video_generate_reports_a_missing_encoder(diffusers_env, monkeypatch, tmp_path) -> None:
    """No imageio means no file. It must not report a successful render."""

    from app.providers.video import WanVideoProvider

    monkeypatch.setitem(sys.modules, "imageio", None)
    monkeypatch.setitem(sys.modules, "imageio.v3", None)
    with pytest.raises(RuntimeError, match="imageio and imageio-ffmpeg are required"):
        WanVideoProvider().generate(_spec(), str(tmp_path))


def test_video_generate_applies_the_requested_lora(diffusers_env, imageio_env, tmp_path) -> None:
    from app.providers.common import PERSONA_ADAPTER_NAME
    from app.providers.video import WanVideoProvider

    provider = WanVideoProvider()
    provider.generate(_spec(lora="persona-xyz"), str(tmp_path))
    assert ("persona-xyz", PERSONA_ADAPTER_NAME) in diffusers_env["pipeline"].loaded


def test_video_health_reports_the_machine(diffusers_env) -> None:
    from app.providers.video import WanVideoProvider

    provider = WanVideoProvider()
    assert provider.health()["loaded"] is False
    provider._load()
    assert provider.health()["loaded"] is True
