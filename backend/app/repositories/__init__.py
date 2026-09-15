"""PR003: persistence repositories.

This package is the persistence layer: the ONLY place in the application
that turns storage (SQLAlchemy models, Redis documents, process memory)
into the product/Core vocabulary and back. Routes and adapters — including
the Core's `MemoryResolver` (through a thin source adapter) and the Core's
`JobService` (through the `JobRepository` interface) — depend on the
repositories, never on the providers.

PR004-prep (Repository Pattern directive): the job flow was decoupled from
PostgreSQL here. `job_repository.py` holds the interface the Core knows;
`postgres_job_repository.py` is the default provider; `redis_job_repository.py`
and `memory_job_repository.py` are the alternatives. Each repository opens
short-lived sessions/connections per call (the convention
`app.store.JobStore` established in PR002), so instances are plain
module-level singletons.
"""

from .job_repository import JobRepository
from .memory_job_repository import MemoryJobRepository
from .persona_repository import (
    PERSONA_IMAGE_TYPES,
    PersonaRepository,
    PersonaRepositoryError,
    persona_repo,
    slugify,
)
from .postgres_job_repository import PostgresJobRepository
from .redis_job_repository import RedisJobRepository

__all__ = [
    "JobRepository",
    "MemoryJobRepository",
    "PersonaRepository",
    "PersonaRepositoryError",
    "PERSONA_IMAGE_TYPES",
    "PostgresJobRepository",
    "RedisJobRepository",
    "persona_repo",
    "slugify",
]
