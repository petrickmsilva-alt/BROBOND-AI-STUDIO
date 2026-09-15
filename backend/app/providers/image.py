"""FLUX/Diffusers image provider.

ETAPA 3: this provider receives **only** a `GenerationSpec`. It never sees a
loose prompt string and never sees a `parameters` dict — every decision arrives
already resolved by the Core, so there is exactly one place where a look is
decided and exactly one object to log.

ETAPA 10: the helpers this file used to carry its own copy of now live in
`providers/common.py`, and conditioning is an object from
`providers/conditioning.py` rather than a branch below. Two changes with real
consequences:

* the IP-Adapter weights are now the FLUX ones. They were SDXL weights
  (`h94/IP-Adapter` + `ip-adapter-plus_sdxl_vit-h.safetensors`) on a FLUX
  pipeline, which would have failed at load time on a GPU machine.
* `CONSUMED_SPEC_FIELDS` now declares `negative_prompt`. `pipeline_arguments`
  has always emitted it — the declaration was simply wrong, and the only test
  covering it checked that declared fields exist on the spec, not that they
  match what the code consumes.

Diffusers is optional so the orchestration API can run on CPU-only machines.
Install the GPU profile before enabling real inference:
`pip install torch diffusers transformers accelerate safetensors`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.contracts import GenerationSpec
from . import conditioning as conditioning_adapters
from .common import (
    apply_lora,
    cuda_availability,
    generator_for,
    health_report,
    require_cuda,
    supported_kwargs,
)


@dataclass
class GenerationOutput:
    path: str
    width: int
    height: int


class ImageProvider(ABC):
    """Contract every image provider implements.

    The signature is the enforcement point of ETAPA 3: a provider cannot be
    handed a prompt string, because it does not accept one.
    """

    @abstractmethod
    def generate(self, spec: GenerationSpec, output_dir: str) -> GenerationOutput:
        """Render `spec` and persist the result under `output_dir`."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Report whether this provider could run right now."""


class FluxDiffusersProvider(ImageProvider):
    #: Spec fields this provider actually consumes. Declared so the mapping is
    #: reviewable and testable instead of implicit in a call site — and checked
    #: against the code by `test_the_declared_fields_match_the_code`, not merely
    #: against the spec's field list.
    #:
    #: `negative_prompt` is consumed (and then filtered out by
    #: `_supported_kwargs`, because FLUX is guidance-distilled and has no
    #: negative prompt). It was missing from this set until ETAPA 10.
    CONSUMED_SPEC_FIELDS: frozenset[str] = frozenset(
        {
            "prompt_compiled",
            "negative_prompt",
            "aspect_ratio",
            "resolution",
            "guidance_scale",
            "steps",
            "seed",
            "lora",
            "controlnet",
            "reference_path",
            "ip_adapter_scale",
        }
    )

    #: Conditioning modes this adapter can honour. ControlNet is deliberately
    #: absent: FLUX ControlNet needs `FluxControlPipeline`, a different pipeline
    #: class, so it is a routing decision rather than a flag on this one.
    SUPPORTED_CONDITIONING: frozenset[str] = frozenset({"ip-adapter"})

    def __init__(self, model_id: str = "black-forest-labs/FLUX.1-dev") -> None:
        self.model_id = model_id
        self._pipeline = None

    # ------------------------------------------------------------------ runtime

    def _load(self):
        if self._pipeline is None:
            try:
                import torch
                from diffusers import FluxPipeline
            except ImportError as error:
                raise RuntimeError("Diffusers GPU dependencies are not installed") from error
            require_cuda()
            self._pipeline = FluxPipeline.from_pretrained(self.model_id, torch_dtype=torch.bfloat16)
            self._pipeline.enable_model_cpu_offload()
        return self._pipeline

    def _apply_lora(self, pipeline, lora: str | None) -> None:
        apply_lora(pipeline, lora)

    def _apply_conditioning(self, pipeline, spec: GenerationSpec) -> None:
        """Honour ControlNet / IP-Adapter, or refuse with a reason.

        ControlNet is refused here because this adapter loads `FluxPipeline`
        and FLUX ControlNet requires `FluxControlPipeline`. The refusal is now a
        declared, testable requirement rather than a bare string.
        """

        controlnet = conditioning_adapters.resolve_controlnet(spec.controlnet)
        if controlnet.enabled and controlnet.mode not in self.SUPPORTED_CONDITIONING:
            raise RuntimeError(
                f"ControlNet '{spec.controlnet}' requires {controlnet.pipeline_class}, "
                f"which this adapter does not load"
            )

        reference = conditioning_adapters.resolve_reference(spec.reference_path)
        if reference.enabled:
            conditioning_adapters.apply_ip_adapter(pipeline, reference, scale=spec.ip_adapter_scale)

    # ---------------------------------------------------------------- generate

    def generate(self, spec: GenerationSpec, output_dir: str) -> GenerationOutput:
        pipeline = self._load()
        self._apply_lora(pipeline, spec.lora)
        self._apply_conditioning(pipeline, spec)

        width, height = _dimensions(spec.aspect_ratio, spec.resolution)
        arguments = pipeline_arguments(spec, width, height)
        # Diffusers changes accepted kwargs between versions, and FLUX is
        # guidance-distilled (it has no negative_prompt). Filter against the
        # installed pipeline instead of hardcoding a version's signature.
        accepted = _supported_kwargs(pipeline, arguments)

        image = pipeline(**accepted).images[0]
        # Named by spec_id: two concurrent jobs must not overwrite one file.
        path = Path(output_dir) / f"{spec.spec_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return GenerationOutput(str(path), width, height)

    def health(self) -> dict[str, Any]:
        available, reason = cuda_availability()
        return health_report(
            self.model_id,
            reason=reason,
            available=available,
            loaded=self._pipeline is not None,
        )


def pipeline_arguments(spec: GenerationSpec, width: int, height: int) -> dict[str, Any]:
    """Map a GenerationSpec onto candidate pipeline kwargs.

    Pure and torch-free so the mapping is unit-testable on any machine. The
    candidate dict is filtered by `_supported_kwargs` before the call.
    """

    return {
        "prompt": spec.prompt_compiled,
        "negative_prompt": spec.negative_prompt,
        "width": width,
        "height": height,
        "guidance_scale": spec.guidance_scale,
        "num_inference_steps": spec.steps,
        "generator": _generator(spec.seed),
    }


#: Shared since ETAPA 10. Kept as module-level names because they are part of
#: this module's tested surface.
_supported_kwargs = supported_kwargs
_generator = generator_for

#: Aspect ratios this provider can render, hoisted out of the function body so
#: the mapping is built once rather than on every call.
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "16:9": (16, 9),
    "1:1": (1, 1),
    "9:16": (9, 16),
    "4:3": (4, 3),
    "3:4": (3, 4),
}

#: Dimensions are rounded to a multiple of this, which the VAE requires.
DIMENSION_MULTIPLE = 8


def _dimensions(aspect_ratio: str, resolution: int) -> tuple[int, int]:
    width_ratio, height_ratio = ASPECT_RATIOS.get(aspect_ratio, (16, 9))
    if width_ratio >= height_ratio:
        width = resolution
        height = round(resolution * height_ratio / width_ratio / DIMENSION_MULTIPLE) * DIMENSION_MULTIPLE
    else:
        height = resolution
        width = round(resolution * width_ratio / height_ratio / DIMENSION_MULTIPLE) * DIMENSION_MULTIPLE
    return width, height
