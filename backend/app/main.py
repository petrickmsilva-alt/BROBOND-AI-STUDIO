"""FastAPI entrypoint for BROBOND AI STUDIO's local service boundary."""
import asyncio
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse, current_user, login, optional_user, register
from .core.config import settings
from .db import Base, engine, get_db
from .events import hub
from .lora import lora_trainer
from .media import MediaError, media
from .models import Asset, TrainingRun, User, Workspace
from .prompt_engine import prompt_engine
from .queue import enqueue, enqueue_lora_training
from .storage import storage
from .system import gpu_info
from .schemas import (
    ImageGenerationRequest, Job, JobStatus, Persona, PersonaCreateRequest,
    StoryboardRequest, StoryboardResponse, StoryboardScene, VideoGenerationRequest,
    AssetResponse, ExportRequest, ExportResponse, GenerationType, LoraVersionResponse, PersonaTrainRequest, PersonaTrainResponse, PromptEnhanceRequest, PromptEnhanceResponse, TrainingStatusResponse,
)
from .store import store

app = FastAPI(
    title="BROBOND AI STUDIO API",
    version="0.1.0",
    description="Local-first orchestration API for generative visual workflows.",
)
# Development bootstrap. Production deployments should run Alembic migrations instead.
Base.metadata.create_all(bind=engine)
# Lightweight local migration for existing SQLite development databases.
if "training_runs" in inspect(engine).get_table_names():
    columns = {column["name"] for column in inspect(engine).get_columns("training_runs")}
    if "workspace_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE training_runs ADD COLUMN workspace_id VARCHAR(36)"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "brobond-api", "mode": "local"}


@app.get("/api/v1/system/gpu", tags=["system"])
def system_gpu() -> dict:
    return gpu_info()


@app.get("/api/v1/system/media", tags=["system"])
def system_media() -> dict[str, object]:
    return media.capabilities()


@app.post("/api/v1/prompts/enhance", response_model=PromptEnhanceResponse, tags=["prompt-engine"])
def enhance_prompt(request: PromptEnhanceRequest) -> PromptEnhanceResponse:
    enhanced = prompt_engine.enhance(request.prompt, request.style, request.persona, request.camera, request.lighting)
    return PromptEnhanceResponse(original=request.prompt, enhanced=enhanced, tokens=enhanced.split(", "))


@app.get("/api/v1/models/image", tags=["models"])
def image_models() -> list[dict[str, str]]:
    return [
        {"id": "flux-1.1-pro-ultra", "label": "Flux 1.1 Pro Ultra", "status": "remote-provider"},
        {"id": "flux-dev", "label": "FLUX.1 Dev", "status": "local-provider"},
    ]


@app.get("/api/v1/models/video", tags=["models"])
def video_models() -> list[dict[str, str]]:
    return [
        {"id": "wan-2.1-t2v", "label": "Wan 2.1 Text to Video", "status": "local-provider"},
        {"id": "hunyuan-video", "label": "Hunyuan Video", "status": "planned-provider"},
    ]


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201, tags=["auth"])
def register_user(request: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return register(request, db)


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["auth"])
def login_user(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return login(request, db)


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["auth"])
def get_current_user(user: User = Depends(current_user)) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)


def _queue_job(kind: GenerationType, prompt: str, parameters: dict | None = None) -> Job:
    job = store.add_job(Job(type=kind, prompt=prompt, parameters=parameters or {}))
    # Redis/Celery is optional in local development; the job remains inspectable.
    enqueue(str(job.id))
    return job


def _generation_parameters(request: ImageGenerationRequest | VideoGenerationRequest, user: User | None, db: Session) -> dict:
    parameters = request.model_dump(mode="json")
    if user:
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
        if workspace:
            parameters["workspace_id"] = workspace.id
    return parameters


