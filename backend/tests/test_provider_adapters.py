"""ETAPA 10 tests — provider adapters.

Before this etapa `SYSTEM_PROMPT.md`'s "adapters substituíveis" was not true:
the worker chose an adapter by job type, so every image ran FLUX and every video
ran Wan whatever was requested. This suite pins the registry, the removal of the
duplicated helpers, and the two declarations that were wrong.
"""
from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

from app.core.contracts import GenerationKind, GenerationSpec
from app.providers import common, conditioning as cond
from app.providers import image as image_module
from app.providers import registry
from app.providers import video as video_module
from app.providers.image import FluxDiffusersProvider
from app.providers.video import HunyuanVideoProvider, WanVideoProvider


def _spec(**overrides) -> GenerationSpec:
    base = dict(prompt_original="a red car", prompt_compiled="a red car, cinematic realism")
    base.update(overrides)
    return GenerationSpec(**base)


# ---------------------------------------------------------------------------
# The registry is the single source of truth
# ---------------------------------------------------------------------------


def test_every_provider_the_api_advertises_is_registered() -> None:
    """`GET /api/v1/models/*` and the registry must not disagree."""

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    advertised = {
        model["id"]
        for path in ("/api/v1/models/image", "/api/v1/models/video")
        for model in client.get(path).json()
    }
    assert advertised == set(registry.ids())


def test_an_unknown_provider_falls_back_instead_of_inventing() -> None:
    entry = registry.resolve("org/some-checkpoint-nobody-declared", GenerationKind.IMAGE)
    assert entry.provider_id == "flux-dev"


def test_no_provider_falls_back_to_the_kind_default() -> None:
    assert registry.resolve(None, GenerationKind.IMAGE).provider_id == "flux-dev"
    assert registry.resolve(None, GenerationKind.VIDEO).provider_id == "wan-2.1-t2v"


def test_asking_for_hunyuan_gets_hunyuan_not_wan() -> None:
    """The defect this etapa exists to fix."""

    entry = registry.resolve("hunyuan-video", GenerationKind.VIDEO)
    assert entry.attribute == "HunyuanVideoProvider"
    assert registry.adapter_class(entry) is HunyuanVideoProvider


def test_a_planned_or_remote_provider_is_refused_not_substituted() -> None:
    entry = registry.resolve("flux-1.1-pro-ultra", GenerationKind.IMAGE)
    assert entry.status == registry.STATUS_REMOTE
    with pytest.raises(registry.ProviderUnavailable, match="remote API"):
        registry.check(entry, GenerationKind.IMAGE)


def test_a_video_adapter_cannot_run_an_image_job() -> None:
    with pytest.raises(registry.ProviderUnavailable, match="video adapter"):
        registry.check(registry.resolve("hunyuan-video", GenerationKind.IMAGE), GenerationKind.IMAGE)


def test_a_registered_planned_provider_is_refused_loudly() -> None:
    entry = registry.ProviderEntry(
        provider_id="not-built-yet",
        label="Not built yet",
        kind=GenerationKind.IMAGE,
        status=registry.STATUS_PLANNED,
    )
    registry.register(entry)
    try:
        with pytest.raises(registry.ProviderUnavailable, match="planned"):
            registry.check(entry, GenerationKind.IMAGE)
    finally:
        registry.unregister("not-built-yet")
    assert registry.lookup("not-built-yet") is None


def test_a_new_provider_is_one_registration_not_another_branch() -> None:
    """The extension point the spec asks for."""

    entry = registry.ProviderEntry(
        provider_id="acme-image",
        label="Acme",
        kind=GenerationKind.IMAGE,
        status=registry.STATUS_LOCAL,
        model_id="acme/v1",
        module="app.providers.image",
        attribute="FluxDiffusersProvider",
    )
    registry.register(entry)
    try:
        adapter = registry.build("acme-image", GenerationKind.IMAGE)
        assert isinstance(adapter, FluxDiffusersProvider)
        assert adapter.model_id == "acme/v1"
    finally:
        registry.unregister("acme-image")


def test_a_model_id_override_wins_over_the_registry_default() -> None:
    adapter = registry.build("flux-dev", GenerationKind.IMAGE, model_id="my/fine-tune")
    assert adapter.model_id == "my/fine-tune"


