"""PR011 — RunPod Flux connector (ETAPA 2).

An image connector that executes on an external GPU cluster instead of a local
diffusers pipeline. The local `flux_provider.py` is untouched and still
registered: this is a second implementation of the same `BaseProvider`
interface, selected by id, not a replacement.

Operations
----------

| Operation         | `spec.mode`      | Needs a reference |
| ----------------- | ---------------- | ----------------- |
| image             | `text-to-image`  | no                |
| image-to-image    | `image-to-image` | yes               |
| upscale           | (method)         | the source asset  |
| inpaint           | `inpaint`        | yes (+ mask)      |
| outpaint          | `outpaint`       | yes               |
| control reference | `control`        | yes               |

Why the extra operations are not new `ProviderCapabilities` fields
------------------------------------------------------------------
`ProviderCapabilities` is the public, frozen shape returned by
`GET /api/v1/providers` and recorded in `docs/API_SNAPSHOT.json`; PR011 is
explicitly forbidden from changing the public Provider Registry. So the five
operations are declared on the connector as `SUPPORTED_OPERATIONS` and
`supports_operation()`, and the shared capability record keeps its 8 fields
(`supports_image=True`, `supports_upscale=True`). Nothing is hidden: the
operation set is asserted by the tests and documented in `docs/GPU_CLUSTER.md`.

Contract, unchanged from ETAPA 3: every rendering method receives **only** a
`GenerationSpec`. There is no method here that takes a prompt string or a
parameters dict, and `upscale` takes the spec plus the path of the asset to
enlarge, exactly as `BaseProvider` declares.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..core.contracts import GenerationKind, GenerationSpec
from .base_provider import (
    ProviderCapabilities,
    ProviderEstimate,
    ProviderAsset,
    unsupported,
)
from .common import dimensions_for
from .gpu_client import GpuClient
from .runpod_base import RunPodProvider

RUNPOD_FLUX_PROVIDER_ID = "runpod-flux"
RUNPOD_FLUX_LABEL = "RunPod Flux"
RUNPOD_FLUX_MODEL_ID = "flux-kontext-pro"
RUNPOD_FLUX_VERSION = "runpod-flux-connector-v1"
RUNPOD_FLUX_MAX_RESOLUTION = "4096"
RUNPOD_FLUX_PROMPT_BUDGET = 1000
RUNPOD_FLUX_VRAM = "24GB"
#: Wall-clock estimate for one cluster render, queue included.
RUNPOD_FLUX_ESTIMATED_SECONDS = 25.0
#: Default enlargement factor when the spec asks for no particular resolution.
DEFAULT_UPSCALE_FACTOR = 2

OPERATION_IMAGE = "image"
OPERATION_UPSCALE = "upscale"
OPERATION_INPAINT = "inpaint"
OPERATION_OUTPAINT = "outpaint"
OPERATION_CONTROL = "control"

MODE_TEXT_TO_IMAGE = "text-to-image"
MODE_IMAGE_TO_IMAGE = "image-to-image"
MODE_INPAINT = "inpaint"
MODE_OUTPAINT = "outpaint"
MODE_CONTROL = "control"

#: Spec modes this connector understands, mapped onto the operation they run.
MODE_OPERATIONS: dict[str, str] = {
    MODE_TEXT_TO_IMAGE: OPERATION_IMAGE,
    MODE_IMAGE_TO_IMAGE: OPERATION_IMAGE,
    MODE_INPAINT: OPERATION_INPAINT,
    MODE_OUTPAINT: OPERATION_OUTPAINT,
    MODE_CONTROL: OPERATION_CONTROL,
}

#: The five operations ETAPA 2 requires, declared where a caller can read them.
SUPPORTED_OPERATIONS: frozenset[str] = frozenset(
    {OPERATION_IMAGE, OPERATION_UPSCALE, OPERATION_INPAINT, OPERATION_OUTPAINT, OPERATION_CONTROL}
)

#: Modes whose job is meaningless without a source frame.
REFERENCE_REQUIRED_MODES: frozenset[str] = frozenset(
    {MODE_IMAGE_TO_IMAGE, MODE_INPAINT, MODE_OUTPAINT, MODE_CONTROL}
)

#: Spec fields the connector consumes, and those it cannot honour. Declared
#: rather than silently dropped — the ETAPA 10 rule.
FLUX_CONSUMED_SPEC_FIELDS: frozenset[str] = frozenset(
    {
        "prompt_compiled",
        "negative_prompt",
        "aspect_ratio",
        "resolution",
        "guidance_scale",
        "steps",
        "seed",
        "lora",
        "mode",
        "reference_path",
        "controlnet",
        "ip_adapter_scale",
    }
)
FLUX_UNSUPPORTED_SPEC_FIELDS: frozenset[str] = frozenset(
    {"duration", "fps", "motion_strength", "cinematic_mode", "slow_motion", "native_audio"}
)


@dataclass(frozen=True)
class RunPodFluxRequest:
    """Everything the cluster is asked for, built only from the spec.

    Serialisable so a test can assert the exact envelope without a network,
    and so telemetry can record what was requested.
    """

    operation: str
    mode: str
    prompt: str
    negative_prompt: str
    width: int
    height: int
    guidance_scale: float
    steps: int
    seed: int | None
    lora: str | None
    aspect_ratio: str
    reference_path: str | None
    control_type: str | None
    control_strength: float
    spec_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_flux_operation(spec: GenerationSpec) -> str:
    """Which operation a spec asks for.

    Unknown modes resolve to a plain image render rather than raising: the
    shared `GenerationSpec.mode` default is video-oriented (`text-to-video`),
    and an image spec that never set it still means "render the prompt".
    """

    return MODE_OPERATIONS.get(spec.mode, OPERATION_IMAGE)


def resolve_flux_mode(spec: GenerationSpec) -> str:
    return spec.mode if spec.mode in MODE_OPERATIONS else MODE_TEXT_TO_IMAGE


def flux_request_from_spec(spec: GenerationSpec) -> RunPodFluxRequest:
    """Pure spec -> request mapping; no I/O, unit-testable on any machine."""

    mode = resolve_flux_mode(spec)
    operation = MODE_OPERATIONS[mode]
    width, height = dimensions_for(spec.aspect_ratio, spec.resolution)
    control = spec.controlnet if spec.controlnet and spec.controlnet != "none" else None
    return RunPodFluxRequest(
        operation=operation,
        mode=mode,
        prompt=spec.prompt_compiled,
        negative_prompt=spec.negative_prompt,
        width=width,
        height=height,
        guidance_scale=spec.guidance_scale,
        steps=spec.steps,
        seed=spec.seed,
        lora=spec.lora,
        aspect_ratio=spec.aspect_ratio,
        reference_path=spec.reference_path if mode in REFERENCE_REQUIRED_MODES else None,
        control_type=control if operation == OPERATION_CONTROL else None,
        control_strength=spec.ip_adapter_scale,
        spec_id=spec.spec_id,
    )


class RunPodFluxProvider(RunPodProvider):
    """Flux on a RunPod serverless endpoint."""

    provider_id = RUNPOD_FLUX_PROVIDER_ID
    label = RUNPOD_FLUX_LABEL
    version = RUNPOD_FLUX_VERSION
    model_id_default = RUNPOD_FLUX_MODEL_ID
    vram = RUNPOD_FLUX_VRAM
    output_suffix = ".png"

    SUPPORTED_OPERATIONS = SUPPORTED_OPERATIONS
    CONSUMED_SPEC_FIELDS = FLUX_CONSUMED_SPEC_FIELDS
    UNSUPPORTED_SPEC_FIELDS = FLUX_UNSUPPORTED_SPEC_FIELDS

    def __init__(self, model_id: str | None = None, *, client: GpuClient | None = None) -> None:
        super().__init__(model_id, client=client)

    # ---------------------------------------------------------- capabilities

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_resolution=RUNPOD_FLUX_MAX_RESOLUTION,
            supports_video=False,
            supports_image=True,
            supports_lora=True,
            supports_upscale=True,
            supports_seed=True,
            supports_negative_prompt=True,
            prompt_budget=RUNPOD_FLUX_PROMPT_BUDGET,
        )

    @classmethod
    def supports_operation(cls, operation: str) -> bool:
        """Whether an ETAPA 2 operation is available on this connector."""

        return operation in cls.SUPPORTED_OPERATIONS

    # -------------------------------------------------------------- payloads

    def payload_for(self, request: RunPodFluxRequest, *, reference: str | None = None) -> dict[str, Any]:
        """The job envelope. The one place that knows the worker's field names."""

        payload: dict[str, Any] = {
            "operation": request.operation,
            "mode": request.mode,
            "model": self.model_id,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "guidance_scale": request.guidance_scale,
            "num_inference_steps": request.steps,
            "aspect_ratio": request.aspect_ratio,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.lora:
            payload["lora"] = request.lora
        if reference:
            payload["image"] = reference
        if request.operation == OPERATION_CONTROL:
            payload["control_type"] = request.control_type or "reference"
            payload["control_strength"] = request.control_strength
        if request.operation == OPERATION_OUTPAINT:
            payload["outpaint"] = True
        if request.operation == OPERATION_INPAINT:
            payload["inpaint"] = True
        return payload

    def upscale_payload(self, spec: GenerationSpec, reference: str) -> dict[str, Any]:
        return {
            "operation": OPERATION_UPSCALE,
            "model": self.model_id,
            "image": reference,
            "scale": DEFAULT_UPSCALE_FACTOR,
            "target_resolution": spec.resolution,
            "prompt": spec.prompt_compiled,
        }

    # ------------------------------------------------------------ operations

    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        """Render (or edit) one image on the cluster.

        Covers four of the five operations — `text-to-image`, `image-to-image`,
        `inpaint`, `outpaint`, `control` — because they are one job envelope
        with different fields, not four different lifecycles.
        """

        request = flux_request_from_spec(spec)
        reference: str | None = None
        if request.mode in REFERENCE_REQUIRED_MODES:
            if not request.reference_path:
                # Fatal by design: retrying cannot conjure a source image.
                raise ValueError(f"runpod flux {request.mode} requires spec.reference_path")
            reference = self.upload_reference(request.reference_path)

        result = self.execute_job(self.payload_for(request, reference=reference))
        path = self.materialise(result, output_dir, request.spec_id)
        return self.asset(
            path,
            GenerationKind.IMAGE.value,
            self.asset_metadata(
                spec,
                result,
                operation=request.operation,
                mode=request.mode,
                vram=self.vram,
            ),
            width=request.width,
            height=request.height,
        )

    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset:
        """Enlarge an existing asset under the same spec contract."""

        reference = self.upload_reference(str(asset_path))
        result = self.execute_job(self.upscale_payload(spec, reference))
        path = self.materialise(result, output_dir, f"{spec.spec_id}-upscaled")
        width, height = dimensions_for(spec.aspect_ratio, spec.resolution)
        return self.asset(
            path,
            GenerationKind.IMAGE.value,
            self.asset_metadata(
                spec,
                result,
                operation=OPERATION_UPSCALE,
                scale=DEFAULT_UPSCALE_FACTOR,
                source=str(asset_path),
                vram=self.vram,
            ),
            width=width * DEFAULT_UPSCALE_FACTOR,
            height=height * DEFAULT_UPSCALE_FACTOR,
        )

    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "video generation")

    def estimate(self, spec: GenerationSpec) -> ProviderEstimate:
        """Estimate for the operation this spec asks for.

        There is deliberately no upscale branch: `upscale` is a *method*, not
        a spec mode, so no spec can ever resolve to it. A branch that cannot
        be reached is a comment pretending to be code.
        """

        return ProviderEstimate(
            provider_id=self.provider_id,
            kind=GenerationKind.IMAGE.value,
            estimated_seconds=RUNPOD_FLUX_ESTIMATED_SECONDS,
            notes=f"runpod flux cluster estimate ({resolve_flux_operation(spec)})",
        )
