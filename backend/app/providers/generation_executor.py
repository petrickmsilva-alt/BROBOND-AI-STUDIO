"""Provider-agnostic generation executor (PR007; hardened in PR009).

Execution flow, all of it provider-name agnostic:

```text
GenerationSpec
  -> Registry.get(requested provider)
       not found / kind refused --------+
  -> RetryEngine( <= 3 attempts, backoff)|
       -> TimeoutManager.run(deadline)   |
            -> BaseProvider.generate_*(spec, dir)
  -> attempts exhausted (retryable) ---->+
  -> fatal error -> propagate (a contract bug must not be masked)
                                         |
  Fallback: Registry.get(MockProvider)   v
  generates the asset and the Job records WHY (never lose the batch)
  -> TelemetryStore.record(provider, latency, queue/render time,
                           success, error_code)
```

Availability is discovered the honest way: by attempting. A provider with no
CUDA fails its first attempt with a plain `RuntimeError`, the engine classifies
it, spends the budget, and the fallback chain takes over with the reason
recorded. `health()` stays a discovery surface for the API; it never gates a
render, because a health probe can be wrong in either direction.

Timing definitions (telemetry):

* ``queue_time_ms``  — wall time spent *outside* provider generation calls:
  registry resolution and backoff waits;
* ``render_time_ms`` — wall time spent inside provider generation calls,
  summed across attempts (a timed-out attempt counts its whole deadline);
* ``latency_ms``     — wall time of the whole ``execute()`` call.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ..core.contracts import GenerationKind, GenerationSpec
from .base_provider import (
    BaseProvider,
    ProviderAsset,
    ProviderError,
    ProviderJob,
    ProviderNotFound,
    ProviderTimeoutError,
    ProviderUnavailable,
    ProviderUnsupported,
)
from .provider_registry import DEFAULT_REGISTRY, ProviderRegistry
from .retry_policy import RetryEngine, RetryOutcome, RetryState
from .telemetry import (
    ERROR_FATAL,
    ERROR_GENERATION,
    ERROR_NOT_REGISTERED,
    ERROR_TIMEOUT,
    ERROR_UNAVAILABLE,
    ERROR_UNSUPPORTED,
    ProviderTelemetryRecord,
    TelemetryStore,
    default_telemetry_store,
)
from .timeout_manager import TimeoutManager

JOB_STATUS_COMPLETE = "complete"

#: Fallback chain target. Importing the id (not the class) keeps the executor
#: coupled to the registry, never to a concrete provider.
FALLBACK_PROVIDER_ID = "mock"


@dataclass(frozen=True)
class GenerationExecution:
    """Result of the universal execution flow."""

    spec: GenerationSpec
    asset: ProviderAsset
    job: ProviderJob
    #: PR009: the telemetry record this execution produced.
    telemetry: ProviderTelemetryRecord | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "spec_id": self.spec.spec_id,
            "asset": self.asset.to_dict(),
            "job": self.job.to_dict(),
        }
        if self.telemetry is not None:
            payload["telemetry"] = self.telemetry.to_dict()
        return payload


class GenerationExecutor:
    """Run GenerationSpec -> Registry -> Provider -> Asset -> Job.

    The executor branches only on the media kind, never on provider/model
    names. Selection is delegated to the registry, execution to the single
    `BaseProvider` interface, resilience to the retry engine, the timeout
    manager and the fallback chain, and observability to the telemetry store.
    """

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        *,
        retry_engine: RetryEngine | None = None,
        timeout_manager: TimeoutManager | None = None,
        telemetry_store: TelemetryStore | None = None,
        fallback_provider_id: str = FALLBACK_PROVIDER_ID,
        fallback_enabled: bool = True,
    ) -> None:
        self.registry = registry or DEFAULT_REGISTRY
        self.retry_engine = retry_engine or RetryEngine()
        self.timeout_manager = timeout_manager or TimeoutManager()
        # `is not None`, not `or`: an empty TelemetryStore is falsy by
        # `__len__`, and silently swapping it for the default store would send
        # records somewhere the caller is not watching.
        self.telemetry_store = telemetry_store if telemetry_store is not None else default_telemetry_store()
        self.fallback_provider_id = fallback_provider_id
        self.fallback_enabled = fallback_enabled

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
        requested_id = provider_id or spec.provider
        started = time.perf_counter()
        render_elapsed: list[float] = []

        provider: BaseProvider | None = None
        fallback_reason: str | None = None
        error_code: str | None = None
        outcome: RetryOutcome | None = None
        attempts = 0

        try:
            provider = self.registry.get(requested_id, kind=kind, model_id=model_id)
        except ProviderNotFound as error:
            fallback_reason = f"provider '{requested_id}' is not registered: {error}"
            error_code = ERROR_NOT_REGISTERED
        except ProviderUnavailable as error:
            fallback_reason = str(error)
            error_code = ERROR_UNAVAILABLE

        if fallback_reason is None and provider is not None:
            outcome = self._run_with_resilience(provider, spec, output_dir, kind, render_elapsed)
            attempts = outcome.attempts
            if outcome.success:
                fallback_reason = None
            elif outcome.final_state is RetryState.FATAL or not self.fallback_enabled:
                # A contract bug (or fallback switched off) must surface — but
                # the failure still leaves a telemetry trail behind.
                self._record_failure(provider, spec, kind, job_id, started, render_elapsed, outcome)
                raise outcome.error if outcome.error is not None else ProviderError("generation failed")
            else:
                fallback_reason, error_code = self._fallback_verdict(provider, outcome)

        if fallback_reason is not None:
            asset = self._fallback_generate(spec, output_dir, kind, fallback_reason)
            executed_provider = self.registry.get(self.fallback_provider_id, kind=kind)
            success_code = error_code
        elif outcome is not None and outcome.success:
            asset = outcome.result
            executed_provider = provider
            success_code = None
        else:  # pragma: no cover - defensive: unreachable by construction
            raise ProviderError("execution finished without an asset or a fallback reason")

        latency_ms = (time.perf_counter() - started) * 1000.0
        render_time_ms = sum(render_elapsed) * 1000.0
        queue_time_ms = max(0.0, latency_ms - render_time_ms)
        record = ProviderTelemetryRecord(
            provider_id=executed_provider.provider_id if executed_provider else self.fallback_provider_id,
            requested_provider_id=str(requested_id or ""),
            spec_id=spec.spec_id,
            kind=kind.value,
            success=True,
            error_code=success_code,
            latency_ms=round(latency_ms, 2),
            queue_time_ms=round(queue_time_ms, 2),
            render_time_ms=round(render_time_ms, 2),
            #: Honest count: a health-gated fallback spent zero attempts.
            attempts=attempts,
            fallback=fallback_reason is not None,
            fallback_reason=fallback_reason,
            job_id=job_id or spec.spec_id,
        )
        self.telemetry_store.record(record)

        estimate_source = executed_provider if executed_provider is not None else provider
        job = ProviderJob(
            id=job_id or spec.spec_id,
            status=JOB_STATUS_COMPLETE,
            provider_id=record.provider_id,
            asset=asset,
            estimate=estimate_source.estimate(spec),
            attempts=record.attempts,
            fallback=record.fallback,
            fallback_from=str(requested_id or "") if record.fallback else None,
            fallback_reason=fallback_reason,
            telemetry=record.to_dict(),
        )
        return GenerationExecution(spec=spec, asset=asset, job=job, telemetry=record)

    # ------------------------------------------------------------------ steps

    def _run_with_resilience(
        self,
        provider: BaseProvider,
        spec: GenerationSpec,
        output_dir: str | Path,
        kind: GenerationKind,
        render_elapsed: list[float],
    ) -> RetryOutcome:
        """Retry + timeout around the provider call."""

        deadline_seconds = self.timeout_manager.seconds_for(provider.provider_id)

        def call() -> ProviderAsset:
            attempt_started = time.perf_counter()
            try:
                return self.timeout_manager.run(
                    provider.provider_id,
                    lambda: self._generate(provider, spec, output_dir, kind),
                    seconds=deadline_seconds,
                )
            finally:
                render_elapsed.append(time.perf_counter() - attempt_started)

        return self.retry_engine.attempt(call)

    def _record_failure(
        self,
        provider: BaseProvider,
        spec: GenerationSpec,
        kind: GenerationKind,
        job_id: str | None,
        started: float,
        render_elapsed: list[float],
        outcome: RetryOutcome,
    ) -> None:
        """Fatal failures propagate — but never silently."""

        latency_ms = (time.perf_counter() - started) * 1000.0
        render_time_ms = sum(render_elapsed) * 1000.0
        error = outcome.error
        code = ERROR_UNSUPPORTED if isinstance(error, ProviderUnsupported) else ERROR_FATAL
        self.telemetry_store.record(
            ProviderTelemetryRecord(
                provider_id=provider.provider_id,
                requested_provider_id=spec.provider or "",
                spec_id=spec.spec_id,
                kind=kind.value,
                success=False,
                error_code=code,
                latency_ms=round(latency_ms, 2),
                queue_time_ms=round(max(0.0, latency_ms - render_time_ms), 2),
                render_time_ms=round(render_time_ms, 2),
                attempts=outcome.attempts,
                fallback=False,
                fallback_reason=None,
                job_id=job_id or spec.spec_id,
            )
        )

    def _fallback_verdict(self, provider: BaseProvider, outcome: RetryOutcome) -> tuple[str, str]:
        """Why the fallback chain takes over, and the matching error code."""

        error = outcome.error
        if isinstance(error, ProviderTimeoutError) or outcome.final_state is RetryState.TIMEOUT:
            return (
                f"provider '{provider.provider_id}' timed out after {outcome.attempts} attempts "
                f"(deadline {self.timeout_manager.seconds_for(provider.provider_id):g}s)",
                ERROR_TIMEOUT,
            )
        if isinstance(error, ProviderUnavailable):
            return (
                f"provider '{provider.provider_id}' unavailable after {outcome.attempts} attempts: {error}",
                ERROR_UNAVAILABLE,
            )
        return (
            f"provider '{provider.provider_id}' failed after {outcome.attempts} attempts: "
            f"{error or 'unknown error'}",
            ERROR_GENERATION,
        )

    @staticmethod
    def _generate(
        provider: BaseProvider, spec: GenerationSpec, output_dir: str | Path, kind: GenerationKind
    ) -> ProviderAsset:
        if kind is GenerationKind.VIDEO:
            return provider.generate_video(spec, output_dir)
        return provider.generate_image(spec, output_dir)

    def _fallback_generate(
        self, spec: GenerationSpec, output_dir: str | Path, kind: GenerationKind, reason: str
    ) -> ProviderAsset:
        """Registry -> MockProvider. The batch never dies for lack of a provider."""

        try:
            fallback = self.registry.get(self.fallback_provider_id, kind=kind)
        except (ProviderNotFound, ProviderUnavailable) as error:
            raise ProviderUnavailable(
                f"fallback provider '{self.fallback_provider_id}' could not take over "
                f"({reason}); original failure: {error}"
            ) from error
        return self._generate(fallback, spec, output_dir, kind)
