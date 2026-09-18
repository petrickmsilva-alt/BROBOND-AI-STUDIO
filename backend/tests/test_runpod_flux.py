"""PR011 — ETAPA 7: the RunPod Flux connector, against a mocked cluster.

The connector is exercised end to end — spec in, file on disk out — with the
same `FakeRunPod` the transport tests use, so what is verified is the real
lifecycle (submit, poll, download) and not a stubbed-out `execute_job`.

The two properties that matter most here are architectural:

* the connector receives **only** a `GenerationSpec` (asserted by signature,
  not by convention), and
* it never handles an HTTP status code, a header or a retry — that is the
  client's job, and the split is what keeps both files small enough to read.
"""
from __future__ import annotations

import base64
import inspect
from pathlib import Path

import pytest
from gpu_fakes import (
    PIXEL_PNG_BASE64,
    PIXEL_PNG_BYTES,
    FakeClock,
    FakeRunPod,
    NeverFinishes,
    gpu_client,
)

from app.core.contracts import GenerationKind, GenerationSpec
from app.providers.base_provider import ProviderUnavailable, ProviderUnsupported
from app.providers.runpod_base import GPU_PROVIDER_NAME, RunPodProvider
from app.providers.runpod_flux_provider import (
    DEFAULT_UPSCALE_FACTOR,
    RUNPOD_FLUX_ESTIMATED_SECONDS,
    MODE_CONTROL,
    MODE_IMAGE_TO_IMAGE,
    MODE_INPAINT,
    MODE_OUTPAINT,
    MODE_TEXT_TO_IMAGE,
    OPERATION_CONTROL,
    OPERATION_IMAGE,
    OPERATION_INPAINT,
    OPERATION_OUTPAINT,
    OPERATION_UPSCALE,
    RUNPOD_FLUX_MODEL_ID,
    RUNPOD_FLUX_PROVIDER_ID,
    RUNPOD_FLUX_VRAM,
    RunPodFluxProvider,
    flux_request_from_spec,
    resolve_flux_mode,
    resolve_flux_operation,
)


def spec(**overrides) -> GenerationSpec:
    fields = {
        "prompt_original": "a lighthouse",
        "prompt_compiled": "a lighthouse at dusk, cinematic, 35mm",
        "negative_prompt": "blurry, watermark",
        "aspect_ratio": "16:9",
        "resolution": 1024,
        "guidance_scale": 3.5,
        "steps": 28,
        "seed": 7,
        "kind": GenerationKind.IMAGE,
        "mode": MODE_TEXT_TO_IMAGE,
        "provider": RUNPOD_FLUX_PROVIDER_ID,
    }
    fields.update(overrides)
    return GenerationSpec(**fields)


def provider(fake: FakeRunPod | None = None, **client_kwargs) -> tuple[RunPodFluxProvider, FakeRunPod]:
    cluster = fake or FakeRunPod(polls_before_done=1)
    return RunPodFluxProvider(client=gpu_client(cluster, FakeClock(), **client_kwargs)), cluster


def reference(tmp_path: Path) -> str:
    path = tmp_path / "reference.png"
    path.write_bytes(PIXEL_PNG_BYTES)
    return str(path)


# ---------------------------------------------------------------------------
# Identity and capabilities
# ---------------------------------------------------------------------------


def test_the_connector_identifies_itself_without_replacing_the_local_flux() -> None:
    connector, _ = provider()

    assert connector.provider_id == "runpod-flux"
    assert connector.model_id == RUNPOD_FLUX_MODEL_ID
    assert connector.vram == RUNPOD_FLUX_VRAM
    assert isinstance(connector, RunPodProvider)


def test_capabilities_keep_the_public_shape_and_claim_image_and_upscale() -> None:
    """`ProviderCapabilities` is the frozen public contract — 8 fields, no more."""

    capabilities = RunPodFluxProvider().capabilities()

    assert capabilities.supports_image is True
    assert capabilities.supports_video is False
    assert capabilities.supports_upscale is True
    assert capabilities.supports_seed is True
    assert capabilities.supports_negative_prompt is True
    assert capabilities.supports_lora is True
    assert capabilities.supports(GenerationKind.IMAGE) is True
    assert capabilities.supports(GenerationKind.VIDEO) is False
    assert set(capabilities.to_dict()) == {
        "max_resolution",
        "supports_video",
        "supports_image",
        "supports_lora",
        "supports_upscale",
        "supports_seed",
        "supports_negative_prompt",
        "prompt_budget",
    }


