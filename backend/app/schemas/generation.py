from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class GenerationBase(BaseModel):
    prompt: str = Field(min_length=1, max_length=4_000)
    negative_prompt: str | None = Field(default=None, max_length=2_000)
    model: str = "flux.1-dev"
    seed: int | None = Field(default=None, ge=0)
    aspect_ratio: str = "1:1"


class ImageGenerationRequest(GenerationBase):
    resolution: str = "1024x1024"
    steps: int = Field(default=28, ge=1, le=100)
    cfg: float = Field(default=6.5, ge=1, le=30)
    lora_id: UUID | None = None
    reference_asset_id: UUID | None = None


class VideoGenerationRequest(GenerationBase):
    mode: Literal["text-to-video", "image-to-video", "start-end-frame"] = "text-to-video"
    duration_seconds: Literal[5, 10, 15] = 5
    fps: Literal[24, 30] = 24
    motion_preset: str = "static"
    cinematic_mode: bool = True
    native_audio: bool = False
    start_asset_id: UUID | None = None
    end_asset_id: UUID | None = None


class GenerationJob(BaseModel):
    id: UUID
    kind: Literal["image", "video"]
    status: Literal["queued", "running", "completed", "failed"]
    prompt: str
    progress: int = Field(default=0, ge=0, le=100)
    created_at: datetime
    output_asset_id: UUID | None = None


class PromptEnhanceRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4_000)
    style: str = "cinematic"
    preserve_subject: bool = True


class PromptEnhanceResponse(BaseModel):
    original: str
    enhanced: str
    style: str


class StoryboardRequest(BaseModel):
    premise: str = Field(min_length=1, max_length=2_000)
    scene_count: int = Field(default=4, ge=2, le=12)
    style: str = "cinematic"


class StoryboardScene(BaseModel):
    index: int
    title: str
    prompt: str
    duration_seconds: int


class StoryboardResponse(BaseModel):
    id: UUID
    premise: str
    scenes: list[StoryboardScene]


class SystemStatus(BaseModel):
    gpu_name: str
    vram_total_gb: float
    vram_used_gb: float
    queue_depth: int
    ffmpeg_available: bool
    storage_provider: str
