"""Celery integration and job lifecycle transitions.

Workers are intentionally provider-agnostic: model adapters can be plugged into
`process_generation` without changing the HTTP API.
"""
from celery import Celery

from .core.config import settings
from .db import SessionLocal
from .models import Asset
from .schemas import GenerationType, JobStatus
from .storage import storage
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
    if not settings.inference_enabled:
        # Orchestration-only mode is safe for machines without model weights.
        job.progress = 100
        job.status = JobStatus.COMPLETE
        return {"job_id": job_id, "status": job.status.value, "mode": "orchestration-only"}
    try:
        if job.type == GenerationType.IMAGE:
            from .providers.image import FluxDiffusersProvider
            result = FluxDiffusersProvider(model_id=job.parameters.get("model", "black-forest-labs/FLUX.1-dev")).generate(job.prompt, job.parameters, settings.weights_dir)
            output_type, content_type, extension = "image", "image/png", "png"
        else:
            from .providers.video import WanVideoProvider
            result = WanVideoProvider(model_id=settings.video_model_id).generate(job.prompt, job.parameters, settings.weights_dir)
            output_type, content_type, extension = "video", "video/mp4", "mp4"
        workspace_id = job.parameters.get("workspace_id")
        if workspace_id:
            object_key, url = storage.save_path(result.path, workspace_id, content_type)
            with SessionLocal() as db:
                asset = Asset(workspace_id=workspace_id, name=f"{job.id}.{extension}", kind=output_type, object_key=object_key)
                db.add(asset)
                db.commit()
            job.output_url = url
        else:
            job.output_url = result.path
        job.progress = 100
        job.status = JobStatus.COMPLETE
    except Exception as error:
        job.status = JobStatus.FAILED
        return {"job_id": job_id, "status": job.status.value, "error": str(error)}
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