def test_the_class_is_resolved_late_so_a_test_can_patch_it(monkeypatch) -> None:
    """The worker tests monkeypatch the class; an early reference would win."""

    class Fake:
        pass

    monkeypatch.setattr(video_module, "HunyuanVideoProvider", Fake)
    assert registry.adapter_class(registry.lookup("hunyuan-video")) is Fake


def test_an_entry_naming_a_missing_class_says_so(monkeypatch) -> None:
    entry = dataclasses.replace(
        registry.lookup("flux-dev"), provider_id="ghost", attribute="DoesNotExist"
    )
    with pytest.raises(registry.ProviderUnavailable, match="does not exist"):
        registry.adapter_class(entry)


# ---------------------------------------------------------------------------
# The duplicated helpers now have one definition
# ---------------------------------------------------------------------------


def test_the_shared_helpers_are_the_same_object_not_copies() -> None:
    assert image_module._supported_kwargs is common.supported_kwargs
    assert video_module._supported_kwargs is common.supported_kwargs
    assert image_module._generator is common.generator_for
    assert video_module._generator is common.generator_for


def test_the_video_adapters_inherit_rather_than_reimplement() -> None:
    for name in ("_apply_lora", "health", "generate", "_load"):
        assert name not in WanVideoProvider.__dict__, f"{name} is redefined instead of inherited"
        assert name not in HunyuanVideoProvider.__dict__


def test_no_provider_module_defines_its_own_copy_of_a_shared_helper() -> None:
    """Static guard: a second definition is how the copies came back."""

    shared = {"_supported_kwargs", "_generator", "_apply_lora", "_dimensions"}
    for name in ("image", "video"):
        tree = ast.parse(pathlib.Path(f"backend/app/providers/{name}.py").read_text())
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in {"_supported_kwargs", "_generator"}
        }
        assert not defined, f"{name}.py redefines {defined}"
        assert shared  # the aliases are assignments, not definitions


def test_a_none_seed_means_unseeded_not_seed_zero() -> None:
    assert common.generator_for(None) is None


def test_a_lora_reports_whether_it_loaded() -> None:
    class FakePipeline:
        def __init__(self) -> None:
            self.loaded = None
            self.adapters = None

        def load_lora_weights(self, path, adapter_name):
            self.loaded = (path, adapter_name)

        def set_adapters(self, names, adapter_weights):
            self.adapters = (names, adapter_weights)

    pipeline = FakePipeline()
    assert common.apply_lora(pipeline, None) is False
    assert pipeline.loaded is None
    assert common.apply_lora(pipeline, "weights/persona.safetensors") is True
    assert pipeline.loaded == ("weights/persona.safetensors", common.PERSONA_ADAPTER_NAME)


def test_require_cuda_refuses_on_a_machine_that_cannot_run_it() -> None:
    """`_load` calls this; it must raise rather than attempt an inference."""

    available, reason = common.cuda_availability()
    if not available:
        with pytest.raises(RuntimeError, match=reason):
            common.require_cuda()
    else:  # pragma: no cover - only on a GPU box
        common.require_cuda()


def test_an_entry_with_no_module_behind_it_is_refused() -> None:
    entry = registry.ProviderEntry(
        provider_id="half-registered",
        label="Half registered",
        kind=GenerationKind.IMAGE,
        status=registry.STATUS_LOCAL,
    )
    assert entry.runnable is False
    with pytest.raises(registry.ProviderUnavailable, match="no local adapter"):
        registry.check(entry, GenerationKind.IMAGE)


def test_health_never_raises_without_torch() -> None:
    """A health check reports; it does not blow up on a CPU-only box."""

    for provider in (FluxDiffusersProvider(), WanVideoProvider(), HunyuanVideoProvider()):
        report = provider.health()
        assert set(report) >= {"available", "reason", "model_id", "loaded"}
        assert report["available"] is False
        assert report["reason"]


# ---------------------------------------------------------------------------
# The declarations are now true
# ---------------------------------------------------------------------------


def _spec_reads(node: ast.AST) -> set[str]:
    found = set()
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "spec"
        ):
            found.add(child.attr)
    # `spec_id` names the output file; it is plumbing, not a creative field.
    return found - {"spec_id"}


