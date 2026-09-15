"""Job and persona facade (Legacy surface, alive by delegation).

PR002. Jobs used to live in a process-local dict: a Celery worker in another
process could never find the job the API had just created, and every deploy
silently dropped the queue (AUDIT.md P0-2b). Jobs now persist as `JobRow`s.

PR004-prep (Repository Pattern directive): this module no longer depends on
PostgreSQL directly. `JobStore` keeps its historical surface
(`store.add_job`, `store.get_job`, `store.set_job_state`, `store.list_jobs`)
for the call sites that still use it — the backend behind the name is now
the Core's `JobService` and its injected `JobRepository`. The PostgreSQL
dependency lives in `repositories.postgres_job_repository`, the only job
module that imports SQLAlchemy.

Personas: the in-memory dict is Legacy since PR003 (the Persona Memory
Engine persists through `repositories.persona_repository`).
"""
from __future__ import annotations

from uuid import UUID

from .job_service import job_service
from .jobs import to_api_job, to_core_job
from .schemas import Job, JobStatus, Persona


class JobStore:
    """Legacy job facade — delegates to the Core's `JobService` (PR004-prep).

    The historical surface is preserved (tests and call sites from earlier
    PRs use it), but the PostgreSQL dependency is gone from this module:
    every call goes through `JobService` and its injected `JobRepository`
    (default: `PostgresJobRepository`, the `jobs` table). All writes still
    reach the shared table, so a worker process and an API process read and
    write the same truth.
    """

    def add_job(self, job: Job) -> Job:
        job_service.create(to_core_job(job))
        return job

    def get_job(self, job_id: UUID | str) -> Job | None:
        core_job = job_service.get(str(job_id))
        return to_api_job(core_job) if core_job is not None else None

    def list_jobs(self, workspace_id: str | None = None) -> list[Job]:
        if workspace_id is not None:
            return [to_api_job(core_job) for core_job in job_service.list_by_workspace(workspace_id)]
        # The unscoped listing is not part of the JobRepository interface:
        # an unfiltered job list is a cross-tenant enumeration vector. The
        # pre-refactor call site that used to reach this case (a user without
        # a workspace) now lists nothing, on purpose.
        return []

    def set_state(self, job_id: UUID | str, *, status: JobStatus | None = None, progress: int | None = None, output_url: str | None = None) -> None:
        """Persist a state change for an existing job.

        Called only from `queue.transition()` — the single point where a job
        moves — so persisting and emitting the event stay one step apart.
        `output_url` participates because the worker assigns it between
        transitions and the next transition is what carries it.
        """

        job_service.transition(
            str(job_id),
            status=status.value if status is not None else None,
            progress=progress,
            output_url=output_url,
        )


#: Persona state that PR004 will move into a table. Kept in memory on purpose:
#: this file already had this dict before PR002, and the standing rule is to
#: evolve, not recreate.
class _PersonaMemory:
    def __init__(self) -> None:
        self.personas: dict[UUID, Persona] = {}

    def add_persona(self, persona: Persona) -> Persona:
        self.personas[persona.id] = persona
        return persona


class Store:
    """The pre-PR002 `store` surface, with jobs now backed by PostgreSQL."""

    def __init__(self) -> None:
        self._jobs = JobStore()
        self._personas = _PersonaMemory()

    # jobs — delegated to the SQL repository
    def add_job(self, job: Job) -> Job:
        return self._jobs.add_job(job)

    def get_job(self, job_id: UUID | str) -> Job | None:
        return self._jobs.get_job(job_id)

    def list_jobs(self, workspace_id: str | None = None) -> list[Job]:
        return self._jobs.list_jobs(workspace_id)

    def set_job_state(self, job_id: UUID | str, *, status: JobStatus | None = None, progress: int | None = None, output_url: str | None = None) -> None:
        self._jobs.set_state(job_id, status=status, progress=progress, output_url=output_url)

    # personas — Legacy since PR003: the Persona Memory Engine persists to
    # PostgreSQL through `repositories.persona_repository`. Kept (never
    # deleted, Bible §2) with no call sites; new code must not use it.
    @property
    def personas(self) -> dict[UUID, Persona]:
        return self._personas.personas

    def add_persona(self, persona: Persona) -> Persona:
        return self._personas.add_persona(persona)


store = Store()
