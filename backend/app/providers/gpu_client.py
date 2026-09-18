"""PR011 — GPU cluster transport (ETAPA 1).

This module is the *only* place in the application that knows how to talk HTTP
to an external GPU cluster. It is deliberately dumb: it submits a payload,
polls a job, cancels it, encodes a reference image and downloads a result. It
does not know what a `GenerationSpec` is, what a prompt is, or what Flux and
Wan are — that knowledge belongs to the connectors in
`runpod_flux_provider.py` and `runpod_wan_provider.py`.

What it provides
----------------
* **async HTTP** through a swappable transport (`GpuTransport`). The default
  transport imports `httpx` lazily, so importing this module never requires a
  network stack — and every test injects a fake transport instead of patching
  sockets.
* **configurable timeout** — per client (`BROBOND_GPU_TIMEOUT`) and per call.
* **exponential retry** on transient failures only. A 400 is a bug in the
  payload and retrying it just burns the deadline; a 502 is the cluster
  breathing and is retried.
* **job polling** at `BROBOND_GPU_POLL_INTERVAL`, bounded by the deadline. On
  expiry the client asks the cluster to cancel the job before giving up:
  abandoning a GPU job without cancelling it is how invoices grow.
* **cancellation** as a first-class operation.
* **reference upload** — the bytes are base64-encoded into a data URI, which is
  what serverless GPU endpoints accept as an input image. No temporary public
  bucket, no signed URL, no secret leaving the backend.
* **result download** — HTTP(S) URLs, `data:` URIs and raw base64 all resolve
  to bytes on disk through one method.

What it deliberately does not provide
-------------------------------------
Business logic. There is no branch here on model name, media kind, aspect
ratio or mode. If a future cluster needs a different job envelope, the
connector builds it and hands it over.

Secrets
-------
The API key is sent in the `Authorization` header and never appears in a
return value, a log line, an error message or a health payload. `describe()`
is the safe public view: endpoint host and configuration flags, no credential.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import mimetypes
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from ..core.config import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Terminal RunPod job states. Anything else means "still working".
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"
STATUS_CANCELLED = "CANCELLED"
STATUS_TIMED_OUT = "TIMED_OUT"
STATUS_IN_QUEUE = "IN_QUEUE"
STATUS_IN_PROGRESS = "IN_PROGRESS"

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED, STATUS_TIMED_OUT}
)
FAILED_STATUSES: frozenset[str] = frozenset({STATUS_FAILED, STATUS_CANCELLED, STATUS_TIMED_OUT})

#: HTTP statuses worth another attempt: the request was well-formed and the
#: cluster could not serve it *right now*.
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})

#: Attempt budget for one HTTP call (1 original + 2 retries).
DEFAULT_MAX_ATTEMPTS = 3

#: Exponential backoff base, in seconds: 0.5s, 1s, 2s, ...
DEFAULT_BACKOFF_SECONDS = 0.5

#: Ceiling for a single backoff sleep, so a long attempt budget cannot stall a
#: worker for minutes between tries.
MAX_BACKOFF_SECONDS = 8.0

#: A health probe gets one attempt. Retrying it three times turns a 5s
#: deadline into a 15s one on a dead endpoint, and whatever polls health —
#: an orchestrator, the readiness endpoint — already retries by asking again.
HEALTH_ATTEMPTS = 1

#: Deadline used by the lightweight `/health` probe. A readiness endpoint must
#: answer fast or not at all — it never inherits the render deadline.
HEALTH_TIMEOUT_SECONDS = 5.0

#: Fallback MIME type for a reference image whose extension says nothing.
DEFAULT_IMAGE_MIME = "image/png"

DATA_URI_PREFIX = "data:"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GpuClientError(RuntimeError):
    """Base error for the GPU transport."""


class GpuNotConfigured(GpuClientError):
    """No endpoint/API key is configured — the DEV default.

    Raised instead of attempting a request against an empty URL, so the caller
    can degrade honestly rather than reporting a network failure that never
    happened.
    """


class GpuTransportError(GpuClientError):
    """The request never produced an HTTP response (DNS, TCP, TLS, timeout)."""


class GpuHttpError(GpuClientError):
    """The cluster answered with an error status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"GPU cluster returned HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message

    @property
    def retryable(self) -> bool:
        return self.status_code in RETRYABLE_STATUS_CODES


class GpuTimeout(GpuClientError):
    """A job did not reach a terminal state before the deadline."""


