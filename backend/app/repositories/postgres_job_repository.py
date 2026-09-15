"""PostgresJobRepository — the default job provider (PR004-prep).

The `jobs` table (Alembic `0001`) remains the source of truth; this module
is where that fact lives. It is the only job module that imports
SQLAlchemy. All the mapping logic that used to sit in `app.store.JobStore`
(lit Legacy since this directive) was moved here, unchanged in behaviour:
`parameters` crosses the boundary as a JSON document, the workspace scope
is read from `parameters["workspace_id"]` (a row created before PR002 may
have a NULL `workspace_id` column and still be addressed through its
parameters, exactly as before).
"""
from __future__ import annotations

import json

from sqlalchemy import select

from ..core.job_service import Job
from ..db import SessionLocal
from ..models import JobRow


def _row_to_job(row: JobRow) -> Job:
    """Rebuild the Core value object from its row (the row is an implementation detail)."""

    try:
        parameters = json.loads(row.parameters or "{}")
    except json.JSONDecodeError:  # pragma: no cover — rows are only written here
        parameters = {}
    return Job(
        id=row.id,
        type=row.type,
        status=row.status,
        prompt=row.prompt,
        parameters=parameters,
        progress=row.progress,
        output_url=row.output_url,
        created_at=row.created_at,
    )


def _row_from_job(job: Job) -> JobRow:
    return JobRow(
        id=job.id,
        workspace_id=job.parameters.get("workspace_id"),
        type=job.type,
        prompt=job.prompt,
        parameters=json.dumps(job.parameters, ensure_ascii=False),
        status=job.status,
        progress=job.progress,
        output_url=job.output_url,
        created_at=job.created_at,
    )


class PostgresJobRepository:
    """JobRepository over the `jobs` table.

    All writes go through `SessionLocal` so a worker process and an API
    process — the two processes that used to be blind to each other — read
    and write the same table (PR002's cross-process contract, preserved).
    """

    def create(self, job: Job) -> Job:
        with SessionLocal() as db:
            db.add(_row_from_job(job))
            db.commit()
        return job

    def get(self, job_id: str) -> Job | None:
        with SessionLocal() as db:
            row = db.get(JobRow, str(job_id))
            return _row_to_job(row) if row else None

    def _apply(self, job_id: str, *, status: str | None, progress: int | None, output_url: str | None) -> Job | None:
        with SessionLocal() as db:
            row = db.get(JobRow, str(job_id))
            if row is None:
                return None
            if status is not None:
                row.status = status
            if progress is not None:
                row.progress = progress
            if output_url is not None:
                row.output_url = output_url
            db.commit()
            return _row_to_job(row)

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
        with SessionLocal() as db:
            statement = select(JobRow).where(JobRow.workspace_id == workspace_id).order_by(JobRow.created_at.desc())
            return [_row_to_job(row) for row in db.scalars(statement).all()]

    def delete(self, job_id: str) -> bool:
        with SessionLocal() as db:
            row = db.get(JobRow, str(job_id))
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True
