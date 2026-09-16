"""ETAPA 11 tests — queue lifecycle events over WebSocket.

`EventHub.publish` existed since the beginning of the repository and had zero
callers. A connected client received one snapshot on connect and then nothing,
however the job progressed. These tests pin the fix: state changes emit, and the
route pushes.
"""
from __future__ import annotations

import ast
import pathlib
import threading
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.events import (
    EVENT_BUFFER_SIZE,
    EVENT_COMPLETE,
    EVENT_FAILED,
    EVENT_STARTED,
    JOB_EVENTS,
    TERMINAL_STATUSES,
    EventHub,
    hub,
    job_event,
)
from app.main import app
from app.models import User, Workspace
from app.providers.base_provider import ProviderUnsupported
from app.schemas import GenerationType, Job, JobStatus
from app.store import store


@pytest.fixture(autouse=True)
def clean_hub():
    """The hub is a module singleton; a leaked buffer would cross tests."""

    hub.events.clear()
    hub.connections.clear()
    yield
    hub.events.clear()
    hub.connections.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def orchestration_only(monkeypatch):
    """No GPU here, so the worker completes without inference."""

    monkeypatch.setattr(settings, "inference_enabled", False)
    monkeypatch.setattr(settings, "storage_enabled", False)
    return settings


def _register(client: TestClient) -> str:
    """Create a real user (and their workspace) and return the bearer token.

    PR002: the queue events socket authenticates through the `token` query
    parameter and only streams jobs the caller's workspace owns, so the socket
    tests need a genuine tenant rather than a bare job.
    """

    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"queue-{uuid4()}@example.com", "name": "Queue Test", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _job_for_token(token: str, prompt: str = "x") -> Job:
    """A job owned by the tenant that issued `token`."""

    import jwt as pyjwt

    from app.core.config import settings as _settings

    with SessionLocal() as db:
        user_id = pyjwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])["sub"]
        user = db.get(User, user_id)
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
        job = store.add_job(Job(type=GenerationType.IMAGE, prompt=prompt, parameters={"workspace_id": workspace.id}))
    return job


class _Reader:
    """One reader thread per socket, started once.

    Starting a fresh reader per assertion was the first draft's mistake: two
    threads competing for the same socket lose messages and can wedge the test
    client's portal, which is what made the suite hang instead of fail.
    """

    def __init__(self, websocket) -> None:
        self.messages: list = []
        self.closed = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(websocket,), daemon=True)
        self._thread.start()

    def _run(self, websocket) -> None:
        try:
            while True:
                self.messages.append(websocket.receive_json())
        except Exception:  # noqa: BLE001 - the socket closing is the exit signal
            pass
        finally:
            self.closed.set()

    def settle(self, seconds: float = 0.6) -> "_Reader":
        """Wait for the server to close the socket, or give up.

        With the in-process TestClient a server-initiated close is not
        observable from the reader (see
        `test_the_route_exits_after_a_terminal_event`), so this budget is a
        lower bound, not a signal — message delivery is asserted with
        `wait_for`, which polls the messages directly.
        """

        self.closed.wait(timeout=seconds)
        return self

    def wait_for(self, predicate, timeout: float = 5.0) -> "_Reader":
        """Poll until `predicate(self.messages)` holds, the socket closes,
        or the budget runs out.

        Message delivery is asserted on the messages, not on the close:
        under load the two no longer arrive in lockstep, and coupling the
        assertions to the close is what flaked the suite.
        """

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(self.messages):
                return self
            if self.closed.is_set():
                break
            time.sleep(0.02)
        return self

    def labels(self) -> list[str]:
        return [m.get("event", "snapshot") for m in self.messages if isinstance(m, dict)]


# ---------------------------------------------------------------------------
# The event payload is a contract
# ---------------------------------------------------------------------------


def test_every_event_carries_the_same_keys() -> None:
    payload = job_event("id-1", status="running", progress=25, event="progress")
    assert set(payload) == {"job_id", "event", "status", "progress", "at"}


def test_optional_fields_appear_only_when_they_mean_something() -> None:
    bare = job_event("id-1", status="running", progress=10, event="progress")
    assert "output_url" not in bare
    assert "error" not in bare

    rich = job_event("id-1", status="failed", progress=10, event="failed", error="boom")
    assert rich["error"] == "boom"


def test_the_event_names_are_declared() -> None:
    assert JOB_EVENTS == (
        "queued", "started", "progress", "complete", "failed", "cancelled",
    )


def test_terminal_statuses_are_the_ones_that_end_the_stream() -> None:
    assert TERMINAL_STATUSES == {"complete", "failed", "cancelled"}
    for status in JobStatus:
        assert (status.value in TERMINAL_STATUSES) == (
            status in {JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED}
        )


