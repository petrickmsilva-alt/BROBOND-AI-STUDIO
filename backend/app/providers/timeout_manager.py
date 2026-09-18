"""PR009 — per-provider execution deadlines (ETAPA 4).

Every provider runs under a deadline it does not choose for itself:

    Flux  90s   (image inference)
    Wan   300s  (video inference)
    *     120s  (generic default)

The numbers come from ``core.config`` and are overridable per deployment:

    BROBOND_PROVIDER_TIMEOUT_FLUX_SECONDS=45
    BROBOND_PROVIDER_TIMEOUT_WAN_SECONDS=600
    BROBOND_PROVIDER_TIMEOUT_DEFAULT_SECONDS=180

Enforcement is honest about what a deadline can do to GPU work: the call runs
in a worker thread and ``run`` gives up waiting at the deadline, raising
``ProviderTimeoutError``. The abandoned thread cannot be preempted (CUDA has no
cancellation), so it may keep running in the background — what the caller is
guaranteed is that it never blocks past the deadline. A deadline of ``0``
disables the guard (used by tests and by providers that manage their own
deadlines).
"""
from __future__ import annotations

import concurrent.futures
from collections.abc import Callable, Mapping
from typing import TypeVar

from ..core.config import settings
from .base_provider import ProviderTimeoutError

T = TypeVar("T")

#: Deadline disabled.
NO_TIMEOUT_SECONDS = 0.0

#: Provider ids and aliases that inherit the Flux image deadline.
FLUX_TIMEOUT_IDS: frozenset[str] = frozenset(
    {
        "flux-dev",
        "flux",
        "flux-1.1-pro-ultra",
        "black-forest-labs/FLUX.1-dev",
        # PR011: the cluster connector renders the same class of workload; the
        # GPU client enforces its own job deadline on top of this one.
        "runpod-flux",
        "runpod-image",
        "flux-kontext-pro",
    }
)

#: Provider ids and aliases that inherit the Wan video deadline. Hunyuan
#: renders are the same class of workload (diffusion video), so they share it.
WAN_TIMEOUT_IDS: frozenset[str] = frozenset(
    {
        "wan-2.1-t2v",
        "wan",
        "wan-video",
        "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
        "hunyuan-video",
        "hunyuan",
        "hunyuanvideo-community/HunyuanVideo",
        # PR011: cluster video renders.
        "runpod-wan",
        "runpod-video",
        "wan-2.1-t2v-14b",
    }
)


class TimeoutManager:
    """Resolves and enforces per-provider deadlines.

    Constructed without arguments it reads the current ``Settings`` (and so the
    environment). An explicit ``overrides`` mapping wins over the settings
    table, which wins over the generic default.
    """

    def __init__(
        self,
        overrides: Mapping[str, float] | None = None,
        *,
        default_seconds: float | None = None,
        flux_seconds: float | None = None,
        wan_seconds: float | None = None,
    ) -> None:
        flux = flux_seconds if flux_seconds is not None else settings.provider_timeout_flux_seconds
        wan = wan_seconds if wan_seconds is not None else settings.provider_timeout_wan_seconds
        self.default_seconds = (
            default_seconds if default_seconds is not None else settings.provider_timeout_default_seconds
        )
        table: dict[str, float] = {}
        table.update({provider_id: flux for provider_id in FLUX_TIMEOUT_IDS})
        table.update({provider_id: wan for provider_id in WAN_TIMEOUT_IDS})
        table.update({key: float(value) for key, value in (overrides or {}).items()})
        self._table = table

    def seconds_for(self, provider_id: str | None) -> float:
        """Deadline for a provider id/alias; the generic default otherwise."""

        if provider_id and provider_id in self._table:
            return float(self._table[provider_id])
        return float(self.default_seconds)

    def run(self, provider_id: str | None, operation: Callable[[], T], *, seconds: float | None = None) -> T:
        """Run ``operation`` under the provider's deadline.

        Raises ``ProviderTimeoutError`` when the deadline expires; any other
        exception raised by the operation propagates untouched.
        """

        deadline = self.seconds_for(provider_id) if seconds is None else float(seconds)
        if deadline <= NO_TIMEOUT_SECONDS:
            return operation()

        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"provider-timeout-{provider_id or 'unknown'}"
        )
        future = pool.submit(operation)
        try:
            return future.result(timeout=deadline)
        except concurrent.futures.TimeoutError as error:
            # Do not join the worker: the whole point is to stop waiting.
            pool.shutdown(wait=False, cancel_futures=True)
            raise ProviderTimeoutError(
                f"provider '{provider_id or 'unknown'}' exceeded its {deadline:g}s deadline"
            ) from error
        finally:
            # On success the future already completed; this only releases the
            # single worker thread.
            pool.shutdown(wait=False)
