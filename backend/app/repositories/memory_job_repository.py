"""MemoryJobRepository — the job provider for tests (PR004-prep).

An isolated, in-memory implementation of `JobRepository`: no I/O, no shared
state between instances, no connection to set up or tear down. It exists so
the Core's `JobService` and the state machine can be tested against a
provider that is provably independent of PostgreSQL — the same reason the
Repository Pattern was introduced.

Each stored `Job` is a copy, so mutating the object handed back by the
repository never corrupts the store (with the SQL provider the row is the
truth; here the dict plays that role).
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime

from ..core.job_service import Job


class MemoryJobRepository:
    """JobRepository over a process-local dict. One instance = one database."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def _copy(self, job: Job) -> Job:
        return Job(
            id=job.id,
            type=job.type,
            status=job.status,
            prompt=job.prompt,
            parameters=copy.deepcopy(job.parameters),
            progress=job.progress,
            output_url=job.output_url,
            created_at=job.created_at,
        )

    def create(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = self._copy(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(str(job_id))
            return self._copy(job) if job else None

    def _apply(
        self,
        job_id: str,
        *,
        status: str | None,
        progress: int | None,
        output_url: str | None,
    ) -> Job | None:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if job is None:
                return None
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if output_url is not None:
                job.output_url = output_url
            return self._copy(job)

    def update(self, job_id: str, *, progress: int | None = None, output_url: str | None = None) -> Job | None:
        return self._apply(job_id, status=None, progress=progress, output_url=output_url)

    def transition(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        output_url: str | None = None,
    ) -> Job | None:
        return self._apply(job_id, status=status, progress=progress, output_url=output_url)

    def list_by_workspace(self, workspace_id: str) -> list[Job]:
        with self._lock:
            jobs = [
                self._copy(job)
                for job in self._jobs.values()
                if job.parameters.get("workspace_id") == workspace_id
            ]
        # created_at may be None (tests); fall back to a safe, stable order.
        jobs.sort(key=lambda job: (job.created_at or datetime.min, job.id), reverse=True)
        return jobs

    def delete(self, job_id: str) -> bool:
        with self._lock:
            return self._jobs.pop(str(job_id), None) is not None