# ---------------------------------------------------------------------------
# The hub
# ---------------------------------------------------------------------------


def test_publish_sync_records_even_with_no_event_loop() -> None:
    """A Celery task has no loop; recording must still happen."""

    local = EventHub()
    payload = job_event("j", status="running", progress=10, event="started")
    local.publish_sync("j", payload)
    assert local.history("j") == [payload]


def test_publish_sync_dispatches_when_a_loop_is_running() -> None:
    import asyncio

    local = EventHub()
    sent: list[dict] = []

    class FakeSocket:
        async def send_text(self, text: str) -> None:
            import json

            sent.append(json.loads(text))

    async def scenario() -> None:
        socket = FakeSocket()
        local.connections["j"].add(socket)  # type: ignore[arg-type]
        local.publish_sync("j", job_event("j", status="running", progress=10, event="started"))
        await asyncio.sleep(0.01)

    asyncio.run(scenario())
    assert len(sent) == 1
    assert sent[0]["event"] == "started"


def test_history_honours_the_cursor() -> None:
    local = EventHub()
    for progress in (10, 25, 40):
        local.record("j", job_event("j", status="running", progress=progress, event="progress"))
    assert [e["progress"] for e in local.history("j")] == [10, 25, 40]
    assert [e["progress"] for e in local.history("j", after=2)] == [40]


def test_the_buffer_is_bounded() -> None:
    local = EventHub()
    for index in range(EVENT_BUFFER_SIZE + 20):
        local.record("j", job_event("j", status="running", progress=index, event="progress"))
    assert len(local.history("j")) == EVENT_BUFFER_SIZE


def test_forget_clears_a_finished_job() -> None:
    local = EventHub()
    local.record("j", job_event("j", status="complete", progress=100, event="complete"))
    local.forget("j")
    assert local.history("j") == []


def test_a_dead_client_is_dropped_without_breaking_the_others() -> None:
    """A socket that vanished mid-job must not stop the remaining clients."""

    import asyncio

    local = EventHub()
    delivered: list[dict] = []

    class DeadSocket:
        async def send_text(self, text: str) -> None:
            raise RuntimeError("connection closed by peer")

    class LiveSocket:
        async def send_text(self, text: str) -> None:
            import json

            delivered.append(json.loads(text))

    async def scenario() -> None:
        dead, live = DeadSocket(), LiveSocket()
        local.connections["j"].add(dead)  # type: ignore[arg-type]
        local.connections["j"].add(live)  # type: ignore[arg-type]
        await local.publish("j", job_event("j", status="running", progress=10, event="started"))
        assert dead not in local.connections["j"], "the dead client was left registered"

    asyncio.run(scenario())
    assert len(delivered) == 1, "the surviving client still got the event"


def test_stats_report_connections_and_buffer() -> None:
    local = EventHub()
    local.record("j", job_event("j", status="running", progress=10, event="started"))
    stats = local.stats()
    assert stats["events_buffered"] == 1
    assert stats["jobs_watched"] == 0


# ---------------------------------------------------------------------------
# transition() is the only place a job moves
# ---------------------------------------------------------------------------


def test_the_worker_never_writes_job_state_directly() -> None:
    """Structural guard: a direct assignment is how events got lost."""

    source = pathlib.Path("backend/app/queue.py").read_text()
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name == "transition":
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "job"
                        and target.attr in {"status", "progress"}
                    ):
                        offenders.append(f"{node.name}:{child.lineno}")
    assert not offenders, f"job state written outside transition(): {offenders}"


def test_transition_emits_and_mutates_together() -> None:
    from app.queue import transition

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    payload = transition(job, JobStatus.RUNNING, 25, event=EVENT_STARTED)

    assert job.status is JobStatus.RUNNING
    assert job.progress == 25
    assert payload["event"] == "started"
    assert payload["progress"] == 25
    assert hub.history(job.id)[-1] is payload


def test_a_progress_tick_does_not_have_to_restate_the_status() -> None:
    from app.queue import transition

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    transition(job, JobStatus.RUNNING, 10, event=EVENT_STARTED)
    transition(job, progress=55)

    assert job.status is JobStatus.RUNNING
    assert job.progress == 55
    assert hub.history(job.id)[-1]["status"] == "running"


def test_transition_carries_the_error_on_failure() -> None:
    from app.queue import transition

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    transition(job, JobStatus.FAILED, event=EVENT_FAILED, error="CUDA GPU is required")
    assert hub.history(job.id)[-1]["error"] == "CUDA GPU is required"


# ---------------------------------------------------------------------------
# The worker reports real milestones
# ---------------------------------------------------------------------------


