"""PR011 — what every RunPod-backed connector does identically.

`runpod_flux_provider` (image) and `runpod_wan_provider` (video) differ in the
job envelope they build and in the media they return. Everything else — client
wiring, the submit/poll/download lifecycle, health reporting, secret hygiene —
is written once, here.

The division of labour is the point of the PR:

    gpu_client.py      transport only: HTTP, retry, poll, cancel, transfer
    runpod_base.py     lifecycle: spec -> payload -> job -> bytes -> asset
    runpod_*_provider  the payload, and nothing else

A connector therefore never sees an HTTP status code, and the client never
sees a `GenerationSpec`.

The synchronous `BaseProvider` interface from PR007 is unchanged: `execute`
still calls `generate_image(spec, output_dir)`. The async transport is bridged
by `run_sync`, so the GPU cluster does not leak an `async def` into a contract
twenty modules already depend on.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..core.contracts import GenerationSpec
from .base_provider import (
    STATUS_READY,
    STATUS_UNAVAILABLE,
    BaseProvider,
    ProviderAsset,
    ProviderHealth,
    ProviderUnavailable,
    health_timestamp,
)
from .gpu_client import (
    GpuClient,
    GpuClientError,
    GpuJobFailed,
    GpuJobResult,
    GpuNotConfigured,
    GpuTimeout,
    run_sync,
)

#: Keys a RunPod worker may use for the produced artifact, in priority order.
#: Serverless templates are not standardised, so the connector reads the union
#: instead of demanding one spelling.
OUTPUT_KEYS: tuple[str, ...] = ("image", "image_url", "video", "video_url", "url", "output", "base64")

#: Provider id of the cluster vendor, reported by readiness.
GPU_PROVIDER_NAME = "runpod"


class RunPodProvider(BaseProvider):
    """Base class for connectors that execute on a RunPod serverless endpoint."""

    provider_id = ""
    label = ""
    version = ""
    model_id_default = ""
    #: Advertised VRAM of the endpoint's GPU class. A string, because that is
    #: what it is: a hardware label, not a measurement this process can take.
    vram = ""
    #: File extension of the artifact this connector produces.
    output_suffix = ".png"

    def __init__(
        self,
        model_id: str | None = None,
        *,
        client: GpuClient | None = None,
    ) -> None:
        self.model_id = model_id or self.model_id_default
        self._client = client
        self._last_job_id: str | None = None

    # ---------------------------------------------------------------- client

    @property
    def client(self) -> GpuClient:
        """The GPU client, created on first use.

        Lazy so that merely listing providers (registry discovery, health of
        the *other* providers) never constructs an HTTP stack.
        """

        if self._client is None:
            self._client = GpuClient()
        return self._client

    @property
    def configured(self) -> bool:
        return self.client.configured

    # ------------------------------------------------------------- lifecycle

    def execute_job(self, payload: Mapping[str, Any]) -> GpuJobResult:
        """submit -> poll -> terminal result, with honest error translation.

        Every GPU failure becomes a `ProviderUnavailable`, which is exactly
        what the PR009 resilience stack already knows how to retry and fall
        back from. A missing configuration is not dressed up as a failure: it
        says the cluster is not configured.
        """

        if not self.configured:
            raise ProviderUnavailable(
                f"provider '{self.provider_id}' has no GPU cluster configured "
                "(set BROBOND_RUNPOD_API_KEY and BROBOND_RUNPOD_ENDPOINT)"
            )
        try:
            result = run_sync(self.client.run(payload))
        except GpuNotConfigured as error:
            raise ProviderUnavailable(str(error)) from error
        except GpuTimeout as error:
            raise ProviderUnavailable(str(error)) from error
        except GpuJobFailed as error:
            raise ProviderUnavailable(str(error)) from error
        except GpuClientError as error:
            raise ProviderUnavailable(f"provider '{self.provider_id}' GPU call failed: {error}") from error
        self._last_job_id = result.id
        return result

    def materialise(self, result: GpuJobResult, output_dir: str | Path, spec_id: str) -> Path:
        """Write the job's artifact to disk and return the path."""

        reference = self.output_reference(result)
        destination = Path(output_dir) / f"{spec_id}{self.output_suffix}"
        try:
            return run_sync(self.client.download(reference, destination))
        except GpuClientError as error:
            raise ProviderUnavailable(
                f"provider '{self.provider_id}' could not download job '{result.id}': {error}"
            ) from error

    @staticmethod
    def output_reference(result: GpuJobResult) -> str:
        """The artifact reference inside a worker's `output` block.

        A completed job with no artifact is a failure, not an empty success —
        saying so here keeps the lie out of the asset store.
        """

        output = result.output or {}
        for key in OUTPUT_KEYS:
            value = output.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list) and value and isinstance(value[0], str):
                return value[0]
        raise ProviderUnavailable(
            f"GPU job '{result.id}' completed without a usable artifact (keys: {sorted(output)})"
        )

    def upload_reference(self, reference_path: str) -> str:
        """Encode a local reference frame for the job payload."""

        try:
            return run_sync(self.client.upload_reference(reference_path))
        except FileNotFoundError as error:
            # Fatal: a missing file is a contract error, and the retry engine
            # correctly refuses to retry `ValueError`.
            raise ValueError(str(error)) from error

    def cancel(self, job_id: str) -> bool:
        """Cancel a submitted job. Never raises."""

        return bool(run_sync(self.client.cancel(job_id)))

    # ----------------------------------------------------------------- health

    def probe(self) -> dict[str, Any]:
        """Live cluster probe, safe to serialise and never raising."""

        return dict(run_sync(self.client.health()))

    def health(self) -> ProviderHealth:
        """Health without secrets.

        Unconfigured is reported as `unavailable` with the reason naming the
        two environment variables — never as an error, and never with the key.
        """

        if not self.configured:
            return self._health_report(False, "GPU cluster is not configured", 0.0)
        probe = self.probe()
        return self._health_report(
            bool(probe.get("available")),
            None if probe.get("available") else str(probe.get("reason") or "GPU cluster unreachable"),
            float(probe.get("latency_ms") or 0.0),
        )

    def _health_report(self, available: bool, reason: str | None, latency_ms: float) -> ProviderHealth:
        return ProviderHealth(
            id=self.provider_id,
            label=self.label,
            status=STATUS_READY if available else STATUS_UNAVAILABLE,
            latency_ms=latency_ms,
            version=self.version,
            capabilities=self.capabilities(),
            reason=reason,
            loaded=False,
            last_health_at=health_timestamp(),
        )

    # ------------------------------------------------------------- metadata

    def asset_metadata(self, spec: GenerationSpec, result: GpuJobResult, **extra: Any) -> dict[str, Any]:
        """Traceability for one render: which cluster, which job, how long.

        No API key, no endpoint URL, no headers — an asset record is read by
        the frontend.
        """

        metadata: dict[str, Any] = {
            "gpu_provider": GPU_PROVIDER_NAME,
            "model_id": self.model_id,
            "job_id": result.id,
            "polls": result.polls,
            "gpu_seconds": result.elapsed_seconds,
            "seed": spec.seed,
        }
        metadata.update(extra)
        return metadata

    def asset(self, path: Path, kind: str, metadata: dict[str, Any], **dimensions: Any) -> ProviderAsset:
        return ProviderAsset(
            path=str(path),
            kind=kind,
            provider_id=self.provider_id,
            metadata=metadata,
            **dimensions,
        )
