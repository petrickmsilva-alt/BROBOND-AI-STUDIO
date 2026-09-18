"""PR011 — ETAPA 6 and ETAPA 4: readiness, and the job path behind it.

Two things are proved here.

**Readiness (ETAPA 6).** `GET /api/v1/system/readiness` grows a `gpu` block
with `available`, `provider`, `model`, `vram` and `latency_ms`. The hard rule
is the one at the bottom of the etapa: *nunca lançar erro 500*. So the failure
modes are enumerated — unconfigured, unreachable, 5xx, a probe that raises an
arbitrary exception — and every single one must still answer 200 with
`available: false`. The endpoint is also not allowed to become a deploy gate:
a missing GPU is a missing capability, not a broken deploy.

**Job execution (ETAPA 4).** The documented path is
`GenerationSpec -> GenerationExecutor -> RunPod -> job_id -> poll -> Asset`,
with **no polling in the frontend**. That is asserted twice: once by running a
spec through the real `GenerationExecutor` into a mocked cluster, and once by
reading the frontend sources and failing if they learned to poll a job status.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gpu_fakes import PIXEL_PNG_BASE64, FakeClock, FakeRunPod, gpu_client

from app.core.contracts import GenerationKind, GenerationSpec
from app.main import app
from app.providers import gpu_health as gpu_health_module
from app.providers.gpu_health import (
    LOCAL_PROVIDER_NAME,
    REASON_NOT_CONFIGURED,
    gpu_health,
    readiness_gpu_block,
    unavailable,
)
from app.providers.provider_registry import ProviderRegistration, ProviderRegistry
from app.providers.retry_policy import RetryEngine, RetryPolicy
from app.providers.runpod_flux_provider import (
    RUNPOD_FLUX_MODEL_ID,
    RUNPOD_FLUX_PROVIDER_ID,
    RUNPOD_FLUX_VRAM,
    RunPodFluxProvider,
)
from app.providers.runpod_wan_provider import RUNPOD_WAN_PROVIDER_ID, RunPodWanProvider

client = TestClient(app)

GPU_KEYS = {"available", "provider", "model", "vram", "latency_ms"}


def configured_client(fake: FakeRunPod | None = None, **overrides):
    return gpu_client(fake or FakeRunPod(), FakeClock(), **overrides)


# ---------------------------------------------------------------------------
# The gpu block, in isolation
# ---------------------------------------------------------------------------


def test_the_block_has_the_documented_shape_when_the_cluster_answers() -> None:
    block = gpu_health(configured_client())

    assert GPU_KEYS <= set(block)
    assert block["available"] is True
    assert block["provider"] == "runpod"
    assert block["model"] == RUNPOD_FLUX_MODEL_ID
    assert block["vram"] == RUNPOD_FLUX_VRAM
    assert isinstance(block["latency_ms"], float)
    assert block["reason"] is None
    assert block["workers"] == {"ready": 2, "running": 1}


def test_an_unconfigured_cluster_reports_available_false_with_the_same_keys() -> None:
    """The DEV default: optional variables, an honest `false`, no exception."""

    block = gpu_health(configured_client(api_key="", endpoint=""))

    assert GPU_KEYS <= set(block)
    assert block["available"] is False
    assert block["reason"] == REASON_NOT_CONFIGURED
    assert "BROBOND_RUNPOD_API_KEY" in block["reason"]


def test_an_unreachable_cluster_reports_available_false() -> None:
    block = gpu_health(configured_client(FakeRunPod(failures=[0, 0, 0])))

    assert block["available"] is False
    assert "connection reset" in block["reason"]
    assert block["endpoint_host"] == "api.runpod.ai"


def test_a_cluster_answering_5xx_reports_available_false() -> None:
    block = gpu_health(configured_client(FakeRunPod(failures=[503, 503, 503])))

    assert block["available"] is False
    assert "503" in block["reason"]


def test_a_probe_that_raises_is_swallowed_into_a_false_block() -> None:
    """The load-bearing `except`: readiness must answer, always."""

    class Exploding:
        configured = True

        def describe(self):
            return {"endpoint_host": "x"}

        async def health(self, timeout=None):
            raise RuntimeError("something nobody predicted")

    block = gpu_health(Exploding())

    assert block["available"] is False
    assert "something nobody predicted" in block["reason"]


def test_the_block_never_carries_a_credential() -> None:
    serialised = json.dumps(gpu_health(configured_client()))

    assert "rp-test-key" not in serialised
    assert "Bearer" not in serialised
    assert "/v2/test-endpoint" not in serialised, "only the host, never the endpoint path"


def test_the_unavailable_helper_keeps_the_contract_keys() -> None:
    assert GPU_KEYS <= set(unavailable("because"))
    assert unavailable("because", latency_ms=5.0)["latency_ms"] == 5.0


# ---------------------------------------------------------------------------
# Composition with the host GPU detection that predates PR011
# ---------------------------------------------------------------------------


def test_the_host_gpu_block_is_preserved_not_replaced() -> None:
    """`backend` and `message` have been in this payload since ETAPA 9."""

    local = {"available": False, "backend": "cpu", "message": "nvidia-smi not found"}

    block = readiness_gpu_block(local, configured_client(api_key="", endpoint=""))

    assert block["backend"] == "cpu"
    assert block["message"] == "nvidia-smi not found"
    assert block["available"] is False
    assert block["cluster"]["available"] is False


def test_a_local_cuda_card_makes_the_block_available_even_without_a_cluster() -> None:
    local = {
        "available": True,
        "backend": "cuda",
        "gpus": [{"name": "NVIDIA RTX 4090", "vram_total_mb": 24564, "driver": "550.54"}],
    }

    block = readiness_gpu_block(local, configured_client(api_key="", endpoint=""))

    assert block["available"] is True
    assert block["provider"] == LOCAL_PROVIDER_NAME
    assert block["model"] == "NVIDIA RTX 4090"
    assert block["vram"] == "24GB"
    assert block["reason"] == REASON_NOT_CONFIGURED, "why the cluster is absent stays visible"


def test_a_local_card_without_a_detail_row_still_produces_the_keys() -> None:
    block = readiness_gpu_block({"available": True, "backend": "cuda"}, configured_client(api_key=""))

    assert block["provider"] == LOCAL_PROVIDER_NAME
    assert block["model"] == ""
    assert block["vram"] == ""


def test_the_cluster_wins_when_both_are_available() -> None:
    local = {"available": True, "backend": "cuda", "gpus": [{"name": "RTX 4090", "vram_total_mb": 24564}]}

    block = readiness_gpu_block(local, configured_client())

    assert block["provider"] == "runpod"
    assert block["model"] == RUNPOD_FLUX_MODEL_ID
    assert block["available"] is True


def test_the_composer_tolerates_a_missing_local_block() -> None:
    block = readiness_gpu_block(None, configured_client())

    assert block["available"] is True
    assert GPU_KEYS <= set(block)


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def test_readiness_exposes_the_gpu_block() -> None:
    body = client.get("/api/v1/system/readiness").json()

    assert GPU_KEYS <= set(body["gpu"])
    assert body["gpu"]["provider"] in {"runpod", LOCAL_PROVIDER_NAME}
    assert "cluster" in body["gpu"]


def test_readiness_keeps_the_pre_pr011_checks() -> None:
    """A new block must not cost the old contract."""

    body = client.get("/api/v1/system/readiness").json()

    assert {"cuda", "ffmpeg", "diffusers", "torch", "celery"}.issubset(body["checks"])
    assert {"ready", "inference_ready", "media_ready", "database", "migrations", "storage"} <= set(body)


def test_an_absent_gpu_does_not_turn_readiness_into_a_503() -> None:
    """A GPU is a capability, not a deploy gate."""

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 200
    assert response.json()["gpu"]["available"] is False, "no cluster and no CUDA in CI"


def test_readiness_never_returns_500_even_if_the_probe_explodes(monkeypatch) -> None:
    """The etapa says it in capitals: *nunca lançar erro 500*."""

    def exploding(*args, **kwargs):
        raise RuntimeError("probe blew up")

    monkeypatch.setattr(gpu_health_module, "GpuClient", exploding)

    response = client.get("/api/v1/system/readiness")

    assert response.status_code == 200
    assert response.json()["gpu"]["available"] is False


def test_the_readiness_payload_is_free_of_secrets(monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "runpod_api_key", "rp-super-secret-key")
    # `.invalid` is reserved by RFC 2606: the probe fails on DNS, instantly
    # and without leaving the machine.
    monkeypatch.setattr(config.settings, "runpod_endpoint", "https://gpu.invalid/v2/private-id")

    body = client.get("/api/v1/system/readiness").text

    assert "rp-super-secret-key" not in body
    assert "private-id" not in body


def test_readiness_is_public_and_needs_no_token() -> None:
    assert client.get("/api/v1/system/readiness").status_code == 200


# ---------------------------------------------------------------------------
# ETAPA 4 — spec -> executor -> RunPod -> job_id -> poll -> asset
# ---------------------------------------------------------------------------


def image_spec() -> GenerationSpec:
    return GenerationSpec(
        prompt_original="a lighthouse",
        prompt_compiled="a lighthouse at dusk",
        kind=GenerationKind.IMAGE,
        provider=RUNPOD_FLUX_PROVIDER_ID,
    )


def registry_with(provider_instance, provider_id: str) -> ProviderRegistry:
    from app.providers.mock_provider import MOCK_PROVIDER_ID, MockProvider

    registry = ProviderRegistry()
    registry.register(
        ProviderRegistration(provider_id, provider_id, lambda model_id=None: provider_instance)
    )
    registry.register(
        ProviderRegistration(MOCK_PROVIDER_ID, "Mock", lambda model_id=None: MockProvider())
    )
    return registry


def test_the_executor_drives_the_cluster_end_to_end(tmp_path) -> None:
    from app.providers.generation_executor import GenerationExecutor

    fake = FakeRunPod(polls_before_done=2)
    connector = RunPodFluxProvider(client=gpu_client(fake, FakeClock()))
    executor = GenerationExecutor(
        registry_with(connector, RUNPOD_FLUX_PROVIDER_ID), telemetry_store=None
    )

    execution = executor.execute(image_spec(), tmp_path)

    assert execution.job.status == "complete"
    assert execution.job.provider_id == RUNPOD_FLUX_PROVIDER_ID
    assert execution.job.fallback is False
    assert Path(execution.asset.path).is_file()
    assert fake.paths[0] == "/run", "the executor submitted a job"
    assert fake.call_count("/status/") == 3, "and the backend did the polling"
    assert (execution.asset.metadata or {})["job_id"] == "job-1"


def test_a_cluster_outage_falls_back_instead_of_failing_the_batch(tmp_path) -> None:
    """PR009's fallback chain works unchanged for a cluster connector."""

    from app.providers.generation_executor import GenerationExecutor

    connector = RunPodFluxProvider(
        client=gpu_client(FakeRunPod(failures=[503] * 30), FakeClock())
    )
    executor = GenerationExecutor(
        registry_with(connector, RUNPOD_FLUX_PROVIDER_ID),
        retry_engine=RetryEngine(RetryPolicy(base_delay_seconds=0.0)),
        telemetry_store=None,
    )

    execution = executor.execute(image_spec(), tmp_path)

    assert execution.job.fallback is True
    assert "runpod-flux" in (execution.job.fallback_reason or "")
    assert Path(execution.asset.path).is_file(), "the batch still produced an asset"


