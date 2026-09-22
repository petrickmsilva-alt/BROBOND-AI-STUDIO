"""Compatibility façade for host capability detection.

``app.system`` was a module before PR010.  It remains the owner of the old
``gpu_info`` shape used by readiness, while ``app.system.gpu_runtime`` exposes
the richer NVIDIA JSON used by the GPU endpoint and model runtimes.
"""
from __future__ import annotations

import shutil
import subprocess

from .gpu_runtime import detect_gpu


def gpu_info() -> dict:
    """Return the pre-existing readiness payload without losing compatibility."""

    result = detect_gpu()
    if result.get("available"):
        cards = [
            {
                "name": card.get("name"),
                "vram_total_mb": card.get("vram_total_mb"),
                "vram_free_mb": card.get("vram_free_mb"),
                "driver": card.get("driver"),
            }
            for card in result.get("gpus", [])
        ]
        return {"available": True, "backend": "cuda", "gpus": cards}
    if result.get("reason") == "nvidia-smi returned no GPUs" and result.get("gpus") == []:
        # A successful but empty probe used to be distinguishable from a
        # command failure by readiness clients; retain that useful distinction.
        return {"available": False, "backend": "cuda", "gpus": []}
    if result.get("reason") == "nvidia-smi not found":
        return {"available": False, "backend": "cpu", "message": "nvidia-smi not found"}
    return {"available": False, "backend": "cpu", "message": "GPU detection failed"}


__all__ = ["detect_gpu", "gpu_info", "shutil", "subprocess"]
