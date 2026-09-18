"""PR011 — ETAPA 7: the GPU transport, fully mocked.

Every test here drives `GpuClient` against `FakeRunPod`, a state machine that
answers the four endpoints the real cluster answers. No socket is opened, no
wall-clock second passes (the clock is fake, so a 300s deadline is tested in
microseconds), and no environment variable is required — which is the point:
a laptop with no RunPod account runs this file exactly like CI does.

What is asserted, beyond "it works":

* a 4xx is **not** retried (retrying a malformed payload only burns the
  deadline), a 5xx is;
* polling walks IN_QUEUE -> IN_PROGRESS -> COMPLETED rather than being handed
  a finished job;
* a deadline **cancels** the job before raising — an abandoned GPU job is a
  bill, not just a lost render;
* the API key appears in the Authorization header and in no return value,
  and is not sent to a third-party result URL.
"""
from __future__ import annotations

import asyncio
import base64

import pytest
from gpu_fakes import (
    DEFAULT_API_KEY,
    DEFAULT_ENDPOINT,
    PIXEL_PNG_BASE64,
    PIXEL_PNG_BYTES,
    FakeClock,
    FakeRunPod,
    NeverFinishes,
    gpu_client,
)

from app.providers.gpu_client import (
    DATA_URI_PREFIX,
    HEALTH_ATTEMPTS,
    MAX_BACKOFF_SECONDS,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_IN_QUEUE,
    GpuClient,
    GpuClientError,
    GpuHttpError,
    GpuJob,
    GpuJobFailed,
    GpuJobResult,
    GpuNotConfigured,
    GpuResponse,
    GpuTimeout,
    GpuTransportError,
    HttpxTransport,
    closing_client,
    run_sync,
)


def run(coroutine):
    return asyncio.run(coroutine)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_a_client_with_no_credentials_is_not_configured_and_never_calls_out() -> None:
    """The DEV default. Optional variables mean *optional*, not "crashes"."""

    fake = FakeRunPod()
    client = gpu_client(fake, api_key="", endpoint="")

    assert client.configured is False
    with pytest.raises(GpuNotConfigured, match="BROBOND_RUNPOD_API_KEY"):
        run(client.request("GET", "health"))
    assert fake.calls == [], "an unconfigured client must not touch the network"


@pytest.mark.parametrize(
    ("api_key", "endpoint", "configured"),
    [
        (DEFAULT_API_KEY, DEFAULT_ENDPOINT, True),
        ("", DEFAULT_ENDPOINT, False),
        (DEFAULT_API_KEY, "", False),
        ("", "", False),
    ],
)
def test_both_the_key_and_the_endpoint_are_required(api_key, endpoint, configured) -> None:
    assert gpu_client(FakeRunPod(), api_key=api_key, endpoint=endpoint).configured is configured


def test_the_client_reads_its_defaults_from_settings(monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "runpod_api_key", "from-env")
    monkeypatch.setattr(config.settings, "runpod_endpoint", "https://example.test/v2/abc/")
    monkeypatch.setattr(config.settings, "gpu_timeout", 42.0)
    monkeypatch.setattr(config.settings, "gpu_poll_interval", 3.5)

    client = GpuClient(transport=FakeRunPod())

    assert client.api_key == "from-env"
    assert client.endpoint == "https://example.test/v2/abc", "a trailing slash is normalised away"
    assert client.timeout == 42.0
    assert client.poll_interval == 3.5


def test_describe_is_safe_to_return_to_a_browser() -> None:
    describe = gpu_client(FakeRunPod()).describe()

    assert describe["configured"] is True
    assert describe["endpoint_host"] == "api.runpod.ai"
    assert describe["api_key_present"] is True
    assert DEFAULT_API_KEY not in repr(describe), "the key itself never leaves the backend"
    assert DEFAULT_ENDPOINT not in repr(describe), "only the host, never the full endpoint path"


def test_the_api_key_travels_in_the_authorization_header() -> None:
    fake = FakeRunPod()
    run(gpu_client(fake).request("GET", "health"))

    assert fake.calls[0].headers["Authorization"] == f"Bearer {DEFAULT_API_KEY}"
    assert fake.calls[0].headers["Content-Type"] == "application/json"