@pytest.mark.parametrize(
    "operation",
    [OPERATION_IMAGE, OPERATION_UPSCALE, OPERATION_INPAINT, OPERATION_OUTPAINT, OPERATION_CONTROL],
)
def test_the_five_etapa_2_operations_are_declared(operation: str) -> None:
    assert RunPodFluxProvider.supports_operation(operation) is True


def test_an_unknown_operation_is_not_claimed() -> None:
    assert RunPodFluxProvider.supports_operation("text-to-video") is False


def test_the_connector_declares_what_it_cannot_honour() -> None:
    """Declared, not silently dropped — the ETAPA 10 rule."""

    assert "duration" in RunPodFluxProvider.UNSUPPORTED_SPEC_FIELDS
    assert "fps" in RunPodFluxProvider.UNSUPPORTED_SPEC_FIELDS
    assert "prompt_compiled" in RunPodFluxProvider.CONSUMED_SPEC_FIELDS
    assert not (
        RunPodFluxProvider.CONSUMED_SPEC_FIELDS & RunPodFluxProvider.UNSUPPORTED_SPEC_FIELDS
    ), "a field cannot be both consumed and unsupported"


# ---------------------------------------------------------------------------
# Spec -> request, pure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "operation"),
    [
        (MODE_TEXT_TO_IMAGE, OPERATION_IMAGE),
        (MODE_IMAGE_TO_IMAGE, OPERATION_IMAGE),
        (MODE_INPAINT, OPERATION_INPAINT),
        (MODE_OUTPAINT, OPERATION_OUTPAINT),
        (MODE_CONTROL, OPERATION_CONTROL),
    ],
)
def test_every_mode_resolves_to_its_operation(mode: str, operation: str) -> None:
    assert resolve_flux_operation(spec(mode=mode)) == operation
    assert resolve_flux_mode(spec(mode=mode)) == mode


def test_the_video_default_mode_is_read_as_a_plain_image_render() -> None:
    """`GenerationSpec.mode` defaults to `text-to-video`; that is not an error."""

    assert resolve_flux_operation(spec(mode="text-to-video")) == OPERATION_IMAGE
    assert resolve_flux_mode(spec(mode="text-to-video")) == MODE_TEXT_TO_IMAGE


def test_the_request_is_built_only_from_the_spec() -> None:
    request = flux_request_from_spec(spec(aspect_ratio="9:16", resolution=768, seed=None))

    assert request.prompt == "a lighthouse at dusk, cinematic, 35mm"
    assert (request.width, request.height) == (432, 768), "portrait: the long side is the height"
    assert request.seed is None, "None means 'let the model choose', never seed zero"
    assert request.to_dict()["negative_prompt"] == "blurry, watermark"


def test_the_raw_brief_never_reaches_the_cluster() -> None:
    """Only the compiled prompt crosses the boundary (ETAPA 3)."""

    connector, fake = provider()
    connector.generate_image(spec(prompt_original="SECRET BRIEF"), "/tmp")

    assert "SECRET BRIEF" not in repr(fake.submitted)
    assert fake.submitted[0]["prompt"] == "a lighthouse at dusk, cinematic, 35mm"


def test_a_controlnet_of_none_is_not_sent_as_a_control_type() -> None:
    request = flux_request_from_spec(spec(mode=MODE_CONTROL, controlnet="none"))

    assert request.control_type is None


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------


def test_the_payload_carries_the_model_and_the_sampling_parameters() -> None:
    connector, fake = provider()

    connector.generate_image(spec(), "/tmp")

    payload = fake.submitted[0]
    assert payload["operation"] == OPERATION_IMAGE
    assert payload["model"] == RUNPOD_FLUX_MODEL_ID
    assert payload["width"] == 1024
    assert payload["height"] == 576
    assert payload["guidance_scale"] == 3.5
    assert payload["num_inference_steps"] == 28
    assert payload["seed"] == 7
    assert "image" not in payload, "text-to-image sends no reference"
    assert "lora" not in payload


