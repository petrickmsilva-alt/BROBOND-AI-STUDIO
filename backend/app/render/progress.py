"""PR008 — Progress Engine: push-based render events, no polling.

Events (ETAPA 4), in lifecycle order:

```text
batch_started -> scene_started -> scene_progress -> scene_completed
             ... per scene ... -> batch_completed
```

Failures and cancellations are expressed through the payload (`status` /
`error` on `scene_completed` / `batch_completed`), not through extra event
names, so a client handles exactly five event types.

Delivery is a push: the orchestrator publishes into per-batch subscriber
queues and the WebSocket route awaits them. History is buffered so a client
that connects late replays what it missed and still ends on the terminal
event.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

EVENT_BATCH_STARTED = "batch_started"
EVENT_SCENE_STARTED = "scene_started"
EVENT_SCENE_PROGRESS = "scene_progress"
EVENT_SCENE_COMPLETED = "scene_completed"
EVENT_BATCH_COMPLETED = "batch_completed"

RENDER_EVENTS: tuple[str, ...] = (
    EVENT_BATCH_STARTED,
    EVENT_SCENE_STARTED,
    EVENT_SCENE_PROGRESS,
    EVENT_SCENE_COMPLETED,
    EVENT_BATCH_COMPLETED,
)

#: Terminal event: after it, nothing further will happen to the batch.
TERMINAL_RENDER_EVENT = EVENT_BATCH_COMPLETED

#: Bounded like the queue hub's buffer, for the same reason.
RENDER_EVENT_BUFFER_SIZE = 256


def render_event(
    batch_id: str,
    event: str,
    *,
    scene_id: str | None = None,
    scene_number: int | None = None,
    status: str | None = None,
    progress: int | None = None,
    eta_seconds: float | None = None,
    error: str | None = None,
    asset: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One render event payload. Fixed keys; optional keys only when set."""

    if event not in RENDER_EVENTS:
        raise ValueError(f"unknown render event: {event}")
    payload: dict[str, Any] = {
        "batch_id": batch_id,
        "event": event,
        "at": datetime.now(UTC).isoformat(),
    }
    if scene_id is not None:
        payload["scene_id"] = scene_id
    if scene_number is not None:
        payload["scene_number"] = scene_number
    if status is not None:
        payload["status"] = status
    if progress is not None:
        payload["progress"] = int(progress)
    if eta_seconds is not None:
        payload["eta_seconds"] = float(eta_seconds)
    if error is not None:
        payload["error"] = error
    if asset is not None:
        payload["asset"] = dict(asset)
    if job is not None:
        payload["job"] = dict(job)
    return payload


class RenderProgressHub:
    """Push hub for render batches: subscribers await, publishers never block."""

    def __init__(self) -> None:
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=RENDER_EVENT_BUFFER_SIZE))
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def publish(self, batch_id: str, event: dict[str, Any]) -> dict[str, Any]:
        """Record for replay and push to every live subscriber.

        Sync-safe and thread-safe: a publisher on another thread than the
        subscriber's loop wakes that loop instead of touching the queue
        directly, so cross-thread publishes are delivered, not dropped.
        """

        self._history[batch_id].append(event)
        for queue in list(self._subscribers.get(batch_id, set())):
            self._deliver(queue, event)
        return event

    @staticmethod
    def _deliver(queue: asyncio.Queue, event: dict[str, Any]) -> None:
        owner = getattr(queue, "_loop", None)
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if owner is not None and owner is not current:
            owner.call_soon_threadsafe(queue.put_nowait, event)
        else:
            queue.put_nowait(event)

    def history(self, batch_id: str, after: int = 0) -> list[dict[str, Any]]:
        return list(self._history.get(batch_id, ())) [after:]

    def subscribe(self, batch_id: str) -> asyncio.Queue:
        """A queue that receives every future event for the batch (push)."""

        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[batch_id].add(queue)
        return queue

    def unsubscribe(self, batch_id: str, queue: asyncio.Queue) -> None:
        self._subscribers.get(batch_id, set()).discard(queue)
        if batch_id in self._subscribers and not self._subscribers[batch_id]:
            del self._subscribers[batch_id]

    def subscriber_count(self, batch_id: str) -> int:
        return len(self._subscribers.get(batch_id, set()))

    def forget(self, batch_id: str) -> None:
        self._history.pop(batch_id, None)

    def clear(self) -> None:
        """Test-only reset."""

        self._history.clear()
        self._subscribers.clear()


#: Composition-root singleton, mirroring `events.hub`.
render_hub = RenderProgressHub()
