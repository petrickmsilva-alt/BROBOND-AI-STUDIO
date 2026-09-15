"""JobRepository — the interface the Core knows (PR004-prep).

Repository Pattern directive: the job flow separates business rules (Core),
persistence (this interface + its implementations) and the database
(provider). The Core's `JobService` depends only on this protocol — it never
imports `PostgresJobRepository`, `RedisJobRepository` or
`MemoryJobRepository`.

Implementations:

* `PostgresJobRepository` — the default; the `jobs` table (PR002 baseline).
* `RedisJobRepository` — opt-in; JSON documents, for a Redis-backed backend.
* `MemoryJobRepository` — tests; isolated, no I/O.

All methods take and return the Core's plain `Job` value object
(`app.core.job_service.Job`); storage specifics (rows, hashes, dicts) are
implementation details that never cross this boundary.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.job_service import Job


@runtime_checkable
class JobRepository(Protocol):
    """The six operations a job persistence backend must provide."""

    def create(self, job: Job) -> Job:
        """Persist a new job and return it."""
        ...

    def get(self, job_id: str) -> Job | None:
        """Return the job or None when it does not exist."""
        ...

    def update(self, job_id: str, *, progress: int | None = None, output_url: str | None = None) -> Job | None:
        """Update metadata (progress/output_url) without changing status."""
        ...

    def transition(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        output_url: str | None = None,
    ) -> Job | None:
        """Persist a state move. Status validation is the Service's job;
        the provider only writes what it is told."""
        ...

    def list_by_workspace(self, workspace_id: str) -> list[Job]:
        """All jobs of one workspace, newest first."""
        ...

    def delete(self, job_id: str) -> bool:
        """Remove a job. Returns False when it did not exist."""
        ...
