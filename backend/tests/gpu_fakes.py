"""PR011 — a complete fake of the RunPod HTTP API, shared by the GPU tests.

Not a mock library and not a recorded cassette: a small state machine that
answers `/run`, `/status/{id}`, `/cancel/{id}` and `/health` the way the real
endpoint does, including the part that matters most — a job is `IN_QUEUE`,
then `IN_PROGRESS`, then terminal, so polling is actually exercised instead of
being short-circuited by an instantly-completed job.

Everything the tests need to steer is a constructor argument: how many polls
before completion, what the worker returns, which calls fail and with which
status. Nothing is patched at module level, so the tests stay parallel-safe
and never leave global state behind.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.providers.gpu_client import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_IN_QUEUE,
    GpuResponse,
    GpuTransportError,
)

#: A one-pixel PNG, base64 — the bytes a worker "renders".
PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PIXEL_PNG_BYTES = base64.b64decode(PIXEL_PNG_BASE64)

DEFAULT_ENDPOINT = "https://api.runpod.ai/v2/test-endpoint"
DEFAULT_API_KEY = "rp-test-key-never-logged"


@dataclass
class RecordedCall:
    """One HTTP call the client made."""

    method: str
    url: str
    json: dict[str, Any] | None
    headers: dict[str, str]
    timeout: float | None

    @property
    def path(self) -> str:
        return self.url.split(DEFAULT_ENDPOINT, 1)[-1] if DEFAULT_ENDPOINT in self.url else self.url

    @property
    def input(self) -> dict[str, Any]:
        return dict((self.json or {}).get("input") or {})


@dataclass
class FakeRunPod:
    """An in-memory RunPod serverless endpoint."""

    #: How many `/status` calls report a non-terminal state before finishing.
    polls_before_done: int = 1
    #: The worker's `output` block on completion.
    output: dict[str, Any] = field(default_factory=lambda: {"image": PIXEL_PNG_BASE64})
    #: Terminal status to finish with.
    final_status: str = STATUS_COMPLETED
    #: `error` string reported with a failing terminal status.
    error: str = ""
    #: Status codes to answer with, consumed in order, before behaving normally.
    #: An entry of 0 raises a transport error instead (a dropped connection).
    failures: list[int] = field(default_factory=list)
    #: `/health` behaviour.
    health_payload: dict[str, Any] = field(
        default_factory=lambda: {"workers": {"ready": 2, "running": 1}, "jobs": {"inQueue": 0}}
    )
    health_status: int = 200

    calls: list[RecordedCall] = field(default_factory=list)
    submitted: list[dict[str, Any]] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    _polls: dict[str, int] = field(default_factory=dict)
    _counter: int = 0

    # ---------------------------------------------------------------- helpers

    @property
    def paths(self) -> list[str]:
        return [call.path for call in self.calls]

    def call_count(self, fragment: str) -> int:
        return len([path for path in self.paths if fragment in path])

    # -------------------------------------------------------------- transport

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> GpuResponse:
        call = RecordedCall(method, url, dict(json) if json else None, dict(headers or {}), timeout)
        self.calls.append(call)

        if self.failures:
            status = self.failures.pop(0)
            if status == 0:
                raise GpuTransportError(f"connection reset on {method} {url}")
            return GpuResponse(status_code=status, json={"error": "cluster busy"})

        path = call.path
        if path.endswith("/health") or path == "/health":
            return GpuResponse(status_code=self.health_status, json=dict(self.health_payload))
        if path.endswith("/run"):
            return self._run(call)
        if "/status/" in path:
            return self._status(path.rsplit("/", 1)[-1])
        if "/cancel/" in path:
            job_id = path.rsplit("/", 1)[-1]
            self.cancelled.append(job_id)
            return GpuResponse(status_code=200, json={"id": job_id, "status": "CANCELLED"})
        if url.startswith("http") and "runpod" not in url:
            # A pre-signed result URL: plain bytes, no JSON.
            return GpuResponse(status_code=200, content=PIXEL_PNG_BYTES)
        return GpuResponse(status_code=404, json={"error": f"no route for {path}"})

    def _run(self, call: RecordedCall) -> GpuResponse:
        self._counter += 1
        job_id = f"job-{self._counter}"
        self.submitted.append(call.input)
        self._polls[job_id] = 0
        return GpuResponse(status_code=200, json={"id": job_id, "status": STATUS_IN_QUEUE})

    def _status(self, job_id: str) -> GpuResponse:
        seen = self._polls.get(job_id, 0)
        self._polls[job_id] = seen + 1
        if seen < self.polls_before_done:
            state = STATUS_IN_QUEUE if seen == 0 else STATUS_IN_PROGRESS
            return GpuResponse(status_code=200, json={"id": job_id, "status": state})
        body: dict[str, Any] = {"id": job_id, "status": self.final_status}
        if self.final_status == STATUS_COMPLETED:
            body["output"] = dict(self.output)
        if self.error:
            body["error"] = self.error
        return GpuResponse(status_code=200, json=body)

    async def aclose(self) -> None:
        self.closed = True


class NeverFinishes(FakeRunPod):
    """An endpoint whose jobs stay in progress forever — for deadline tests."""

    def _status(self, job_id: str) -> GpuResponse:
        self._polls[job_id] = self._polls.get(job_id, 0) + 1
        return GpuResponse(status_code=200, json={"id": job_id, "status": STATUS_IN_PROGRESS})


class FakeClock:
    """Monotonic time the test advances by sleeping, so no wall time passes."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def gpu_client(transport, clock: FakeClock | None = None, **overrides):
    """A configured `GpuClient` wired to a fake transport and a fake clock."""

    from app.providers.gpu_client import GpuClient

    clock = clock or FakeClock()
    kwargs: dict[str, Any] = {
        "api_key": DEFAULT_API_KEY,
        "endpoint": DEFAULT_ENDPOINT,
        "timeout": 60.0,
        "poll_interval": 1.0,
        "backoff_seconds": 0.5,
        "transport": transport,
        "sleep": clock.sleep,
        "monotonic": clock.monotonic,
    }
    kwargs.update(overrides)
    return GpuClient(**kwargs)
