"""Lazy, CUDA-only model runtimes used by the online generation routes.

The package is safe to import on an API process without CUDA: torch, diffusers
and the video encoder are imported only when a render actually loads a model.
"""

from .flux_runtime import FLUX_MODEL_ID, FluxRuntime, flux_runtime, get_flux_runtime
from .wan_runtime import WAN_MODEL_ID, WanRuntime, get_wan_runtime, wan_runtime

__all__ = [
    "FLUX_MODEL_ID",
    "FluxRuntime",
    "flux_runtime",
    "get_flux_runtime",
    "WAN_MODEL_ID",
    "WanRuntime",
    "wan_runtime",
    "get_wan_runtime",
]
