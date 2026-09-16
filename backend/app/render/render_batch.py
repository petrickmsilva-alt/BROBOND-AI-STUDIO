"""PR008 — RenderBatch: one storyboard rendered as independently tracked scenes.

A batch is the unit the Queue UI shows: it is created from a Director
`ProductionPlan` (or an edited `StoryboardState`), started once, and then
each scene moves on its own progress (0-100) while the batch aggregates.

States (ETAPA 3), in lifecycle order:

```text
queued -> running -> rendering -> completed
                            \\-> failed
queued/running/rendering ----> cancelled
```

`running` means the orchestrator took the batch; `rendering` means the first
scene reached the executor. The distinction matters to the Queue UI: a batch
can be accepted (`running`) before any GPU work starts (`rendering`).
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

PROGRESS_QUEUED = 0
PROGRESS_COMPLETE = 100


class RenderBatchStatus(str, Enum):
    """Lifecycle of a batch. Cancelled and failed are terminal, like completed."""

    QUEUED = "queued"
    RUNNING = "running"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RenderSceneStatus(str, Enum):
    """Lifecycle of one scene. Each scene moves independently of its siblings."""

    QUEUED = "queued"
    RUNNING = "running"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_BATCH_STATUSES: frozenset[str] = frozenset(
    {RenderBatchStatus.COMPLETED.value, RenderBatchStatus.FAILED.value, RenderBatchStatus.CANCELLED.value}
)

TERMINAL_SCENE_STATUSES: frozenset[str] = frozenset(
    {RenderSceneStatus.COMPLETED.value, RenderSceneStatus.FAILED.value, RenderSceneStatus.CANCELLED.value}
)

CANCELLABLE_BATCH_STATUSES: frozenset[str] = frozenset(
    {RenderBatchStatus.QUEUED.value, RenderBatchStatus.RUNNING.value, RenderBatchStatus.RENDERING.value}
)

#: Scenes a retry picks back up. Completed scenes are never re-rendered.
RETRYABLE_SCENE_STATUSES: frozenset[str] = frozenset(
    {RenderSceneStatus.FAILED.value, RenderSceneStatus.CANCELLED.value, RenderSceneStatus.QUEUED.value}
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class RenderScene:
    """One scene inside a batch, with its own progress and result."""

    scene_id: str
    scene_number: int
    title: str
    status: str = RenderSceneStatus.QUEUED.value
    progress: int = PROGRESS_QUEUED
    spec_id: str | None = None
    asset: dict[str, object] | None = None
    job: dict[str, object] | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def __post_init__(self) -> None:
        if not self.scene_id.strip():
            raise ValueError("scene_id is required")
        if self.scene_number < 1:
            raise ValueError("scene_number must be positive")
        if not self.title.strip():
            raise ValueError("title is required")
        self.progress = max(PROGRESS_QUEUED, min(PROGRESS_COMPLETE, int(self.progress)))

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_SCENE_STATUSES

    def mark_running(self) -> None:
        self.status = RenderSceneStatus.RUNNING.value
        self.started_at = self.started_at or _utcnow().isoformat()

    def mark_rendering(self, progress: int) -> None:
        self.status = RenderSceneStatus.RENDERING.value
        self.progress = max(PROGRESS_QUEUED, min(PROGRESS_COMPLETE, int(progress)))

    def mark_completed(self, *, asset: dict[str, object], job: dict[str, object], spec_id: str) -> None:
        self.status = RenderSceneStatus.COMPLETED.value
        self.progress = PROGRESS_COMPLETE
        self.asset = dict(asset)
        self.job = dict(job)
        self.spec_id = spec_id
        self.error = None
        self.finished_at = _utcnow().isoformat()

    def mark_failed(self, error: str) -> None:
        self.status = RenderSceneStatus.FAILED.value
        self.error = error or "render failed"
        self.finished_at = _utcnow().isoformat()

    def mark_cancelled(self) -> None:
        if self.is_terminal:
            return
        self.status = RenderSceneStatus.CANCELLED.value
        self.finished_at = _utcnow().isoformat()

    def reset_for_retry(self) -> None:
        self.status = RenderSceneStatus.QUEUED.value
        self.progress = PROGRESS_QUEUED
        self.error = None
        self.started_at = None
        self.finished_at = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RenderBatch:
    """A storyboard render: ordered scenes, aggregate progress, ETA."""

    batch_id: str
    workspace_id: str
    project_id: str
    kind: str
    provider: str
    scenes: list[RenderScene] = field(default_factory=list)
    status: str = RenderBatchStatus.QUEUED.value
    production_plan_id: str | None = None
    storyboard_version: int | None = None
    persona_id: str | None = None
    style: str = ""
    aspect_ratio: str = "16:9"
    fps: int = 24
    seed: int | None = None
    created_at: str = field(default_factory=lambda: _utcnow().isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    eta_seconds: float = 0.0
    cancel_requested: bool = False

    def __post_init__(self) -> None:
        if not self.batch_id.strip():
            raise ValueError("batch_id is required")
        if not self.workspace_id.strip():
            raise ValueError("workspace_id is required")
        if self.kind not in {"image", "video"}:
            raise ValueError("kind must be image or video")
        if not self.scenes:
            raise ValueError("scenes are required")

    # ------------------------------------------------------------ aggregates

    @property
    def scene_count(self) -> int:
        return len(self.scenes)

    @property
    def progress(self) -> int:
        """Mean of the independent scene progresses, rounded down."""

        # `__post_init__` guarantees at least one scene, so no empty guard.
        return int(sum(scene.progress for scene in self.scenes) / len(self.scenes))

    @property
    def completed_scenes(self) -> int:
        return sum(1 for scene in self.scenes if scene.status == RenderSceneStatus.COMPLETED.value)

    @property
    def failed_scenes(self) -> int:
        return sum(1 for scene in self.scenes if scene.status == RenderSceneStatus.FAILED.value)

    @property
    def current_scene(self) -> RenderScene | None:
        """First scene that still needs work, or None when all are terminal."""

        for scene in self.scenes:
            if not scene.is_terminal:
                return scene
        return None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_BATCH_STATUSES

    @property
    def is_cancellable(self) -> bool:
        return self.status in CANCELLABLE_BATCH_STATUSES

    # ----------------------------------------------------------- transitions

    def mark_running(self) -> None:
        self.status = RenderBatchStatus.RUNNING.value
        self.started_at = self.started_at or _utcnow().isoformat()

    def mark_rendering(self) -> None:
        if self.status == RenderBatchStatus.RUNNING.value:
            self.status = RenderBatchStatus.RENDERING.value

    def finish(self) -> None:
        """Terminal state from the scenes: any failure fails the batch."""

        if self.cancel_requested:
            self.status = RenderBatchStatus.CANCELLED.value
        elif any(scene.status == RenderSceneStatus.FAILED.value for scene in self.scenes):
            self.status = RenderBatchStatus.FAILED.value
        else:
            self.status = RenderBatchStatus.COMPLETED.value
        self.finished_at = _utcnow().isoformat()
        self.eta_seconds = 0.0

    def request_cancel(self) -> bool:
        """Ask the run loop to stop. Returns False when already terminal."""

        if not self.is_cancellable:
            return False
        self.cancel_requested = True
        for scene in self.scenes:
            if not scene.is_terminal and scene.status == RenderSceneStatus.QUEUED.value:
                scene.mark_cancelled()
        if self.status == RenderBatchStatus.QUEUED.value:
            self.status = RenderBatchStatus.CANCELLED.value
            self.finished_at = _utcnow().isoformat()
        return True

    def reset_for_retry(self) -> int:
        """Re-queue failed/cancelled scenes. Returns how many were reset."""

        reset = 0
        for scene in self.scenes:
            if scene.status in RETRYABLE_SCENE_STATUSES and scene.status != RenderSceneStatus.QUEUED.value:
                scene.reset_for_retry()
                reset += 1
        if reset:
            self.status = RenderBatchStatus.QUEUED.value
            self.finished_at = None
            self.cancel_requested = False
            self.eta_seconds = 0.0
        return reset

    def scene(self, scene_id: str) -> RenderScene | None:
        for item in self.scenes:
            if item.scene_id == scene_id:
                return item
        return None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["scenes"] = [scene.to_dict() for scene in self.scenes]
        payload["progress"] = self.progress
        payload["scene_count"] = self.scene_count
        payload["completed_scenes"] = self.completed_scenes
        payload["failed_scenes"] = self.failed_scenes
        current = self.current_scene
        payload["current_scene_id"] = current.scene_id if current else None
        payload["current_scene_number"] = current.scene_number if current else None
        return payload


class RenderBatchStore:
    """In-memory batch registry, shared by the routes, the orchestrator and the socket.

    Batches are orchestration state (like the queue's event buffer), not product
    rows: the durable artifacts are the Asset rows the pipeline writes. A restart
    drops queued batches, which is stated in docs/RENDER_ENGINE.md rather than
    hidden.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._batches: dict[str, RenderBatch] = {}

    def put(self, batch: RenderBatch) -> RenderBatch:
        with self._lock:
            self._batches[batch.batch_id] = batch
        return batch

    def get(self, batch_id: str) -> RenderBatch | None:
        with self._lock:
            return self._batches.get(batch_id)

    def get_for_workspace(self, batch_id: str, workspace_id: str) -> RenderBatch | None:
        batch = self.get(batch_id)
        if batch is None or batch.workspace_id != workspace_id:
            return None
        return batch

    def list_for_workspace(self, workspace_id: str) -> list[RenderBatch]:
        with self._lock:
            batches = [batch for batch in self._batches.values() if batch.workspace_id == workspace_id]
        return sorted(batches, key=lambda batch: batch.created_at, reverse=True)

    def new_id(self) -> str:
        return f"render_{uuid4().hex}"

    def clear(self) -> None:
        """Test-only reset. Production never drops batches except by restart."""

        with self._lock:
            self._batches.clear()


#: Composition-root singleton, mirroring `events.hub` and `storage.storage`.
render_store = RenderBatchStore()
