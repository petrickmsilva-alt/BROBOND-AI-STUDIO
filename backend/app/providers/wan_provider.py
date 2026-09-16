"""Wan adapter for the universal PR007 provider interface."""
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

WAN_PROVIDER_ID = "wan-2.1-t2v"
WAN_LABEL = "Wan"
WAN_MODEL_ID = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
WAN_VERSION = "diffusers-wan-adapter-v1"
WAN_MAX_RESOLUTION = "832x832"
WAN_PROMPT_BUDGET = 1200
WAN_ESTIMATED_SECONDS_PER_SECOND = 12.0

HUNYUAN_PROVIDER_ID = "hunyuan-video"
HUNYUAN_LABEL = "Hunyuan"
HUNYUAN_MODEL_ID = "hunyuanvideo-community/HunyuanVideo"
HUNYUAN_VERSION = "diffusers-hunyuan-adapter-v1"
HUNYUAN_MAX_RESOLUTION = "1280x1280"


def _legacy_video_class(attribute: str):
    """Resolve late so existing provider monkeypatch tests still hit the adapter."""

    return getattr(importlib.import_module("app.providers.video"), attribute)


class _DiffusersVideoUniversalProvider(BaseProvider):
    """Shared universal wrapper for diffusers-backed video adapters."""

    provider_id = ""
    label = ""
    version = ""
    model_id_default = ""
    legacy_attribute = ""
    max_resolution = WAN_MAX_RESOLUTION

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or self.model_id_default
        self._legacy = None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_resolution=self.max_resolution,
            supports_video=True,
            supports_image=False,
            supports_lora=True,
            supports_upscale=False,
            supports_seed=True,
            supports_negative_prompt=True,
            prompt_budget=WAN_PROMPT_BUDGET,
        )

    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        raise unsupported(self.provider_id, "image generation")

    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        output = self._adapter().generate(spec, str(output_dir))
        return ProviderAsset(
            path=output.path,
            kind=GenerationKind.VIDEO.value,
            provider_id=self.provider_id,
            duration_seconds=output.duration_seconds,
            fps=output.fps,
        )

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
            kind=GenerationKind.VIDEO.value,
            estimated_seconds=max(1.0, float(spec.duration) * WAN_ESTIMATED_SECONDS_PER_SECOND),
            notes="local video adapter estimate",
        )

    def _adapter(self):
        if self._legacy is None:
            self._legacy = _legacy_video_class(self.legacy_attribute)(model_id=self.model_id)
        return self._legacy


class WanProvider(_DiffusersVideoUniversalProvider):
    """Universal wrapper around the existing Wan video adapter."""

    provider_id = WAN_PROVIDER_ID
    label = WAN_LABEL
    version = WAN_VERSION
    model_id_default = WAN_MODEL_ID
    legacy_attribute = "WanVideoProvider"
    max_resolution = WAN_MAX_RESOLUTION


class HunyuanProvider(_DiffusersVideoUniversalProvider):
    """Universal wrapper for the existing Hunyuan adapter.

    PR007's frontend highlights Flux, Wan and Mock, but the registry can already
    carry future providers without the Core learning their names.
    """

    provider_id = HUNYUAN_PROVIDER_ID
    label = HUNYUAN_LABEL
    version = HUNYUAN_VERSION
    model_id_default = HUNYUAN_MODEL_ID
    legacy_attribute = "HunyuanVideoProvider"
    max_resolution = HUNYUAN_MAX_RESOLUTION
