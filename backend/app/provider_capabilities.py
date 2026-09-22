"""Application-boundary helpers for universal provider discovery.

This module is intentionally outside ``app.core``: provider IDs and capability lookup are
runtime/application concerns. FastAPI routes call these helpers so ``main.py`` stays a thin
transport layer.
"""

from __future__ import annotations

from .providers.base_provider import STATUS_READY, ProviderHealth, ProviderNotFound
from .providers.provider_registry import DEFAULT_REGISTRY, ProviderRegistry
from .schemas import UniversalProviderResponse

_SECRET_MARKERS = ("secret", "token", "bearer", "password", "api_key", "apikey", "credential")
_REDACTED_REASON = "provider diagnostic redacted"


def list_universal_provider_responses(
    registry: ProviderRegistry = DEFAULT_REGISTRY,
) -> list[UniversalProviderResponse]:
    """Return public, secret-free provider discovery payloads."""

    return [UniversalProviderResponse(**_public_health_payload(report)) for report in registry.health_all()]


def prompt_budget_for_provider(
    provider_id: str | None,
    *,
    default_budget: int,
    registry: ProviderRegistry = DEFAULT_REGISTRY,
) -> int:
    """Resolve a provider prompt budget without leaking provider knowledge into Core/routes."""

    if not provider_id:
        return default_budget
    try:
        return registry.capabilities(provider_id).prompt_budget
    except ProviderNotFound:
        return default_budget


def _public_health_payload(report: ProviderHealth) -> dict[str, object]:
    payload = report.to_dict()
    payload["reason"] = _redact_reason(report.reason)

    # PR010: the sidebar must not call a CUDA-capable but unloaded model
    # "online".  The universal registry remains the public provider contract;
    # the local runtime singleton is the authority for the two concrete model
    # loaded flags.  Imports stay lazy so discovery is still safe on API-only
    # machines.
    if report.id == "flux-dev":
        from .runtime import get_flux_runtime

        runtime = get_flux_runtime().status()
        payload["loaded"] = runtime["loaded"]
        payload["available"] = bool(runtime["loaded"])
        payload["status"] = STATUS_READY if runtime["loaded"] else "unavailable"
        if not runtime["loaded"]:
            payload["reason"] = "model not loaded"
    elif report.id == "wan-2.1-t2v":
        from .runtime import get_wan_runtime

        runtime = get_wan_runtime().status()
        payload["loaded"] = runtime["loaded"]
        payload["available"] = bool(runtime["loaded"])
        payload["status"] = STATUS_READY if runtime["loaded"] else "unavailable"
        if not runtime["loaded"]:
            payload["reason"] = "model not loaded"
    else:
        # PR009: the frontend shows availability as a first-class fact,
        # derived here (one definition) rather than in every consumer.
        payload["available"] = report.status == STATUS_READY
    return payload


def _redact_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    normalized = reason.casefold()
    if any(marker in normalized for marker in _SECRET_MARKERS):
        return _REDACTED_REASON
    return reason