def test_headers_omit_authorization_when_there_is_no_key() -> None:
    assert "Authorization" not in gpu_client(FakeRunPod(), api_key="").headers()


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
def test_transient_statuses_are_retried_and_then_succeed(status: int) -> None:
    fake = FakeRunPod(failures=[status])
    clock = FakeClock()

    response = run(gpu_client(fake, clock).request("GET", "health"))

    assert response.ok
    assert len(fake.calls) == 2, "one failure, one retry"
    assert clock.slept == [0.5], "the retry waited one backoff step"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_not_retried(status: int) -> None:
    """Retrying a bad payload three times just fails three times, slower."""

    fake = FakeRunPod(failures=[status])

    with pytest.raises(GpuHttpError) as error:
        run(gpu_client(fake).request("POST", "run", json={"input": {}}))

    assert error.value.status_code == status
    assert error.value.retryable is False
    assert len(fake.calls) == 1


def test_a_dropped_connection_is_retried() -> None:
    fake = FakeRunPod(failures=[0, 0])
    clock = FakeClock()

    response = run(gpu_client(fake, clock).request("GET", "health"))

    assert response.ok
    assert clock.slept == [0.5, 1.0], "exponential, not constant"


def test_the_attempt_budget_is_finite_and_the_last_error_surfaces() -> None:
    fake = FakeRunPod(failures=[503, 503, 503])

    with pytest.raises(GpuHttpError, match="503"):
        run(gpu_client(fake, max_attempts=3).request("GET", "health"))

    assert len(fake.calls) == 3, "3 attempts, not an infinite loop"


def test_the_last_transport_error_surfaces_when_every_attempt_drops() -> None:
    fake = FakeRunPod(failures=[0, 0, 0])

    with pytest.raises(GpuTransportError, match="connection reset"):
        run(gpu_client(fake).request("GET", "health"))


def test_backoff_is_exponential_and_capped() -> None:
    client = gpu_client(FakeRunPod(), backoff_seconds=1.0)

    assert [client.backoff_for(n) for n in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 8.0]
    assert client.backoff_for(10) == MAX_BACKOFF_SECONDS, "a cap, so a worker never stalls"


def test_a_single_attempt_client_does_not_sleep() -> None:
    fake = FakeRunPod(failures=[503])
    clock = FakeClock()

    with pytest.raises(GpuHttpError):
        run(gpu_client(fake, clock, max_attempts=1).request("GET", "health"))

    assert clock.slept == [], "nothing to wait for when there is no next attempt"
    assert gpu_client(fake, max_attempts=0).max_attempts == 1, "at least one attempt, always"


# ---------------------------------------------------------------------------
# Submit / poll / cancel
# ---------------------------------------------------------------------------


def test_submit_wraps_the_payload_in_the_input_envelope() -> None:
    fake = FakeRunPod()

    job = run(gpu_client(fake).submit({"prompt": "a lighthouse"}))

    assert isinstance(job, GpuJob)
    assert job.id == "job-1"
    assert job.status == STATUS_IN_QUEUE
    assert job.terminal is False
    assert fake.calls[0].json == {"input": {"prompt": "a lighthouse"}}
    assert fake.paths[0] == "/run"


def test_submit_refuses_a_response_without_a_job_id() -> None:
    class NoId(FakeRunPod):
        def _run(self, call):
            return GpuResponse(status_code=200, json={"status": "IN_QUEUE"})

    with pytest.raises(GpuClientError, match="without an id"):
        run(gpu_client(NoId()).submit({}))


def test_polling_walks_the_real_state_machine() -> None:
    """IN_QUEUE -> IN_PROGRESS -> COMPLETED, one HTTP call per state."""

    fake = FakeRunPod(polls_before_done=2)
    clock = FakeClock()
    client = gpu_client(fake, clock)

    job = run(client.submit({"prompt": "x"}))
    result = run(client.poll(job.id))

    assert isinstance(result, GpuJobResult)
    assert result.succeeded is True
    assert result.status == STATUS_COMPLETED
    assert result.polls == 3
    assert result.output == {"image": PIXEL_PNG_BASE64}
    assert clock.slept == [1.0, 1.0], "it waited the poll interval between polls"
    assert fake.call_count("/status/") == 3


