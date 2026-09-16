"""Universal provider interface for PR007.

The Core produces a `GenerationSpec`; providers are the only layer allowed to
know model brands, checkpoints or runtime SDKs. Every adapter implements the
same interface, so orchestration can route a job without knowing whether the
selected implementation is Flux, Wan, Mock, or a future remote service.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.contracts import GenerationKind, GenerationSpec

DEFAULT_PROMPT_BUDGET = 1000
DEFAULT_ESTIMATED_SECONDS = 1.0
NO_COST_UNITS = 0.0

STATUS_READY = "ready"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"


def health_timestamp() -> str:
    """UTC ISO-8601 stamp for health reports (PR009)."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProviderError(RuntimeError):
    """Base error for the universal provider layer."""


class ProviderNotFound(ProviderError, KeyError):
    """No provider was registered for the requested id or alias."""


class ProviderUnavailable(ProviderError):
    """A provider exists but cannot satisfy the requested operation."""


class ProviderUnsupported(ProviderUnavailable):
    """The provider does not support this media operation."""


class ProviderTimeoutError(ProviderError):
    """A provider execution exceeded its configured deadline (PR009).

    The deadline abandons the *wait*: GPU work cannot be preempted, so the
    abandoned thread may keep running until the runtime finishes it. What the
    caller is guaranteed is that it never blocks past the deadline.
    """


@dataclass(frozen=True)
class ProviderCapabilities:
    """Capabilities a provider can safely expose to the API and frontend."""

    max_resolution: str
    supports_video: bool
    supports_image: bool
    supports_lora: bool
    supports_upscale: bool
    supports_seed: bool
    supports_negative_prompt: bool
    prompt_budget: int = DEFAULT_PROMPT_BUDGET

    def supports(self, kind: GenerationKind) -> bool:
        return self.supports_video if kind is GenerationKind.VIDEO else self.supports_image

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderEstimate:
    """Planning estimate for a provider execution.

    It is intentionally generic: the executor can display/record it without
    understanding a model-specific billing or timing model.
    """

    provider_id: str
    kind: str
    estimated_seconds: float
    cost_units: float = NO_COST_UNITS
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderAsset:
    """The provider's output before storage turns it into a workspace asset."""

    path: str
    kind: str
    provider_id: str
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0
    fps: int = 0
    metadata: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("path is required")
        if self.kind not in {GenerationKind.IMAGE.value, GenerationKind.VIDEO.value}:
            raise ValueError("kind must be image or video")
        if not self.provider_id:
            raise ValueError("provider_id is required")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata or {})
        return payload


@dataclass(frozen=True)
class ProviderHealth:
    """Health payload exposed by `GET /api/v1/providers`."""

    id: str
    label: str
    status: str
    latency_ms: float
    version: str
    capabilities: ProviderCapabilities
    reason: str | None = None
    loaded: bool = False
    #: PR009: when this health report was produced (UTC ISO-8601).
    last_health_at: str | None = None

    def with_latency(self, latency_ms: float) -> "ProviderHealth":
        """Registry measurement point: stamps the latency *and* the instant."""

        return replace(self, latency_ms=latency_ms, last_health_at=health_timestamp())

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["capabilities"] = self.capabilities.to_dict()
        return payload


@dataclass(frozen=True)
class ProviderJob:
    """Executor-level job record: spec -> provider -> asset -> job.

    PR009 additions are all optional so a plain `spec -> provider -> asset`
    run keeps the exact PR007 shape; they only mean something when the retry
    engine or the fallback chain acted on the execution.
    """

    id: str
    status: str
    provider_id: str
    asset: ProviderAsset
    estimate: ProviderEstimate
    #: PR009: how many provider attempts the executor spent (1 = first try won).
    attempts: int = 1
    #: PR009: set when the asset came from the fallback provider, with the
    #: reason the requested provider could not produce it. The reason is the
    #: job's audit trail — a fallback that hides why it happened is a lie.
    fallback: bool = False
    fallback_from: str | None = None
    fallback_reason: str | None = None
    #: PR009: telemetry snapshot (provider, latency, queue/render time, ...).
    telemetry: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["asset"] = self.asset.to_dict()
        payload["estimate"] = self.estimate.to_dict()
        return payload


class BaseProvider(ABC):
    """Single mandatory provider interface.

    All rendering/upscaling methods receive the `GenerationSpec`. No adapter has
    a method that accepts a prompt string or an ad-hoc parameters dictionary.
    """

    provider_id: str
    label: str
    version: str

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return public capability metadata for discovery."""

    @abstractmethod
    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        """Generate an image for `spec`."""

    @abstractmethod
    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset:
        """Generate a video for `spec`."""

    @abstractmethod
    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset:
        """Upscale an existing asset under the same spec contract."""

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Return a safe health report with no secrets."""

    @abstractmethod
    def estimate(self, spec: GenerationSpec) -> ProviderEstimate:
        """Estimate execution cost/latency for `spec`."""


def unsupported(provider_id: str, operation: str) -> ProviderUnsupported:
    return ProviderUnsupported(f"provider '{provider_id}' does not support {operation}")