class GpuJobFailed(GpuClientError):
    """The cluster finished the job in a non-success terminal state."""

    def __init__(self, job_id: str, status: str, error: str = "") -> None:
        detail = f": {error}" if error else ""
        super().__init__(f"GPU job '{job_id}' ended as {status}{detail}")
        self.job_id = job_id
        self.status = status
        self.error = error


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GpuResponse:
    """One HTTP response, reduced to what this layer needs."""

    status_code: int
    json: dict[str, Any] | None = None
    content: bytes = b""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def payload(self) -> dict[str, Any]:
        return self.json or {}

    def error_message(self) -> str:
        if self.json is not None:
            return str(self.json.get("error") or self.json.get("message") or self.json)
        return self.content[:200].decode("utf-8", "replace")


class GpuTransport(Protocol):
    """The seam every test uses instead of a socket."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> GpuResponse:  # pragma: no cover - protocol declaration
        ...

    async def aclose(self) -> None:  # pragma: no cover - protocol declaration
        ...


class HttpxTransport:
    """Default transport: one lazily-created `httpx.AsyncClient`.

    `httpx` is imported inside the call, never at module import, so this file
    stays importable on a machine that only wants to read the constants (and
    so the architecture tests can parse it without installing anything).
    """

    def __init__(self) -> None:
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import httpx
            except ImportError as error:  # pragma: no cover - httpx is pinned
                raise GpuTransportError("httpx is required to reach the GPU cluster") from error
            self._client = httpx.AsyncClient()
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> GpuResponse:
        client = self._ensure_client()
        try:
            response = await client.request(
                method, url, json=dict(json) if json is not None else None, headers=dict(headers or {}), timeout=timeout
            )
        except Exception as error:  # noqa: BLE001 - every httpx failure is a transport failure here
            raise GpuTransportError(f"{method} {_safe_url(url)} failed: {error}") from error
        body: dict[str, Any] | None
        try:
            parsed = response.json()
            body = parsed if isinstance(parsed, dict) else {"data": parsed}
        except Exception:  # noqa: BLE001 - a binary or empty body is normal
            body = None
        return GpuResponse(status_code=response.status_code, json=body, content=response.content)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _safe_url(url: str) -> str:
    """Scheme and host only.

    Error messages from this module end up in `/api/v1/system/readiness`,
    which is public. A query string can carry a token, and a serverless
    endpoint path carries the endpoint id — neither belongs in a payload a
    browser can read, and the host alone is enough to tell two deployments
    apart.
    """

    parsed = urlparse(url)
    if not parsed.netloc:
        # No host to name (a relative or malformed URL). Drop the query string
        # and return what is left rather than inventing a host.
        return url.split("?")[0]
    return f"{parsed.scheme}://{parsed.netloc}"


# ---------------------------------------------------------------------------
# Job records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GpuJob:
    """A submitted job: the handle the cluster gave back."""

    id: str
    status: str = STATUS_IN_QUEUE

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


@dataclass(frozen=True)
class GpuJobResult:
    """A finished job."""

    id: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    polls: int = 0
    elapsed_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.status == STATUS_COMPLETED


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class GpuClient:
    """Async HTTP client for a serverless GPU endpoint (RunPod shape).

    Every knob has a settings-backed default and an explicit override, so a
    connector can tighten a deadline without editing the environment and a
    test can drive the whole thing with `sleep=noop`.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        timeout: float | None = None,
        poll_interval: float | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        transport: GpuTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.runpod_api_key
        self.endpoint = (endpoint if endpoint is not None else settings.runpod_endpoint).rstrip("/")
        self.timeout = float(timeout if timeout is not None else settings.gpu_timeout)
        self.poll_interval = float(
            poll_interval if poll_interval is not None else settings.gpu_poll_interval
        )
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_seconds = float(backoff_seconds)
        self._transport = transport or HttpxTransport()
        self._sleep = sleep or asyncio.sleep
        self._monotonic = monotonic or time.monotonic

    # ------------------------------------------------------------ inspection

    @property
    def configured(self) -> bool:
        """True when an endpoint *and* a key are present.

        Both are required: an endpoint without a key gets 401s, and a key
        without an endpoint has nowhere to go. In DEV neither is set and the
        whole GPU layer reports itself unavailable instead of failing.
        """

        return bool(self.endpoint and self.api_key)

    def describe(self) -> dict[str, Any]:
        """Configuration view safe to return to a browser. No credential."""

        return {
            "configured": self.configured,
            "endpoint_host": urlparse(self.endpoint).netloc if self.endpoint else "",
            "timeout_seconds": self.timeout,
            "poll_interval_seconds": self.poll_interval,
            "max_attempts": self.max_attempts,
            "api_key_present": bool(self.api_key),
        }

    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ------------------------------------------------------------------ HTTP

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> GpuResponse:
        """One authenticated call with exponential retry on transient errors."""

        if not self.configured:
            raise GpuNotConfigured(
                "GPU cluster is not configured: set BROBOND_RUNPOD_API_KEY and BROBOND_RUNPOD_ENDPOINT"
            )
        url = f"{self.endpoint}/{path.lstrip('/')}"
        return await self._send(method, url, json=json, timeout=timeout, headers=self.headers())

    async def _send(
        self,
        method: str,
        url: str,
        *,
        json: Mapping[str, Any] | None,
        timeout: float | None,
        headers: Mapping[str, str] | None,
        max_attempts: int | None = None,
    ) -> GpuResponse:
        deadline = float(timeout if timeout is not None else self.timeout)
        attempts = max(1, int(max_attempts if max_attempts is not None else self.max_attempts))
        last_error: GpuClientError | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = await self._transport.request(
                    method, url, json=json, headers=headers, timeout=deadline
                )
            except GpuTransportError as error:
                last_error = error
            else:
                if response.ok:
                    return response
                error = GpuHttpError(response.status_code, response.error_message())
                if not error.retryable:
                    # A 4xx is a contract bug: the same payload will fail
                    # identically three times, only slower.
                    raise error
                last_error = error
            if attempt < attempts:
                await self._sleep(self.backoff_for(attempt))
        raise last_error if last_error is not None else GpuTransportError("request failed")

    def backoff_for(self, attempt: int) -> float:
        """Exponential backoff for `attempt` (1-based), capped."""

        return min(MAX_BACKOFF_SECONDS, self.backoff_seconds * (2 ** (attempt - 1)))

    # ------------------------------------------------------------------ jobs

    async def submit(self, payload: Mapping[str, Any]) -> GpuJob:
        """POST /run — hand the job envelope to the cluster."""

        response = await self.request("POST", "run", json={"input": dict(payload)})
        body = response.payload()
        job_id = str(body.get("id") or "")
        if not job_id:
            raise GpuClientError(f"GPU cluster accepted the job without an id: {body}")
        return GpuJob(id=job_id, status=str(body.get("status") or STATUS_IN_QUEUE))

    async def status(self, job_id: str) -> GpuJobResult:
        """GET /status/{id} — one snapshot, no waiting."""

        response = await self.request("GET", f"status/{job_id}")
        return self._result_from(job_id, response.payload())

    async def cancel(self, job_id: str) -> bool:
        """POST /cancel/{id}. Returns whether the cluster acknowledged it.

        Never raises: cancellation is a best-effort courtesy, usually issued
        while another error is already on its way up the stack, and masking
        that error with a cancellation failure would hide the real cause.
        """

        try:
            await self.request("POST", f"cancel/{job_id}")
        except GpuClientError:
            return False
        return True

    async def poll(
        self,
        job_id: str,
        *,
        timeout: float | None = None,
        poll_interval: float | None = None,
    ) -> GpuJobResult:
        """Poll until the job is terminal, the deadline expires, or it fails.

        On expiry the job is cancelled and `GpuTimeout` is raised. Polling
        lives here and nowhere else — in particular, never in the browser.
        """

        deadline = float(timeout if timeout is not None else self.timeout)
        interval = float(poll_interval if poll_interval is not None else self.poll_interval)
        started = self._monotonic()
        polls = 0
        while True:
            snapshot = await self.status(job_id)
            polls += 1
            elapsed = self._monotonic() - started
            if snapshot.status in TERMINAL_STATUSES:
                result = GpuJobResult(
                    id=snapshot.id,
                    status=snapshot.status,
                    output=snapshot.output,
                    error=snapshot.error,
                    polls=polls,
                    elapsed_seconds=round(elapsed, 3),
                )
                if result.status in FAILED_STATUSES:
                    raise GpuJobFailed(job_id, result.status, result.error)
                return result
            if deadline > 0 and elapsed + interval > deadline:
                await self.cancel(job_id)
                raise GpuTimeout(
                    f"GPU job '{job_id}' did not finish within {deadline:g}s "
                    f"(last status {snapshot.status}, {polls} polls)"
                )
            await self._sleep(interval)

    async def run(
        self,
        payload: Mapping[str, Any],
        *,
        timeout: float | None = None,
        poll_interval: float | None = None,
    ) -> GpuJobResult:
        """submit -> poll -> result. The whole job lifecycle, server-side."""

        job = await self.submit(payload)
        return await self.poll(job.id, timeout=timeout, poll_interval=poll_interval)

    @staticmethod
    def _result_from(job_id: str, body: Mapping[str, Any]) -> GpuJobResult:
        output = body.get("output")
        return GpuJobResult(
            id=str(body.get("id") or job_id),
            status=str(body.get("status") or STATUS_IN_PROGRESS),
            output=dict(output) if isinstance(output, Mapping) else ({"data": output} if output else {}),
            error=str(body.get("error") or ""),
        )

    # ------------------------------------------------------------- transfers

    async def upload_reference(self, reference_path: str | Path) -> str:
        """Encode a reference image as a data URI the cluster can consume.

        Serverless GPU endpoints take input images inline; the alternative —
        publishing the frame to a public bucket and passing a URL — would put
        tenant media on the open internet to save a base64 encode.
        """

        path = Path(reference_path)
        if not path.is_file():
            # Fatal by design: retrying cannot conjure a missing reference.
            raise FileNotFoundError(f"reference image not found: {path}")
        data = await asyncio.to_thread(path.read_bytes)
        mime = mimetypes.guess_type(path.name)[0] or DEFAULT_IMAGE_MIME
        return f"{DATA_URI_PREFIX}{mime};base64,{base64.b64encode(data).decode('ascii')}"

    async def download(self, source: str, destination: str | Path) -> Path:
        """Materialise a result to disk from a URL, a data URI or base64."""

        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = await self.fetch_bytes(source)
        await asyncio.to_thread(target.write_bytes, data)
        return target

    async def fetch_bytes(self, source: str) -> bytes:
        """The bytes behind a result reference, whatever shape it arrived in."""

        if not source:
            raise GpuClientError("the GPU job returned an empty result reference")
        if source.startswith(DATA_URI_PREFIX):
            return _decode_base64(source.split(",", 1)[-1])
        if source.startswith(("http://", "https://")):
            # No Authorization header: result URLs are pre-signed, and sending
            # the cluster key to an arbitrary host would leak it.
            response = await self._send(
                "GET", source, json=None, timeout=self.timeout, headers=None
            )
            return response.content
        return _decode_base64(source)

    # ----------------------------------------------------------------- probe

    async def health(
        self, *, timeout: float = HEALTH_TIMEOUT_SECONDS, attempts: int = HEALTH_ATTEMPTS
    ) -> dict[str, Any]:
        """GET /health with a short deadline and a single attempt. Never raises.

        The return value is a plain dict that is safe to serialise: it carries
        worker counts and a measured latency, never a credential.
        """

        if not self.configured:
            return {
                "available": False,
                "reason": "GPU cluster is not configured (BROBOND_RUNPOD_API_KEY / BROBOND_RUNPOD_ENDPOINT)",
                "latency_ms": 0.0,
            }
        started = self._monotonic()
        try:
            response = await self._send(
                "GET",
                f"{self.endpoint}/health",
                json=None,
                timeout=timeout,
                headers=self.headers(),
                max_attempts=attempts,
            )
        except GpuClientError as error:
            return {
                "available": False,
                "reason": str(error),
                "latency_ms": round((self._monotonic() - started) * 1000.0, 2),
            }
        latency_ms = round((self._monotonic() - started) * 1000.0, 2)
        body = response.payload()
        workers = body.get("workers") if isinstance(body.get("workers"), Mapping) else {}
        return {
            "available": True,
            "reason": None,
            "latency_ms": latency_ms,
            "workers": dict(workers),
            "jobs": dict(body["jobs"]) if isinstance(body.get("jobs"), Mapping) else {},
        }

    async def aclose(self) -> None:
        await self._transport.aclose()