def test_an_unseeded_spec_omits_the_seed_instead_of_sending_zero() -> None:
    connector, fake = provider()

    connector.generate_image(spec(seed=None), "/tmp")

    assert "seed" not in fake.submitted[0]


def test_a_persona_lora_is_forwarded() -> None:
    connector, fake = provider()

    connector.generate_image(spec(lora="weights/petrick.safetensors"), "/tmp")

    assert fake.submitted[0]["lora"] == "weights/petrick.safetensors"


def test_control_reference_sends_the_control_type_and_strength(tmp_path) -> None:
    connector, fake = provider()

    connector.generate_image(
        spec(mode=MODE_CONTROL, controlnet="depth", ip_adapter_scale=0.42, reference_path=reference(tmp_path)),
        tmp_path,
    )

    payload = fake.submitted[0]
    assert payload["operation"] == OPERATION_CONTROL
    assert payload["control_type"] == "depth"
    assert payload["control_strength"] == 0.42
    assert payload["image"].startswith("data:image/png;base64,")


def test_control_without_a_named_controlnet_falls_back_to_plain_reference(tmp_path) -> None:
    connector, fake = provider()

    connector.generate_image(spec(mode=MODE_CONTROL, reference_path=reference(tmp_path)), tmp_path)

    assert fake.submitted[0]["control_type"] == "reference"


@pytest.mark.parametrize(
    ("mode", "flag"), [(MODE_INPAINT, "inpaint"), (MODE_OUTPAINT, "outpaint")]
)
def test_inpaint_and_outpaint_flag_themselves_in_the_payload(tmp_path, mode: str, flag: str) -> None:
    connector, fake = provider()

    connector.generate_image(spec(mode=mode, reference_path=reference(tmp_path)), tmp_path)

    assert fake.submitted[0][flag] is True
    assert fake.submitted[0]["operation"] == mode


# ---------------------------------------------------------------------------
# The full lifecycle
# ---------------------------------------------------------------------------


def test_generate_image_submits_polls_downloads_and_writes_the_file(tmp_path) -> None:
    connector, fake = provider(FakeRunPod(polls_before_done=2))

    asset = connector.generate_image(spec(), tmp_path)

    assert fake.paths == ["/run", "/status/job-1", "/status/job-1", "/status/job-1"]
    written = Path(asset.path)
    assert written.read_bytes() == PIXEL_PNG_BYTES
    assert written.name.endswith(".png")
    assert asset.kind == "image"
    assert asset.provider_id == RUNPOD_FLUX_PROVIDER_ID
    assert (asset.width, asset.height) == (1024, 576)


def test_the_asset_metadata_traces_the_job_without_leaking_a_secret(tmp_path) -> None:
    connector, _ = provider(FakeRunPod(polls_before_done=1))

    asset = connector.generate_image(spec(), tmp_path)

    metadata = asset.metadata or {}
    assert metadata["gpu_provider"] == GPU_PROVIDER_NAME
    assert metadata["job_id"] == "job-1"
    assert metadata["model_id"] == RUNPOD_FLUX_MODEL_ID
    assert metadata["polls"] == 2
    assert metadata["operation"] == OPERATION_IMAGE
    assert metadata["vram"] == RUNPOD_FLUX_VRAM
    assert "api_key" not in repr(metadata).lower()
    assert "bearer" not in repr(metadata).lower()


def test_a_reference_mode_uploads_the_local_frame_inline(tmp_path) -> None:
    connector, fake = provider()

    connector.generate_image(spec(mode=MODE_IMAGE_TO_IMAGE, reference_path=reference(tmp_path)), tmp_path)

    encoded = fake.submitted[0]["image"]
    assert base64.b64decode(encoded.split(",", 1)[1]) == PIXEL_PNG_BYTES


@pytest.mark.parametrize("mode", [MODE_IMAGE_TO_IMAGE, MODE_INPAINT, MODE_OUTPAINT, MODE_CONTROL])
def test_a_reference_mode_without_a_reference_is_a_fatal_value_error(tmp_path, mode: str) -> None:
    """Fatal, not retryable: retrying cannot conjure a source image."""

    connector, fake = provider()

    with pytest.raises(ValueError, match="reference_path"):
        connector.generate_image(spec(mode=mode), tmp_path)
    assert fake.calls == [], "it refuses before spending a GPU second"


