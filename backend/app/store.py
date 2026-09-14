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

    def get_job(self, job_id: UUID) -> Job | None:
        return self.jobs.get(job_id)

    def add_persona(self, persona: Persona) -> Persona:
        self.personas[persona.id] = persona
        return persona


store = MemoryStore()
