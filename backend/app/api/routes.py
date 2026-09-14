import asyncio
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.generation import (
    GenerationJob,
    ImageGenerationRequest,
    PromptEnhanceRequest,
    PromptEnhanceResponse,
    StoryboardRequest,
    StoryboardResponse,
    StoryboardScene,
    SystemStatus,
    VideoGenerationRequest,
)
from app.services.generation import generation_service, queue_service

router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(payload: LoginRequest) -> TokenResponse:
    """Issue a local workspace token.

    The first local build accepts any validly-shaped credentials. Replace this
    boundary with a PostgreSQL user repository and password hash verification
    before exposing the API to a network.
    """

    token = create_access_token(payload.email, workspace_id="personal")
    return TokenResponse(access_token=token, expires_in=60 * 60)


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness endpoint used by Docker and local orchestration."""

    return {"status": "ok", "service": "brobond-api"}


@router.get("/system", response_model=SystemStatus, tags=["system"])
async def system_status() -> SystemStatus:
    """Expose a provider-neutral system snapshot for the studio dashboard."""

    return SystemStatus(
        gpu_name="Local GPU adapter",
        vram_total_gb=24.0,
        vram_used_gb=18.4,
        queue_depth=queue_service.depth(),
        ffmpeg_available=True,
        storage_provider="minio",
    )


@router.post("/generations/image", response_model=GenerationJob, status_code=202, tags=["generation"])
async def create_image_generation(payload: ImageGenerationRequest) -> GenerationJob:
    """Queue an image generation job for a GPU worker."""

    job = generation_service.submit_image(payload)
    return queue_service.enqueue(job)


@router.post("/generations/video", response_model=GenerationJob, status_code=202, tags=["generation"])
async def create_video_generation(payload: VideoGenerationRequest) -> GenerationJob:
    """Queue a video generation job for a GPU worker and FFmpeg pipeline."""

    job = generation_service.submit_video(payload)
    return queue_service.enqueue(job)


@router.get("/queue", response_model=list[GenerationJob], tags=["generation"])
async def list_queue() -> list[GenerationJob]:
    """List jobs visible to the current local workspace."""

    return queue_service.list_jobs()


@router.post("/prompts/enhance", response_model=PromptEnhanceResponse, tags=["prompt engine"])
async def enhance_prompt(payload: PromptEnhanceRequest) -> PromptEnhanceResponse:
    """Return a deterministic starter enhancement until an LLM provider is configured."""

    subject = payload.prompt.strip().rstrip(".")
    enhanced = (
        f"Ultra-realistic {subject}, cinematic composition, intentional camera language, "
        "volumetric atmosphere, tactile natural textures, controlled contrast, "
        "subtle film grain, editorial color grade, 35mm lens, high detail."
    )
    return PromptEnhanceResponse(original=payload.prompt, enhanced=enhanced, style=payload.style)


@router.post("/storyboards", response_model=StoryboardResponse, tags=["storyboard"])
async def create_storyboard(payload: StoryboardRequest) -> StoryboardResponse:
    """Split a premise into connected scene contracts for later generation."""

    scene_templates = [
        ("The arrival", "Establish the world and introduce the subject."),
        ("The crossing", "Move the subject through the central environment."),
        ("The signal", "Create a quiet emotional or visual turning point."),
        ("Beyond the frame", "Resolve the beat with an image that lingers."),
    ]
    scenes: list[StoryboardScene] = []
    for index in range(payload.scene_count):
        title, beat = scene_templates[index % len(scene_templates)]
        scenes.append(
            StoryboardScene(
                index=index + 1,
                title=title,
                prompt=f"{beat} Premise: {payload.premise}. Style: {payload.style}.",
                duration_seconds=4 + (index % 3),
            )
        )
    return StoryboardResponse(id=uuid4(), premise=payload.premise, scenes=scenes)


@router.websocket("/ws/queue")
async def queue_socket(websocket: WebSocket) -> None:
    """Stream a lightweight queue snapshot; replace with Redis pub/sub in production."""

    await websocket.accept()
    try:
        while True:
            await websocket.send_json({"queue_depth": queue_service.depth(), "jobs": [job.model_dump(mode="json") for job in queue_service.list_jobs()]})
            await asyncio.sleep(2)
    except (WebSocketDisconnect, RuntimeError):
        # A browser closing the panel should not leave a worker task behind.
        return
