"""In-process WebSocket event hub for queue updates.

ETAPA 11. `EventHub.publish` existed since the beginning of this repository and
had **zero callers** — measured, not inferred. The consequence was visible end
to end: a job went from `queued`/0% to `complete`/100% while a connected
WebSocket client received nothing at all, because the route sent one snapshot on
connect and then blocked in `await websocket.receive_text()` forever.

Two things had to change, and both are structural rather than cosmetic:

1. **State changes emit.** `queue.transition()` is now the only place a job's
   status or progress is written, and it always emits. It is no longer possible
   to move a job without telling anyone.
2. **The hub is callable from sync code.** A Celery task has no event loop, so
   `await hub.publish(...)` was never going to work from the worker. `publish_sync`
   records the event unconditionally and dispatches to live clients when a loop
   is available.

Honest limitation, stated rather than hidden: this hub is **in-process**. A
Celery worker is a separate process, so events it emits are not visible to the
API process that holds the WebSockets. Closing that gap needs a shared broker
(Redis pub/sub) — see `ETAPA11_REPORT.md`. What this module guarantees is that
every transition is recorded and that a client in the same process sees it.
"""
import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from uuid import UUID

from fastapi import WebSocket

#: How many events are kept per job for replay. Bounded so a long-running
#: process does not grow without limit.
EVENT_BUFFER_SIZE = 64

#: Event names a client can expect. Declared so the payload is a contract
#: rather than whatever the worker happened to build that day.
EVENT_QUEUED = "queued"
EVENT_STARTED = "started"
EVENT_PROGRESS = "progress"
EVENT_COMPLETE = "complete"
EVENT_FAILED = "failed"
EVENT_CANCELLED = "cancelled"

JOB_EVENTS: tuple[str, ...] = (
    EVENT_QUEUED,
    EVENT_STARTED,
    EVENT_PROGRESS,
    EVENT_COMPLETE,
    EVENT_FAILED,
    EVENT_CANCELLED,
)

#: Statuses after which nothing further will happen to a job.
TERMINAL_STATUSES: frozenset[str] = frozenset({"complete", "failed", "cancelled"})


def job_event(
    job_id: UUID | str,
    *,
    status: str,
    progress: int,
    event: str,
    output_url: str | None = None,
    error: str | None = None,
) -> dict:
    """Build a job event payload.

    One shape, one place. A client can rely on these keys existing, and the
    `event` key distinguishes a progress tick from a terminal transition — which
    a bare status cannot, because `complete` is both a status and an event.
    """

    payload = {
        "job_id": str(job_id),
        "event": event,
        "status": status,
        "progress": int(progress),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if output_url is not None:
        payload["output_url"] = output_url
    if error is not None:
        payload["error"] = error
    return payload


class EventHub:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()
        #: Recent events per job, so a client that connects after a transition
        #: still learns about it. Bounded to `EVENT_BUFFER_SIZE`.
        self.events: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=EVENT_BUFFER_SIZE))

    async def connect(self, job_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.connections[str(job_id)].add(websocket)

    async def disconnect(self, job_id: UUID, websocket: WebSocket) -> None:
        async with self.lock:
            self.connections[str(job_id)].discard(websocket)

    # ------------------------------------------------------------------ events

    def record(self, job_id: UUID | str, payload: dict) -> dict:
        """Store an event for replay. Sync-safe: touches no event loop.

        Returns the payload so a caller can both record and return it.
        """

        self.events[str(job_id)].append(payload)
        return payload

    def history(self, job_id: UUID | str, after: int = 0) -> list[dict]:
        """Events recorded for a job, from index `after` onwards."""

        return list(self.events[str(job_id)])[after:]

    def forget(self, job_id: UUID | str) -> None:
        """Drop buffered events. Called once a job is terminal and drained."""

        self.events.pop(str(job_id), None)

    async def publish(self, job_id: UUID, payload: dict) -> None:
        """Send to every client watching this job, and keep it for replay."""

        self.record(job_id, payload)
        async with self.lock:
            clients = list(self.connections.get(str(job_id), set()))
        for client in clients:
            try:
                await client.send_text(json.dumps(payload))
            except Exception:
                await self.disconnect(job_id, client)

    def publish_sync(self, job_id: UUID | str, payload: dict) -> dict:
        """Record an event and dispatch it if an event loop can take it.

        A Celery task runs with no running loop, so `await hub.publish(...)` is
        not available there. Recording is unconditional — that is what makes the
        transition visible to a client in this process. Dispatch is best effort.
        """

        self.record(job_id, payload)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return payload
        loop.create_task(self.publish(job_id, payload))
        return payload

    # ------------------------------------------------------------------- stats

    def stats(self) -> dict[str, int]:
        """How many clients are connected, and for how many jobs."""

        return {
            "connections": sum(len(clients) for clients in self.connections.values()),
            "jobs_watched": len([job for job, clients in self.connections.items() if clients]),
            "events_buffered": sum(len(buffer) for buffer in self.events.values()),
        }


hub = EventHub()
