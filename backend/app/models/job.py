"""PR004-prep: the Job model, in its own module (Repository Pattern directive).

The job table is the only model owned by the job persistence layer: the
`JobRepository` implementations in `backend/app/repositories/` are the only
modules that read or write `JobRow`. Moving the class to `models/job.py`
makes that ownership explicit without changing the table, the migration
(`0001`) or any import site — `app.models` re-exports the name.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class JobRow(Base):
    """PR002: a persisted generation job.

    Jobs used to live in a process-local dict (`MemoryStore`), so a Celery
    worker in another process could never see the job the API created, and
    every deploy silently dropped the queue. The row is the single source of
    truth now; `app.store.JobStore` is the repository over it. `parameters`
    stays a JSON document because `Job.parameters` is a free-form dict and the
    spec adapter reads it field by field — no schema migration is needed when
    the UI grows a new generation option.
    """

    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    type: Mapped[str] = mapped_column(String(16))
    prompt: Mapped[str] = mapped_column(Text)
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), index=True, default="queued")
    progress: Mapped[int] = mapped_column(default=0)
    output_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

