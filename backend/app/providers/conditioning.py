"""Conditioning adapters: ControlNet and IP-Adapter.

ETAPA 10. `SYSTEM_PROMPT.md` names ControlNet and IP Adapter as *adapters*, but
until now they were a branch inside the FLUX provider:

    if spec.controlnet != "none":
        raise RuntimeError("ControlNet '...' requires a ControlNet-specific pipeline variant")
    if spec.reference_path:
        pipeline.load_ip_adapter("h94/IP-Adapter",
                                 weight_name="ip-adapter-plus_sdxl_vit-h.safetensors")

Two problems, both real:

1. **The IP-Adapter weights were SDXL weights on a FLUX pipeline.**
   `h94/IP-Adapter` + `ip-adapter-plus_sdxl_vit-h.safetensors` targets SDXL.
   The diffusers documentation for `FluxPipeline` specifies
   `XLabs-AI/flux-ip-adapter` with `weight_name="ip_adapter.safetensors"` and an
   explicit `image_encoder_pretrained_model_name_or_path`. On a GPU machine the
   old call would have failed at load time.
2. **ControlNet is not a flag on an image pipeline.** Flux ControlNet needs
   `FluxControlPipeline`, a different pipeline class. Raising inside the FLUX
   provider made that a runtime surprise instead of a routing decision.

So conditioning becomes an object with a declared requirement, and the registry
refuses the combination *before* anything is loaded.

Nothing here imports torch or diffusers at module scope.
"""
from __future__ import annotations

from dataclasses import dataclass


class ConditioningError(RuntimeError):
    """A conditioning mode this pipeline cannot honour."""


@dataclass(frozen=True)
class IpAdapterWeights:
    """Where an IP-Adapter's weights live, per base model.

    Weight files are not interchangeable between base models, which is exactly
    the mistake this dataclass exists to prevent.
    """

    repo: str
    weight_name: str
    image_encoder: str


#: IP-Adapter weights for a FLUX base model, per the diffusers FluxPipeline docs.
FLUX_IP_ADAPTER = IpAdapterWeights(
    repo="XLabs-AI/flux-ip-adapter",
    weight_name="ip_adapter.safetensors",
    image_encoder="openai/clip-vit-large-patch14",
)

#: IP-Adapter weights for an SDXL base model. Kept because it is a real,
#: supported combination — just not the one FLUX needs.
SDXL_IP_ADAPTER = IpAdapterWeights(
    repo="h94/IP-Adapter",
    weight_name="ip-adapter-plus_sdxl_vit-h.safetensors",
    image_encoder="h94/IP-Adapter",
)


@dataclass(frozen=True)
class Conditioning:
    """What a pipeline needs in order to honour a conditioning request.

    `pipeline_class` is the diffusers class the *base* pipeline must be an
    instance of. ControlNet is the case that needs it: FLUX ControlNet runs on
    `FluxControlPipeline`, not on `FluxPipeline`.
    """

    mode: str
    pipeline_class: str | None = None
    weights: IpAdapterWeights | None = None
    argument: str | None = None

    @property
    def enabled(self) -> bool:
        return self.mode not in ("", "none")


#: No conditioning. The common case, and the value `spec.controlnet` defaults to.
NONE = Conditioning(mode="none")

#: FLUX ControlNet. Needs the control pipeline variant, so the registry can
#: refuse the combination instead of the pipeline raising mid-load.
FLUX_CONTROLNET = Conditioning(
    mode="controlnet",
    pipeline_class="FluxControlPipeline",
    argument="control_image",
)

#: FLUX IP-Adapter, with the weights that actually match a FLUX base model.
FLUX_IP_ADAPTER_CONDITIONING = Conditioning(
    mode="ip-adapter",
    weights=FLUX_IP_ADAPTER,
    argument="ip_adapter_image",
)


def resolve_controlnet(controlnet: str | None) -> Conditioning:
    """Map `spec.controlnet` onto a conditioning requirement.

    Anything other than `"none"`/empty asks for ControlNet. The specific
    ControlNet variant is a model-selection concern owned by the registry, not
    something inferred here.
    """

    if not controlnet or controlnet == "none":
        return NONE
    return FLUX_CONTROLNET


def resolve_reference(reference_path: str | None) -> Conditioning:
    """Map `spec.reference_path` onto an IP-Adapter requirement."""

    if not reference_path:
        return NONE
    return FLUX_IP_ADAPTER_CONDITIONING


def apply_ip_adapter(pipeline, conditioning: Conditioning, *, scale: float) -> None:
    """Load IP-Adapter weights that match the pipeline's base model.

    Raises rather than loading the wrong weights: a mismatched IP-Adapter fails
    obscurely at inference time, and an obscure failure on a GPU worker is
    expensive to diagnose.
    """

    weights = conditioning.weights
    if weights is None:
        raise ConditioningError("IP-Adapter conditioning carries no weights")
    if not hasattr(pipeline, "load_ip_adapter"):
        raise ConditioningError("this pipeline does not support IP-Adapter")
    pipeline.load_ip_adapter(
        weights.repo,
        weight_name=weights.weight_name,
        image_encoder_pretrained_model_name_or_path=weights.image_encoder,
    )
    pipeline.set_ip_adapter_scale(float(scale))


def controlnet_arguments(conditioning: Conditioning, control_image) -> dict[str, object]:
    """The pipeline kwargs a ControlNet run needs, if any."""

    if not conditioning.enabled or conditioning.argument is None:
        return {}
    return {conditioning.argument: control_image}