def test_run_is_submit_plus_poll() -> None:
    fake = FakeRunPod(polls_before_done=1)

    result = run(gpu_client(fake).run({"prompt": "x"}))

    assert result.succeeded
    assert fake.paths[:2] == ["/run", "/status/job-1"]


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "TIMED_OUT"])
def test_a_failed_terminal_state_raises_with_the_worker_error(status: str) -> None:
    fake = FakeRunPod(polls_before_done=0, final_status=status, error="CUDA out of memory")

    with pytest.raises(GpuJobFailed) as error:
        run(gpu_client(fake).run({"prompt": "x"}))

    assert error.value.status == status
    assert error.value.job_id == "job-1"
    assert "CUDA out of memory" in str(error.value)


def test_a_failed_job_without_an_error_message_still_names_the_state() -> None:
    fake = FakeRunPod(polls_before_done=0, final_status=STATUS_FAILED)

    with pytest.raises(GpuJobFailed, match="ended as FAILED"):
        run(gpu_client(fake).run({"prompt": "x"}))


def test_the_deadline_cancels_the_job_before_giving_up() -> None:
    """An abandoned GPU job keeps billing. The client asks for a cancel."""

    fake = NeverFinishes()
    clock = FakeClock()
    client = gpu_client(fake, clock, timeout=5.0, poll_interval=1.0)

    with pytest.raises(GpuTimeout, match="did not finish within 5s"):
        run(client.run({"prompt": "x"}))

    assert fake.cancelled == ["job-1"], "the cluster was told to stop"
    assert clock.now <= 5.0, "it never polls past the deadline"


def test_a_zero_timeout_polls_without_a_deadline() -> None:
    fake = FakeRunPod(polls_before_done=4)
    clock = FakeClock()

    result = run(gpu_client(fake, clock, timeout=0.0).run({"prompt": "x"}))

    assert result.polls == 5


def test_cancel_reports_success_and_failure_without_raising() -> None:
    fake = FakeRunPod()
    client = gpu_client(fake)

    assert run(client.cancel("job-9")) is True
    assert fake.cancelled == ["job-9"]

    fake.failures = [500, 500, 500]
    assert run(client.cancel("job-9")) is False, "a failed cancel must not mask the real error"


def test_status_returns_a_snapshot_without_waiting() -> None:
    fake = FakeRunPod(polls_before_done=3)
    client = gpu_client(fake)

    job = run(client.submit({}))
    snapshot = run(client.status(job.id))

    assert snapshot.status == STATUS_IN_QUEUE
    assert snapshot.succeeded is False
    assert snapshot.polls == 0, "a snapshot is not a poll loop"


def test_a_non_mapping_output_is_still_carried() -> None:
    fake = FakeRunPod(polls_before_done=0, output={})
    fake._status = lambda job_id: GpuResponse(  # type: ignore[assignment]
        status_code=200, json={"id": job_id, "status": STATUS_COMPLETED, "output": ["a", "b"]}
    )

    result = run(gpu_client(fake).run({}))

    assert result.output == {"data": ["a", "b"]}


def test_a_status_body_without_a_status_field_is_treated_as_in_progress() -> None:
    fake = NeverFinishes()
    fake._status = lambda job_id: GpuResponse(status_code=200, json={"id": job_id})  # type: ignore[assignment]

    with pytest.raises(GpuTimeout):
        run(gpu_client(fake, timeout=2.0, poll_interval=1.0).run({}))


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------


def test_upload_reference_encodes_the_image_as_a_data_uri(tmp_path) -> None:
    """Inline base64, so tenant media never lands in a public bucket."""

    source = tmp_path / "frame.png"
    source.write_bytes(PIXEL_PNG_BYTES)

    encoded = run(gpu_client(FakeRunPod()).upload_reference(source))

    assert encoded.startswith(f"{DATA_URI_PREFIX}image/png;base64,")
    assert base64.b64decode(encoded.split(",", 1)[1]) == PIXEL_PNG_BYTES


def test_upload_reference_guesses_a_mime_type_and_falls_back(tmp_path) -> None:
    jpeg = tmp_path / "frame.jpg"
    jpeg.write_bytes(PIXEL_PNG_BYTES)
    unknown = tmp_path / "frame.whatever"
    unknown.write_bytes(PIXEL_PNG_BYTES)
    client = gpu_client(FakeRunPod())

    assert run(client.upload_reference(jpeg)).startswith("data:image/jpeg;base64,")
    assert run(client.upload_reference(unknown)).startswith("data:image/png;base64,")


