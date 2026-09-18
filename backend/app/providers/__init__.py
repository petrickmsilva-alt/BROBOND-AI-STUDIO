"""Pluggable model providers.

PR007 adds a universal provider interface beside the legacy ETAPA 10 adapters.
The legacy modules stay for compatibility; new orchestration goes through
`BaseProvider`, `ProviderRegistry` and `GenerationExecutor`.

PR009 turns the universal layer into the real AI connector path: Flux and Wan
connectors that receive only a `GenerationSpec`, plus the resilience and
observability stack (retry engine, timeout manager, fallback chain and
telemetry store) wrapped by the executor.

PR011 adds the external GPU cluster: `gpu_client` (transport only) plus the
`runpod-flux` and `runpod-wan` connectors, registered beside the local ones,
and `gpu_health` for the readiness endpoint.
"""
from .base_provider import (
    BaseProvider,
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
    ProviderJob,
    ProviderNotFound,
    ProviderTimeoutError,
    ProviderUnavailable,
    ProviderUnsupported,
)
from .generation_executor import GenerationExecution, GenerationExecutor
from .gpu_client import (
    GpuClient,
    GpuClientError,
    GpuHttpError,
    GpuJob,
    GpuJobFailed,
    GpuJobResult,
    GpuNotConfigured,
    GpuResponse,
    GpuTimeout,
    GpuTransportError,
)
# Only `readiness_gpu_block` is re-exported: a name `gpu_health` on the package
# would shadow the `app.providers.gpu_health` submodule for anyone importing it.
from .gpu_health import readiness_gpu_block
from .runpod_base import RunPodProvider
from .runpod_flux_provider import RunPodFluxProvider
from .runpod_wan_provider import RunPodWanProvider
from .provider_registry import ProviderRegistration, ProviderRegistry
from .retry_policy import RetryDecision, RetryEngine, RetryOutcome, RetryPolicy, RetryState
from .telemetry import ProviderTelemetryRecord, TelemetryStore, default_telemetry_store
from .timeout_manager import TimeoutManager

__all__ = [
    "BaseProvider",
    "GenerationExecution",
    "GenerationExecutor",
    "GpuClient",
    "GpuClientError",
    "GpuHttpError",
    "GpuJob",
    "GpuJobFailed",
    "GpuJobResult",
    "GpuNotConfigured",
    "GpuResponse",
    "GpuTimeout",
    "GpuTransportError",
    "ProviderAsset",
    "ProviderCapabilities",
    "ProviderEstimate",
    "ProviderHealth",
    "ProviderJob",
    "ProviderNotFound",
    "ProviderRegistration",
    "ProviderRegistry",
    "ProviderTelemetryRecord",
    "ProviderTimeoutError",
    "ProviderUnavailable",
    "ProviderUnsupported",
    "RetryDecision",
    "RunPodFluxProvider",
    "RunPodProvider",
    "RunPodWanProvider",
    "RetryEngine",
    "RetryOutcome",
    "RetryPolicy",
    "RetryState",
    "TelemetryStore",
    "TimeoutManager",
    "default_telemetry_store",
    "readiness_gpu_block",
]