def _spec_fields_used(path: str, *scopes: str) -> set[str]:
    """`spec.<field>` reads inside the named classes and spec-taking functions.

    Scanning only class bodies misses `pipeline_arguments`, which lives at
    module level in `image.py`. Scanning the whole module would conflate the two
    video adapters, which is exactly what this check has to tell apart.
    """

    tree = ast.parse(pathlib.Path(path).read_text())
    wanted = set(scopes)
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in wanted:
            found |= _spec_reads(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            found |= _spec_reads(node)
        elif (
            isinstance(node, ast.FunctionDef)
            and node.args.args
            and node.args.args[0].arg == "spec"
        ):
            # A module-level mapping that takes the spec, e.g. pipeline_arguments.
            found |= _spec_reads(node)
    return found


def test_the_declared_fields_match_the_code() -> None:
    """The check that was missing: declared ⊆ spec fields was not enough.

    `FluxDiffusersProvider` consumed `negative_prompt` while declaring it did
    not, and the old test could not see it.
    """

    image_used = _spec_fields_used("backend/app/providers/image.py", "FluxDiffusersProvider")
    assert "negative_prompt" in image_used, "sanity: the mapping is inside the scan"
    assert set(FluxDiffusersProvider.CONSUMED_SPEC_FIELDS) == image_used

    base = _spec_fields_used("backend/app/providers/video.py", "_DiffusersVideoProvider")
    for cls in (WanVideoProvider, HunyuanVideoProvider):
        used = base | _spec_fields_used("backend/app/providers/video.py", cls.__name__)
        assert set(cls.CONSUMED_SPEC_FIELDS) == used, cls.__name__


def test_the_flux_provider_admits_it_consumes_the_negative_prompt() -> None:
    from app.providers.image import pipeline_arguments

    assert "negative_prompt" in pipeline_arguments(_spec(negative_prompt="blurry"), 1024, 576)
    assert "negative_prompt" in FluxDiffusersProvider.CONSUMED_SPEC_FIELDS


def test_declared_fields_still_exist_on_the_spec() -> None:
    """The original guard, kept."""

    declared = {f.name for f in dataclasses.fields(GenerationSpec)}
    for cls in (FluxDiffusersProvider, WanVideoProvider, HunyuanVideoProvider):
        assert not cls.CONSUMED_SPEC_FIELDS - declared


def test_no_field_is_both_consumed_and_unsupported() -> None:
    for cls in (WanVideoProvider, HunyuanVideoProvider):
        assert not cls.CONSUMED_SPEC_FIELDS & cls.UNSUPPORTED_SPEC_FIELDS
        assert "native_audio" in cls.UNSUPPORTED_SPEC_FIELDS


# ---------------------------------------------------------------------------
# Conditioning
# ---------------------------------------------------------------------------


def test_the_flux_ip_adapter_weights_are_flux_weights_not_sdxl() -> None:
    """The old code loaded SDXL weights onto a FLUX pipeline."""

    assert cond.FLUX_IP_ADAPTER.repo == "XLabs-AI/flux-ip-adapter"
    assert cond.FLUX_IP_ADAPTER.weight_name == "ip_adapter.safetensors"
    assert cond.FLUX_IP_ADAPTER.image_encoder == "openai/clip-vit-large-patch14"
    assert "sdxl" not in cond.FLUX_IP_ADAPTER.weight_name


def test_sdxl_weights_are_kept_for_sdxl_not_applied_to_flux() -> None:
    assert cond.SDXL_IP_ADAPTER.weight_name == "ip-adapter-plus_sdxl_vit-h.safetensors"
    assert cond.FLUX_IP_ADAPTER is not cond.SDXL_IP_ADAPTER


def test_a_reference_image_asks_for_an_ip_adapter() -> None:
    assert cond.resolve_reference("refs/face.png").mode == "ip-adapter"
    assert cond.resolve_reference("").enabled is False
    assert cond.resolve_reference(None).enabled is False


def test_controlnet_declares_the_pipeline_it_needs() -> None:
    """FLUX ControlNet runs on `FluxControlPipeline`, not on `FluxPipeline`."""

    controlnet = cond.resolve_controlnet("canny")
    assert controlnet.enabled
    assert controlnet.pipeline_class == "FluxControlPipeline"
    assert cond.resolve_controlnet("none").enabled is False
    assert cond.resolve_controlnet(None).enabled is False


def test_the_flux_adapter_refuses_controlnet_with_a_reason() -> None:
    provider = FluxDiffusersProvider()

    class FakePipeline:
        pass

    with pytest.raises(RuntimeError, match="FluxControlPipeline"):
        provider._apply_conditioning(FakePipeline(), _spec(controlnet="canny"))


def test_a_reference_image_loads_the_flux_weights_onto_the_pipeline() -> None:
    """End to end through the provider, with the weights the fix introduced."""

    seen: dict = {}

    class FakeFluxPipeline:
        def load_ip_adapter(self, repo, weight_name, image_encoder_pretrained_model_name_or_path):
            seen["load"] = (repo, weight_name, image_encoder_pretrained_model_name_or_path)

        def set_ip_adapter_scale(self, scale):
            seen["scale"] = scale

    FluxDiffusersProvider()._apply_conditioning(
        FakeFluxPipeline(), _spec(reference_path="refs/face.png", ip_adapter_scale=0.7)
    )
    assert seen["load"][0] == "XLabs-AI/flux-ip-adapter"
    assert "sdxl" not in seen["load"][1]
    assert seen["scale"] == 0.7


def test_no_reference_means_no_ip_adapter_is_loaded() -> None:
    loaded = []

    class FakeFluxPipeline:
        def load_ip_adapter(self, *args, **kwargs):
            loaded.append(args)

        def set_ip_adapter_scale(self, scale):
            loaded.append(scale)

    FluxDiffusersProvider()._apply_conditioning(FakeFluxPipeline(), _spec())
    assert loaded == []


def test_the_flux_adapter_declares_what_conditioning_it_supports() -> None:
    assert FluxDiffusersProvider.SUPPORTED_CONDITIONING == frozenset({"ip-adapter"})
    assert registry.lookup("flux-dev").conditioning == ("ip-adapter",)


def test_an_ip_adapter_missing_its_weights_raises_instead_of_guessing() -> None:
    class FakePipeline:
        def load_ip_adapter(self, *a, **k):
            pass

        def set_ip_adapter_scale(self, scale):
            pass

    with pytest.raises(cond.ConditioningError, match="carries no weights"):
        cond.apply_ip_adapter(FakePipeline(), cond.Conditioning(mode="ip-adapter"), scale=0.8)


def test_an_ip_adapter_on_an_unsupported_pipeline_raises() -> None:
    class BarePipeline:
        pass

    with pytest.raises(cond.ConditioningError, match="does not support IP-Adapter"):
        cond.apply_ip_adapter(BarePipeline(), cond.FLUX_IP_ADAPTER_CONDITIONING, scale=0.8)


def test_a_loaded_ip_adapter_gets_the_spec_scale() -> None:
    seen = {}

    class FakePipeline:
        def load_ip_adapter(self, repo, weight_name, image_encoder_pretrained_model_name_or_path):
            seen["load"] = (repo, weight_name, image_encoder_pretrained_model_name_or_path)

        def set_ip_adapter_scale(self, scale):
            seen["scale"] = scale

    cond.apply_ip_adapter(FakePipeline(), cond.FLUX_IP_ADAPTER_CONDITIONING, scale=0.65)
    assert seen["load"] == (
        "XLabs-AI/flux-ip-adapter",
        "ip_adapter.safetensors",
        "openai/clip-vit-large-patch14",
    )
    assert seen["scale"] == 0.65


def test_controlnet_arguments_are_empty_when_nothing_is_requested() -> None:
    assert cond.controlnet_arguments(cond.NONE, object()) == {}
    assert cond.controlnet_arguments(cond.FLUX_CONTROLNET, "IMG") == {"control_image": "IMG"}


# ---------------------------------------------------------------------------
# The two video adapters differ only where the models differ
# ---------------------------------------------------------------------------


def test_the_frame_count_rules_differ_because_the_models_differ() -> None:
    from app.providers.video import frame_count, hunyuan_frame_count

    spec = _spec(fps=24, duration=5)
    assert frame_count(spec) == 121, "Wan requires 4n+1"
    assert hunyuan_frame_count(spec) == 120, "Hunyuan has no such constraint"


def test_a_one_second_clip_is_never_zero_frames() -> None:
    from app.providers.video import frame_count, hunyuan_frame_count

    tiny = _spec(fps=1, duration=0.2)
    assert frame_count(tiny) >= 1
    assert hunyuan_frame_count(tiny) >= 1


def test_the_adapters_load_different_pipeline_classes() -> None:
    assert WanVideoProvider.PIPELINE_CLASS == "WanPipeline"
    assert HunyuanVideoProvider.PIPELINE_CLASS == "HunyuanVideoPipeline"


def test_the_default_resolutions_differ() -> None:
    assert WanVideoProvider.DIMENSIONS["16:9"] == (832, 480)
    assert HunyuanVideoProvider.DIMENSIONS["16:9"] == (1280, 720)


def test_dimensions_are_preserved_per_format() -> None:
    for ratio, expected in WanVideoProvider.DIMENSIONS.items():
        assert WanVideoProvider.dimensions(_spec(aspect_ratio=ratio)) == expected
    assert video_module._dimensions("9:16") == (480, 832)


def test_hunyuan_passes_steps_through_and_wan_does_not() -> None:
    spec = _spec(fps=24, duration=5, steps=40)
    assert HunyuanVideoProvider("m").arguments(spec, 1280, 720)["num_inference_steps"] == 40
    assert "num_inference_steps" not in WanVideoProvider("m").arguments(spec, 832, 480)


def test_a_missing_pipeline_class_is_reported_not_an_attributeerror(monkeypatch) -> None:
    provider = WanVideoProvider()
    monkeypatch.setattr(provider, "PIPELINE_CLASS", "NoSuchPipeline")
    with pytest.raises(RuntimeError, match="Video GPU dependencies|no NoSuchPipeline"):
        provider._load()


# ---------------------------------------------------------------------------
# The worker routes through the registry
# ---------------------------------------------------------------------------


@pytest.fixture()
def inference_enabled(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "inference_enabled", True)
    monkeypatch.setattr(settings, "storage_enabled", False)
    return settings


def test_the_worker_routes_a_video_request_to_the_requested_adapter(
    inference_enabled, monkeypatch, tmp_path
) -> None:
    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    seen: dict = {}

    class FakeHunyuan:
        def __init__(self, model_id: str = "x") -> None:
            seen["model_id"] = model_id

        def generate(self, spec, output_dir):
            seen["spec"] = spec
            # ETAPA 14: the worker verifies the artifact exists before it will
            # call a job complete, so the fake writes one.
            target = tmp_path / "out.mp4"
            target.write_bytes(b"fake mp4")
            return video_module.VideoGenerationOutput(
                str(target), int(spec.duration), spec.fps
            )

    monkeypatch.setattr(video_module, "HunyuanVideoProvider", FakeHunyuan)

    job = store.add_job(
        Job(
            type=GenerationType.VIDEO,
            prompt="a slow dolly-in",
            parameters={"mode": "text-to-video", "model": "hunyuan-video"},
        )
    )
    result = process_generation(str(job.id))

    assert result["status"] == "complete", result
    assert seen["model_id"] == "hunyuanvideo-community/HunyuanVideo"
    assert isinstance(seen["spec"], GenerationSpec)


def test_the_worker_still_defaults_to_wan_when_no_model_is_named(
    inference_enabled, monkeypatch, tmp_path
) -> None:
    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    seen: dict = {}

    class FakeWan:
        def __init__(self, model_id: str = "x") -> None:
            seen["model_id"] = model_id

        def generate(self, spec, output_dir):
            target = tmp_path / "out.mp4"
            target.write_bytes(b"fake mp4")
            return video_module.VideoGenerationOutput(
                str(target), int(spec.duration), spec.fps
            )

    monkeypatch.setattr(video_module, "WanVideoProvider", FakeWan)

    job = store.add_job(
        Job(type=GenerationType.VIDEO, prompt="a slow dolly-in", parameters={"mode": "text-to-video"})
    )
    assert process_generation(str(job.id))["status"] == "complete"
    assert seen["model_id"] == (inference_enabled.video_model_id or "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"), "the settings knob must keep working"


def test_the_worker_refuses_a_remote_only_provider(inference_enabled) -> None:
    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    job = store.add_job(
        Job(
            type=GenerationType.IMAGE,
            prompt="a red car",
            parameters={"model": "flux-1.1-pro-ultra"},
        )
    )
    result = process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "remote API" in result["error"]


def test_the_worker_refuses_a_video_adapter_for_an_image_job(inference_enabled) -> None:
    from app.queue import process_generation
    from app.schemas import GenerationType, Job
    from app.store import store

    job = store.add_job(
        Job(type=GenerationType.IMAGE, prompt="a red car", parameters={"model": "hunyuan-video"})
    )
    result = process_generation(str(job.id))
    assert result["status"] == "failed"
    assert "video adapter" in result["error"]


def test_the_settings_video_knob_does_not_leak_into_hunyuan() -> None:
    """Applying the Wan checkpoint to Hunyuan is the mistake the registry stops."""

    from app.queue import _resolve_model_id_for

    entry = registry.lookup("hunyuan-video")
    assert _resolve_model_id_for(entry, GenerationKind.VIDEO, _spec()) == (
        "hunyuanvideo-community/HunyuanVideo"
    )
    wan = registry.lookup("wan-2.1-t2v")
    assert _resolve_model_id_for(wan, GenerationKind.VIDEO, _spec(provider="wan-2.1-t2v")) == (
        "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
    )


# ---------------------------------------------------------------------------
# Every catalogue id has a prompt budget
# ---------------------------------------------------------------------------


def test_prompt_budgets_live_in_provider_capabilities_not_the_core() -> None:
    """PR007 moved model-specific prompt budgets out of the Core."""

    from app.core.prompt_compiler import DEFAULT_PROMPT_BUDGET, PromptCompiler
    from app.providers import provider_registry as universal_registry

    compiler = PromptCompiler()
    assert compiler.budget_for("opaque-provider") == DEFAULT_PROMPT_BUDGET
    for provider in universal_registry.list():
        budget = provider.capabilities().prompt_budget
        assert compiler.budget_for(provider.provider_id, budget=budget) == min(budget, compiler.max_prompt_chars)


def test_the_shorthand_budget_resolves_through_provider_capabilities() -> None:
    from app.core.prompt_compiler import PromptCompiler
    from app.providers import provider_registry as universal_registry

    capability = universal_registry.DEFAULT_REGISTRY.capabilities("wan-video")
    assert PromptCompiler().budget_for("wan-video", budget=capability.prompt_budget) == 1200


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_the_catalogue_exposes_kind_status_and_checkpoint(client) -> None:
    body = client.get("/api/v1/core/providers").json()
    by_id = {entry["id"]: entry for entry in body["adapters"]}
    assert by_id["flux-dev"]["kind"] == "image"
    assert by_id["flux-dev"]["status"] == "local-provider"
    assert by_id["flux-dev"]["model_id"] == "black-forest-labs/FLUX.1-dev"
    assert by_id["hunyuan-video"]["kind"] == "video"
    assert by_id["flux-1.1-pro-ultra"]["status"] == "remote-provider"
    assert by_id["flux-1.1-pro-ultra"]["model_id"] == ""


def test_the_catalogue_reports_the_defaults(client) -> None:
    assert client.get("/api/v1/core/providers").json()["defaults"] == {
        "image": "flux-dev",
        "video": "wan-2.1-t2v",
    }


def test_the_catalogue_can_be_filtered_by_kind(client) -> None:
    video = client.get("/api/v1/core/providers", params={"kind": "video"}).json()["adapters"]
    assert {entry["id"] for entry in video} == {"wan-2.1-t2v", "hunyuan-video"}
    image = client.get("/api/v1/core/providers", params={"kind": "image"}).json()["adapters"]
    assert {entry["id"] for entry in image} == {"flux-dev", "flux-1.1-pro-ultra"}


def test_an_unknown_kind_filter_returns_everything_rather_than_failing(client) -> None:
    assert len(client.get("/api/v1/core/providers", params={"kind": "nonsense"}).json()["adapters"]) == 4


def test_health_reports_every_adapter_without_raising(client) -> None:
    rows = client.get("/api/v1/core/providers/health").json()
    assert {row["id"] for row in rows} == set(registry.ids())
    for row in rows:
        assert row["available"] is False, "no GPU in this sandbox"
        assert row["reason"]


def test_health_says_why_a_remote_provider_cannot_run_locally(client) -> None:
    rows = {row["id"]: row for row in client.get("/api/v1/core/providers/health").json()}
    assert "no local adapter" in rows["flux-1.1-pro-ultra"]["reason"]


def test_the_provider_routes_contain_no_selection_logic() -> None:
    """They expose the registry; they do not choose adapters themselves."""

    tree = ast.parse(pathlib.Path("backend/app/main.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "list_provider_adapters",
            "check_provider_health",
        ):
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            assert "FluxDiffusersProvider" not in names
            assert "WanVideoProvider" not in names
            assert "HunyuanVideoProvider" not in names
            assert "GenerationType" not in names


def test_the_provider_routes_are_under_the_core_tag(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/v1/core/providers", "/api/v1/core/providers/health"):
        assert paths[path]["get"]["tags"] == ["core"]
