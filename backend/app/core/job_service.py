"""Job lifecycle — the Core's view of a job (PR004-prep).

Repository Pattern directive: the job flow must not depend on PostgreSQL.
This module is the business core of the job lifecycle and knows exactly one
thing: the `JobRepository` interface (structural — the concrete provider is
injected). It never imports a provider (Postgres, Redis or memory), never
imports SQLAlchemy, and never touches the database.

Layers, in dependency order:

    JobService (core)        business rules: state machine, validation
        |
        |  calls through the interface only
        v
    JobRepository (protocol) repositories/job_repository.py
        |
        +-- PostgresJobRepository   (default; the jobs table)
        +-- RedisJobRepository      (opt-in; JSON documents)
        +-- MemoryJobRepository     (tests; isolated, no I/O)

The `Job` here is a plain value object: the API's pydantic `Job` is mapped
to it at the application boundary (`app/jobs.py`), so nothing in this module
requires FastAPI or Pydantic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # the interface is a type hint only — no runtime coupling
    from ..repositories.job_repository import JobRepository


#: The `Job` value object that crosses the Core boundary.
@dataclass
class Job:
    id: str
    type: str
    status: str = "queued"
    prompt: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    progress: int = 0
    output_url: str | None = None
    created_at: datetime | None = None


class InvalidJobTransition(Exception):
    """Raised when a job is moved to a state the state machine forbids.

    The permitted set is exactly the vocabulary the product uses (queued,
    running, complete, failed, cancelled); the external `completed` spelling
    stays a boundary concern of the API layer, as it has always been.
    """


#: The only states a job may be in (Bible §14 vocabulary, internal spelling).
JOB_STATUSES = ("queued", "running", "complete", "failed", "cancelled")

#: Terminal states: a job that reached one never changes status again.
JOB_TERMINAL_STATUSES = frozenset({"complete", "failed", "cancelled"})

#: The state machine. `queued` may go straight to `complete` (the
#: orchestration-only worker path), to `failed` (it never ran) or to
#: `cancelled` (the cancel route). `running` may finish, fail or be
#: cancelled. Terminal states accept no status change — progress-only ticks
#: are always allowed, because a tick carries no status.
JOB_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "complete", "failed", "cancelled"}),
    "running": frozenset({"complete", "failed", "cancelled"}),
    "complete": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


class JobService:
    """The job lifecycle rules, over any `JobRepository` (dependency injection).

    This is the only component allowed to decide *how* a job may move. The
    repository is a passive provider: it stores what it is told. Swapping
    PostgreSQL for Redis (or memory, in tests) is a one-line change at the
    composition root — this module never changes.
    """

    def __init__(self, repository: "JobRepository") -> None:
        self._repository = repository

    # ---------------------------------------------------------------- reads

    def get(self, job_id: str | int) -> Job | None:
        return self._repository.get(str(job_id))

    def list_by_workspace(self, workspace_id: str) -> list[Job]:
        return self._repository.list_by_workspace(workspace_id)

    # --------------------------------------------------------------- writes

    def create(self, job: Job) -> Job:
        """Persist a new job. The status must already be a known state."""

        if job.status not in JOB_TRANSITIONS:
            raise ValueError(f"unknown job status: {job.status!r}")
        return self._repository.create(job)

    def update(self, job_id: str | int, *, progress: int | None = None, output_url: str | None = None) -> Job | None:
        """Update job metadata without touching the status.

        Used for output_url assignments between transitions (the worker
        assigns the URL and the next transition carries it).
        """

        return self._repository.update(str(job_id), progress=progress, output_url=output_url)

    def transition(
        self,
        job_id: str | int,
        *,
        status: str | None = None,
        progress: int | None = None,
        output_url: str | None = None,
    ) -> Job | None:
        """Move a job to a new status/progress, validating the state machine.

        Returns the stored job after the move, or None when the job does not
        exist (the caller decides how to react — today the worker and the
        routes both treat a vanished job as "nothing to move"). Raising
        `InvalidJobTransition` for a forbidden status change makes a bad
        move impossible to persist silently.
        """

        current = self._repository.get(str(job_id))
        if current is None:
            return None
        if status is not None and status != current.status:
            if status not in JOB_TRANSITIONS:
                raise ValueError(f"unknown job status: {status!r}")
            if status not in JOB_TRANSITIONS[current.status]:
                raise InvalidJobTransition(f"job {job_id} cannot move {current.status!r} -> {status!r}")
        return self._repository.transition(str(job_id), status=status, progress=progress, output_url=output_url)

    def delete(self, job_id: str | int) -> bool:
        return self._repository.delete(str(job_id))
