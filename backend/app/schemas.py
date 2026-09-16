"""Typed API contracts for the local-first generation service."""
from datetime import datetime
from enum import Enum
from typing import Any, Literal
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
    #: PR003: resolve the persona's identity, default style and LoRA from the
    #: persistent Persona Memory Engine. Optional — requests without it
    #: behave exactly as before.
    persona_id: str | None = Field(default=None, max_length=36)
    #: PR004: optionally narrow the persona wardrobe block to the items the
    #: project selected (names exactly as stored on the persona).
    wardrobe: list[str] | None = None


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
    #: PR003: resolve the persona's identity, default style and LoRA from the
    #: persistent Persona Memory Engine (same optional rule as images).
    persona_id: str | None = Field(default=None, max_length=36)
    #: PR004: optionally narrow the persona wardrobe block (same rule as images).
    wardrobe: list[str] | None = None


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
    #: PR002: the workspace that owns this persona, so training and LoRA
    #: listing can be checked against the acting user's tenant. Optional for
    #: compatibility with rows and payloads created before PR002.
    workspace_id: str | None = None


# ---------------------------------------------------------------------------
# PR003 — Persona Memory Engine (persistent persona profiles)
# ---------------------------------------------------------------------------


class PersonaWardrobeItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PersonaWardrobeResponse(BaseModel):
    id: str
    name: str
    category: str
    metadata: dict[str, Any]


class PersonaRevisionResponse(BaseModel):
    id: str
    revision: int
    notes: dict[str, Any]
    created_by: str
    created_at: datetime


class PersonaImageResponse(BaseModel):
    id: str
    #: Asset ids are strings: the legacy training flow may reference assets
    #: that are created after the persona, and the row stores plain ids.
    asset_id: str
    image_type: Literal["face", "body", "style", "reference"]
    order_index: int
    #: Present only while the referenced asset still exists.
    name: str | None = None
    url: str | None = None


class PersonaProfileResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    slug: str
    age: int
    height: float
    body_type: str
    skin_tone: str
    hair: str
    beard: str
    eyes: str
    voice: str
    default_style: str
    lora_id: str | None
    revision: int
    created_at: datetime
    updated_at: datetime
    wardrobe: list[PersonaWardrobeResponse]
    images: list[PersonaImageResponse]
    revisions: list[PersonaRevisionResponse]