def test_the_worker_no_longer_jumps_from_ten_to_a_hundred(
    client, orchestration_only, monkeypatch
) -> None:
    """The old worker emitted two states. A client could not render a progress bar."""

    import app.providers.image as image_module

    from app.providers.image import GenerationOutput

    seen: list[int] = []

    class RecordingFlux:
        def __init__(self, model_id: str = "x") -> None:
            pass

        def generate(self, spec, output_dir):
            seen.append(store.get_job(spec.spec_id) and 0 or 0)
            # ETAPA 14: the worker checks the artifact before completing, so the
            # fake has to produce one.
            target = pathlib.Path(output_dir)
            target.mkdir(parents=True, exist_ok=True)
            written = target / "out.png"
            written.write_bytes(b"\x89PNG fake")
            return GenerationOutput(str(written), 1024, 576)

    monkeypatch.setattr(image_module, "FluxDiffusersProvider", RecordingFlux)
    monkeypatch.setattr(settings, "inference_enabled", True)

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    from app.queue import process_generation

    result = process_generation(str(job.id))
    assert result["status"] == "complete", result

    progresses = [event["progress"] for event in hub.history(job.id)]
    assert len(set(progresses)) >= 4, progresses
    assert progresses[0] == 10
    assert progresses[-1] == 100
    assert progresses == sorted(progresses), "progress must never go backwards"


def test_a_failing_job_emits_failed_with_the_reason(client, monkeypatch) -> None:
    import app.providers.flux_provider as flux_module

    # PR009: a *fatal* provider error is the one thing the fallback chain
    # refuses to mask, so it is the honest way to drive a job to `failed`.
    def broken_generate(self, spec, output_dir):
        raise ProviderUnsupported("CUDA GPU is required")

    monkeypatch.setattr(flux_module.FluxProvider, "generate_image", broken_generate)
    monkeypatch.setattr(settings, "inference_enabled", True)
    monkeypatch.setattr(settings, "storage_enabled", False)

    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    from app.queue import process_generation

    result = process_generation(str(job.id))
    assert result["status"] == "failed"

    last = hub.history(job.id)[-1]
    assert last["event"] == "failed"
    assert last["error"] == "CUDA GPU is required"


def test_a_cancelled_job_emits_cancelled(client, orchestration_only) -> None:
    job = store.add_job(Job(type=GenerationType.IMAGE, prompt="x", parameters={}))
    # PR002: state lives in the row now, so the test cancels through the store
    # exactly like the cancel route does — not by mutating a stale copy.
    store.set_job_state(job.id, status=JobStatus.CANCELLED)
    from app.queue import process_generation

    assert process_generation(str(job.id))["status"] == "cancelled"
    assert hub.history(job.id)[-1]["event"] == "cancelled"


def test_an_unknown_job_does_not_emit_anything(client, orchestration_only) -> None:
    from app.queue import process_generation

    assert process_generation("00000000-0000-0000-0000-000000000000")["status"] == "cancelled"
    assert hub.stats()["events_buffered"] == 0


# ---------------------------------------------------------------------------
# The WebSocket route pushes
# ---------------------------------------------------------------------------


def test_a_connected_client_sees_the_job_finish(client, orchestration_only) -> None:
    """The defect, end to end: this used to receive one snapshot and hang."""

    token = _register(client)
    job = _job_for_token(token)
    with client.websocket_connect(f"/api/v1/queue/events/{job.id}?token={token}") as websocket:
        reader = _Reader(websocket)
        from app.queue import process_generation

        process_generation(str(job.id))
        reader.wait_for(lambda m: any(x.get("event") == "complete" for x in m))

    assert reader.labels()[0] == "snapshot"
    assert "started" in reader.labels()
    assert "complete" in reader.labels()
    # PR002: the wire says `completed`; the internal state stays `complete`.
    # `complete` is terminal: nothing may follow it on the wire.
    assert reader.messages[-1]["status"] == "completed"
    assert reader.messages[-1]["progress"] == 100


def test_the_terminal_event_is_sent_once(client, orchestration_only) -> None:
    """A first draft drained the buffer and then re-sent `complete`."""

    token = _register(client)
    job = _job_for_token(token)
    with client.websocket_connect(f"/api/v1/queue/events/{job.id}?token={token}") as websocket:
        reader = _Reader(websocket)
        from app.queue import process_generation

        process_generation(str(job.id))
        reader.wait_for(lambda m: any(x.get("event") == "complete" for x in m))
        time.sleep(0.2)  # a regressed duplicate would follow immediately

    assert reader.labels().count("complete") == 1


