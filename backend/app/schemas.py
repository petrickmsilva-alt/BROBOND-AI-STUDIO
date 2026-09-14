"""Typed API contracts for the local-first generation service."""
from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class Job(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: GenerationType
    status: JobStatus = JobStatus.QUEUED
    prompt: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    progress: int = 0
    output_url: str | None = None
    parameters: dict = Field(default_factory=dict)


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    negative_prompt: str = Field(default="", max_length=2000)
    model: str = "flux-1.1-pro-ultra"
    aspect_ratio: Literal["16:9", "1:1", "9:16", "4:3", "3:4"] = "16:9"
    resolution: Literal["1024", "2048", "4096"] = "2048"
    seed: int | None = Field(default=None, ge=0)
    guidance_scale: float = Field(default=7.5, ge=1, le=30)
    steps: int = Field(default=28, ge=1, le=100)
    lora_id: UUID | None = None
    reference_asset_id: UUID | None = None
    controlnet: Literal["none", "pose", "depth", "canny", "tile"] = "none"
    controlnet_scale: float = Field(default=0.8, ge=0, le=2)
    ip_adapter_scale: float = Field(default=0.7, ge=0, le=1)


class VideoGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    mode: Literal["text-to-video", "image-to-video", "start-end-frame"] = "text-to-video"
    duration_seconds: Literal[5, 10, 15] = 5
    fps: Literal[24, 30] = 24
    aspect_ratio: Literal["16:9", "1:1", "9:16"] = "16:9"
    camera_motion: str = "static"
    cinematic_mode: bool = True
    slow_motion: bool = False
    native_audio: bool = False
    lora_id: UUID | None = None
    reference_asset_id: UUID | None = None


class PersonaCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=1, le=120)
    appearance: str = Field(min_length=1, max_length=500)
    eye_color: str = Field(min_length=1, max_length=80)
    beard: str = Field(default="", max_length=120)
    hair: str = Field(default="", max_length=120)
    height_m: float = Field(gt=0.4, lt=3)
    style: str = Field(min_length=1, max_length=160)
    reference_asset_ids: list[UUID] = Field(default_factory=list, max_length=50)


class PersonaTrainRequest(BaseModel):
    reference_asset_ids: list[UUID] = Field(min_length=20, max_length=50)
    style: str = Field(default="cinematic realism", max_length=160)


class PersonaTrainResponse(BaseModel):
    persona_id: UUID
    run_id: UUID | None = None
    status: str
    progress: int = 0
    image_count: int
    message: str


class TrainingStatusResponse(BaseModel):
    run_id: UUID
    persona_id: UUID
    status: str
    progress: int
    log: str
    output_asset_id: str | None = None


class LoraVersionResponse(BaseModel):
    asset_id: str
    persona_id: UUID
    name: str
    version: str
    url: str
    created_at: datetime


class Persona(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: Literal["training", "trained", "failed"] = "training"
    lora_version: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    details: PersonaCreateRequest


class AssetResponse(BaseModel):
    id: str
    name: str
    kind: str
    object_key: str
    url: str
    created_at: datetime


class ExportRequest(BaseModel):
    quality: Literal["720p", "1080p", "2k", "4k"] = "1080p"
    fps: Literal[24, 30] = 24
    format: Literal["mp4"] = "mp4"


class ExportResponse(BaseModel):
    asset_id: str
    status: str
    output_url: str | None = None
    message: str


class PromptEnhanceRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    style: str | None = Field(default=None, max_length=120)
    persona: str | None = Field(default=None, max_length=200)
    camera: str | None = Field(default=None, max_length=160)
    lighting: str | None = Field(default=None, max_length=160)


class PromptEnhanceResponse(BaseModel):
    original: str
    enhanced: str
    tokens: list[str]


class StoryboardRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    scene_count: int = Field(default=4, ge=2, le=12)
    persona: str | None = Field(default=None, max_length=200)
    style: str = Field(default="cinematic realism", max_length=120)
    camera_language: str = Field(default="coherent camera movement", max_length=200)


class StoryboardScene(BaseModel):
    number: int
    title: str
    prompt: str
    duration_seconds: int = 5


class StoryboardResponse(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    brief: str
    scenes: list[StoryboardScene]
