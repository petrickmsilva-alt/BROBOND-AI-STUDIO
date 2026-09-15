"""The wired job service — composition point (PR004-prep).

`app.main` and `app.queue` both need the running `JobService`, and neither
may import the other (main enqueues, the worker transitions). This tiny
module is where the Core service meets its provider: the **default**
provider is `PostgresJobRepository` (the `jobs` table, PR002 baseline).

Swapping the persistence backend is a one-line change here:

    job_service = JobService(RedisJobRepository(url="redis://..."))

Nothing in the Core, the routes or the worker changes — that is the point
of the Repository Pattern directive.
"""
from __future__ import annotations

from .core.job_service import JobService
from .repositories import PostgresJobRepository

job_service = JobService(PostgresJobRepository())
