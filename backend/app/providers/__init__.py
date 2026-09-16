"""Pluggable model providers.

PR007 adds a universal provider interface beside the legacy ETAPA 10 adapters.
The legacy modules stay for compatibility; new orchestration goes through
`BaseProvider`, `ProviderRegistry` and `GenerationExecutor`.
"""
from .base_provider import (
    BaseProvider,
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
    ProviderJob,
    ProviderNotFound,
    ProviderUnavailable,
    ProviderUnsupported,
)
from .generation_executor import GenerationExecution, GenerationExecutor
from .provider_registry import ProviderRegistration, ProviderRegistry

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
    "ProviderUnavailable",
    "ProviderUnsupported",
]