def test_a_video_spec_reaches_the_wan_connector(tmp_path) -> None:
    from app.providers.generation_executor import GenerationExecutor

    fake = FakeRunPod(polls_before_done=0, output={"video": PIXEL_PNG_BASE64})
    connector = RunPodWanProvider(client=gpu_client(fake, FakeClock()))
    spec = GenerationSpec(
        prompt_original="a car",
        prompt_compiled="a car on a coastal road",
        kind=GenerationKind.VIDEO,
        provider=RUNPOD_WAN_PROVIDER_ID,
    )

    execution = GenerationExecutor(
        registry_with(connector, RUNPOD_WAN_PROVIDER_ID), telemetry_store=None
    ).execute(spec, tmp_path)

    assert execution.asset.kind == "video"
    assert Path(execution.asset.path).suffix == ".mp4"


def test_the_cluster_connectors_are_registered_without_changing_the_defaults() -> None:
    """PR011 adds registrations; it does not repoint the platform."""

    from app.providers.provider_registry import create_default_registry

    registry = create_default_registry()

    assert registry.get("runpod-flux").provider_id == RUNPOD_FLUX_PROVIDER_ID
    assert registry.get("runpod-image").provider_id == RUNPOD_FLUX_PROVIDER_ID
    assert registry.get("runpod-wan").provider_id == RUNPOD_WAN_PROVIDER_ID
    assert registry.get("runpod-video").provider_id == RUNPOD_WAN_PROVIDER_ID
    assert registry.defaults() == {"image": "flux-dev", "video": "wan-2.1-t2v"}


