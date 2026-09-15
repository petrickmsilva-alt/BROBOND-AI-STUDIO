"""Job and persona repositories.

PR002. Jobs used to live in a process-local dict: a Celery worker in another
process could never find the job the API had just created, and every deploy
silently dropped the queue (AUDIT.md P0-2b). Jobs now persist as `JobRow`s —
this module is the repository the API and the worker both go through, so
there is exactly one way to read or write job state.

Personas intentionally remain in memory: persisting them is PR004's scope,
and the Core's `PersonaSource` protocol already makes that swap a one-line
injection. The `store` singleton keeps its pre-PR002 surface
(`store.add_job`, `store.get_job`, `store.add_persona`) so no call site or
test needed a rename — only the backend behind the name changed.
"""
from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select

from .db import SessionLocal
from .models import JobRow
from .schemas import GenerationType, Job, JobStatus, Persona


def _row_to_job(row: JobRow) -> Job:
    """Rebuild the API object from its row.

    `parameters` crosses the boundary as a JSON document; the spec adapter
    reads it field by field, so a new generation option added by the UI needs
    no schema change — only a reader in `spec_adapter`.
    """

    try:
        parameters = json.loads(row.parameters or "{}")
    except json.JSONDecodeError:  # pragma: no cover — rows are only written here
        parameters = {}
    return Job(
        id=UUID(row.id),
        type=GenerationType(row.type),
        status=JobStatus(row.status),
        prompt=row.prompt,
        parameters=parameters,
        progress=row.progress,
        output_url=row.output_url,
        created_at=row.created_at,
    )


class JobStore:
    """SQL-backed repository for jobs.

    Methods take and return the API's `Job` object; the row is an
    implementation detail. All writes go through `SessionLocal` so a worker
    process and an API process — the two processes that used to be blind to
    each other — now read and write the same table.
    """

    def add_job(self, job: Job) -> Job:
        with SessionLocal() as db:
            db.add(
                JobRow(
                    id=str(job.id),
                    workspace_id=job.parameters.get("workspace_id"),
                    type=job.type.value,
                    prompt=job.prompt,
                    parameters=json.dumps(job.parameters, ensure_ascii=False),
                    status=job.status.value,
                    progress=job.progress,
                    output_url=job.output_url,
                )
            )
            db.commit()
        return job

    def get_job(self, job_id: UUID | str) -> Job | None:
        with SessionLocal() as db:
            row = db.get(JobRow, str(job_id))
            return _row_to_job(row) if row else None

    def list_jobs(self, workspace_id: str | None = None) -> list[Job]:
        with SessionLocal() as db:
            statement = select(JobRow).order_by(JobRow.created_at.desc())
            if workspace_id is not None:
                statement = statement.where(JobRow.workspace_id == workspace_id)
            return [_row_to_job(row) for row in db.scalars(statement).all()]

    def set_state(self, job_id: UUID | str, *, status: JobStatus | None = None, progress: int | None = None, output_url: str | None = None) -> None:
        """Persist a state change for an existing job.

        Called only from `queue.transition()` — the single point where a job
        moves — so persisting and emitting the event stay one step apart.
        `output_url` participates because the worker assigns it between
        transitions and the next transition is what carries it.
        """

        with SessionLocal() as db:
            row = db.get(JobRow, str(job_id))
            if row is None:
                return
            if status is not None:
                row.status = status.value
            if progress is not None:
                row.progress = progress
            if output_url is not None:
                row.output_url = output_url
            db.commit()


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

    # personas — in memory until PR004
    @property
    def personas(self) -> dict[UUID, Persona]:
        return self._personas.personas

    def add_persona(self, persona: Persona) -> Persona:
        return self._personas.add_persona(persona)


store = Store()
