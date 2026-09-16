"""Provider-agnostic generation executor for PR007."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.contracts import GenerationKind, GenerationSpec
from .base_provider import ProviderAsset, ProviderJob
from .provider_registry import DEFAULT_REGISTRY, ProviderRegistry

JOB_STATUS_COMPLETE = "complete"


@dataclass(frozen=True)
class GenerationExecution:
    """Result of the universal execution flow."""

    spec: GenerationSpec
    asset: ProviderAsset
    job: ProviderJob

    def to_dict(self) -> dict[str, object]:
        return {
            "spec_id": self.spec.spec_id,
            "asset": self.asset.to_dict(),
            "job": self.job.to_dict(),
        }


class GenerationExecutor:
    """Run GenerationSpec -> Registry -> Provider -> Asset -> Job.

    The executor branches only on the media kind, never on provider/model names.
    Provider selection is delegated to the registry and execution is delegated to
    the single `BaseProvider` interface.
    """

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or DEFAULT_REGISTRY

    def execute(
        self,
        spec: GenerationSpec,
        output_dir: str | Path,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
        job_id: str | None = None,
    ) -> GenerationExecution:
        kind = spec.kind if isinstance(spec.kind, GenerationKind) else GenerationKind(str(spec.kind))
        provider = self.registry.get(provider_id or spec.provider, kind=kind, model_id=model_id)
        estimate = provider.estimate(spec)
        if kind is GenerationKind.VIDEO:
            asset = provider.generate_video(spec, output_dir)
        else:
            asset = provider.generate_image(spec, output_dir)
        job = ProviderJob(
            id=job_id or spec.spec_id,
            status=JOB_STATUS_COMPLETE,
            provider_id=provider.provider_id,
            asset=asset,
            estimate=estimate,
        )
        return GenerationExecution(spec=spec, asset=asset, job=job)
