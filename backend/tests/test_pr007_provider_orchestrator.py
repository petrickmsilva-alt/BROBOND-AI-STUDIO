from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.contracts import GenerationKind, GenerationSpec
from app.main import app
from app.provider_capabilities import list_universal_provider_responses, prompt_budget_for_provider
from app.providers.base_provider import (
    BaseProvider,
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
    ProviderUnavailable,
)
from app.providers.flux_provider import FluxProvider
from app.providers.generation_executor import GenerationExecutor
from app.providers.mock_provider import MockProvider
from app.providers.provider_registry import ProviderRegistration, ProviderRegistry, create_default_registry
from app.providers.wan_provider import WanProvider
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


# ---------------------------------------------------------------------------
# BaseProvider
# ---------------------------------------------------------------------------


def test_base_provider_declares_the_universal_abstract_interface() -> None:
    assert BaseProvider.__abstractmethods__ == {
        "capabilities",
        "generate_image",
        "generate_video",
        "upscale",
        "health",
        "estimate",
    }
    for method in ("generate_image", "generate_video", "upscale", "estimate"):
        signature = inspect.signature(getattr(BaseProvider, method))
        assert "spec" in signature.parameters
        assert signature.parameters["spec"].annotation in {"GenerationSpec", GenerationSpec}
        assert "prompt" not in signature.parameters
        assert "parameters" not in signature.parameters


def test_provider_payloads_are_serializable_and_safe() -> None:
    capabilities = ProviderCapabilities(
        max_resolution="1024",
        supports_video=True,
        supports_image=True,
        supports_lora=True,
        supports_upscale=True,
        supports_seed=True,
        supports_negative_prompt=True,
    )
    estimate = ProviderEstimate("mock", "image", 0.1)
    asset = ProviderAsset("/tmp/fake.png", "image", "mock", width=1024, height=1024)
    health = ProviderHealth("mock", "Mock", "ready", 1.2, "v1", capabilities)

    assert capabilities.to_dict()["supports_seed"] is True
    assert estimate.to_dict()["provider_id"] == "mock"
    assert asset.to_dict()["metadata"] == {}
    assert health.to_dict()["capabilities"]["max_resolution"] == "1024"
    with pytest.raises(ValueError, match="kind"):
        ProviderAsset("/tmp/fake.txt", "text", "mock")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_default_registry_lists_flux_wan_mock_and_future_video_adapters() -> None:
    registry = create_default_registry()
    providers = registry.list()
    labels = {provider.label for provider in providers}

    assert {"Flux", "Wan", "Mock"} <= labels
    assert registry.get("flux", kind=GenerationKind.IMAGE).provider_id == "flux-dev"
    assert registry.get(None, kind=GenerationKind.IMAGE).provider_id == "flux-dev"
    assert registry.get(None, kind=GenerationKind.VIDEO).provider_id == "wan-2.1-t2v"
    assert registry.defaults() == {"image": "flux-dev", "video": "wan-2.1-t2v"}


def test_registry_adds_a_provider_by_registration_not_by_branch() -> None:
    registry = ProviderRegistry()
    registry.register(
        ProviderRegistration(
            provider_id="local-mock",
            label="Local Mock",
            factory=lambda model_id=None: MockProvider(),
            aliases=("mock-alias",),
            default_for=(GenerationKind.IMAGE,),
        )
    )

    assert registry.get("mock-alias").provider_id == "mock"
    assert registry.get(None, kind=GenerationKind.IMAGE).provider_id == "mock"

    registry.register(
        ProviderRegistration(
            provider_id="image-only",
            label="Image Only",
            factory=lambda model_id=None: FluxProvider(),
        )
    )
    with pytest.raises(ProviderUnavailable, match="video"):
        registry.get("image-only", kind=GenerationKind.VIDEO)


def test_registry_health_all_reports_latency_version_status_and_capabilities() -> None:
    registry = ProviderRegistry()
    registry.register(ProviderRegistration("mock", "Mock", lambda model_id=None: MockProvider()))

    rows = registry.health_all()

    assert len(rows) == 1
    row = rows[0]
    assert row.id == "mock"
    assert row.status == "ready"
    assert row.latency_ms >= 0
    assert row.version == "mock-provider-v1"
    assert row.capabilities.supports_image is True


