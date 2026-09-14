"""Celery integration and job lifecycle transitions.

Workers are intentionally provider-agnostic: model adapters can be plugged into
`process_generation` without changing the HTTP API.
"""
from pathlib import Path

from celery import Celery

from .core.config import settings
from .db import SessionLocal
from .models import Asset, TrainingRun
from .schemas import GenerationType, JobStatus
from .storage import storage
from .store import store
from .training import execute_training, prepare_dataset

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
        lora_path = None
        lora_id = job.parameters.get("lora_id")
        workspace_id = job.parameters.get("workspace_id")
        if lora_id and workspace_id:
            with SessionLocal() as db:
                lora_asset = db.get(Asset, str(lora_id))
            if not lora_asset or lora_asset.kind != "lora" or lora_asset.workspace_id != workspace_id:
                raise RuntimeError("Selected LoRA adapter is not available in this workspace")
            if settings.storage_enabled:
                raise RuntimeError("MinIO LoRA download adapter is required before GPU inference")
            lora_path = str(storage.local_path(lora_asset.object_key))
            if not Path(lora_path).is_file():
                raise RuntimeError("Selected LoRA adapter file is missing")
        if job.type == GenerationType.IMAGE:
            from .providers.image import FluxDiffusersProvider
            parameters = {**job.parameters, "lora_path": lora_path} if lora_path else job.parameters
            result = FluxDiffusersProvider(model_id=job.parameters.get("model", "black-forest-labs/FLUX.1-dev")).generate(job.prompt, parameters, settings.weights_dir)
            output_type, content_type, extension = "image", "image/png", "png"
        else:
            from .providers.video import WanVideoProvider
            parameters = {**job.parameters, "lora_path": lora_path} if lora_path else job.parameters
            result = WanVideoProvider(model_id=settings.video_model_id).generate(job.prompt, parameters, settings.weights_dir)
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


@celery_app.task(bind=True, name="brobond.train_lora")
def train_lora(self, run_id: str, persona_id: str, workspace_id: str | None, asset_ids: list[str], identity: str, style: str) -> dict[str, str]:
    def update(status: str, progress: int, log: str) -> None:
        with SessionLocal() as db:
            run = db.get(TrainingRun, run_id)
            if run:
                run.status, run.progress, run.log = status, progress, log
                db.commit()
    try:
        from uuid import UUID
        update("running", 10, "Preparing reference dataset")
        dataset = prepare_dataset(UUID(persona_id), [UUID(asset_id) for asset_id in asset_ids], identity, style)
        update("running", 35, "Dataset and captions prepared")
        output = execute_training(dataset, dataset.parent / "loras")
        output_asset_id = None
        if workspace_id:
            object_key, _ = storage.save_path(str(output), workspace_id, "application/octet-stream")
            with SessionLocal() as db:
                asset = Asset(workspace_id=workspace_id, name=output.name, kind="lora", object_key=object_key)
                db.add(asset)
                db.flush()
                run = db.get(TrainingRun, run_id)
                if run:
                    run.output_asset_id = asset.id
                db.commit()
                output_asset_id = asset.id
        update("complete", 100, f"LoRA adapter created: {output.name}")
        return {"persona_id": persona_id, "status": "complete", "output": str(output), "asset_id": output_asset_id or ""}
    except Exception as error:
        update("failed", 100, str(error))
        return {"persona_id": persona_id, "status": "failed", "error": str(error)}


def enqueue_lora_training(run_id: str, persona_id: str, workspace_id: str | None, asset_ids: list[str], identity: str, style: str) -> bool:
    if not settings.queue_enabled:
        return False
    try:
        train_lora.delay(run_id, persona_id, workspace_id, asset_ids, identity, style)
        return True
    except Exception:
        return False


def enqueue(job_id: str) -> bool:
    """Submit to Redis. Return false when queue is disabled or unavailable."""
    if not settings.queue_enabled:
        return False
    try:
        process_generation.delay(job_id)
        return True
    except Exception:
        return False
