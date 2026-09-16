"""ETAPA 3: providers receive only a GenerationSpec — never loose strings.

The signature is the enforcement point, so most of these tests inspect it
directly. The end-to-end test at the bottom patches the provider and asserts on
what the worker actually handed it.
"""
import inspect
import sys
import types as types_module
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.contracts import GenerationKind, GenerationSpec
from app.providers.image import FluxDiffusersProvider, GenerationOutput, ImageProvider
from app.providers.image import _dimensions as image_dimensions
from app.providers.image import pipeline_arguments as image_arguments
from app.providers.video import VideoProvider, VideoGenerationOutput, WanVideoProvider
from app.providers.video import _dimensions as video_dimensions
from app.providers.video import frame_count, pipeline_arguments as video_arguments


def _spec(**overrides) -> GenerationSpec:
    base = dict(prompt_original="a red car", prompt_compiled="a red car, cinematic realism")
    base.update(overrides)
    return GenerationSpec(**base)


# ------------------------------------------------- the contract is the signature


@pytest.mark.parametrize("provider_class", [FluxDiffusersProvider, WanVideoProvider])
def test_generate_accepts_a_spec_and_nothing_else(provider_class) -> None:
    parameters = list(inspect.signature(provider_class.generate).parameters)
    assert parameters == ["self", "spec", "output_dir"]


@pytest.mark.parametrize("provider_class", [FluxDiffusersProvider, WanVideoProvider])
def test_no_provider_accepts_a_prompt_string_or_a_parameters_dict(provider_class) -> None:
    """The literal wording of ETAPA 3: "Nunca strings soltas"."""

    signature = inspect.signature(provider_class.generate)
    assert "prompt" not in signature.parameters
    assert "parameters" not in signature.parameters
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        annotation = inspect.get_annotations(provider_class.generate).get(name)
        assert annotation is not None, f"{name} is untyped"
    assert inspect.get_annotations(provider_class.generate)["spec"] in ("GenerationSpec", GenerationSpec)


@pytest.mark.parametrize("base_class", [ImageProvider, VideoProvider])
def test_the_provider_contract_is_abstract(base_class) -> None:
    with pytest.raises(TypeError):
        base_class()  # type: ignore[abstract]


@pytest.mark.parametrize("provider_class", [FluxDiffusersProvider, WanVideoProvider])
def test_every_provider_reports_health(provider_class) -> None:
    report = provider_class().health()
    assert set(report) >= {"available", "reason", "model_id"}
    assert report["available"] is False, "no CUDA in CI, so this must not claim readiness"


# ------------------------------------------------------------------ pure mapping


def test_image_arguments_come_only_from_the_spec() -> None:
    arguments = image_arguments(
        _spec(guidance_scale=9.0, steps=40, negative_prompt="blurry", seed=None), 1024, 576
    )
    assert arguments["prompt"] == "a red car, cinematic realism"
    assert arguments["negative_prompt"] == "blurry"
    assert arguments["guidance_scale"] == 9.0
    assert arguments["num_inference_steps"] == 40
    assert (arguments["width"], arguments["height"]) == (1024, 576)


def test_video_frame_count_is_derived_from_the_spec() -> None:
    assert video_arguments(_spec(fps=24, duration=5), 832, 480)["num_frames"] == frame_count(_spec(fps=24, duration=5))
    assert frame_count(_spec(fps=24, duration=5)) == 121, "Wan expects a 4n+1 frame count"
    assert frame_count(_spec(fps=24, duration=5)) % 4 == 1
    assert frame_count(_spec(fps=30, duration=2)) % 4 == 1


def test_video_arguments_use_the_specs_own_timing() -> None:
    arguments = video_arguments(_spec(fps=30, duration=10), 832, 480)
    assert arguments["num_frames"] == frame_count(_spec(fps=30, duration=10))


@pytest.mark.parametrize("provider_class", [FluxDiffusersProvider, WanVideoProvider])
def test_consumed_fields_are_declared_and_really_exist(provider_class) -> None:
    import dataclasses

    declared = {f.name for f in dataclasses.fields(GenerationSpec)}
    assert provider_class.CONSUMED_SPEC_FIELDS
    unknown = provider_class.CONSUMED_SPEC_FIELDS - declared
    assert not unknown, f"{provider_class.__name__} declares fields the spec does not have: {unknown}"


def test_the_video_provider_declares_what_it_cannot_honour() -> None:
    """Declaring an unsupported field beats dropping it silently."""

    assert "native_audio" in WanVideoProvider.UNSUPPORTED_SPEC_FIELDS
    assert not (WanVideoProvider.CONSUMED_SPEC_FIELDS & WanVideoProvider.UNSUPPORTED_SPEC_FIELDS)


# --------------------------------------------------------------- kwarg filtering


class _StrictPipeline:
    """A pipeline with a fixed signature, like FLUX (no negative_prompt)."""

    def __call__(self, prompt, width, height, guidance_scale, num_inference_steps, generator=None):
        self.received = dict(
            prompt=prompt, width=width, height=height,
            guidance_scale=guidance_scale, num_inference_steps=num_inference_steps, generator=generator,
        )
        return SimpleNamespace(images=[SimpleNamespace(save=lambda path: None)], frames=[[]])


