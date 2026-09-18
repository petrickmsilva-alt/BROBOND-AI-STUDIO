"""PR011 — the GPU block of `GET /api/v1/system/readiness` (ETAPA 6).

One function, one shape:

    {
      "available": true,
      "provider": "runpod",
      "model": "flux-kontext-pro",
      "vram": "24GB",
      "latency_ms": 380
    }

and, when the cluster is not configured or not answering, the same five keys
with `available: false` plus a `reason` that says which of the two it was.

Three rules this module exists to keep:

1. **It never raises.** A readiness probe that 500s tells an orchestrator
   nothing except that the probe is broken. Every failure path returns a
   payload; the broad `except` at the end is the load-bearing part, not
   defensive noise.
2. **It never leaks a secret.** The payload carries a model name and a
   latency. The API key is not in it, and neither is the endpoint URL — only
   the host, which is what an operator needs to tell two deployments apart.
3. **It answers fast.** The probe runs under `HEALTH_TIMEOUT_SECONDS` (5s),
   not the render deadline (300s). A cold serverless endpoint must not hold
   the readiness response open for five minutes.

Deliberately *not* a route: `app.main` owns the HTTP surface, and the readiness
endpoint composes this block the same way it composes the database, migration
and storage gates.
"""
from __future__ import annotations

from typing import Any

from .gpu_client import HEALTH_TIMEOUT_SECONDS, GpuClient, run_sync
from .runpod_base import GPU_PROVIDER_NAME
from .runpod_flux_provider import RUNPOD_FLUX_MODEL_ID, RUNPOD_FLUX_VRAM

#: Reported when no cluster credentials are present. This is the DEV default
#: and it is not an error: the four PR011 variables are optional.
REASON_NOT_CONFIGURED = (
    "GPU cluster is not configured (set BROBOND_RUNPOD_API_KEY and BROBOND_RUNPOD_ENDPOINT)"
)


def unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """The `available: false` payload, with the same keys as a live one."""

    payload: dict[str, Any] = {
        "available": False,
        "provider": GPU_PROVIDER_NAME,
        "model": RUNPOD_FLUX_MODEL_ID,
        "vram": RUNPOD_FLUX_VRAM,
        "latency_ms": 0.0,
        "reason": reason,
    }
    payload.update(extra)
    return payload


def gpu_health(client: GpuClient | None = None, *, timeout: float = HEALTH_TIMEOUT_SECONDS) -> dict[str, Any]:
    """The `gpu` block of the readiness payload. Never raises."""

    try:
        probe_client = client if client is not None else GpuClient()
        if not probe_client.configured:
            return unavailable(REASON_NOT_CONFIGURED)
        probe = dict(run_sync(probe_client.health(timeout=timeout)))
    except Exception as error:  # noqa: BLE001 - readiness must answer, always
        return unavailable(f"GPU probe failed: {error}")

    if not probe.get("available"):
        return unavailable(
            str(probe.get("reason") or "GPU cluster unreachable"),
            latency_ms=float(probe.get("latency_ms") or 0.0),
            endpoint_host=probe_client.describe()["endpoint_host"],
        )

    payload: dict[str, Any] = {
        "available": True,
        "provider": GPU_PROVIDER_NAME,
        "model": RUNPOD_FLUX_MODEL_ID,
        "vram": RUNPOD_FLUX_VRAM,
        "latency_ms": float(probe.get("latency_ms") or 0.0),
        "reason": None,
        "endpoint_host": probe_client.describe()["endpoint_host"],
    }
    workers = probe.get("workers")
    if isinstance(workers, dict) and workers:
        payload["workers"] = workers
    return payload


#: What `app.system.gpu_info()` reports when the host itself has a CUDA card.
LOCAL_PROVIDER_NAME = "local"
#: 1 GiB in MiB, for turning `nvidia-smi`'s megabytes into the "24GB" label.
MB_PER_GB = 1024


def _local_summary(local: dict[str, Any]) -> tuple[str, str]:
    """(model, vram) of the first local GPU, as strings."""

    cards = local.get("gpus")
    if not isinstance(cards, list) or not cards:
        return "", ""
    card = cards[0] if isinstance(cards[0], dict) else {}
    total_mb = card.get("vram_total_mb")
    vram = f"{round(float(total_mb) / MB_PER_GB)}GB" if isinstance(total_mb, (int, float)) else ""
    return str(card.get("name") or ""), vram


def readiness_gpu_block(
    local: dict[str, Any] | None = None, client: GpuClient | None = None
) -> dict[str, Any]:
    """The `gpu` block of `/api/v1/system/readiness`.

    Two things can provide a GPU to this deployment — the host itself
    (`nvidia-smi`, detected by `app.system.gpu_info`) and the external cluster
    — and the endpoint has reported the first one since ETAPA 9. PR011 does
    not replace that with the cluster; it composes them, because a payload
    that said `available: false` while the host had a CUDA card would be
    false, and one that dropped `backend`/`message` would break the shell that
    reads them.

    Precedence is by capability, not by preference: whichever can actually
    render names the `provider`, with the cluster first because that is what a
    deploy on Render will have. The full cluster probe stays under `cluster`,
    so nothing is summarised away.
    """

    local_info = dict(local or {})
    cluster = gpu_health(client)
    local_available = bool(local_info.get("available"))
    cluster_available = bool(cluster.get("available"))

    block: dict[str, Any] = {**local_info, "cluster": cluster}
    block["available"] = cluster_available or local_available
    if cluster_available:
        block["provider"] = cluster["provider"]
        block["model"] = cluster["model"]
        block["vram"] = cluster["vram"]
        block["latency_ms"] = cluster["latency_ms"]
        block["reason"] = None
    elif local_available:
        model, vram = _local_summary(local_info)
        block["provider"] = LOCAL_PROVIDER_NAME
        block["model"] = model
        block["vram"] = vram
        block["latency_ms"] = 0.0
        # The host can render; the cluster still cannot, and why stays visible.
        block["reason"] = cluster.get("reason")
    else:
        block["provider"] = cluster["provider"]
        block["model"] = cluster["model"]
        block["vram"] = cluster["vram"]
        block["latency_ms"] = cluster["latency_ms"]
        block["reason"] = cluster.get("reason")
    return block
