"""Small in-memory repository used by the local development API.

Replace this adapter with SQLAlchemy repositories when persistence is enabled.
"""
from uuid import UUID

from .schemas import Job, Persona


class MemoryStore:
    def __init__(self) -> None:
        self.jobs: dict[UUID, Job] = {}
        self.personas: dict[UUID, Persona] = {}

    def add_job(self, job: Job) -> Job:
        self.jobs[job.id] = job
        return job

    def get_job(self, job_id: UUID | str) -> Job | None:
        """Look a job up by `UUID` or by its string form.

        Jobs are stored under `UUID` keys but cross a process boundary as
        strings (Celery serialises the task argument), so `store.get_job("…")`
        used to miss every job and the worker reported `cancelled` without ever
        running. Accepting both keeps the existing UUID callers working.
        """

        job = self.jobs.get(job_id)
        if job is None and isinstance(job_id, str):
            try:
                job = self.jobs.get(UUID(job_id))
            except ValueError:
                return None
        return job

    def add_persona(self, persona: Persona) -> Persona:
        self.personas[persona.id] = persona
        return persona


store = MemoryStore()
