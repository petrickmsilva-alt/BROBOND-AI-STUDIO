"""Pluggable model providers.

PR007 adds a universal provider interface beside the legacy ETAPA 10 adapters.
The legacy modules stay for compatibility; new orchestration goes through
`BaseProvider`, `ProviderRegistry` and `GenerationExecutor`.

PR009 turns the universal layer into the real AI connector path: Flux and Wan
connectors that receive only a `GenerationSpec`, plus the resilience and
observability stack (retry engine, timeout manager, fallback chain and
telemetry store) wrapped by the executor.
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
from .provider_registry import ProviderRegistration, ProviderRegistry
from .retry_policy import RetryDecision, RetryEngine, RetryOutcome, RetryPolicy, RetryState
from .telemetry import ProviderTelemetryRecord, TelemetryStore, default_telemetry_store
from .timeout_manager import TimeoutManager

__all__ = [
    "BaseProvider",
    "GenerationExecution",
    "GenerationExecutor",
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
    "RetryEngine",
    "RetryOutcome",
    "RetryPolicy",
    "RetryState",
    "TelemetryStore",
    "TimeoutManager",
    "default_telemetry_store",
]