def test_a_missing_reference_file_is_a_fatal_value_error(tmp_path) -> None:
    connector, _ = provider()

    with pytest.raises(ValueError, match="not found"):
        connector.generate_image(
            spec(mode=MODE_IMAGE_TO_IMAGE, reference_path=str(tmp_path / "gone.png")), tmp_path
        )


def test_upscale_sends_the_source_and_names_the_output(tmp_path) -> None:
    connector, fake = provider()
    source = tmp_path / "render.png"
    source.write_bytes(PIXEL_PNG_BYTES)

    asset = connector.upscale(spec(), source, tmp_path)

    payload = fake.submitted[0]
    assert payload["operation"] == OPERATION_UPSCALE
    assert payload["scale"] == DEFAULT_UPSCALE_FACTOR
    assert payload["image"].startswith("data:image/png;base64,")
    assert Path(asset.path).name.endswith("-upscaled.png")
    assert (asset.width, asset.height) == (2048, 1152)
    assert (asset.metadata or {})["source"] == str(source)


def test_a_result_url_is_downloaded_instead_of_decoded(tmp_path) -> None:
    connector, _ = provider(
        FakeRunPod(polls_before_done=0, output={"image_url": "https://cdn.example.test/job-1.png"})
    )

    asset = connector.generate_image(spec(), tmp_path)

    assert Path(asset.path).read_bytes() == PIXEL_PNG_BYTES


def test_a_list_of_results_takes_the_first(tmp_path) -> None:
    connector, _ = provider(FakeRunPod(polls_before_done=0, output={"image": [PIXEL_PNG_BASE64]}))

    assert Path(connector.generate_image(spec(), tmp_path).path).read_bytes() == PIXEL_PNG_BYTES


# ---------------------------------------------------------------------------
# Failure translation
# ---------------------------------------------------------------------------


def test_an_unconfigured_cluster_is_unavailable_not_a_crash(tmp_path) -> None:
    connector = RunPodFluxProvider(client=gpu_client(FakeRunPod(), api_key="", endpoint=""))

    with pytest.raises(ProviderUnavailable, match="BROBOND_RUNPOD_API_KEY"):
        connector.generate_image(spec(), tmp_path)


def test_a_failed_job_becomes_provider_unavailable(tmp_path) -> None:
    """Which is exactly what the PR009 retry/fallback stack already handles."""

    connector, _ = provider(FakeRunPod(polls_before_done=0, final_status="FAILED", error="OOM"))

    with pytest.raises(ProviderUnavailable, match="OOM"):
        connector.generate_image(spec(), tmp_path)


def test_a_cluster_timeout_becomes_provider_unavailable(tmp_path) -> None:
    connector, fake = provider(NeverFinishes(), timeout=4.0, poll_interval=1.0)

    with pytest.raises(ProviderUnavailable, match="did not finish"):
        connector.generate_image(spec(), tmp_path)
    assert fake.cancelled == ["job-1"]


def test_a_persistent_http_error_becomes_provider_unavailable(tmp_path) -> None:
    connector, _ = provider(FakeRunPod(failures=[500, 500, 500]))

    with pytest.raises(ProviderUnavailable, match="GPU call failed"):
        connector.generate_image(spec(), tmp_path)


def test_a_completed_job_with_no_artifact_is_a_failure_not_an_empty_success(tmp_path) -> None:
    connector, _ = provider(FakeRunPod(polls_before_done=0, output={"logs": "done"}))

    with pytest.raises(ProviderUnavailable, match="without a usable artifact"):
        connector.generate_image(spec(), tmp_path)


def test_a_corrupt_result_reference_is_reported_against_the_job(tmp_path) -> None:
    connector, _ = provider(FakeRunPod(polls_before_done=0, output={"image": "!!!not base64!!!"}))

    with pytest.raises(ProviderUnavailable, match="could not download job"):
        connector.generate_image(spec(), tmp_path)