def test_provider_capability_helpers_keep_main_thin_and_core_opaque() -> None:
    class TokenReasonMock(MockProvider):
        def health(self) -> ProviderHealth:
            return ProviderHealth(
                id=self.provider_id,
                label=self.label,
                status="unavailable",
                latency_ms=0,
                version=self.version,
                capabilities=self.capabilities(),
                reason="missing API_TOKEN=super-secret",
            )

    registry = ProviderRegistry()
    registry.register(ProviderRegistration("mock", "Mock", lambda model_id=None: TokenReasonMock()))

    rows = list_universal_provider_responses(registry)

    assert rows[0].id == "mock"
    assert rows[0].capabilities.supports_upscale is True
    assert "token" not in (rows[0].reason or "").casefold()
    assert "secret" not in (rows[0].reason or "").casefold()
    assert prompt_budget_for_provider("mock", default_budget=333, registry=registry) == 1200
    assert prompt_budget_for_provider("missing", default_budget=333, registry=registry) == 333
    assert prompt_budget_for_provider("", default_budget=333, registry=registry) == 333


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def test_mock_provider_returns_fake_image_video_and_upscale_assets(tmp_path: Path) -> None:
    provider = MockProvider()
    image = provider.generate_image(spec(kind=GenerationKind.IMAGE), tmp_path)
    video = provider.generate_video(spec(kind=GenerationKind.VIDEO), tmp_path)
    upscaled = provider.upscale(spec(kind=GenerationKind.IMAGE), image.path, tmp_path / "up")

    assert Path(image.path).read_bytes()
    # PR009: the mock honours the spec's aspect ratio (fallback assets must
    # survive the quality gate); 16:9 at the 1024 mock cap.
    assert image.kind == "image" and image.width == 1024 and image.height == 576
    square = provider.generate_image(spec(aspect_ratio="1:1"), tmp_path)
    assert square.width == 1024 and square.height == 1024
    assert Path(video.path).read_bytes()
    assert video.kind == "video" and video.duration_seconds == 5 and video.fps == 24
    assert Path(upscaled.path).read_bytes()
    assert provider.health().status == "ready"
    assert provider.estimate(spec()).estimated_seconds == 0.1


def test_flux_provider_runs_the_real_connector_without_accepting_prompt_strings(monkeypatch, tmp_path: Path) -> None:
    """PR009: the connector receives only the spec — the pipeline seam sees it too."""

    seen: dict[str, object] = {}

    class FakePipeline:
        def __call__(self, **kwargs):
            seen["kwargs"] = kwargs
            return SimpleNamespace(images=[SimpleNamespace(save=lambda path: Path(path).write_bytes(b"fake"), size=(1024, 576))])

    def fake_loader(model_id: str, mode: str):
        seen["model_id"] = model_id
        seen["mode"] = mode
        return FakePipeline()

    provider = FluxProvider(model_id="custom-flux", pipeline_loader=fake_loader)
    output = provider.generate_image(spec(provider="flux-dev", seed=None), tmp_path)

    assert seen["model_id"] == "custom-flux"
    assert seen["mode"] == "text-to-image"
    assert seen["kwargs"]["prompt"] == "compiled cinematic prompt"
    assert output.kind == "image"
    assert output.provider_id == "flux-dev"
    assert Path(output.path).read_bytes() == b"fake"
    # Health never raises, even without CUDA.
    assert provider.health().status in {"ready", "unavailable"}
    with pytest.raises(ProviderUnavailable, match="video generation"):
        provider.generate_video(spec(kind=GenerationKind.VIDEO), tmp_path)


def test_flux_provider_signature_never_accepts_a_prompt_or_parameters() -> None:
    """The literal ETAPA 3 rule, applied to the PR009 real connector."""

    signature = inspect.signature(FluxProvider.generate_image)
    assert list(signature.parameters) == ["self", "spec", "output_dir"]
    assert "prompt" not in signature.parameters
    assert "parameters" not in signature.parameters


