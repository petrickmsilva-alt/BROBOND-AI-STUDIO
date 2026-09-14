"""FastAPI entrypoint for BROBOND AI STUDIO's local service boundary."""
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse, current_user, login, register
from .db import Base, engine, get_db
from .models import User
from .schemas import (
    ImageGenerationRequest, Job, JobStatus, Persona, PersonaCreateRequest,
    StoryboardRequest, StoryboardResponse, StoryboardScene, VideoGenerationRequest,
    GenerationType,
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


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201, tags=["auth"])
def register_user(request: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return register(request, db)


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["auth"])
def login_user(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return login(request, db)


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["auth"])
def get_current_user(user: User = Depends(current_user)) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)


def _queue_job(kind: GenerationType, prompt: str) -> Job:
    return store.add_job(Job(type=kind, prompt=prompt))


@app.post("/api/v1/generations/images", response_model=Job, status_code=202, tags=["generations"])
def create_image_generation(request: ImageGenerationRequest) -> Job:
    """Create an image job. A Celery provider will consume this job in production."""
    return _queue_job(GenerationType.IMAGE, request.prompt)


@app.post("/api/v1/generations/videos", response_model=Job, status_code=202, tags=["generations"])
def create_video_generation(request: VideoGenerationRequest) -> Job:
    """Create an H.264 video job for the configured video provider."""
    return _queue_job(GenerationType.VIDEO, request.prompt)


@app.get("/api/v1/jobs/{job_id}", response_model=Job, tags=["generations"])
def get_job(job_id: UUID) -> Job:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


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
