"""Flux adapter for the universal PR007 provider interface."""
from __future__ import annotations

import importlib
from pathlib import Path

from ..core.contracts import GenerationKind, GenerationSpec
from .base_provider import (
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
    STATUS_READY,
    STATUS_UNAVAILABLE,
    BaseProvider,
    unsupported,
)

FLUX_PROVIDER_ID = "flux-dev"
FLUX_LABEL = "Flux"
FLUX_MODEL_ID = "black-forest-labs/FLUX.1-dev"
FLUX_VERSION = "diffusers-flux-adapter-v1"
FLUX_MAX_RESOLUTION = "4096"
FLUX_PROMPT_BUDGET = 1000
FLUX_ESTIMATED_SECONDS = 45.0


def _legacy_adapter_class():
    """Resolve late so tests can monkeypatch `app.providers.image.FluxDiffusersProvider`."""

    return getattr(importlib.import_module("app.providers.image"), "FluxDiffusersProvider")


class FluxProvider(BaseProvider):
    """Universal wrapper around the existing local Flux image adapter."""

    provider_id = FLUX_PROVIDER_ID
    label = FLUX_LABEL
    version = FLUX_VERSION

    def __init__(self, model_id: str = FLUX_MODEL_ID) -> None:
        self.model_id = model_id
        self._legacy = None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_resolution=FLUX_MAX_RESOLUTION,
            supports_video=False,
            supports_image=True,
            supports_lora=True,
            supports_upscale=False,
            supports_seed=True,
            supports_negative_prompt=True,
            prompt_budget=FLUX_PROMPT_BUDGET,
        )

    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        output = self._adapter().generate(spec, str(output_dir))
        return ProviderAsset(
            path=output.path,
            kind=GenerationKind.IMAGE.value,
            provider_id=self.provider_id,
            width=output.width,
            height=output.height,
        )

    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "video generation")

    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "upscale")

    def health(self) -> ProviderHealth:
        try:
            report = self._adapter().health()
        except Exception as error:  # pragma: no cover - defensive adapter boundary
            return ProviderHealth(
                id=self.provider_id,
                label=self.label,
                status=STATUS_UNAVAILABLE,
                latency_ms=0.0,
                version=self.version,
                capabilities=self.capabilities(),
                reason=str(error),
            )
        available = bool(report.get("available"))
        return ProviderHealth(
            id=self.provider_id,
            label=self.label,
            status=STATUS_READY if available else STATUS_UNAVAILABLE,
            latency_ms=0.0,
            version=self.version,
            capabilities=self.capabilities(),
            reason=report.get("reason"),
            loaded=bool(report.get("loaded", False)),
        )

    def estimate(self, spec: GenerationSpec) -> ProviderEstimate:
        return ProviderEstimate(
            provider_id=self.provider_id,
            kind=GenerationKind.IMAGE.value,
            estimated_seconds=FLUX_ESTIMATED_SECONDS,
            notes="local image adapter estimate",
        )

    def _adapter(self):
        if self._legacy is None:
            self._legacy = _legacy_adapter_class()(model_id=self.model_id)
        return self._legacy
