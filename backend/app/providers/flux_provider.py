"""PR009 — Flux real connector (ETAPA 1).

The universal registry kept its shape; what changed is that this module is now
the connector itself instead of a wrapper around the legacy ETAPA 10 adapter.

Contract, unchanged from ETAPA 3 and enforced by signature:

* the connector receives **only** a `GenerationSpec` — there is no method,
  public or private, that accepts a prompt string or a parameters dict;
* the only text that reaches the pipeline is the compiled prompt; the raw
  user brief carried by the spec is never read here.

Supported operations and controls:

* `text-to-image` — `FluxPipeline`
* `image-to-image` — `FluxImg2ImgPipeline`, driven by `spec.reference_path`
* `seed` — seeded CUDA generator (`None` means "let the model choose")
* `negative_prompt` — passed through and filtered against the installed
  pipeline signature (FLUX is guidance-distilled, so diffusers drops it)
* `lora` — persona LoRA loaded through the shared `apply_lora` helper
* `aspect_ratio` — resolved to pixel dimensions by the shared rule

The diffusers import stays lazy, so the module is importable on a CPU-only
machine; `health()` reports why it cannot run instead of raising.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..core.contracts import GenerationKind, GenerationSpec
from .base_provider import (
    BaseProvider,
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
    STATUS_READY,
    STATUS_UNAVAILABLE,
    health_timestamp,
    unsupported,
)
from .common import (
    apply_lora,
    cuda_availability,
    dimensions_for,
    generator_for,
    load_reference_image,
    require_cuda,
    supported_kwargs,
)

FLUX_PROVIDER_ID = "flux-dev"
FLUX_LABEL = "Flux"
FLUX_MODEL_ID = "black-forest-labs/FLUX.1-dev"
FLUX_VERSION = "flux-real-connector-v1"
FLUX_MAX_RESOLUTION = "4096"
FLUX_PROMPT_BUDGET = 1000
FLUX_ESTIMATED_SECONDS = 45.0
#: Documented default deadline; `core.config` (ENV-overridable) is the source
#: of truth the TimeoutManager reads.
FLUX_TIMEOUT_SECONDS = 90.0

MODE_TEXT_TO_IMAGE = "text-to-image"
MODE_IMAGE_TO_IMAGE = "image-to-image"
FLUX_MODES: tuple[str, ...] = (MODE_TEXT_TO_IMAGE, MODE_IMAGE_TO_IMAGE)

#: diffusers pipeline class per mode.
PIPELINE_CLASS_BY_MODE: dict[str, str] = {
    MODE_TEXT_TO_IMAGE: "FluxPipeline",
    MODE_IMAGE_TO_IMAGE: "FluxImg2ImgPipeline",
}

#: Spec fields this connector consumes. Declared, not implicit — and anything
#: it cannot honour is listed in `UNSUPPORTED_SPEC_FIELDS` below.
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
    }
)

#: Declared instead of silently dropped. ControlNet needs `FluxControlPipeline`
#: (a routing decision, not a flag); IP-Adapter wiring lives in the legacy
#: ETAPA 10 adapter; video-only fields do not apply to an image connector.
FLUX_UNSUPPORTED_SPEC_FIELDS: frozenset[str] = frozenset(
    {"controlnet", "ip_adapter_scale", "duration", "fps", "motion_strength", "cinematic_mode"}
)


@dataclass(frozen=True)
class FluxRequest:
    """Everything Flux receives for one render — built only from the spec.

    `prompt` is always `spec.prompt_compiled`; the connector has no path to a
    raw prompt. Serialisable so tests and telemetry can inspect exactly what
    would be handed to the pipeline.
    """

    mode: str
    prompt: str
    negative_prompt: str
    seed: int | None
    lora: str | None
    aspect_ratio: str
    width: int
    height: int
    guidance_scale: float
    steps: int
    reference_path: str | None
    spec_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_flux_mode(spec: GenerationSpec) -> str:
    """The image mode for a spec.

    Only an explicit `image-to-image` selects the img2img pipeline; every
    other value (including the shared spec default, which is video-oriented)
    means "render the prompt", i.e. text-to-image.
    """

    if spec.mode == MODE_IMAGE_TO_IMAGE:
        return MODE_IMAGE_TO_IMAGE
    return MODE_TEXT_TO_IMAGE


def flux_request_from_spec(spec: GenerationSpec) -> FluxRequest:
    """Pure spec -> request mapping; unit-testable without torch."""

    mode = resolve_flux_mode(spec)
    width, height = dimensions_for(spec.aspect_ratio, spec.resolution)
    return FluxRequest(
        mode=mode,
        prompt=spec.prompt_compiled,
        negative_prompt=spec.negative_prompt,
        seed=spec.seed,
        lora=spec.lora,
        aspect_ratio=spec.aspect_ratio,
        width=width,
        height=height,
        guidance_scale=spec.guidance_scale,
        steps=spec.steps,
        reference_path=spec.reference_path if mode == MODE_IMAGE_TO_IMAGE else None,
        spec_id=spec.spec_id,
    )


def flux_pipeline_arguments(request: FluxRequest) -> dict[str, Any]:
    """Map a FluxRequest onto candidate pipeline kwargs (pure, torch-free).

    The installed pipeline's signature filters the result, so kwargs a given
    diffusers version or pipeline class does not accept are dropped there,
    never hardcoded away here.
    """

    arguments: dict[str, Any] = {
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "width": request.width,
        "height": request.height,
        "guidance_scale": request.guidance_scale,
        "num_inference_steps": request.steps,
        "generator": generator_for(request.seed),
    }
    if request.mode == MODE_IMAGE_TO_IMAGE:
        arguments["image"] = load_reference_image(request.reference_path)
    return arguments


class FluxPipelineLoader:
    """Lazy diffusers loader; importable on machines without torch."""

    def __call__(self, model_id: str, mode: str):
        try:
            import torch
            from diffusers import __dict__ as diffusers_namespace
        except ImportError as error:
            raise RuntimeError("Diffusers GPU dependencies are not installed") from error
        class_name = PIPELINE_CLASS_BY_MODE[mode]
        pipeline_class = diffusers_namespace.get(class_name)
        if pipeline_class is None:
            raise RuntimeError(f"the installed diffusers has no {class_name}; upgrade diffusers")
        require_cuda()
        pipeline = pipeline_class.from_pretrained(model_id, torch_dtype=torch.bfloat16)
        pipeline.enable_model_cpu_offload()
        return pipeline


class FluxProvider(BaseProvider):
    """Real Flux image connector behind the universal `BaseProvider` interface."""

    provider_id = FLUX_PROVIDER_ID
    label = FLUX_LABEL
    version = FLUX_VERSION

    def __init__(
        self,
        model_id: str = FLUX_MODEL_ID,
        *,
        pipeline_loader: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.model_id = model_id
        self._pipeline = None
        self._pipeline_mode: str | None = None
        self._pipeline_loader = pipeline_loader or FluxPipelineLoader()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_resolution=FLUX_MAX_RESOLUTION,
            supports_video=False,
            supports_image=True,
            supports_lora=True,
            supports_upscale=False,
            supports_seed=True,
            supports_negative_prompt=True,
            prompt_budget=FLUX_PROMPT_BUDGET,
        )

    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        request = flux_request_from_spec(spec)
        if request.mode == MODE_IMAGE_TO_IMAGE and not request.reference_path:
            # A fatal error by design: retrying cannot conjure a source image.
            raise ValueError("flux image-to-image requires spec.reference_path")

        pipeline = self._pipeline_for(request.mode)
        apply_lora(pipeline, request.lora)
        accepted = supported_kwargs(pipeline, flux_pipeline_arguments(request))
        result = pipeline(**accepted)
        image = result.images[0]

        path = Path(output_dir) / f"{request.spec_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        width, height = getattr(image, "size", (request.width, request.height))
        return ProviderAsset(
            path=str(path),
            kind=GenerationKind.IMAGE.value,
            provider_id=self.provider_id,
            width=int(width),
            height=int(height),
            metadata={"mode": request.mode, "model_id": self.model_id, "seed": request.seed},
        )

    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "video generation")

    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "upscale")

    def health(self) -> ProviderHealth:
        available, reason = cuda_availability()
        return ProviderHealth(
            id=self.provider_id,
            label=self.label,
            status=STATUS_READY if available else STATUS_UNAVAILABLE,
            latency_ms=0.0,
            version=self.version,
            capabilities=self.capabilities(),
            reason=reason,
            loaded=self._pipeline is not None,
            last_health_at=health_timestamp(),
        )

    def estimate(self, spec: GenerationSpec) -> ProviderEstimate:
        return ProviderEstimate(
            provider_id=self.provider_id,
            kind=GenerationKind.IMAGE.value,
            estimated_seconds=FLUX_ESTIMATED_SECONDS,
            notes="flux real connector estimate",
        )

    def _pipeline_for(self, mode: str):
        """One loaded pipeline per mode; switching modes reloads."""

        if self._pipeline is None or self._pipeline_mode != mode:
            self._pipeline = self._pipeline_loader(self.model_id, mode)
            self._pipeline_mode = mode
        return self._pipeline