def test_a_client_that_loses_its_configuration_mid_flight_is_unavailable(tmp_path) -> None:
    """Belt and braces: the guard is checked, and the client checks again."""

    connector, _ = provider()
    connector.client.api_key = ""  # e.g. a settings reload between the two checks
    connector.configured  # noqa: B018 - the property is read by execute_job

    class Lying:
        configured = True

        async def run(self, payload):
            from app.providers.gpu_client import GpuNotConfigured

            raise GpuNotConfigured("endpoint disappeared")

    connector._client = Lying()
    with pytest.raises(ProviderUnavailable, match="endpoint disappeared"):
        connector.generate_image(spec(), tmp_path)


def test_video_is_refused_rather_than_faked(tmp_path) -> None:
    connector, _ = provider()

    with pytest.raises(ProviderUnsupported, match="video generation"):
        connector.generate_video(spec(kind=GenerationKind.VIDEO), tmp_path)


# ---------------------------------------------------------------------------
# Health, estimates and cancellation
# ---------------------------------------------------------------------------


def test_health_is_ready_when_the_cluster_answers() -> None:
    connector, _ = provider()

    report = connector.health()

    assert report.status == "ready"
    assert report.reason is None
    assert report.last_health_at
    assert report.capabilities.supports_image is True


def test_health_is_unavailable_and_explains_itself_when_unconfigured() -> None:
    connector = RunPodFluxProvider(client=gpu_client(FakeRunPod(), api_key="", endpoint=""))

    report = connector.health()

    assert report.status == "unavailable"
    assert "not configured" in (report.reason or "")


def test_health_is_unavailable_when_the_cluster_is_unreachable() -> None:
    connector, _ = provider(FakeRunPod(failures=[0, 0, 0]))

    report = connector.health()

    assert report.status == "unavailable"
    assert "connection reset" in (report.reason or "")


def test_health_never_carries_the_credential() -> None:
    connector, _ = provider()

    assert "rp-test-key" not in repr(connector.health().to_dict())


def test_the_estimate_names_the_operation_it_priced() -> None:
    connector, _ = provider()

    render = connector.estimate(spec())

    assert render.kind == "image"
    assert render.estimated_seconds == 25.0
    assert "runpod flux" in render.notes
    assert f"({OPERATION_IMAGE})" in render.notes
    assert f"({OPERATION_INPAINT})" in connector.estimate(spec(mode=MODE_INPAINT)).notes


def test_a_job_can_be_cancelled_through_the_connector() -> None:
    connector, fake = provider()

    assert connector.cancel("job-42") is True
    assert fake.cancelled == ["job-42"]


def test_the_client_is_created_lazily_and_only_once(monkeypatch) -> None:
    """Listing providers must not build an HTTP stack."""

    created: list[int] = []

    class CountingClient:
        def __init__(self, *args, **kwargs):
            created.append(1)
            self.configured = False

    monkeypatch.setattr("app.providers.runpod_base.GpuClient", CountingClient)
    connector = RunPodFluxProvider()

    assert created == [], "constructing the provider touches nothing"
    assert connector.client is connector.client
    assert created == [1]


# ---------------------------------------------------------------------------
# Architecture guards
# ---------------------------------------------------------------------------


def test_the_connector_receives_only_the_spec() -> None:
    assert list(inspect.signature(RunPodFluxProvider.generate_image).parameters) == [
        "self",
        "spec",
        "output_dir",
    ]
    assert list(inspect.signature(RunPodFluxProvider.upscale).parameters) == [
        "self",
        "spec",
        "asset_path",
        "output_dir",
    ]


def test_the_connector_never_speaks_http() -> None:
    """Transport belongs to `gpu_client`. This file must stay business-only."""

    source = Path("backend/app/providers/runpod_flux_provider.py").read_text(encoding="utf-8")
    for banned in ("import httpx", "Authorization", "status_code", "requests.", "await "):
        assert banned not in source, f"{banned!r} belongs in gpu_client.py"


def test_the_connector_does_not_import_the_director_or_the_storyboard() -> None:
    source = Path("backend/app/providers/runpod_flux_provider.py").read_text(encoding="utf-8")
    for banned in ("director", "storyboard", "prompt_compiler"):
        assert f"import {banned}" not in source
