"""Universal provider registry for PR007.

The registry maps opaque ids/aliases to provider factories. It contains no
routing branches by model name: adding Kling, Runway or another backend is a
registration, not a conditional in an executor or in the Core.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from ..core.contracts import GenerationKind
from .base_provider import (
    BaseProvider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderNotFound,
    ProviderUnavailable,
    STATUS_ERROR,
)
from .flux_provider import FLUX_LABEL, FLUX_MODEL_ID, FLUX_PROVIDER_ID, FluxProvider
from .mock_provider import MOCK_LABEL, MOCK_PROVIDER_ID, MockProvider
from .wan_provider import (
    HUNYUAN_LABEL,
    HUNYUAN_MODEL_ID,
    HUNYUAN_PROVIDER_ID,
    WAN_LABEL,
    WAN_MODEL_ID,
    WAN_PROVIDER_ID,
    HunyuanProvider,
    WanProvider,
)

ProviderFactory = Callable[[str | None], BaseProvider]

NO_LATENCY_MS = 0.0
LATENCY_PRECISION_DIGITS = 2


@dataclass(frozen=True)
class ProviderRegistration:
    """One registry row."""

    provider_id: str
    label: str
    factory: ProviderFactory
    aliases: tuple[str, ...] = ()
    default_for: tuple[GenerationKind, ...] = ()


class ProviderRegistry:
    """Registry of universal providers."""

    def __init__(self) -> None:
        self._registrations: dict[str, ProviderRegistration] = {}
        self._aliases: dict[str, str] = {}
        self._defaults: dict[GenerationKind, str] = {}
        self._order: list[str] = []

    def register(self, registration: ProviderRegistration) -> None:
        """Add or replace a provider registration."""

        if registration.provider_id not in self._registrations:
            self._order.append(registration.provider_id)
        self._registrations[registration.provider_id] = registration
        for alias in registration.aliases:
            self._aliases[alias] = registration.provider_id
        for kind in registration.default_for:
            self._defaults[kind] = registration.provider_id

    def get(
        self,
        provider_id: str | None = None,
        *,
        kind: GenerationKind | None = None,
        model_id: str | None = None,
    ) -> BaseProvider:
        """Return the provider for an id, alias or kind default."""

        resolved_id = self._resolve_id(provider_id, kind)
        registration = self._registrations.get(resolved_id)
        if registration is None:
            raise ProviderNotFound(f"provider '{provider_id}' is not registered")
        provider = registration.factory(model_id)
        if kind is not None and not provider.capabilities().supports(kind):
            raise ProviderUnavailable(
                f"provider '{provider.provider_id}' cannot generate {kind.value} assets"
            )
        return provider

    def list(self) -> tuple[BaseProvider, ...]:
        """Registered providers in registration order."""

        return tuple(self._registrations[provider_id].factory(None) for provider_id in self._order)

    def health_all(self) -> tuple[ProviderHealth, ...]:
        """Health of every provider, with measured latency and no secrets."""

        reports: list[ProviderHealth] = []
        for provider in self.list():
            started = time.perf_counter()
            try:
                report = provider.health()
            except Exception as error:  # pragma: no cover - defensive boundary
                report = ProviderHealth(
                    id=provider.provider_id,
                    label=provider.label,
                    status=STATUS_ERROR,
                    latency_ms=NO_LATENCY_MS,
                    version=provider.version,
                    capabilities=provider.capabilities(),
                    reason=str(error),
                )
            latency = round((time.perf_counter() - started) * 1000, LATENCY_PRECISION_DIGITS)
            reports.append(report.with_latency(latency))
        return tuple(reports)

    def defaults(self) -> dict[str, str]:
        return {kind.value: provider_id for kind, provider_id in self._defaults.items()}

    def capabilities(self, provider_id: str | None, *, kind: GenerationKind | None = None) -> ProviderCapabilities:
        return self.get(provider_id, kind=kind).capabilities()

    def _resolve_id(self, provider_id: str | None, kind: GenerationKind | None) -> str:
        if provider_id:
            return self._aliases.get(provider_id, provider_id)
        if kind is not None and kind in self._defaults:
            return self._defaults[kind]
        raise ProviderNotFound("provider id is required when no kind default is registered")


def create_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        ProviderRegistration(
            provider_id=FLUX_PROVIDER_ID,
            label=FLUX_LABEL,
            factory=lambda model_id=None: FluxProvider(model_id=model_id or FLUX_MODEL_ID),
            aliases=(FLUX_LABEL, FLUX_MODEL_ID, "flux"),
            default_for=(GenerationKind.IMAGE,),
        )
    )
    registry.register(
        ProviderRegistration(
            provider_id=WAN_PROVIDER_ID,
            label=WAN_LABEL,
            factory=lambda model_id=None: WanProvider(model_id=model_id or WAN_MODEL_ID),
            aliases=(WAN_LABEL, WAN_MODEL_ID, "wan", "wan-video"),
            default_for=(GenerationKind.VIDEO,),
        )
    )
    registry.register(
        ProviderRegistration(
            provider_id=MOCK_PROVIDER_ID,
            label=MOCK_LABEL,
            factory=lambda model_id=None: MockProvider(),
            aliases=(MOCK_LABEL, "mock-image", "mock-video"),
        )
    )
    registry.register(
        ProviderRegistration(
            provider_id=HUNYUAN_PROVIDER_ID,
            label=HUNYUAN_LABEL,
            factory=lambda model_id=None: HunyuanProvider(model_id=model_id or HUNYUAN_MODEL_ID),
            aliases=(HUNYUAN_LABEL, HUNYUAN_MODEL_ID, "hunyuan"),
        )
    )
    return registry


DEFAULT_REGISTRY = create_default_registry()


def register(registration: ProviderRegistration) -> None:
    DEFAULT_REGISTRY.register(registration)


def get(provider_id: str | None = None, *, kind: GenerationKind | None = None, model_id: str | None = None) -> BaseProvider:
    return DEFAULT_REGISTRY.get(provider_id, kind=kind, model_id=model_id)


def list() -> tuple[BaseProvider, ...]:  # noqa: A001 - required public API name
    return DEFAULT_REGISTRY.list()


def health_all() -> tuple[ProviderHealth, ...]:
    return DEFAULT_REGISTRY.health_all()


def defaults() -> dict[str, str]:
    return DEFAULT_REGISTRY.defaults()
