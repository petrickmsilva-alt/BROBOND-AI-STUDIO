"""Mock provider for tests and local orchestration.

Never remove this adapter: PR007 needs a provider that can exercise the whole
registry/executor path without GPU dependencies or external services.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ..core.contracts import GenerationKind, GenerationSpec
from .base_provider import (
    ProviderAsset,
    ProviderCapabilities,
    ProviderEstimate,
    ProviderHealth,
    STATUS_READY,
    BaseProvider,
)

MOCK_PROVIDER_ID = "mock"
MOCK_LABEL = "Mock"
MOCK_VERSION = "mock-provider-v1"
MOCK_MAX_RESOLUTION = "1024"
MOCK_PROMPT_BUDGET = 1200
MOCK_IMAGE_BYTES = b"fake brobond png\n"
MOCK_VIDEO_BYTES = b"fake brobond mp4\n"
MOCK_UPSCALE_BYTES = b"upscaled\n"
MOCK_ESTIMATED_SECONDS = 0.1
DEFAULT_IMAGE_SIZE = 1024


class MockProvider(BaseProvider):
    """GPU-free provider that returns deterministic fake assets."""

    provider_id = MOCK_PROVIDER_ID
    label = MOCK_LABEL
    version = MOCK_VERSION

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_resolution=MOCK_MAX_RESOLUTION,
            supports_video=True,
            supports_image=True,
            supports_lora=True,
            supports_upscale=True,
            supports_seed=True,
            supports_negative_prompt=True,
            prompt_budget=MOCK_PROMPT_BUDGET,
        )

    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        path = self._path(output_dir, spec, "png")
        path.write_bytes(MOCK_IMAGE_BYTES)
        return ProviderAsset(
            path=str(path),
            kind=GenerationKind.IMAGE.value,
            provider_id=self.provider_id,
            width=DEFAULT_IMAGE_SIZE,
            height=DEFAULT_IMAGE_SIZE,
            metadata={"fake": True},
        )

    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        path = self._path(output_dir, spec, "mp4")
        path.write_bytes(MOCK_VIDEO_BYTES)
        return ProviderAsset(
            path=str(path),
            kind=GenerationKind.VIDEO.value,
            provider_id=self.provider_id,
            duration_seconds=spec.duration,
            fps=spec.fps,
            metadata={"fake": True},
        )

    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset:
        source = Path(asset_path)
        path = self._path(output_dir, spec, "upscaled.png")
        if source.exists():
            shutil.copyfile(source, path)
        else:
            path.write_bytes(MOCK_UPSCALE_BYTES)
        return ProviderAsset(
            path=str(path),
            kind=GenerationKind.IMAGE.value,
            provider_id=self.provider_id,
            width=DEFAULT_IMAGE_SIZE,
            height=DEFAULT_IMAGE_SIZE,
            metadata={"fake": True, "upscaled": True},
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            id=self.provider_id,
            label=self.label,
            status=STATUS_READY,
            latency_ms=0.0,
            version=self.version,
            capabilities=self.capabilities(),
            reason=None,
            loaded=True,
        )

    def estimate(self, spec: GenerationSpec) -> ProviderEstimate:
        return ProviderEstimate(
            provider_id=self.provider_id,
            kind=spec.kind.value,
            estimated_seconds=MOCK_ESTIMATED_SECONDS,
            notes="deterministic fake asset",
        )

    @staticmethod
    def _path(output_dir: str | Path, spec: GenerationSpec, suffix: str) -> Path:
        path = Path(output_dir) / f"{spec.spec_id}.{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
