"""Celery integration and job lifecycle transitions.

Workers are intentionally provider-agnostic: model adapters can be plugged into
`process_generation` without changing the HTTP API.
"""
from celery import Celery

from .core.config import settings
from .schemas import JobStatus
from .store import store

redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")
celery_app = Celery("brobond", broker=redis_url, backend=redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json", accept_content=["json"])


@celery_app.task(bind=True, name="brobond.process_generation")
def process_generation(self, job_id: str) -> dict[str, str]:
    """Placeholder worker lifecycle; replace the body with model provider calls."""
    job = store.get_job(job_id)
    if not job or job.status == JobStatus.CANCELLED:
        return {"job_id": job_id, "status": "cancelled"}
    job.status = JobStatus.RUNNING
    job.progress = 10
    # Future: call Flux/Wan provider, stream progress, save to MinIO.
    job.status = JobStatus.COMPLETE
    job.progress = 100
    return {"job_id": job_id, "status": job.status.value}


def enqueue(job_id: str) -> bool:
    """Submit to Redis. Return false when queue is disabled or unavailable."""
    if not settings.queue_enabled:
        return False
    try:
        process_generation.delay(job_id)
        return True
    except Exception:
        return False