class _LoosePipeline:
    def __call__(self, **kwargs):
        self.received = kwargs
        return SimpleNamespace(images=[SimpleNamespace(save=lambda path: None)], frames=[[]])


def test_unsupported_kwargs_are_filtered_instead_of_crashing_the_pipeline() -> None:
    from app.providers.image import _supported_kwargs

    candidates = image_arguments(_spec(negative_prompt="blurry"), 1024, 576)
    accepted = _supported_kwargs(_StrictPipeline(), candidates)
    assert "negative_prompt" not in accepted
    assert accepted["prompt"] == "a red car, cinematic realism"


def test_a_pipeline_with_kwargs_passthrough_keeps_everything() -> None:
    from app.providers.video import _supported_kwargs

    candidates = video_arguments(_spec(), 832, 480)
    assert _supported_kwargs(_LoosePipeline(), candidates) == candidates


# -------------------------------------------------------------------- dimensions


def test_image_dimensions_are_unchanged() -> None:
    assert image_dimensions("16:9", 1024) == (1024, 576)
    assert image_dimensions("9:16", 1024) == (576, 1024)
    assert image_dimensions("1:1", 1024) == (1024, 1024)
    assert image_dimensions("unknown", 1024) == (1024, 576)


def test_video_dimensions_are_unchanged() -> None:
    """Pinned by the pre-existing test_video_provider.py; restated for locality."""

    assert video_dimensions("16:9") == (832, 480)
    assert video_dimensions("9:16") == (480, 832)
    assert video_dimensions("1:1") == (512, 512)
    assert video_dimensions("unknown") == (832, 480)


# --------------------------------------------------------------------- end to end


@pytest.fixture()
def inference_enabled(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "inference_enabled", True)
    monkeypatch.setattr(settings, "storage_enabled", False)
    return settings


def test_the_worker_hands_the_image_provider_only_a_spec(inference_enabled, monkeypatch, tmp_path) -> None:
    """The whole point of ETAPA 3, verified through the real worker.

    PR009: the worker crosses the universal executor into the real Flux
    connector, so the seam under test is the connector's pipeline loader and
    its `generate_image` boundary — still "spec and output dir only".
    """

    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    import app.providers.flux_provider as flux_module

    received: dict = {}

    class FakeFluxPipeline:
        def __call__(self, **kwargs):
            received["pipeline_kwargs"] = kwargs

            def save(path):
                # ETAPA 14: the worker checks that a file was really written.
                # 1024x576 is exactly 16:9, the ratio this job asks for.
                Path(path).write_bytes(b"\x89PNG fake")

            return SimpleNamespace(images=[SimpleNamespace(save=save, size=(1024, 576))])

    def fake_loader(self, model_id, mode):
        received["model_id"] = model_id
        received["mode"] = mode
        return FakeFluxPipeline()

    monkeypatch.setattr(flux_module.FluxPipelineLoader, "__call__", fake_loader)
    monkeypatch.setattr(flux_module, "generator_for", lambda seed: ("generator", seed))

    original_generate = flux_module.FluxProvider.generate_image

    def spy_generate(self, spec, output_dir):
        received["spec"] = spec
        received["arg_count"] = 2
        return original_generate(self, spec, output_dir)

    monkeypatch.setattr(flux_module.FluxProvider, "generate_image", spy_generate)

    job = store.add_job(
        Job(
            type=GenerationType.IMAGE,
            prompt="a red car",
            parameters={"model": "flux-dev", "aspect_ratio": "16:9", "resolution": "2048", "steps": 36, "seed": 7},
        )
    )
    result = process_generation(str(job.id))

    assert result["status"] == "complete", result
    assert received["arg_count"] == 2, "the provider must receive the spec and the output dir only"
    assert isinstance(received["spec"], GenerationSpec)
    spec = received["spec"]
    assert spec.prompt_compiled.startswith("a red car")
    assert spec.resolution == 2048
    assert spec.steps == 36
    assert spec.seed == 7
    assert received["model_id"] == "black-forest-labs/FLUX.1-dev"
    assert received["mode"] == "text-to-image"
    # The pipeline only ever sees the compiled prompt — never a raw one.
    assert received["pipeline_kwargs"]["prompt"] == spec.prompt_compiled
    assert received["pipeline_kwargs"]["generator"] == ("generator", 7)


