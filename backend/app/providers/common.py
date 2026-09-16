"""Shared implementation for the diffusers-backed adapters.

ETAPA 10. Until this etapa `image.py` and `video.py` each carried their own copy
of four helpers, measured to be byte-identical or differing only in a docstring:

    _generator          identical (151 chars, both files)
    _apply_lora         identical (151 chars, both files)
    health              identical modulo the provider name
    _supported_kwargs   identical modulo the docstring

Two copies of a seed generator is not a style problem: a fix applied to one
silently does not apply to the other. Everything below has exactly one
definition, and the adapters import it.

Nothing here imports torch or diffusers at module scope, so the whole layer
stays importable on a CPU-only machine.
"""
from __future__ import annotations

import inspect
from typing import Any

#: Adapter name used for every persona LoRA, so a provider can tell its own
#: weights apart from anything else loaded onto the pipeline.
PERSONA_ADAPTER_NAME = "brobond_persona"

#: Default persona LoRA weight. One adapter, full strength.
PERSONA_ADAPTER_WEIGHT = 1.0


def supported_kwargs(pipeline, candidates: dict[str, Any]) -> dict[str, Any]:
    """Keep only the kwargs the installed pipeline actually accepts.

    Diffusers changes accepted kwargs between versions, so the filter reads the
    installed signature instead of hardcoding a version's. A `**kwargs`
    passthrough accepts everything, in which case the candidates are returned
    untouched rather than silently dropped.
    """

    try:
        signature = inspect.signature(pipeline.__call__)
    except (TypeError, ValueError):  # pragma: no cover - exotic callables
        return candidates
    accepts_var_keyword = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )
    if accepts_var_keyword:
        return candidates
    accepted = set(signature.parameters)
    return {key: value for key, value in candidates.items() if key in accepted}


def generator_for(seed: int | None):
    """A seeded CUDA generator, or `None` for an unseeded run.

    Returning `None` rather than a generator is deliberate: a `None` seed must
    mean "let the model choose", not "seed zero".
    """

    if seed is None:
        return None
    import torch

    return torch.Generator(device="cuda").manual_seed(seed)


def apply_lora(pipeline, lora: str | None) -> bool:
    """Load a persona LoRA onto the pipeline.

    Returns whether anything was loaded, so a caller can report it instead of
    guessing from a `None` check.
    """

    if not lora:
        return False
    pipeline.load_lora_weights(lora, adapter_name=PERSONA_ADAPTER_NAME)
    pipeline.set_adapters([PERSONA_ADAPTER_NAME], adapter_weights=[PERSONA_ADAPTER_WEIGHT])
    return True


def health_report(model_id: str, *, reason: str | None, available: bool, loaded: bool) -> dict[str, Any]:
    """The one shape every provider's `health()` returns.

    `available` is a claim about *this machine right now*, never about whether
    the code is correct. A provider with no CUDA reports `available: False` and
    says why, rather than raising at health-check time.
    """

    return {
        "available": available,
        "reason": reason,
        "model_id": model_id,
        "loaded": loaded,
    }


def cuda_availability() -> tuple[bool, str | None]:
    """Whether CUDA inference could run here, and why not if it could not."""

    try:
        import torch
    except ImportError:
        return False, "torch is not installed"
    if not torch.cuda.is_available():
        return False, "CUDA GPU is required"
    return True, None


def require_cuda() -> None:
    """Raise unless CUDA inference could run here.

    Called from `_load`, never from `health`: a health check must not raise.
    """

    available, reason = cuda_availability()
    if not available:
        raise RuntimeError(reason)


#: Aspect ratios image providers can render. Hoisted here in PR009 so the real
#: connectors and the legacy ETAPA 10 adapter share one definition.
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "16:9": (16, 9),
    "1:1": (1, 1),
    "9:16": (9, 16),
    "4:3": (4, 3),
    "3:4": (3, 4),
}

#: Dimensions are rounded to a multiple of this, which the VAE requires.
DIMENSION_MULTIPLE = 8


def dimensions_for(aspect_ratio: str, resolution: int) -> tuple[int, int]:
    """Longest side fixed by `resolution`; the other follows the ratio."""

    width_ratio, height_ratio = ASPECT_RATIOS.get(aspect_ratio, (16, 9))
    if width_ratio >= height_ratio:
        width = resolution
        height = round(resolution * height_ratio / width_ratio / DIMENSION_MULTIPLE) * DIMENSION_MULTIPLE
    else:
        height = resolution
        width = round(resolution * width_ratio / height_ratio / DIMENSION_MULTIPLE) * DIMENSION_MULTIPLE
    return width, height


def load_reference_image(reference_path: str | None):
    """Open the spec's reference image for image-conditioned generation.

    Raises `ValueError` (a fatal, non-retryable error) when the path is
    missing: an image-to-image request without a source image is an invalid
    spec, not a transient failure.
    """

    if not reference_path:
        raise ValueError("image-conditioned generation requires spec.reference_path")
    from PIL import Image

    return Image.open(reference_path).convert("RGB")
