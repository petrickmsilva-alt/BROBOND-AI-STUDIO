"""Celery integration and job lifecycle transitions.

Workers are intentionally provider-agnostic: model adapters can be plugged into
`process_generation` without changing the HTTP API.
"""
from dataclasses import replace
from pathlib import Path

from celery import Celery

from .core.config import settings
from .core.contracts import GenerationKind
from .events import (
    EVENT_CANCELLED,
    EVENT_COMPLETE,
    EVENT_FAILED,
    EVENT_PROGRESS,
    EVENT_QUEUED,
    EVENT_STARTED,
    hub,
    job_event,
)
from .db import SessionLocal
from .models import Asset, TrainingRun
from .preprocessing import preprocessor
from .providers import registry as provider_registry
from .providers.registry import DEFAULTS as PROVIDER_DEFAULTS
from .schemas import GenerationType, JobStatus
from .spec_adapter import compile_job, resolve_model_id
from .core.quality import QualityGate
from .storage import storage
from .store import store
from .training import execute_training, prepare_dataset

redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")
celery_app = Celery("brobond", broker=redis_url, backend=redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json", accept_content=["json"])


#: ETAPA 14: the gate that checks a rendered artifact against the spec that
#: produced it. Shared with the API so a manual assessment and the worker's
#: verdict can never disagree.
quality_gate = QualityGate()

#: Progress milestones. The worker used to jump from 10 to 100, which gave a
#: client nothing to render between "it started" and "it finished".
PROGRESS_STARTED = 10
PROGRESS_SPEC_COMPILED = 25
PROGRESS_INPUTS_RESOLVED = 40
PROGRESS_RENDERING = 55
PROGRESS_PERSISTED = 90
PROGRESS_DONE = 100


def transition(
    job,
    status: JobStatus | None = None,
    progress: int | None = None,
    *,
    event: str = EVENT_PROGRESS,
    error: str | None = None,
) -> dict:
    """Move a job and emit the event, in one step.

    This is the only place a job's status or progress is written. Before ETAPA 11
    every call site assigned the two fields directly and nothing was emitted,
    which is why `EventHub.publish` had no callers at all: there was no single
    moment that meant "the job moved".

    Writing state and emitting together makes it impossible to move a job
    silently. `status` and `progress` are both optional so a pure progress tick
    does not have to restate the status.
    """

    if status is not None:
        job.status = status
    if progress is not None:
        job.progress = progress
    # PR002: the row moves with the object. Jobs used to live in a process
    # dict, so a worker in another process wrote state the API could never
    # see; the row is the shared truth and the emit stays in the same step.
    store.set_job_state(
        job.id,
        status=job.status,
        progress=job.progress,
        output_url=job.output_url,
    )
    payload = job_event(
        job.id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        progress=int(job.progress or 0),
        event=event,
        output_url=job.output_url,
        error=error,
    )
    return hub.publish_sync(job.id, payload)


def _resolve_model_id_for(entry, kind: GenerationKind, spec) -> str:
    """The checkpoint this entry should load.

    Two pre-existing knobs keep working, and neither is allowed to leak into
    another provider:

    * `spec.provider` is already resolved by the spec adapter (ETAPA 3), so an
      image job keeps using it.
    * `settings.video_model_id` configures the *default* video provider only.
      Applying it to Hunyuan would load the Wan checkpoint, which is the exact
      class of mistake the registry exists to prevent.
    """

    if kind is GenerationKind.VIDEO:
        if entry.provider_id == PROVIDER_DEFAULTS[GenerationKind.VIDEO]:
            return settings.video_model_id
        return entry.model_id
    return resolve_model_id(spec.provider, entry.model_id)


@celery_app.task(bind=True, name="brobond.process_generation")
def process_generation(self, job_id: str) -> dict[str, str]:
    """Placeholder worker lifecycle; replace the body with model provider calls."""
    job = store.get_job(job_id)
    if not job:
        return {"job_id": job_id, "status": "cancelled"}
    if job.status == JobStatus.CANCELLED:
        transition(job, event=EVENT_CANCELLED)
        return {"job_id": job_id, "status": "cancelled"}
    transition(job, JobStatus.RUNNING, PROGRESS_STARTED, event=EVENT_STARTED)
    if not settings.inference_enabled:
        # Orchestration-only mode is safe for machines without model weights.
        transition(job, JobStatus.COMPLETE, PROGRESS_DONE, event=EVENT_COMPLETE)
        return {"job_id": job_id, "status": job.status.value, "mode": "orchestration-only"}
    try:
        lora_path = None
        reference_path = None
        lora_id = job.parameters.get("lora_id")
        workspace_id = job.parameters.get("workspace_id")
        if lora_id and workspace_id:
            with SessionLocal() as db:
                lora_asset = db.get(Asset, str(lora_id))
            if not lora_asset or lora_asset.kind != "lora" or lora_asset.workspace_id != workspace_id:
                raise RuntimeError("Selected LoRA adapter is not available in this workspace")
            # ETAPA 12: `storage.download` covers both backends, so object
            # storage no longer has to be refused here. It returns the stored
            # file directly in local mode and fetches to the same path from S3.
            destination = storage.local_path(lora_asset.object_key)
            lora_path = str(storage.download(lora_asset.object_key, destination))
            if not Path(lora_path).is_file():
                raise RuntimeError("Selected LoRA adapter file is missing")
        reference_id = job.parameters.get("reference_asset_id")
        if reference_id and workspace_id:
            with SessionLocal() as db:
                reference_asset = db.get(Asset, str(reference_id))
            if not reference_asset or reference_asset.kind != "image" or reference_asset.workspace_id != workspace_id:
                raise RuntimeError("Reference image is not available in this workspace")
            destination = storage.local_path(reference_asset.object_key)
            reference_path = str(storage.download(reference_asset.object_key, destination))
            if not Path(reference_path).is_file():
                raise RuntimeError("Reference image file is missing")

        # ETAPA 3: the Core makes every creative decision and the provider
        # receives *only* the resulting spec — no prompt string, no parameters
        # dict. `lora` and `reference_path` are folded in here as concrete local
        # paths, after workspace ownership was validated above. A LoRA coming
        # from persona memory is already a path and is passed through.
        compiled = compile_job(job)
        transition(job, progress=PROGRESS_SPEC_COMPILED)
        spec = replace(
            compiled.spec,
            lora=lora_path or compiled.spec.lora,
            reference_path=reference_path,
        )

        # ETAPA 10: the adapter is chosen by the *requested provider*, through
        # the registry, instead of by job type alone. Until now every image job
        # ran FLUX and every video job ran Wan whatever was asked for, so
        # requesting Hunyuan returned Wan with no error.
        kind = GenerationKind.VIDEO if job.type == GenerationType.VIDEO else GenerationKind.IMAGE
        requested = job.parameters.get("model")
        entry = provider_registry.resolve(requested, kind)
        # Refuse an unavailable combination before anything is loaded: a planned
        # or remote-only provider must fail loudly rather than run a different
        # model than the one requested.
        provider_registry.check(entry, kind)
        transition(job, progress=PROGRESS_INPUTS_RESOLVED)
        model_id = _resolve_model_id_for(entry, kind, spec)
        provider = provider_registry.build(entry.provider_id, kind, model_id=model_id)

        transition(job, progress=PROGRESS_RENDERING)
        result = provider.generate(spec, settings.weights_dir)

        # ETAPA 14: nothing ever looked at what came back. A provider could hand
        # over a path that did not exist, or a frame whose geometry contradicted
        # the spec, and the job was still marked complete with that broken
        # `output_url`. The gate checks the artifact against the spec that
        # produced it; a violation fails the job instead of shipping it.
        report = quality_gate.assess(spec, quality_gate.measure(result), kind=kind)
        if not report.ok:
            reasons = "; ".join(f"{item['rule']}: {item['detail']}" for item in report.violations)
            raise RuntimeError(f"Quality gate rejected the render — {reasons}")

        if kind is GenerationKind.VIDEO:
            output_type, content_type, extension = "video", "video/mp4", "mp4"
        else:
            output_type, content_type, extension = "image", "image/png", "png"
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
        transition(job, progress=PROGRESS_PERSISTED)
        transition(job, JobStatus.COMPLETE, PROGRESS_DONE, event=EVENT_COMPLETE)
    except Exception as error:
        transition(job, JobStatus.FAILED, event=EVENT_FAILED, error=str(error))
        return {"job_id": job_id, "status": job.status.value, "error": str(error)}
    return {"job_id": job_id, "status": job.status.value}


@celery_app.task(bind=True, name="brobond.preprocess_reference")
def preprocess_reference(self, source: str, mode: str, destination: str) -> dict[str, str]:
    try:
        output = preprocessor.preprocess(source, mode, destination)
        return {"status": "complete", "mode": mode, "output": output}
    except Exception as error:
        return {"status": "failed", "mode": mode, "error": str(error)}


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
