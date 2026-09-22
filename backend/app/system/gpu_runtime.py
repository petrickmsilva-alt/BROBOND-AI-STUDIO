"""NVIDIA host capability detection.

The detector is deliberately small and side-effect free: it never imports
``torch`` and it never attempts to initialise CUDA.  ``nvidia-smi`` is the
operator-facing source of truth for the card, memory, driver and CUDA
compatibility reported by the host.  Model runtimes use this module for
status, while their own lazy loaders still require ``torch.cuda`` before
allocating anything.
"""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
from typing import Any


_QUERY = (
    "nvidia-smi",
    "--query-gpu=name,memory.total,memory.free,driver_version",
    "--format=csv,noheader,nounits",
)
_CUDA_VERSION = re.compile(r"CUDA Version\s*:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _unavailable(reason: str) -> dict[str, Any]:
    """Return the stable failure contract without inventing hardware facts."""

    return {"available": False, "reason": reason}


def _cuda_version() -> str | None:
    """Read the CUDA compatibility version from the normal nvidia-smi banner."""

    try:
        banner = subprocess.check_output(
            ("nvidia-smi",), text=True, stderr=subprocess.STDOUT, timeout=3
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = _CUDA_VERSION.search(banner)
    return match.group(1) if match else None


def _memory_gb(megabytes: str) -> float:
    """Convert nvidia-smi's MiB value to a useful, stable GiB number."""

    value = float(megabytes.strip())
    # The API is a capacity/status surface, so report whole GiB (the same
    # convention as the product card) rather than exposing MiB rounding noise.
    return int(round(value / 1024))


def _parse_rows(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in csv.reader(line for line in output.splitlines() if line.strip()):
        if len(row) < 4:
            continue
        name, total, free, driver = (item.strip() for item in row[:4])
        try:
            total_gb = _memory_gb(total)
            free_gb = _memory_gb(free)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "name": name,
                "vram_gb": total_gb,
                "vram_free_gb": free_gb,
                "driver": driver,
                # Kept for readiness' existing local summary contract.
                "vram_total_mb": int(float(total)),
                "vram_free_mb": int(float(free)),
            }
        )
    return rows


def detect_gpu() -> dict[str, Any]:
    """Detect the first NVIDIA adapter and return JSON-serialisable facts.

    No GPU is an ordinary deployment state.  In particular, this function
    never raises when ``nvidia-smi`` is absent, exits non-zero, or returns a
    partial response; callers can safely expose its result from a health
    endpoint.
    """

    if shutil.which("nvidia-smi") is None:
        return _unavailable("nvidia-smi not found")

    try:
        output = subprocess.check_output(_QUERY, text=True, stderr=subprocess.STDOUT, timeout=3)
    except FileNotFoundError:
        return _unavailable("nvidia-smi not found")
    except (OSError, subprocess.SubprocessError):
        return _unavailable("nvidia-smi failed")

    if not output.strip():
        return {"available": False, "reason": "nvidia-smi returned no GPUs", "gpus": []}
    cards = _parse_rows(output)
    if not cards:
        return {"available": False, "reason": "GPU detection failed", "gpus": []}

    primary = cards[0]
    result: dict[str, Any] = {
        "available": True,
        "provider": "NVIDIA",
        "name": primary["name"],
        "vram_gb": primary["vram_gb"],
        "vram_free_gb": primary["vram_free_gb"],
        "cuda": _cuda_version(),
        "driver": primary["driver"],
    }
    # Multiple cards are useful to operators and preserve the old readiness
    # endpoint's ability to summarise the local host.  The top-level fields
    # above remain the documented single-GPU response.
    result["gpus"] = cards
    return result


# Friendly aliases make the module useful to workers and tests without making
# callers depend on one private function name.
gpu_info = detect_gpu
get_gpu_info = detect_gpu
get_gpu_status = detect_gpu
detect_nvidia_gpu = detect_gpu

__all__ = [
    "detect_gpu",
    "detect_nvidia_gpu",
    "get_gpu_info",
    "get_gpu_status",
    "gpu_info",
]