def _decode_base64(payload: str) -> bytes:
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as error:
        raise GpuClientError("the GPU job returned a result that is not base64") from error


# ---------------------------------------------------------------------------
# Sync bridge
# ---------------------------------------------------------------------------


def run_sync(coroutine: Awaitable[Any]) -> Any:
    """Run an awaitable from synchronous code.

    `BaseProvider` is a synchronous interface (PR007) and the GPU transport is
    async. Rather than forking the provider contract, the connectors bridge
    here: normally `asyncio.run`, and — when a loop is already running in this
    thread, e.g. inside an async FastAPI endpoint — on a private loop in a
    worker thread, because `asyncio.run` refuses to nest.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_as_coroutine(coroutine))

    import threading

    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["value"] = asyncio.run(_as_coroutine(coroutine))
        except BaseException as error:  # noqa: BLE001 - re-raised in the caller
            box["error"] = error

    thread = threading.Thread(target=worker, name="brobond-gpu-bridge")
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


async def _as_coroutine(awaitable: Awaitable[Any]) -> Any:
    return await awaitable


@contextlib.contextmanager
def closing_client(client: GpuClient):
    """Use a client for one synchronous operation and release its transport."""

    try:
        yield client
    finally:
        with contextlib.suppress(Exception):
            run_sync(client.aclose())