def test_a_client_that_connects_late_gets_the_history(client, orchestration_only) -> None:
    token = _register(client)
    job = _job_for_token(token)
    from app.queue import process_generation

    process_generation(str(job.id))
    assert hub.history(job.id), "the transitions were recorded"

    with client.websocket_connect(f"/api/v1/queue/events/{job.id}?token={token}") as websocket:
        reader = _Reader(websocket)
        reader.wait_for(lambda m: any(x.get("event") == "complete" for x in m))

    assert reader.labels()[0] == "snapshot"
    assert reader.messages[0]["status"] == "completed", "the client learns the current state first"
    assert "started" in reader.labels()
    assert "complete" in reader.labels()


def test_the_route_exits_after_a_terminal_event(client, orchestration_only) -> None:
    """A finished job must not leave the server looping forever.

    Asserted through the hub's connection count rather than through a client-side
    exception: `TestClient.receive_json` blocks on a server-initiated close
    instead of raising, so the reader thread is not a usable signal. The route
    disconnecting and freeing the buffer is the observable proof it returned.
    """

    token = _register(client)
    job = _job_for_token(token)
    with client.websocket_connect(f"/api/v1/queue/events/{job.id}?token={token}") as websocket:
        _Reader(websocket)
        time.sleep(0.1)
        assert hub.stats()["connections"] == 1, "the client was never registered"

        from app.queue import process_generation

        process_generation(str(job.id))
        for _ in range(50):
            if hub.stats()["connections"] == 0:
                break
            time.sleep(0.05)

    assert hub.stats()["connections"] == 0, "the route never exited"
    assert hub.history(job.id) == [], "the buffer was not freed"


def test_the_buffer_is_freed_once_a_client_is_done(client, orchestration_only) -> None:
    token = _register(client)
    job = _job_for_token(token)
    with client.websocket_connect(f"/api/v1/queue/events/{job.id}?token={token}") as websocket:
        reader = _Reader(websocket)
        from app.queue import process_generation

        process_generation(str(job.id))
        reader.wait_for(lambda m: any(x.get("event") == "complete" for x in m))
    # Exiting the with block disconnects the client, which ends the route and
    # frees the buffer.
    time.sleep(0.1)
    assert hub.history(job.id) == []


def test_an_unknown_job_is_refused_with_a_policy_violation(client) -> None:
    from starlette.websockets import WebSocketDisconnect

    token = _register(client)
    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(f"/api/v1/queue/events/00000000-0000-0000-0000-000000000000?token={token}"):
            pass
    assert raised.value.code == 1008


def test_an_unauthenticated_socket_is_refused_before_accept(client) -> None:
    """PR002: the token rides the query string; without it there is no stream."""

    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect("/api/v1/queue/events/00000000-0000-0000-0000-000000000000"):
            pass
    assert raised.value.code == 1008


def test_a_failure_reaches_the_client_with_its_reason(client, monkeypatch) -> None:
    import app.providers.flux_provider as flux_module

    def broken_generate(self, spec, output_dir):
        raise ProviderUnsupported("CUDA GPU is required")

    monkeypatch.setattr(flux_module.FluxProvider, "generate_image", broken_generate)
    monkeypatch.setattr(settings, "inference_enabled", True)
    monkeypatch.setattr(settings, "storage_enabled", False)

    token = _register(client)
    job = _job_for_token(token)
    with client.websocket_connect(f"/api/v1/queue/events/{job.id}?token={token}") as websocket:
        reader = _Reader(websocket)
        from app.queue import process_generation

        process_generation(str(job.id))
        reader.wait_for(lambda m: any(x.get("event") == "failed" for x in m))

    assert reader.messages[-1]["event"] == "failed"
    assert reader.messages[-1]["error"] == "CUDA GPU is required"


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_the_route_contains_no_lifecycle_logic_of_its_own() -> None:
    """It drains the hub; the worker owns the transitions."""

    tree = ast.parse(pathlib.Path("backend/app/main.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "queue_events":
            written = [
                child.attr
                for child in ast.walk(node)
                if isinstance(child, ast.Assign)
                for target in child.targets
                if isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "job"
            ]
            assert not written, f"the route writes job state: {written}"
            return
    raise AssertionError("queue_events is not defined")


def test_all_websockets_are_still_declared() -> None:
    from fastapi.routing import APIWebSocketRoute

    paths = {route.path for route in app.routes if isinstance(route, APIWebSocketRoute)}
    assert paths == {
        "/api/v1/queue/events/{job_id}",
        "/api/v1/personas/{persona_id}/training/events/{run_id}",
        # PR008: the render progress socket is a third declaration, not a
        # replacement — the queue and training sockets are untouched.
        "/ws/render/{batch_id}",
    }