def test_upload_reference_fails_loudly_on_a_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="reference image not found"):
        run(gpu_client(FakeRunPod()).upload_reference(tmp_path / "gone.png"))


def test_download_accepts_a_data_uri_bare_base64_and_a_url(tmp_path) -> None:
    fake = FakeRunPod()
    client = gpu_client(fake)

    for index, source in enumerate(
        [
            f"data:image/png;base64,{PIXEL_PNG_BASE64}",
            PIXEL_PNG_BASE64,
            "https://cdn.example.test/results/job-1.png",
        ]
    ):
        target = run(client.download(source, tmp_path / "nested" / f"out-{index}.png"))
        assert target.read_bytes() == PIXEL_PNG_BYTES


def test_downloading_a_result_url_does_not_send_the_cluster_key() -> None:
    """A pre-signed URL is a third party. The credential stays home."""

    fake = FakeRunPod()

    run(gpu_client(fake).fetch_bytes("https://cdn.example.test/results/job-1.png"))

    assert fake.calls[-1].headers == {}


def test_an_empty_or_malformed_result_reference_is_an_error() -> None:
    client = gpu_client(FakeRunPod())

    with pytest.raises(GpuClientError, match="empty result reference"):
        run(client.fetch_bytes(""))
    with pytest.raises(GpuClientError, match="not base64"):
        run(client.fetch_bytes("!!! not base64 !!!"))


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


def test_health_reports_workers_and_a_measured_latency() -> None:
    fake = FakeRunPod()
    clock = FakeClock()
    client = gpu_client(fake, clock)

    probe = run(client.health())

    assert probe["available"] is True
    assert probe["reason"] is None
    assert probe["workers"] == {"ready": 2, "running": 1}
    assert probe["jobs"] == {"inQueue": 0}
    assert probe["latency_ms"] >= 0.0
    assert fake.calls[0].timeout == 5.0, "the probe uses its own short deadline"


def test_health_never_raises_when_the_cluster_is_down() -> None:
    fake = FakeRunPod(failures=[0, 0, 0])

    probe = run(gpu_client(fake).health())

    assert probe["available"] is False
    assert "connection reset" in probe["reason"]


def test_the_health_probe_does_not_retry() -> None:
    """Three retries would turn a 5s readiness deadline into a 15s one."""

    fake = FakeRunPod(failures=[503, 503, 503])

    probe = run(gpu_client(fake).health())

    assert probe["available"] is False
    assert len(fake.calls) == 1, "one attempt; whoever polls readiness retries by polling"


def test_the_health_attempt_budget_is_one() -> None:
    assert HEALTH_ATTEMPTS == 1


def test_health_on_an_unconfigured_client_names_the_variables() -> None:
    probe = run(gpu_client(FakeRunPod(), api_key="", endpoint="").health())

    assert probe["available"] is False
    assert "BROBOND_RUNPOD_API_KEY" in probe["reason"]


def test_health_tolerates_a_payload_without_worker_blocks() -> None:
    fake = FakeRunPod(health_payload={})

    probe = run(gpu_client(fake).health())

    assert probe["available"] is True
    assert probe["workers"] == {}
    assert probe["jobs"] == {}


# ---------------------------------------------------------------------------
# Response object, sync bridge and default transport
# ---------------------------------------------------------------------------


def test_the_response_object_exposes_ok_payload_and_error_text() -> None:
    assert GpuResponse(200).ok is True
    assert GpuResponse(500).ok is False
    assert GpuResponse(200, json=None).payload() == {}
    assert GpuResponse(400, json={"error": "bad prompt"}).error_message() == "bad prompt"
    assert GpuResponse(400, json={"message": "nope"}).error_message() == "nope"
    assert GpuResponse(400, json={"detail": "x"}).error_message() == "{'detail': 'x'}"
    assert GpuResponse(500, content=b"gateway down").error_message() == "gateway down"


def test_run_sync_bridges_the_async_client_from_synchronous_code() -> None:
    fake = FakeRunPod(polls_before_done=0)
    client = gpu_client(fake)

    result = run_sync(client.run({"prompt": "x"}))

    assert result.succeeded


