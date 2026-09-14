"""FastAPI entrypoint for BROBOND AI STUDIO's local service boundary."""
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse, current_user, login, register
from .core.config import settings
from .db import Base, engine, get_db
from .events import hub
from .models import Asset, User, Workspace
from .queue import enqueue
from .storage import storage
from .system import gpu_info
from .schemas import (
    ImageGenerationRequest, Job, JobStatus, Persona, PersonaCreateRequest,
    StoryboardRequest, StoryboardResponse, StoryboardScene, VideoGenerationRequest,
    AssetResponse, GenerationType,
)
from .store import store

app = FastAPI(
    title="BROBOND AI STUDIO API",
    version="0.1.0",
    description="Local-first orchestration API for generative visual workflows.",
)
# Development bootstrap. Production deployments should run Alembic migrations instead.
Base.metadata.create_all(bind=engine)

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


@app.get("/api/v1/models/image", tags=["models"])
def image_models() -> list[dict[str, str]]:
    return [
        {"id": "flux-1.1-pro-ultra", "label": "Flux 1.1 Pro Ultra", "status": "remote-provider"},
        {"id": "flux-dev", "label": "FLUX.1 Dev", "status": "local-provider"},
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


@app.post("/api/v1/generations/images", response_model=Job, status_code=202, tags=["generations"])
def create_image_generation(request: ImageGenerationRequest) -> Job:
    """Create an image job. A Celery provider will consume this job in production."""
    return _queue_job(GenerationType.IMAGE, request.prompt, request.model_dump(mode="json"))


@app.post("/api/v1/generations/videos", response_model=Job, status_code=202, tags=["generations"])
def create_video_generation(request: VideoGenerationRequest) -> Job:
    """Create an H.264 video job for the configured video provider."""
    return _queue_job(GenerationType.VIDEO, request.prompt, request.model_dump(mode="json"))


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


@app.post("/api/v1/personas", response_model=Persona, status_code=202, tags=["personas"])
def create_persona(request: PersonaCreateRequest) -> Persona:
    """Register a persona and reserve a future LoRA training job."""
    return store.add_persona(Persona(details=request, status="training"))


@app.post("/api/v1/storyboards/expand", response_model=StoryboardResponse, tags=["storyboards"])
def expand_storyboard(request: StoryboardRequest) -> StoryboardResponse:
    """Create deterministic scene prompts until an LLM prompt engine is configured."""
    scenes = [
        StoryboardScene(
            number=index,
            title=f"Scene {index}",
            prompt=f"{request.brief}. Cinematic sequence {index} of {request.scene_count}, coherent visual continuity, cinematic lighting.",
        )
        for index in range(1, request.scene_count + 1)
    ]
    return StoryboardResponse(brief=request.brief, scenes=scenes)


@app.get("/api/v1/queue", response_model=list[Job], tags=["queue"])
def list_queue() -> list[Job]:
    return list(store.jobs.values())