def test_the_worker_hands_the_video_provider_only_a_spec(inference_enabled, monkeypatch, tmp_path) -> None:
    """PR009: the video seam under test is the real Wan connector."""

    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    import app.providers.wan_provider as wan_module

    received: dict = {}

    def fake_imwrite(target, frames, fps=None, codec=None):
        Path(target).write_bytes(b"fake mp4")

    module = types_module.ModuleType("imageio.v3")
    module.imwrite = fake_imwrite
    parent = types_module.ModuleType("imageio")
    parent.v3 = module
    monkeypatch.setitem(sys.modules, "imageio", parent)
    monkeypatch.setitem(sys.modules, "imageio.v3", module)

    class FakeWanPipeline:
        def __call__(self, **kwargs):
            received["pipeline_kwargs"] = kwargs
            return SimpleNamespace(frames=[[object()]])

    def fake_loader(self, model_id, pipeline_class_name):
        received["model_id"] = model_id
        received["pipeline_class"] = pipeline_class_name
        return FakeWanPipeline()

    monkeypatch.setattr(wan_module.VideoPipelineLoader, "__call__", fake_loader)

    original_generate = wan_module.WanProvider.generate_video

    def spy_generate(self, spec, output_dir):
        received["spec"] = spec
        return original_generate(self, spec, output_dir)

    monkeypatch.setattr(wan_module.WanProvider, "generate_video", spy_generate)

    job = store.add_job(
        Job(
            type=GenerationType.VIDEO,
            prompt="a slow dolly-in",
            parameters={"mode": "text-to-video", "duration_seconds": 10, "fps": 24, "aspect_ratio": "9:16"},
        )
    )
    result = process_generation(str(job.id))

    assert result["status"] == "complete", result
    spec = received["spec"]
    assert isinstance(spec, GenerationSpec)
    assert spec.kind is GenerationKind.VIDEO
    assert spec.duration == 10.0
    assert spec.aspect_ratio == "9:16"
    assert received["pipeline_class"] == "WanPipeline"
    assert received["pipeline_kwargs"]["prompt"] == spec.prompt_compiled
    assert received["pipeline_kwargs"]["num_frames"] % 4 == 1


def test_a_job_is_found_by_its_string_id(inference_enabled, monkeypatch, tmp_path) -> None:
    """Regression: the worker used to miss every job and report `cancelled`.

    PR009: the seam is the real Flux connector's pipeline loader.
    """

    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    import app.providers.flux_provider as flux_module

    class FakeFluxPipeline:
        def __call__(self, **kwargs):
            def save(path):
                Path(path).write_bytes(b"\x89PNG fake")

            return SimpleNamespace(images=[SimpleNamespace(save=save, size=(1024, 576))])

    monkeypatch.setattr(
        flux_module.FluxPipelineLoader, "__call__", lambda self, model_id, mode: FakeFluxPipeline()
    )
    monkeypatch.setattr(flux_module, "generator_for", lambda seed: None)

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    assert process_generation(str(job.id))["status"] == "complete"


def test_an_unavailable_provider_falls_back_to_mock_and_records_the_reason(inference_enabled, monkeypatch) -> None:
    """PR009 ETAPA 5: a provider that cannot run is not a dead job.

    A persistent retryable failure spends the attempt budget and then the
    fallback chain (Registry -> MockProvider) produces the asset; the reason
    is recorded on the job/telemetry instead of being swallowed.
    """

    from app.queue import process_generation
    from app.providers.retry_policy import RetryPolicy
    from app.providers.generation_executor import GenerationExecutor
    from app.schemas import GenerationType, Job
    from app.store import store

    import app.queue as queue_module

    class BrokenFluxPipeline:
        def __call__(self, **kwargs):
            raise RuntimeError("CUDA GPU is required for the FLUX provider")

    import app.providers.flux_provider as flux_module

    monkeypatch.setattr(
        flux_module.FluxPipelineLoader, "__call__", lambda self, model_id, mode: BrokenFluxPipeline()
    )
    monkeypatch.setattr(flux_module, "generator_for", lambda seed: None)

    # A no-op sleeper keeps the retry budget honest without slowing the suite.
    fast_executor = GenerationExecutor(retry_engine=_no_sleep_engine())
    monkeypatch.setattr(queue_module, "generation_executor", fast_executor)

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    result = process_generation(str(job.id))

    assert result["status"] == "complete", result
    record = fast_executor.telemetry_store.recent(1)[0]
    assert record.fallback is True
    assert record.error_code == "generation-error"
    assert "CUDA" in (record.fallback_reason or "")
    assert record.provider_id == "mock"


def test_a_fatal_provider_error_still_fails_the_job(inference_enabled, monkeypatch) -> None:
    """PR009: fallback masks unavailability, never a contract bug.

    A fatal error (unsupported operation / invalid spec) must surface as a
    failed job — silently handing back a mock asset would hide a routing bug.
    """

    from app.queue import process_generation
    from app.providers.base_provider import ProviderUnsupported
    from app.schemas import GenerationType, Job
    from app.store import store

    import app.providers.flux_provider as flux_module

    def raise_fatal(self, spec, output_dir):
        raise ProviderUnsupported("provider 'flux-dev' does not support this")

    monkeypatch.setattr(flux_module.FluxProvider, "generate_image", raise_fatal)

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    result = process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "does not support" in result["error"]


def _no_sleep_engine():
    from app.providers.retry_policy import RetryEngine, RetryPolicy

    return RetryEngine(RetryPolicy(), sleeper=lambda _seconds: None)