def test_wan_provider_runs_the_real_connector_without_duplicating_video_logic(monkeypatch, tmp_path: Path) -> None:
    """PR009: Wan and Hunyuan still share one generate_video implementation."""

    seen: dict[str, object] = {}

    # imageio is a GPU-worker dependency; inject the module the way
    # test_provider_runtime.py does so the encode path is testable in CI.
    import sys
    import types

    def fake_imwrite(target, frames, fps=None, codec=None):
        seen["fps"] = fps
        seen["codec"] = codec
        Path(target).write_bytes(b"fake")

    module = types.ModuleType("imageio.v3")
    module.imwrite = fake_imwrite
    parent = types.ModuleType("imageio")
    parent.v3 = module
    monkeypatch.setitem(sys.modules, "imageio", parent)
    monkeypatch.setitem(sys.modules, "imageio.v3", module)

    class FakePipeline:
        def __call__(self, **kwargs):
            seen["kwargs"] = kwargs
            return SimpleNamespace(frames=[[object()]])

    def fake_loader(model_id: str, pipeline_class_name: str):
        seen["model_id"] = model_id
        seen["pipeline_class"] = pipeline_class_name
        return FakePipeline()

    provider = WanProvider(model_id="custom-wan", pipeline_loader=fake_loader)
    output = provider.generate_video(
        spec(provider="wan-2.1-t2v", kind=GenerationKind.VIDEO, seed=None), tmp_path
    )

    assert "generate_video" not in WanProvider.__dict__
    assert seen["model_id"] == "custom-wan"
    assert seen["pipeline_class"] == "WanPipeline"
    assert seen["kwargs"]["prompt"] == "compiled cinematic prompt"
    assert seen["kwargs"]["num_frames"] % 4 == 1, "Wan's 4n+1 frame rule"
    assert output.kind == "video"
    assert output.provider_id == "wan-2.1-t2v"
    assert output.duration_seconds == 5
    assert output.fps == 24
    assert Path(output.path).read_bytes() == b"fake"
    assert provider.health().status in {"ready", "unavailable"}
    with pytest.raises(ProviderUnavailable, match="image generation"):
        provider.generate_image(spec(), tmp_path)


# ---------------------------------------------------------------------------
# Executor and API
# ---------------------------------------------------------------------------


def test_generation_executor_runs_spec_registry_provider_asset_job_without_knowing_provider_names(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    registry.register(
        ProviderRegistration(
            provider_id="mock",
            label="Mock",
            factory=lambda model_id=None: MockProvider(),
            default_for=(GenerationKind.IMAGE, GenerationKind.VIDEO),
        )
    )
    executor = GenerationExecutor(registry)

    result = executor.execute(spec(provider="mock", kind=GenerationKind.IMAGE), tmp_path, job_id="job-1")

    assert result.asset.provider_id == "mock"
    assert Path(result.asset.path).exists()
    assert result.job.id == "job-1"
    assert result.job.status == "complete"
    assert result.to_dict()["job"]["asset"]["kind"] == "image"


def test_executor_uses_video_method_for_video_specs(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    registry.register(ProviderRegistration("mock", "Mock", lambda model_id=None: MockProvider()))
    result = GenerationExecutor(registry).execute(spec(provider="mock", kind=GenerationKind.VIDEO), tmp_path)

    assert result.asset.kind == "video"
    assert result.job.estimate.kind == "video"


def test_health_endpoint_exposes_status_latency_version_and_capabilities_without_secrets() -> None:
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    rows = response.json()
    by_label = {row["label"]: row for row in rows}

    assert {"Flux", "Wan", "Mock"} <= set(by_label)
    for label in ("Flux", "Wan", "Mock"):
        row = by_label[label]
        assert {"status", "latency_ms", "version", "capabilities"} <= set(row)
        assert row["latency_ms"] >= 0
        assert "max_resolution" in row["capabilities"]
        assert "supports_video" in row["capabilities"]
        assert "supports_image" in row["capabilities"]
        leaked = " ".join(str(value).casefold() for value in row.values())
        assert "secret" not in leaked
        assert "token" not in leaked


def test_core_does_not_name_provider_brands_or_catalogue_ids() -> None:
    root = Path("backend/app/core")
    banned = ("FLUX", "Wan-", "Hunyuan", "Kling", "RunwayML", "flux-dev", "wan-2.1", "hunyuan-video")
    offenders: dict[str, list[str]] = {}
    for path in root.rglob("*.py"):
        hits = [token for token in banned if token in path.read_text(encoding="utf-8")]
        if hits:
            offenders[str(path)] = hits
    assert offenders == {}


def test_main_route_delegates_provider_discovery_and_budget_lookup() -> None:
    source = Path("backend/app/main.py").read_text(encoding="utf-8")

    assert "list_universal_provider_responses()" in source
    assert "prompt_budget_for_provider(" in source
    assert "DEFAULT_REGISTRY.capabilities" not in source
    assert ".health_all()" not in source


def test_frontend_provider_page_uses_capability_discovery() -> None:
    source = Path("app/studio/providers/page.tsx").read_text(encoding="utf-8")
    api_source = Path("lib/api.ts").read_text(encoding="utf-8")

    assert "/studio/providers" in str(Path("app/studio/providers/page.tsx"))
    assert "listProviders(" in source
    assert "Flux" in source and "Wan" in source and "Mock" in source
    assert "Status" not in source or "status" in source
    assert "latency_ms" in source
    assert "capabilities" in source
    assert "Testar" in source
    assert "createImageJob(" not in source
    assert "createVideoJob(" not in source
    assert "get<UniversalProvider[]>('/api/v1/providers')" in api_source
