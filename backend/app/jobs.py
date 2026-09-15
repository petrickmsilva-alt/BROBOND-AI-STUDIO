"""Job boundary mapping — API object <-> Core value object (PR004-prep).

The Core works with its own plain `Job` (`app.core.job_service.Job`); the
API and the worker work with the pydantic `Job` from `app.schemas`. This
module is the only place where the two meet, so the mapping exists exactly
once and no Core or provider module ever sees a Pydantic model.
"""
from __future__ import annotations

from uuid import UUID

from .core.job_service import Job as CoreJob
from .schemas import GenerationType, Job, JobStatus


def to_core_job(job: Job) -> CoreJob:
    """API job -> Core value object (at creation time)."""

    return CoreJob(
        id=str(job.id),
        type=job.type.value,
        status=job.status.value,
        prompt=job.prompt,
        parameters=dict(job.parameters or {}),
        progress=job.progress,
        output_url=job.output_url,
        created_at=job.created_at,
    )


def to_api_job(job: CoreJob) -> Job:
    """Core value object -> API job (for responses and the worker)."""

    return Job(
        id=UUID(job.id),
        type=GenerationType(job.type),
        status=JobStatus(job.status),
        prompt=job.prompt,
        parameters=dict(job.parameters or {}),
        progress=job.progress,
        output_url=job.output_url,
        created_at=job.created_at,
    )