def test_run_sync_works_inside_a_running_event_loop() -> None:
    """`asyncio.run` refuses to nest, so the bridge uses a worker thread."""

    fake = FakeRunPod(polls_before_done=0)
    client = gpu_client(fake)

    async def inside_a_loop():
        return run_sync(client.run({"prompt": "x"}))

    assert asyncio.run(inside_a_loop()).succeeded


def test_run_sync_propagates_the_error_from_the_worker_thread() -> None:
    client = gpu_client(FakeRunPod(), api_key="", endpoint="")

    async def inside_a_loop():
        return run_sync(client.request("GET", "health"))

    with pytest.raises(GpuNotConfigured):
        asyncio.run(inside_a_loop())


def test_closing_client_releases_the_transport() -> None:
    fake = FakeRunPod()
    with closing_client(gpu_client(fake)) as client:
        assert client.configured
    assert getattr(fake, "closed", False) is True


def test_aclose_is_idempotent_on_the_default_transport() -> None:
    transport = HttpxTransport()

    run(transport.aclose())  # nothing was ever created; this must not raise

    assert transport._client is None


def test_the_default_transport_maps_httpx_onto_the_gpu_response(monkeypatch) -> None:
    """The one place `httpx` is touched, exercised without a network."""

    class FakeHttpxResponse:
        status_code = 200
        content = b'{"id": "job-7"}'

        def json(self):
            return {"id": "job-7"}

    class FakeAsyncClient:
        def __init__(self) -> None:
            self.closed = False
            self.seen: dict = {}

        async def request(self, method, url, json=None, headers=None, timeout=None):
            self.seen = {"method": method, "url": url, "json": json, "headers": headers, "timeout": timeout}
            return FakeHttpxResponse()

        async def aclose(self):
            self.closed = True

    transport = HttpxTransport()
    client = FakeAsyncClient()
    transport._client = client

    response = run(transport.request("POST", "https://example.test/run", json={"input": {}}, timeout=9.0))

    assert response.status_code == 200
    assert response.json == {"id": "job-7"}
    assert client.seen["timeout"] == 9.0
    run(transport.aclose())
    assert client.closed is True


def test_the_default_transport_survives_a_non_json_body() -> None:
    class Binary:
        status_code = 200
        content = PIXEL_PNG_BYTES

        def json(self):
            raise ValueError("not json")

    class Client:
        async def request(self, *args, **kwargs):
            return Binary()

        async def aclose(self):
            return None

    transport = HttpxTransport()
    transport._client = Client()

    response = run(transport.request("GET", "https://cdn.example.test/x.png"))

    assert response.json is None
    assert response.content == PIXEL_PNG_BYTES
    assert response.payload() == {}


def test_the_default_transport_wraps_every_network_failure() -> None:
    class Exploding:
        async def request(self, *args, **kwargs):
            raise OSError("no route to host")

        async def aclose(self):
            return None

    transport = HttpxTransport()
    transport._client = Exploding()

    with pytest.raises(GpuTransportError, match="no route to host"):
        run(transport.request("GET", "https://api.runpod.ai/v2/x/health?token=secret"))


def test_the_transport_error_message_never_echoes_a_query_string() -> None:
    class Exploding:
        async def request(self, *args, **kwargs):
            raise OSError("boom")

        async def aclose(self):
            return None

    transport = HttpxTransport()
    transport._client = Exploding()

    with pytest.raises(GpuTransportError) as error:
        run(transport.request("GET", "https://api.runpod.ai/v2/x/health?token=super-secret"))

    assert "super-secret" not in str(error.value)


def test_the_safe_url_helper_copes_with_a_url_that_has_no_host() -> None:
    """Defensive: an error message must never become the thing that crashes."""

    from app.providers.gpu_client import _safe_url

    assert _safe_url("/status/job-1?token=secret") == "/status/job-1"
    assert _safe_url("not a url") == "not a url"
    assert _safe_url("https://api.runpod.ai/v2/id/run?x=1") == "https://api.runpod.ai"


def test_a_non_dict_json_body_is_wrapped_rather_than_dropped() -> None:
    class ListBody:
        status_code = 200
        content = b"[1, 2]"

        def json(self):
            return [1, 2]

    class Client:
        async def request(self, *args, **kwargs):
            return ListBody()

        async def aclose(self):
            return None

    transport = HttpxTransport()
    transport._client = Client()

    assert run(transport.request("GET", "https://x.test")).json == {"data": [1, 2]}