def test_the_registry_reports_cluster_health_without_secrets() -> None:
    from app.providers.provider_registry import create_default_registry

    rows = {row.id: row for row in create_default_registry().health_all()}

    assert rows["runpod-flux"].status == "unavailable", "no credentials in CI"
    assert "not configured" in (rows["runpod-flux"].reason or "")
    assert rows["runpod-wan"].capabilities.supports_video is True


def test_the_public_provider_list_redacts_nothing_it_should_not_and_leaks_nothing(monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "runpod_api_key", "rp-leak-me")
    monkeypatch.setattr(config.settings, "runpod_endpoint", "https://gpu.invalid/v2/leaky")

    body = client.get("/api/v1/providers").text

    assert "rp-leak-me" not in body
    assert "runpod-flux" in body


@pytest.mark.parametrize(
    "source",
    ["app/page.tsx", "app/studio/render/page.tsx", "app/studio/providers/page.tsx", "lib/api.ts"],
)
def test_the_frontend_does_not_poll_a_gpu_job(source: str) -> None:
    """ETAPA 4: *nenhum polling no frontend*. Progress arrives over WebSocket."""

    text = Path(source).read_text(encoding="utf-8")

    for banned in ("runpod", "/status/", "api.runpod.ai", "RUNPOD_API_KEY"):
        assert banned not in text, f"{banned!r} must never appear in browser code"


def test_no_frontend_file_mentions_the_cluster_credentials() -> None:
    """Zero secrets exposed to the frontend — checked across the whole tree."""

    roots = [Path("app"), Path("lib"), Path("components")]
    offenders = [
        str(path)
        for root in roots
        for path in root.rglob("*.ts*")
        if "RUNPOD" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