class PersonaUpdateRequest(BaseModel):
    """Partial update; only the provided fields are applied.

    Any identity field that changes bumps ``revision`` and appends a
    ``persona_identity_revision`` row (the ETAPA 4 continuity rule).
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    age: int | None = Field(default=None, ge=1, le=120)
    height: float | None = Field(default=None, gt=0.4, lt=3.0)
    body_type: str | None = Field(default=None, max_length=80)
    skin_tone: str | None = Field(default=None, max_length=80)
    hair: str | None = Field(default=None, max_length=120)
    beard: str | None = Field(default=None, max_length=120)
    eyes: str | None = Field(default=None, max_length=80)
    voice: str | None = Field(default=None, max_length=120)
    default_style: str | None = Field(default=None, max_length=160)
    lora_id: str | None = Field(default=None, max_length=36)
    wardrobe: list[PersonaWardrobeItem] | None = None


class PersonaImageAddRequest(BaseModel):
    asset_id: str = Field(min_length=1, max_length=36)
    image_type: Literal["face", "body", "style", "reference"] = "reference"
    order_index: int | None = Field(default=None, ge=0)


class JobResponse(BaseModel):
    """The external shape of a job (PR002).

    Identical to `Job` except `status`, which is mapped through
    `events.external_status`: the system keeps `complete` internally and
    answers `completed` on the wire (Bible §14) without breaking clients and
    stored state that know `complete` (Bible §2).
    """

    id: UUID
    type: str
    status: str
    prompt: str
    created_at: datetime
    progress: int
    output_url: str | None = None
    parameters: dict = Field(default_factory=dict)

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        from .events import external_status

        return cls(
            id=job.id,
            type=job.type.value,
            status=external_status(job.status.value),
            prompt=job.prompt,
            created_at=job.created_at,
            progress=job.progress,
            output_url=job.output_url,
            parameters=job.parameters,
        )


class AssetResponse(BaseModel):
    id: str
    name: str
    kind: str
    object_key: str
    url: str
    created_at: datetime


class ConditioningRequest(BaseModel):
    mode: Literal["edges", "depth", "pose", "tile"]


class KnowledgeResponse(BaseModel):
    id: str
    category: str
    code: str
    title: str
    content: str
    source: str
    version: int


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


# ---------------------------------------------------------------------------
# BROBOND CORE (ETAPA 2)
#
# These are API contracts, deliberately separate from the domain objects in
# `app.core.contracts`. The Core owns decisions; these models own transport.
# ---------------------------------------------------------------------------


class SceneBeatResponse(BaseModel):
    number: int
    objective: str
    emotion: str
    camera: str
    lighting: str
    motion: str
    duration_seconds: float = 5.0
    shot_code: str | None = None
    reference: str = ""


class DirectorRequest(BaseModel):
    """A plain-language intention. No technical vocabulary is required."""

    intent: str = Field(min_length=1, max_length=1000)
    scene_count: int | None = Field(default=None, ge=1, le=12)
    style: str | None = Field(default=None, max_length=120)
    camera_language: str | None = Field(default=None, max_length=200)
    duration_per_scene: float = Field(default=5.0, gt=0, le=60)


class DirectorBriefResponse(BaseModel):
    concept: str
    format: str
    logline: str
    script: str
    beats: list[SceneBeatResponse]
    camera_language: str
    lighting_language: str
    music: str
    pacing: str
    style_hint: str
    duration_seconds: float
    scene_count: int
    #: Non-empty when the intention could follow more than one language and the
    #: director needs one short answer before committing.
    clarification: str = ""


# ---------------------------------------------------------------------------
# PR005 — Director AI Engine (planning only)
# ---------------------------------------------------------------------------


class DirectorProductionPlanRequest(BaseModel):
    """Human intention + production controls. This route never renders."""

    user_intent: str = Field(min_length=1, max_length=4000)
    persona_id: str | None = Field(default=None, max_length=120)
    platform: str = Field(default="studio", min_length=1, max_length=80)
    duration: float = Field(default=30.0, gt=0, le=600)
    mood: str | None = Field(default=None, max_length=40)


class DirectorShotPlanResponse(BaseModel):
    scene_number: int
    title: str
    objective: str
    emotion: str
    camera: str
    lens: str
    lighting: str
    motion: str
    duration: float
    prompt: str
    negative_prompt: str
    environment: str


class DirectorProductionPlanResponse(BaseModel):
    id: str
    title: str
    concept: str
    mood: str
    audience: str
    platform: str
    duration: float
    style: str
    music: str
    voice: str
    persona_id: str | None
    shots: list[DirectorShotPlanResponse]
    created_at: datetime


class GenerationSpecRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    kind: Literal["image", "video"] = "image"
    project_id: str | None = Field(default=None, max_length=36)
    persona_id: str | None = Field(default=None, max_length=80)
    #: PR004: optionally narrow the persona wardrobe block to selected items.
    wardrobe: list[str] | None = None
    style: str | None = Field(default=None, max_length=120)
    shot: str | None = Field(default=None, max_length=80)
    provider: str = Field(default="flux-dev", max_length=80)
    aspect_ratio: Literal["16:9", "1:1", "9:16", "4:3", "3:4"] = "16:9"
    fps: int | None = Field(default=None, ge=1, le=120)
    duration: float = Field(default=5.0, gt=0, le=60)
    seed: int | None = Field(default=None, ge=0)
    lora: str | None = Field(default=None, max_length=300)
    controlnet: Literal["none", "pose", "depth", "canny", "tile"] = "none"
    camera: str | None = Field(default=None, max_length=200)
    lens: str | None = Field(default=None, max_length=200)
    lighting: str | None = Field(default=None, max_length=200)
    motion: str | None = Field(default=None, max_length=200)
    weather: str = Field(default="", max_length=120)
    negative_prompt: str = Field(default="", max_length=2000)
    # Sampling extras. A provider receives only the GenerationSpec, so these
    # travel inside it and must be settable (and visible) here too.
    resolution: Literal["1024", "2048", "4096"] | None = None
    guidance_scale: float | None = Field(default=None, ge=1, le=30)
    steps: int | None = Field(default=None, ge=1, le=100)
    ip_adapter_scale: float | None = Field(default=None, ge=0, le=1)
    mode: Literal["text-to-video", "image-to-video", "start-end-frame"] | None = None
    cinematic_mode: bool = True
    slow_motion: bool = False
    native_audio: bool = False


# ---------------------------------------------------------------------------
# ETAPA 4 — persona memory (versioned, governed identity)
# ---------------------------------------------------------------------------


class PersonaRevisionRequest(BaseModel):
    """An identity or administrative edit. Every write is attributed."""

    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)
    authorized: bool = Field(
        default=False,
        description="Identity changes (name, age, height, body, hair, beard, eyes, voice, wardrobe) are rejected without it.",
    )
    name: str | None = Field(default=None, min_length=1, max_length=120)
    age: int | None = Field(default=None, ge=1, le=120)
    height_m: float | None = Field(default=None, gt=0.4, lt=3)
    body_type: str | None = Field(default=None, max_length=120)
    hair: str | None = Field(default=None, max_length=120)
    beard: str | None = Field(default=None, max_length=120)
    eyes: str | None = Field(default=None, max_length=120)
    voice: str | None = Field(default=None, max_length=160)
    wardrobe: str | None = Field(default=None, max_length=200)
    default_style: str | None = Field(default=None, max_length=120)
    lora_path: str | None = Field(default=None, max_length=500)


class PersonaTransitionRequest(BaseModel):
    """Approval or retirement. Requires an actor and a reason: these are audit events."""

    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=500)


class PersonaVersionResponse(BaseModel):
    revision: int
    version: int
    action: str
    actor: str
    reason: str
    changed: list[str] = Field(default_factory=list)
    created_at: str
    persona: dict[str, object] = Field(default_factory=dict)


class PersonaMemoryResponse(BaseModel):
    persona_id: str
    name: str
    status: str
    version: int
    generable: bool = Field(description="Only an approved identity may drive a generation.")
    identity_phrase: str = Field(default="", description="The PERSONA prompt block this identity produces.")
    default_style: str = ""
    lora_path: str | None = None
    persona: dict[str, object] = Field(default_factory=dict)


class PersonaHistoryResponse(BaseModel):
    persona_id: str
    name: str
    status: str
    version: int
    generable: bool
    identity_versions: list[int] = Field(default_factory=list)
    changed_fields: dict[str, list[int]] = Field(default_factory=dict)
    identity_changed: bool = False
    persona: dict[str, object] = Field(
        default_factory=dict,
        description="The current identity in full, so a client reading history does not need a second call.",
    )
    history: list[PersonaVersionResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ETAPA 5 — cinematic library (grammar + rules from knowledge_base/CINEMATIC_BIBLE.md)
# ---------------------------------------------------------------------------


class LensProfileResponse(BaseModel):
    focal_mm: int
    semantics: list[str] = Field(default_factory=list)


class FrameProfileResponse(BaseModel):
    name: str
    carries: str
    keywords: list[str] = Field(default_factory=list)


class LightingProfileResponse(BaseModel):
    name: str
    role: str
    constraint: str = ""
    keywords: list[str] = Field(default_factory=list)


class TimeQualityResponse(BaseModel):
    """A light quality and the tone it supports — a different shape from a light role."""

    name: str
    supports: str
    keywords: list[str] = Field(default_factory=list)


class AngleProfileResponse(BaseModel):
    """An angle and the effect it creates — a different shape from a shot size."""

    name: str
    creates: str
    keywords: list[str] = Field(default_factory=list)


class MotivationResponse(BaseModel):
    name: str
    description: str
    keywords: list[str] = Field(default_factory=list)


class FramingResponse(BaseModel):
    frames: list[FrameProfileResponse] = Field(default_factory=list)
    angles: list[AngleProfileResponse] = Field(default_factory=list)


class LightingResponse(BaseModel):
    lights: list[LightingProfileResponse] = Field(default_factory=list)
    time_qualities: list[TimeQualityResponse] = Field(default_factory=list)


class RuleFindingResponse(BaseModel):
    rule: str
    status: str = Field(description="ok | attention | violation")
    detail: str
    source: str = "knowledge_base/CINEMATIC_BIBLE.md"


class LibraryAuditResponse(BaseModel):
    styles_audited: int
    shots_audited: int
    rules: list[str] = Field(default_factory=list)
    compliant: list[str] = Field(default_factory=list)
    flagged: dict[str, list[RuleFindingResponse]] = Field(default_factory=dict)


class EpisodeConsistencyResponse(BaseModel):
    scenes: int
    consistent: bool
    grain: list[str] = Field(default_factory=list)
    lut: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    findings: list[RuleFindingResponse] = Field(default_factory=list)


class StyleExplanationResponse(BaseModel):
    style_id: str
    name: str
    explanation: str
    motivations: list[str] = Field(default_factory=list)
    lens_mm: int | None = None
    findings: list[RuleFindingResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ETAPA 6 — shot library (300 direction presets)
# ---------------------------------------------------------------------------


class ShotPresetResponse(BaseModel):
    code: str
    name: str
    family: str = ""
    frame: str = ""
    lens: str = ""
    lens_mm: int | None = Field(default=None, description="Focal length read by the cinematic grammar.")
    camera_path: str = ""
    speed: str = ""
    focus: str = ""
    shake: str = ""
    depth: str = ""
    lighting: str = ""
    intention: str = ""
    continuity: str = ""
    motivations: list[str] = Field(
        default_factory=list,
        description="Which CINEMATIC_BIBLE motivations this movement claims.",
    )


class ShotFamilyResponse(BaseModel):
    family: str
    label: str
    count: int


class ShotLibraryAuditResponse(BaseModel):
    total: int
    target: int
    meets_target: bool
    published: int
    expanded: int
    families: dict[str, int] = Field(default_factory=dict)
    violations: dict[str, list[str]] = Field(default_factory=dict)
    duplicates: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ETAPA 8 — storyboard engine (a brief cast into real shots)
#
# Named CoreStoryboard* to avoid colliding with the pre-existing
# StoryboardRequest/StoryboardScene/StoryboardResponse used by
# /api/v1/storyboards/expand, which is preserved unchanged.
# ---------------------------------------------------------------------------


class CoreStoryboardRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    scene_count: int = Field(default=5, ge=2, le=12)
    persona: str | None = Field(default=None, max_length=200)
    style: str | None = Field(default=None, max_length=120)
    camera_language: str | None = Field(default=None, max_length=200)
    duration_per_scene: float = Field(default=5.0, gt=0, le=30)


class CoreStoryboardShotResponse(BaseModel):
    number: int
    shot_code: str
    shot_name: str
    family: str
    frame: str
    lens: str
    camera_path: str
    lighting: str
    motion: str
    motivation: str = Field(description="Which CINEMATIC_BIBLE motivation the move claims.")
    intention: str
    continuity: str = Field(description="What the next scene has to match.")
    objective: str
    emotion: str
    duration_seconds: float


class CoreStoryboardFindingResponse(BaseModel):
    rule: str
    status: str = Field(description="violation | attention")
    detail: str


class CoreStoryboardResponse(BaseModel):
    brief: str
    format: str
    scene_count: int
    runtime_seconds: float
    lens_progression: list[str] = Field(default_factory=list)
    family_sequence: list[str] = Field(default_factory=list)
    shot_codes: list[str] = Field(default_factory=list)
    shots: list[CoreStoryboardShotResponse] = Field(default_factory=list)
    valid: bool = Field(description="False when any sequence rule is violated.")
    violations: list[CoreStoryboardFindingResponse] = Field(default_factory=list)
    attention: list[CoreStoryboardFindingResponse] = Field(default_factory=list)
    beat_sheet: str = Field(default="", description="Director-readable beat sheet, not a prompt.")


# ---------------------------------------------------------------------------
# ETAPA 9 — prompt compiler: a cast storyboard compiled scene by scene
# ---------------------------------------------------------------------------


class CoreStoryboardCompileRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    scene_count: int = Field(default=5, ge=2, le=12)
    persona_id: str | None = Field(default=None, max_length=120)
    style: str | None = Field(default=None, max_length=120)
    camera_language: str | None = Field(default=None, max_length=200)
    duration_per_scene: float = Field(default=5.0, gt=0, le=30)
    provider: str = Field(default="", max_length=60)
    negative_prompt: str = Field(default="", max_length=600)


class CompiledSceneResponse(BaseModel):
    number: int
    shot_code: str
    prompt: str
    negative_prompt: str
    tokens: list[str] = Field(default_factory=list)
    dropped: list[str] = Field(
        default_factory=list,
        description="Blocks dropped to fit the provider budget. Never silent.",
    )


class CoreStoryboardCompileResponse(BaseModel):
    brief: str
    format: str
    provider: str
    budget: int = Field(description="Character budget applied, per provider.")
    scene_count: int
    runtime_seconds: float
    valid: bool
    shot_codes: list[str] = Field(default_factory=list)
    scenes: list[CompiledSceneResponse] = Field(default_factory=list)
    violations: list[CoreStoryboardFindingResponse] = Field(default_factory=list)
    attention: list[CoreStoryboardFindingResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ETAPA 10 — provider adapters
# ---------------------------------------------------------------------------


class ProviderAdapterResponse(BaseModel):
    id: str
    label: str
    kind: str = Field(description="image | video")
    status: str = Field(description="local-provider | remote-provider | planned-provider")
    model_id: str = Field(default="", description="Checkpoint the adapter loads. Empty when there is no local adapter.")
    conditioning: list[str] = Field(default_factory=list)


class ProviderHealthResponse(BaseModel):
    id: str
    available: bool
    reason: str | None = None
    model_id: str = ""
    loaded: bool = False


class ProviderCatalogueResponse(BaseModel):
    adapters: list[ProviderAdapterResponse] = Field(default_factory=list)
    defaults: dict[str, str] = Field(
        default_factory=dict, description="What runs when a job names no provider, per kind."
    )


class ProviderCapabilitiesResponse(BaseModel):
    max_resolution: str
    supports_video: bool
    supports_image: bool
    supports_lora: bool
    supports_upscale: bool
    supports_seed: bool
    supports_negative_prompt: bool
    prompt_budget: int


class UniversalProviderResponse(BaseModel):
    id: str
    label: str
    status: str
    latency_ms: float
    version: str
    capabilities: ProviderCapabilitiesResponse
    reason: str | None = None
    loaded: bool = False
    #: PR009: when the health report was produced (UTC ISO-8601).
    last_health_at: str | None = None
    #: PR009: explicit availability flag (status == "ready").
    available: bool = False


class ProviderTelemetryResponse(BaseModel):
    """One provider execution as recorded by the executor (PR009)."""

    provider_id: str
    requested_provider_id: str
    spec_id: str
    kind: str
    success: bool
    error_code: str | None = None
    latency_ms: float
    queue_time_ms: float
    render_time_ms: float
    attempts: int = 1
    fallback: bool = False
    fallback_reason: str | None = None
    job_id: str | None = None
    at: str = ""


class ProviderTestResponse(BaseModel):
    """Outcome of the `/studio/providers` real test button (PR009)."""

    provider_id: str
    executed_provider_id: str
    kind: str
    success: bool
    fallback: bool
    fallback_reason: str | None = None
    error_code: str | None = None
    attempts: int = 0
    latency_ms: float = 0.0
    queue_time_ms: float = 0.0
    render_time_ms: float = 0.0
    asset_kind: str = ""
    asset_bytes: int = 0


class GenerationSpecResponse(BaseModel):
    """The compiled GenerationSpec. Providers receive exactly this (ETAPA 3)."""

    spec_id: str
    schema_version: str
    kind: str
    project_id: str | None = None
    user_id: str | None = None
    persona_id: str | None = None
    style_id: str | None = None
    prompt_original: str
    prompt_compiled: str
    negative_prompt: str = ""
    camera: str = ""
    lens: str = ""
    lighting: str = ""
    motion: str = ""
    weather: str = ""
    aspect_ratio: str = "16:9"
    fps: int = 24
    duration: float = 5.0
    provider: str = "flux-dev"
    seed: int | None = None
    lora: str | None = None
    controlnet: str = "none"
    # Sampling extras carried inside the spec (ETAPA 3). Exposed so a dry run
    # shows exactly what a provider will be handed instead of hiding it.
    resolution: int = 1024
    guidance_scale: float = 7.5
    steps: int = 28
    ip_adapter_scale: float = 0.7
    mode: str = "text-to-video"
    cinematic_mode: bool = True
    slow_motion: bool = False
    native_audio: bool = False
    motion_strength: float = 1.0
    reference_path: str | None = None
    tokens: list[str] = Field(default_factory=list)
    #: Which source won each contested field. Makes a look explainable.
    trace: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ETAPA 13 — video timeline
# ---------------------------------------------------------------------------


class TimelineRequest(BaseModel):
    """A brief plus whatever media has already been rendered for it.

    `sources` maps a 1-based scene number to the object key already produced for
    that scene. Scenes left out stay unrendered, and the response says so —
    a timeline never claims media exists that does not.
    """

    brief: str = Field(min_length=1, max_length=4000)
    scene_count: int = Field(default=5, ge=2, le=12)
    persona: str | None = Field(default=None, max_length=200)
    style: str = Field(default="cinematic realism", max_length=120)
    camera_language: str = Field(default="coherent camera movement", max_length=200)
    duration_per_scene: float = Field(default=5.0, gt=0, le=60)
    resolution: Literal["720p", "1080p", "2k", "4k"] = "1080p"
    fps: int = Field(default=24, ge=1, le=120)
    sources: dict[int, str] = Field(default_factory=dict)


class TimelineClipResponse(BaseModel):
    index: int
    shot_code: str
    family: str
    start_seconds: float
    duration_seconds: float
    end_seconds: float
    transition: str
    source: str = ""
    rendered: bool = False


class TimelineAudioResponse(BaseModel):
    #: The Director's own music language. Not a file: nothing synthesises audio.
    bed: str = ""
    fade_in_seconds: float = 1.0
    fade_out_seconds: float = 2.0
    declared: bool = False


class TimelineFindingResponse(BaseModel):
    rule: str
    status: str
    detail: str


class TimelineResponse(BaseModel):
    format: str
    clip_count: int
    duration_seconds: float
    aspect_ratio: str
    resolution: str
    width: int
    height: int
    fps: int
    #: True only when every clip has real media behind it.
    complete: bool
    rendered_clips: int
    unrendered_clips: list[int] = Field(default_factory=list)
    valid: bool
    violations: list[TimelineFindingResponse] = Field(default_factory=list)
    warnings: list[TimelineFindingResponse] = Field(default_factory=list)
    audio: TimelineAudioResponse
    clips: list[TimelineClipResponse] = Field(default_factory=list)


class TimelineFormatResponse(BaseModel):
    format: str
    aspect_ratio: str
    label: str


class TimelineCatalogueResponse(BaseModel):
    default_aspect_ratio: str
    default_resolution: str
    resolutions: dict[str, list[int]]
    transitions: list[str]
    formats: list[TimelineFormatResponse]


# ---------------------------------------------------------------------------
# ETAPA 14 — quality gate
# ---------------------------------------------------------------------------


class QualityAssessRequest(BaseModel):
    """A rendered artifact and the spec it was supposed to satisfy.

    `object_key` is resolved through the storage guard, so this endpoint can
    never be pointed at an arbitrary path on the worker's filesystem. The
    geometry is what the producer reported; the gate compares that claim against
    the spec, and says plainly when the pixels themselves were not read.
    """

    object_key: str = Field(min_length=1, max_length=1000)
    kind: Literal["image", "video"] = "image"
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0)
    fps: int = Field(default=0, ge=0, le=240)
    #: What the spec asked for.
    aspect_ratio: Literal["16:9", "1:1", "9:16", "4:3", "3:4"] = "16:9"
    requested_duration: float = Field(default=5.0, gt=0, le=600)
    requested_fps: int = Field(default=24, ge=1, le=240)


class QualityFindingResponse(BaseModel):
    rule: str
    status: str
    detail: str


class QualityReportResponse(BaseModel):
    spec_id: str = ""
    kind: str
    verdict: str
    #: False when something blocks delivery. Warnings do not block.
    ok: bool
    #: Share of applicable structural checks that passed — not an aesthetic score.
    structural_score: float
    checks_run: int
    checks_passed: int
    violations: list[QualityFindingResponse] = Field(default_factory=list)
    warnings: list[QualityFindingResponse] = Field(default_factory=list)
    facts: dict = Field(default_factory=dict)


class QualityRuleResponse(BaseModel):
    rule: str
    status: str
    detail: str


class QualityCapabilitiesResponse(BaseModel):
    assesses: list[str]
    #: Stated explicitly so no client can infer an aesthetic judgement.
    does_not_assess: list[str]
    model_loaded: bool
    note: str
    spec_fields_known: int
    rules: list[QualityRuleResponse]


# ---------------------------------------------------------------------------
# PR008 — Cinematic Render Engine
#
# The batch create request carries the Director plan inline: production plans
# are planning artifacts (PR005/PR006) and are not persisted server-side, so
# the client sends the storyboard it wants rendered.
# ---------------------------------------------------------------------------


class RenderSceneRequest(BaseModel):
    """One storyboard scene to render, as planned by the Director."""

    scene_number: int = Field(ge=1, le=64)
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=2000)
    emotion: str = Field(default="", max_length=200)
    camera: str = Field(default="", max_length=500)
    lens: str = Field(default="", max_length=200)
    lighting: str = Field(default="", max_length=500)
    motion: str = Field(default="", max_length=500)
    duration: float = Field(default=5.0, gt=0, le=600)
    environment: str = Field(default="", max_length=1000)
    mood: str = Field(default="", max_length=120)
    negative_prompt: str = Field(default="", max_length=2000)
    seed: int | None = Field(default=None, ge=0)


class RenderBatchCreateRequest(BaseModel):
    """Create a render batch from an inline Director plan."""

    scenes: list[RenderSceneRequest] = Field(min_length=1, max_length=64)
    kind: Literal["image", "video"] = "image"
    #: Opaque provider id resolved by the registry ("" = kind default).
    provider: str = Field(default="", max_length=80)
    project_id: str = Field(default="default-project", max_length=120)
    production_plan_id: str | None = Field(default=None, max_length=120)
    storyboard_version: int | None = Field(default=None, ge=1)
    persona_id: str | None = Field(default=None, max_length=120)
    style: str = Field(default="", max_length=500)
    mood: str = Field(default="", max_length=120)
    aspect_ratio: Literal["16:9", "1:1", "9:16", "4:3", "3:4"] = "16:9"
    fps: int = Field(default=24, ge=1, le=120)
    #: Base seed; scenes without their own seed get base + index.
    seed: int | None = Field(default=None, ge=0)


class RenderAssetResponse(BaseModel):
    scene_id: str
    scene_number: int
    kind: str
    object_key: str
    url: str
    thumbnail_key: str
    thumbnail_url: str
    metadata_key: str
    metadata_url: str
    prompt: str
    seed: int | None = None
    provider_id: str
    spec_id: str
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0
    fps: int = 0


class RenderSceneResponse(BaseModel):
    scene_id: str
    scene_number: int
    title: str
    status: str
    progress: int
    spec_id: str | None = None
    asset: RenderAssetResponse | None = None
    job: dict | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class RenderBatchResponse(BaseModel):
    batch_id: str
    workspace_id: str
    project_id: str
    kind: str
    provider: str
    status: str
    scenes: list[RenderSceneResponse] = Field(default_factory=list)
    production_plan_id: str | None = None
    storyboard_version: int | None = None
    persona_id: str | None = None
    style: str = ""
    aspect_ratio: str = "16:9"
    fps: int = 24
    seed: int | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    eta_seconds: float = 0.0
    progress: int = 0
    scene_count: int = 0
    completed_scenes: int = 0
    failed_scenes: int = 0
    current_scene_id: str | None = None
    current_scene_number: int | None = None


class RenderBatchSummaryResponse(BaseModel):
    """Queue UI row: everything the list needs, without per-scene payloads."""

    batch_id: str
    project_id: str
    kind: str
    provider: str
    status: str
    progress: int
    scene_count: int
    completed_scenes: int
    failed_scenes: int
    current_scene_number: int | None = None
    eta_seconds: float = 0.0
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class RenderRetryResponse(BaseModel):
    batch_id: str
    status: str
    retried_scenes: int
    message: str


# ---------------------------------------------------------------------------
# V3.1 — Cinematic Knowledge Graph
# ---------------------------------------------------------------------------


class GraphNodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    entity_type: str = Field(min_length=1, max_length=32)
    attributes: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    slug: str | None = Field(default=None, max_length=180)


class GraphNodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    entity_type: str | None = Field(default=None, min_length=1, max_length=32)
    attributes: dict[str, Any] | None = None
    aliases: list[str] | None = None


class GraphNodeResponse(BaseModel):
    id: str
    workspace_id: str
    entity_type: str
    name: str
    slug: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class GraphEdgeCreate(BaseModel):
    source_id: str = Field(min_length=1, max_length=36)
    target_id: str = Field(min_length=1, max_length=36)
    relation: str = Field(min_length=1, max_length=64)


class GraphEdgeResponse(BaseModel):
    id: str
    workspace_id: str
    source_id: str
    target_id: str
    relation: str
    inverse: str = ""
    created_at: str = ""


class GraphQueryMatchResponse(BaseModel):
    node: GraphNodeResponse
    score: int
    matched_fields: list[str] = Field(default_factory=list)


class GraphQueryResponse(BaseModel):
    query: str
    entity_type: str | None = None
    count: int
    matches: list[GraphQueryMatchResponse] = Field(default_factory=list)


class GraphNeighborsResponse(BaseModel):
    node: GraphNodeResponse
    depth: int
    direction: str
    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    edges: list[GraphEdgeResponse] = Field(default_factory=list)


class GraphCharacterRelationResponse(BaseModel):
    relation: str
    direction: str
    peer: GraphNodeResponse
    phrase: str


class GraphCharacterContextResponse(BaseModel):
    name: str
    found: bool
    persona_id: str | None = None
    node: GraphNodeResponse | None = None
    phrases: list[str] = Field(default_factory=list)
    relations: list[GraphCharacterRelationResponse] = Field(default_factory=list)
    relation_counts: dict[str, int] = Field(default_factory=dict)


class GraphSeedResponse(BaseModel):
    created_nodes: int
    created_edges: int
    skipped_nodes: int
    skipped_edges: int


# ---------------------------------------------------------------------------
# V3.2 — Character Continuity Engine
# ---------------------------------------------------------------------------


class ContinuityPersonaRequest(BaseModel):
    """Persona-global scope: identity and voice resolve in every campaign."""

    persona_id: str = Field(min_length=1, max_length=120)


class ContinuityScopeRequest(BaseModel):
    """Campaign scope with an optional per-episode override (None = default)."""

    persona_id: str = Field(min_length=1, max_length=120)
    campaign_id: str = Field(default="default", max_length=120)
    episode: int | None = Field(default=None, ge=1)


class ContinuityIdentityRequest(ContinuityPersonaRequest):
    face: str = Field(default="", max_length=500)
    hair: str = Field(default="", max_length=500)
    beard: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=500)
    skin: str = Field(default="", max_length=500)
    age_appearance: str = Field(default="", max_length=500)


class ContinuityIdentityResponse(BaseModel):
    persona_id: str
    face: str = ""
    hair: str = ""
    beard: str = ""
    body: str = ""
    skin: str = ""
    age_appearance: str = ""
    fingerprint: str = ""
    version: int = 1
    updated_at: str = ""


class ContinuityWardrobeRequest(ContinuityScopeRequest):
    outfit: str = Field(default="", max_length=500)
    accessories: str = Field(default="", max_length=500)
    colors: str = Field(default="", max_length=500)
    shoes: str = Field(default="", max_length=500)
    watch: str = Field(default="", max_length=500)


class ContinuityWardrobeResponse(BaseModel):
    persona_id: str
    campaign_id: str
    #: Where the returned lock was written; None means campaign default.
    source_episode: int | None = None
    outfit: str = ""
    accessories: str = ""
    colors: str = ""
    shoes: str = ""
    watch: str = ""
    fingerprint: str = ""
    version: int = 1
    updated_at: str = ""


class ContinuityLocationRequest(ContinuityScopeRequest):
    showroom: str = Field(default="", max_length=500)
    studio: str = Field(default="", max_length=500)
    street: str = Field(default="", max_length=500)
    city: str = Field(default="", max_length=500)
    base_lighting: str = Field(default="", max_length=500)


class ContinuityLocationResponse(BaseModel):
    persona_id: str
    campaign_id: str
    #: Where the returned lock was written; None means campaign default.
    source_episode: int | None = None
    showroom: str = ""
    studio: str = ""
    street: str = ""
    city: str = ""
    base_lighting: str = ""
    fingerprint: str = ""
    version: int = 1
    updated_at: str = ""


class ContinuityVehicleRequest(ContinuityScopeRequest):
    vehicle: str = Field(default="", max_length=500)
    color: str = Field(default="", max_length=500)
    plate: str = Field(default="", max_length=120)
    wheels: str = Field(default="", max_length=500)
    finish: str = Field(default="", max_length=500)


class ContinuityVehicleResponse(BaseModel):
    persona_id: str
    campaign_id: str
    #: Where the returned lock was written; None means campaign default.
    source_episode: int | None = None
    vehicle: str = ""
    color: str = ""
    plate: str = ""
    wheels: str = ""
    finish: str = ""
    fingerprint: str = ""
    version: int = 1
    updated_at: str = ""


class ContinuityVoiceRequest(ContinuityPersonaRequest):
    voice_profile: str = Field(default="", max_length=500)
    default_emotion: str = Field(default="", max_length=500)
    speed: str = Field(default="", max_length=120)
    intensity: str = Field(default="", max_length=120)


class ContinuityVoiceResponse(BaseModel):
    persona_id: str
    voice_profile: str = ""
    default_emotion: str = ""
    speed: str = ""
    intensity: str = ""
    fingerprint: str = ""
    version: int = 1
    updated_at: str = ""


class ContinuityResolveResponse(BaseModel):
    persona_id: str
    campaign_id: str
    episode: int
    identity: ContinuityIdentityResponse | None = None
    wardrobe: ContinuityWardrobeResponse | None = None
    location: ContinuityLocationResponse | None = None
    vehicle: ContinuityVehicleResponse | None = None
    voice: ContinuityVoiceResponse | None = None
    phrases: list[str] = Field(default_factory=list)
    fingerprints: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    drift: list[str] = Field(default_factory=list)
    consistent: bool = False
    block: str = ""


class ContinuityEpisodeCreate(BaseModel):
    persona_id: str = Field(min_length=1, max_length=120)
    campaign_id: str = Field(default="default", max_length=120)
    #: Omitted means "the next episode number" (max + 1, or 1).
    episode: int | None = Field(default=None, ge=1)
    title: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=2000)


class ContinuityEpisodeResponse(BaseModel):
    id: str
    workspace_id: str
    persona_id: str
    campaign_id: str
    episode: int
    title: str = ""
    notes: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