@app.post("/api/v1/generations/images", response_model=Job, status_code=202, tags=["generations"])
def create_image_generation(request: ImageGenerationRequest, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> Job:
    """Create an image job. Authenticated jobs are persisted to the user's asset library."""
    return _queue_job(GenerationType.IMAGE, request.prompt, _generation_parameters(request, user, db))


@app.post("/api/v1/generations/videos", response_model=Job, status_code=202, tags=["generations"])
def create_video_generation(request: VideoGenerationRequest, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> Job:
    """Create an H.264 video job for the configured video provider."""
    return _queue_job(GenerationType.VIDEO, request.prompt, _generation_parameters(request, user, db))


@app.get("/api/v1/jobs/{job_id}", response_model=Job, tags=["generations"])
def get_job(job_id: UUID) -> Job:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=Job, tags=["queue"])
def cancel_job(job_id: UUID) -> Job:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found")
    if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
        job.status = JobStatus.CANCELLED
    return job


@app.websocket("/api/v1/queue/events/{job_id}")
async def queue_events(websocket: WebSocket, job_id: UUID) -> None:
    job = store.get_job(job_id)
    if not job:
        await websocket.close(code=1008, reason="Generation job not found")
        return
    await hub.connect(job_id, websocket)
    try:
        await websocket.send_json(job.model_dump(mode="json"))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(job_id, websocket)


@app.post("/api/v1/assets/upload", response_model=AssetResponse, status_code=201, tags=["assets"])
async def upload_asset(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AssetResponse:
    """Upload an asset to MinIO or the local media adapter."""
    allowed = {"image/", "video/", "audio/"}
    if not file.content_type or not any(file.content_type.startswith(prefix) for prefix in allowed):
        raise HTTPException(status_code=415, detail="Only image, video and audio files are supported")
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    key, url = await storage.save(file, workspace.id)
    kind = file.content_type.split("/", 1)[0]
    asset = Asset(workspace_id=workspace.id, name=file.filename or "upload", kind=kind, object_key=key)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return AssetResponse(id=asset.id, name=asset.name, kind=asset.kind, object_key=asset.object_key, url=url, created_at=asset.created_at)


@app.get("/api/v1/assets", response_model=list[AssetResponse], tags=["assets"])
def list_assets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[AssetResponse]:
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
    if not workspace:
        return []
    assets = db.scalars(select(Asset).where(Asset.workspace_id == workspace.id).order_by(Asset.created_at.desc())).all()
    return [AssetResponse(id=a.id, name=a.name, kind=a.kind, object_key=a.object_key, url=storage.signed_url(a.object_key), created_at=a.created_at) for a in assets]


@app.get("/api/v1/assets/download/{object_key:path}", tags=["assets"])
def download_local_asset(object_key: str):
    if settings.storage_enabled:
        raise HTTPException(status_code=404, detail="Use the signed MinIO URL")
    try:
        path = storage.local_path(object_key)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid asset path") from error
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path)


@app.post("/api/v1/assets/{asset_id}/export", response_model=ExportResponse, tags=["exports"])
def export_video(asset_id: str, request: ExportRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ExportResponse:
    if not media.available:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on this worker")
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
    asset = db.get(Asset, asset_id)
    if not workspace or not asset or asset.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.kind != "video":
        raise HTTPException(status_code=422, detail="Only video assets can be exported")
    if settings.storage_enabled:
        raise HTTPException(status_code=501, detail="MinIO source download adapter is not enabled for exports yet")
    try:
        source = str(storage.local_path(asset.object_key))
        destination = str(storage.local_path(f"{workspace.id}/exports/{asset.id}-{request.quality}.mp4"))
        media.export_h264(source, destination, request.quality, request.fps)
        output_key = f"{workspace.id}/exports/{asset.id}-{request.quality}.mp4"
        output_asset = Asset(workspace_id=workspace.id, name=f"{asset.name}-{request.quality}.mp4", kind="video", object_key=output_key)
        db.add(output_asset)
        db.commit()
        return ExportResponse(asset_id=output_asset.id, status="complete", output_url=storage.signed_url(output_key), message="H.264 export complete")
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/v1/personas", response_model=Persona, status_code=202, tags=["personas"])
def create_persona(request: PersonaCreateRequest) -> Persona:
    """Register a persona and reserve a future LoRA training job."""
    return store.add_persona(Persona(details=request, status="training"))


@app.post("/api/v1/personas/{persona_id}/train", response_model=PersonaTrainResponse, status_code=202, tags=["personas"])
def train_persona(persona_id: UUID, request: PersonaTrainRequest, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> PersonaTrainResponse:
    persona = store.personas.get(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    try:
        plan = lora_trainer.build_plan(persona_id, request.reference_asset_ids, persona.details.name, request.style)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    persona.status = "training"
    persona.details.reference_asset_ids = request.reference_asset_ids
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id)) if user else None
    run = TrainingRun(persona_id=str(persona_id), workspace_id=workspace.id if workspace else None, status="queued", progress=0, log="Training plan created")
    db.add(run)
    db.commit()
    db.refresh(run)
    queued = enqueue_lora_training(run.id, str(persona_id), run.workspace_id, [str(asset_id) for asset_id in request.reference_asset_ids], persona.details.name, request.style)
    message = "LoRA training job queued for a GPU worker" if queued else "Training run created; enable Redis and the GPU worker to execute it"
    return PersonaTrainResponse(persona_id=persona_id, run_id=UUID(run.id), status=run.status, progress=run.progress, image_count=plan.image_count, message=message)


@app.get("/api/v1/personas/{persona_id}/training/{run_id}", response_model=TrainingStatusResponse, tags=["personas"])
def training_status(persona_id: UUID, run_id: UUID, db: Session = Depends(get_db)) -> TrainingStatusResponse:
    run = db.get(TrainingRun, str(run_id))
    if not run or run.persona_id != str(persona_id):
        raise HTTPException(status_code=404, detail="Training run not found")
    return TrainingStatusResponse(run_id=run_id, persona_id=persona_id, status=run.status, progress=run.progress, log=run.log, output_asset_id=run.output_asset_id)


@app.get("/api/v1/personas/{persona_id}/loras", response_model=list[LoraVersionResponse], tags=["personas"])
def list_persona_loras(persona_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[LoraVersionResponse]:
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
    if not workspace:
        return []
    runs = db.scalars(select(TrainingRun).where(TrainingRun.persona_id == str(persona_id), TrainingRun.workspace_id == workspace.id, TrainingRun.status == "complete")).all()
    versions: list[LoraVersionResponse] = []
    for index, run in enumerate(runs, start=1):
        if not run.output_asset_id:
            continue
        asset = db.get(Asset, run.output_asset_id)
        if asset:
            versions.append(LoraVersionResponse(asset_id=asset.id, persona_id=persona_id, name=asset.name, version=f"v{index}", url=storage.signed_url(asset.object_key), created_at=asset.created_at))
    return versions


@app.websocket("/api/v1/personas/{persona_id}/training/events/{run_id}")
async def training_events(websocket: WebSocket, persona_id: UUID, run_id: UUID) -> None:
    await websocket.accept()
    try:
        while True:
            with SessionLocal() as db:
                run = db.get(TrainingRun, str(run_id))
            if not run or run.persona_id != str(persona_id):
                await websocket.send_json({"status": "failed", "progress": 100, "log": "Training run not found"})
                break
            await websocket.send_json({"run_id": run.id, "status": run.status, "progress": run.progress, "log": run.log})
            if run.status in {"complete", "failed", "cancelled"}:
                break
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@app.post("/api/v1/storyboards/expand", response_model=StoryboardResponse, tags=["storyboards"])
def expand_storyboard(request: StoryboardRequest) -> StoryboardResponse:
    """Expand a brief into connected, independently renderable scene prompts."""
    camera_progression = ["wide establishing shot", "tracking medium shot", "low angle push-in", "intimate close-up"]
    scenes = []
    for index in range(1, request.scene_count + 1):
        camera = f"{camera_progression[(index - 1) % len(camera_progression)]}, {request.camera_language}"
        prompt = prompt_engine.enhance(request.brief, style=request.style, persona=request.persona, camera=camera, lighting="consistent blue-hour lighting across the sequence")
        scenes.append(StoryboardScene(number=index, title=f"Scene {index:02d}", prompt=f"{prompt} Continuity beat {index} of {request.scene_count}.", duration_seconds=5))
    return StoryboardResponse(brief=request.brief, scenes=scenes)


@app.get("/api/v1/queue", response_model=list[Job], tags=["queue"])
def list_queue() -> list[Job]:
    return list(store.jobs.values())
