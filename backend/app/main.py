"""FastAPI entrypoint for BROBOND AI STUDIO's local service boundary."""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .assets import (
    AssetLibraryEntryResponse,
    LibraryFilters,
    asset_library,
    parse_tags,
)
from .assets.library_schemas import build_entry_response
from .audit import audit
from .auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse, auth_rate_limiter, current_user, login, optional_user, register, ws_identity
from .conditioning import catalog
from .core.contracts import GenerationKind, GenerationSpec, GraphContext
from .core.director import CameraDirector, DirectorAgent as ProductionDirectorAgent
from .core import (
    ASPECT_BY_FORMAT,
    ASPECT_RATIOS as CORE_ASPECT_RATIOS,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_RESOLUTION,
    RESOLUTIONS,
    TRANSITIONS,
    CinematicLibrary,
    MAX_RUNTIME_SECONDS,
    MeasuredOutput,
    QualityGate,
    StoryboardEngine,
    VideoTimeline,
    FAMILY_LABELS,
    FULL_SHOT_LIBRARY,
    SeedShotSource,
    ShotLibrary,
    MemoryError_,
    PersonaLedger,
    PersonaMemoryEngine,
    PersonaNotFound,
    DirectorAgent,
    GenerationSpecBuilder,
    MemoryResolver,
    PromptCompiler,
    ShotResolver,
    StyleResolver,
)
from .continuity import (
    ContinuityRepositoryError,
    ContinuityResolver,
    ContinuityValidationError,
    IdentityLock,
    LocationLock,
    VehicleLock,
    VoiceLock,
    WardrobeLock,
    continuity_repo,
    continuity_store_for,
)
from .campaign import (
    CampaignValidationError,
    CampaignError,
    InvalidDeliveryError,
    UnknownAssetError,
    UnknownCampaignError,
    campaign_service,
)
from .quality import (
    APPROVED_AT,
    CRITERIA as QUALITY_CRITERIA,
    DEFAULT_WEIGHTS as QUALITY_DEFAULT_WEIGHTS,
    IMAGE_CRITERIA,
    ISSUE_BELOW,
    KIND_IMAGE,
    KIND_VIDEO,
    MASTERPIECE_AT,
    MediaFacts,
    QUALITY_ENGINE_VERSION,
    QUALITY_STATUSES,
    QualityEngine,
    QualityScorer,
    QualityValidationError,
    RETRY_BELOW,
    SOURCES as QUALITY_SOURCES,
    STRENGTH_AT,
    UPSCALE_SHORT_SIDE_BELOW,
    UnknownReportError,
    VIDEO_CRITERIA,
    quality_repo,
)
from .quality import UnknownAssetError as UnknownQualityAssetError
from .core.config import settings
from .core.database_guard import database_guard
from .db import SessionLocal, get_db
from .events import EVENT_CANCELLED, TERMINAL_STATUSES, hub, job_event
from .graph import (
    GraphRepositoryError,
    GraphValidationError,
    RelationshipError,
    character_graph_for,
    edge_view,
    graph_repo,
    inverse_of,
    node_view,
    relationship_engine_for,
    semantic_query_for,
)
from .knowledge import resolve as resolve_knowledge, seed_knowledge
from .lora import lora_trainer
from .media import MediaError, media
from .models import Asset, TrainingRun, User, Workspace
from .provider_capabilities import list_universal_provider_responses, prompt_budget_for_provider
from .providers import registry as provider_registry
from .providers.generation_executor import GenerationExecutor
from .providers.gpu_health import readiness_gpu_block
from .providers.provider_registry import DEFAULT_REGISTRY as UNIVERSAL_REGISTRY
from .providers.telemetry import default_telemetry_store
from .prompt_engine import prompt_engine
from .queue import enqueue, enqueue_lora_training, transition
from .readiness import readiness
from .render import (
    EVENT_BATCH_COMPLETED as RENDER_TERMINAL_EVENT,
    SceneRenderInput,
    render_hub,
    render_store,
)
from .render.render_orchestrator import RenderOrchestrator, default_persona_phrase
from .storage import storage
from .system import gpu_info
from .schemas import (
    AngleProfileResponse,
    QualityAssessRequest,
    QualityCapabilitiesResponse,
    QualityFindingResponse,
    QualityReportResponse,
    QualityRuleResponse,
    TimelineAudioResponse,
    TimelineCatalogueResponse,
    TimelineClipResponse,
    TimelineFindingResponse,
    TimelineFormatResponse,
    TimelineRequest,
    TimelineResponse,
    AssetResponse, ConditioningRequest, DirectorBriefResponse, DirectorProductionPlanRequest,
    DirectorProductionPlanResponse, DirectorRequest, DirectorShotPlanResponse, ExportRequest, ExportResponse,
    EpisodeConsistencyResponse,
    FrameProfileResponse,
    FramingResponse,
    GenerationSpecRequest, GenerationSpecResponse, GenerationType, KnowledgeResponse, LoraVersionResponse,
    ImageGenerationRequest, Job, JobResponse, JobStatus, Persona, PersonaCreateRequest,
    PersonaImageAddRequest,
    PersonaImageResponse,
    PersonaProfileResponse,
    PersonaRevisionResponse,
    PersonaUpdateRequest,
    PersonaWardrobeResponse,
    LensProfileResponse,
    LibraryAuditResponse,
    LightingProfileResponse,
    LightingResponse,
    MotivationResponse,
    PersonaHistoryResponse,
    PersonaMemoryResponse,
    PersonaRevisionRequest,
    PersonaTrainRequest, PersonaTrainResponse, PromptEnhanceRequest, PromptEnhanceResponse, SceneBeatResponse,
    PersonaTransitionRequest,
    PersonaVersionResponse,
    RuleFindingResponse,
    ShotFamilyResponse, ShotLibraryAuditResponse, ShotPresetResponse,
    CompiledSceneResponse, CoreStoryboardCompileRequest, CoreStoryboardCompileResponse,
    ProviderAdapterResponse, ProviderCatalogueResponse, ProviderHealthResponse,
    ProviderTelemetryResponse, ProviderTestResponse,
    UniversalProviderResponse,
    CoreStoryboardFindingResponse, CoreStoryboardRequest, CoreStoryboardResponse,
    CoreStoryboardShotResponse,
    StoryboardRequest, StoryboardResponse, StoryboardScene, VideoGenerationRequest,
    StyleExplanationResponse,
    TimeQualityResponse,
    TrainingStatusResponse,
    RenderBatchCreateRequest,
    RenderBatchResponse,
    RenderBatchSummaryResponse,
    RenderRetryResponse,
    GraphCharacterContextResponse,
    GraphCharacterRelationResponse,
    GraphEdgeCreate,
    GraphEdgeResponse,
    GraphNeighborsResponse,
    GraphNodeCreate,
    GraphNodeResponse,
    GraphNodeUpdate,
    GraphQueryMatchResponse,
    GraphQueryResponse,
    GraphSeedResponse,
    ContinuityEpisodeCreate,
    ContinuityEpisodeResponse,
    ContinuityIdentityRequest,
    ContinuityIdentityResponse,
    ContinuityLocationRequest,
    ContinuityLocationResponse,
    ContinuityResolveResponse,
    ContinuityVehicleRequest,
    ContinuityVehicleResponse,
    ContinuityVoiceRequest,
    ContinuityVoiceResponse,
    ContinuityWardrobeRequest,
    ContinuityWardrobeResponse,
    CampaignBriefingRequest,
    CampaignCreateRequest,
    CampaignDuplicateRequest,
    CampaignDeliverRequest,
    CampaignInterpretationResponse,
    CampaignBriefResponse,
    CampaignAssetResponse,
    CampaignEpisodeResponse,
    CampaignExportResponse,
    CampaignResponse,
    CampaignDetailResponse,
    QualityAssessAssetRequest,
    QualityAssetReportResponse,
    QualityConfigResponse,
    QualityCriterionResponse,
    QualityDecisionRequest,
)
from .repositories import PersonaRepositoryError, persona_repo
from .job_service import job_service
from .jobs import to_api_job, to_core_job

#: How often the queue WebSocket checks the event buffer, in seconds. The hub is
#: in-process and the worker runs synchronously, so the route polls rather than
#: blocking on a push it may never receive.
QUEUE_EVENT_POLL_SECONDS = 0.05


app = FastAPI(
    title="BROBOND AI STUDIO API",
    version="0.1.0",
    description="Local-first orchestration API for generative visual workflows.",
)
def _bootstrap_database(retries: int = 12, delay_seconds: float = 5.0) -> None:
    """Apply migrations and seed knowledge, retrying while the database is
    still booting. On Render the managed Postgres can take a few minutes to
    become reachable after a fresh blueprint deploy; retrying here avoids a
    crash-loop on first boot.

    PR002: the schema now comes from Alembic instead of `create_all` plus a
    manual `ALTER TABLE`. The initial migration is idempotent, so a legacy
    dev database created by the old bootstrap upgrades in place instead of
    needing to be dropped. Moving this out of import time is a later PR —
    the test suite opens 25 `TestClient`s that rely on the import-time
    bootstrap, and redesigning that fixture is out of scope here."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            alembic_config = AlembicConfig(str(alembic_ini))
            alembic_config.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
            command.upgrade(alembic_config, "head")
            with SessionLocal() as seed_db:
                seed_knowledge(seed_db)
            return
        except Exception as exc:  # pragma: no cover - depends on DB availability
            last_error = exc
            print(f"[brobond] database not ready (attempt {attempt}/{retries}): {exc}", flush=True)
            time.sleep(delay_seconds)
    raise RuntimeError(f"database bootstrap failed after {retries} attempts: {last_error}")


# PR009.4 — startup banner. Deliberately a bare print, never a log line that
# can be filtered out: the very first thing a deploy log shows is which
# database engine the process is really on. It goes to stderr so tools that
# import the app while capturing stdout (scripts/gen_api_doc.py) stay clean.
# The Render-without-Postgres case no longer reaches this point at all —
# `Settings.refuse_sqlite_on_render` raises RuntimeError before the app can
# boot on an ephemeral SQLite file.
print(f"[brobond] {settings.database_banner()}", file=sys.stderr, flush=True)

def _await_database(retries: int = 12, delay_seconds: float = 5.0) -> None:
    """PR009.4.1 — the database must answer before FastAPI accepts requests.

    `database_guard.verify()` proves the configured database answers
    ``SELECT 1`` within its 5-second deadline. The retry budget exists for
    the same reason `_bootstrap_database` has one: on a fresh Render
    blueprint deploy the managed Postgres can take minutes to become
    reachable. Once the budget is spent the guard's
    ``RuntimeError("PostgreSQL unavailable")`` propagates and the process
    never comes up — Render keeps the previous deploy live instead of
    marking a broken service healthy.
    """

    for attempt in range(1, retries + 1):
        try:
            database_guard.verify()
            return
        except RuntimeError:
            if attempt == retries:
                raise
            print(f"[brobond] database guard: no answer (attempt {attempt}/{retries})", flush=True)
            time.sleep(delay_seconds)


_await_database()
_bootstrap_database()

# ---------------------------------------------------------------------------
# BROBOND CORE — composition root (ETAPA 2)
#
# The ten Core components are instantiated here, at the application boundary,
# and never import each other: GenerationSpecBuilder receives the other four by
# injection. Routes hand intent to these objects and map the result back onto
# the API contract, so no generation logic lives in the HTTP layer.
# ---------------------------------------------------------------------------
# PersonaLedger is the single source of persona identity: PersonaMemoryEngine
# writes history into it and MemoryResolver reads from it, so a character
# approved through the API is immediately visible to the spec builder. The
# ledger seeds from the same canonical list the old SeedPersonaSource used.
cinematic_library = CinematicLibrary()
persona_ledger = PersonaLedger()
persona_engine = PersonaMemoryEngine(ledger=persona_ledger)


class _CompositePersonaSource:
    """PR003: persistent personas first, the character ledger as fallback.

    Implements the Core's `PersonaSource` protocol at the application
    boundary: the Core still imports no SQLAlchemy. `fetch` lets the spec
    builder resolve a persona by id whether it is a PostgreSQL row or a
    seeded character. `search` deliberately returns the ledger only:
    persistent personas are workspace-scoped product data and must never
    leak into the global character catalog (tenant privacy).
    """

    def __init__(self, ledger: PersonaLedger) -> None:
        self._ledger = ledger

    def fetch(self, persona_id: str):
        row = persona_repo.find_by_id(persona_id)
        if row is not None:
            return persona_repo.to_memory(row)
        return self._ledger.fetch(persona_id)

    def search(self, query: str = "") -> list:
        return self._ledger.search(query)


class _PersistentPersonaProfileSource:
    """PR003: `PersonaProfileSource` adapter over the persona repository.

    The MemoryResolver uses it in `resolve_persona`; the Core never sees a
    SQLAlchemy model, only the `PersonaProfile` contract.
    """

    def get_profile(self, persona_id: str):
        row = persona_repo.find_by_id(persona_id)
        return persona_repo.to_profile(row) if row is not None else None


memory_resolver = MemoryResolver(_CompositePersonaSource(persona_ledger), profile_source=_PersistentPersonaProfileSource())
style_resolver = StyleResolver()
# ETAPA 6: the resolver serves the full 300-shot library. SEED_SHOTS (the ten
# published presets) stays untouched; the expansion is composed in here, at the
# application boundary, so shot_resolver.py never imports shot_library.py.
shot_library = ShotLibrary()
shot_resolver = ShotResolver(SeedShotSource(FULL_SHOT_LIBRARY))
prompt_compiler = PromptCompiler()
director_agent = DirectorAgent()
production_director_agent = ProductionDirectorAgent(
    camera_director=CameraDirector(shot_library),
    prompt_compiler=prompt_compiler,
)
spec_builder = GenerationSpecBuilder(
    memory=memory_resolver,
    styles=style_resolver,
    shots=shot_resolver,
    compiler=prompt_compiler,
)

# ETAPA 8: the storyboard engine composes the Director, the 300-shot library and
# the cinematic grammar. It sits last because it depends on all three.
storyboard_engine = StoryboardEngine(
    director=director_agent,
    shots=shot_library,
    grammar=cinematic_library,
)

# ETAPA 13: the timeline assembles what the engine cast. It sits after the engine
# because it consumes the engine's shots, and it shares the engine's runtime
# ceiling so a sequence cannot pass one and fail the other.
video_timeline = VideoTimeline(max_runtime_seconds=MAX_RUNTIME_SECONDS)

# ETAPA 14: the same gate the worker runs, exposed for assessment on demand. One
# instance so a manual check and the worker's verdict cannot disagree.
quality_gate = QualityGate()

# V3.4: the Quality AI Engine — the aesthetic layer on top of the structural
# gate. One default instance for the common path; a request that re-balances
# weights builds its own engine so a caller's table never leaks into another
# request. It recommends only; nothing here executes a retry or an upscale.
quality_engine = QualityEngine()

# PR008: the Cinematic Render Engine. The orchestrator resolves persona
# identity through the same MemoryResolver the spec builder uses, so a locked
# persona renders the same phrase it compiles with everywhere else.
def _render_persona_phrase(persona_id: str | None) -> str:
    if not persona_id:
        return default_persona_phrase(None)
    persona = memory_resolver.resolve(persona_id)
    phrase = memory_resolver.identity_phrase(persona) if persona is not None else ""
    return phrase or default_persona_phrase(persona_id)


render_orchestrator = RenderOrchestrator(persona_phrase=_render_persona_phrase)

# PR009: executor behind the /studio/providers "Teste Real" button. Same
# registry/retry/timeout/fallback/telemetry stack every render crosses, so the
# button exercises the real path instead of a separate diagnostic one.
provider_test_executor = GenerationExecutor()

#: Deterministic seed for provider connectivity tests: the same test spec must
#: render the same way twice, so a diff means the provider changed.
PROVIDER_TEST_SEED = 7


def _provider_test_kind(provider_id: str) -> GenerationKind:
    """Video providers are tested with video, everyone else with image."""

    try:
        capabilities = UNIVERSAL_REGISTRY.capabilities(provider_id)
    except Exception:  # noqa: BLE001 - unknown ids fall through to image
        return GenerationKind.IMAGE
    return GenerationKind.VIDEO if capabilities.supports_video and not capabilities.supports_image else GenerationKind.IMAGE


def _provider_test_spec(provider_id: str, kind: GenerationKind) -> GenerationSpec:
    return GenerationSpec(
        prompt_original="provider connectivity test",
        prompt_compiled="BROBOND provider connectivity test — deterministic spec, no creative intent",
        provider=provider_id,
        kind=kind,
        seed=PROVIDER_TEST_SEED,
        aspect_ratio="1:1",
        resolution=256,
        duration=1.0,
        fps=8,
        mode="text-to-video" if kind is GenerationKind.VIDEO else "text-to-image",
    )


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-brobond-trace"],
)


@app.get("/", include_in_schema=False)
@app.head("/", include_in_schema=False)
def root() -> dict[str, str]:
    """Friendly landing route: hosting probes (Render sends `HEAD /`) and
    people who open the bare API URL get a 200 instead of a 404. The real
    health check remains `/api/v1/health`."""
    return {
        "service": "brobond-api",
        "status": "ok",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/health", tags=["system"])
@app.get("/api/v1/health", tags=["system"])
def health() -> JSONResponse:
    """Liveness with a real database probe (PR009.4.1).

    The payload reports what the guard measures right now, never a cached
    truth: if the database stops answering, the route answers 503 Service
    Unavailable — never 200 — and Render's health check takes the service
    out of rotation instead of routing traffic to a dead deploy.
    """

    connected = database_guard.ping()
    body = {
        "status": "ok" if connected else "unavailable",
        "service": "brobond-api",
        "mode": "local",
        "database": "connected" if connected else "disconnected",
        "provider": database_guard.provider(),
    }
    return JSONResponse(status_code=200 if connected else 503, content=body)


@app.get("/api/v1/system/gpu", tags=["system"])
def system_gpu() -> dict:
    return gpu_info()


def _migrations_ready() -> bool:
    """True when the database sits at Alembic's head revision (PR009.4.1).

    Read-only by design: it compares `alembic_version` against the script
    directory and never upgrades anything — schema changes remain the sole
    job of `_bootstrap_database` at startup.
    """

    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
    from sqlalchemy import text as sqla_text

    from .db import engine as db_engine

    try:
        alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        alembic_config = AlembicConfig(str(alembic_ini))
        alembic_config.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
        head = ScriptDirectory.from_config(alembic_config).get_current_head()
        with db_engine.connect() as connection:
            current = connection.execute(sqla_text("SELECT version_num FROM alembic_version")).scalar()
        return current == head
    except Exception:
        return False


def _storage_ready() -> bool:
    """True when the active storage backend accepts a write probe (PR009.4.1)."""

    try:
        if settings.storage_enabled:
            storage.client.head_bucket(Bucket=settings.minio_bucket)
            return True
        probe = storage.local_root / ".readiness-probe"
        probe.write_bytes(b"ok")
        probe.unlink()
        return True
    except Exception:
        return False


@app.get("/api/v1/system/readiness", tags=["system"])
def system_readiness() -> JSONResponse:
    """GPU preflight plus the PR009.4.1 deploy gates.

    PR011 adds a `gpu` block describing the external cluster (provider, model,
    VRAM, measured latency). It is informational: an unavailable cluster
    never turns this into a 503 and never raises.

    The three top-level booleans — `database`, `migrations`, `storage` —
    answer "can this deploy serve traffic?" independently of the GPU checks:
    a broken database or a half-applied migration returns 503 so an
    orchestrator never promotes the deploy.
    """

    body = readiness()
    body["database"] = database_guard.ping()
    body["migrations"] = _migrations_ready()
    body["storage"] = _storage_ready()
    # PR011 — the external GPU cluster, folded into the existing `gpu` block
    # beside the host detection it has always carried. Reported, never
    # enforced: it is a capability, not a deploy gate, so `gpu.available:
    # false` must not turn this response into a 503. The composer never raises.
    body["gpu"] = readiness_gpu_block(body.get("gpu"))
    deploy_ready = body["database"] and body["migrations"] and body["storage"]
    return JSONResponse(status_code=200 if deploy_ready else 503, content=body)


@app.get("/api/v1/system/media", tags=["system"])
def system_media() -> dict[str, object]:
    return media.capabilities()


@app.post("/api/v1/prompts/enhance", response_model=PromptEnhanceResponse, tags=["prompt-engine"])
def enhance_prompt(request: PromptEnhanceRequest) -> PromptEnhanceResponse:
    enhanced = prompt_engine.enhance(request.prompt, request.style, request.persona, request.camera, request.lighting)
    return PromptEnhanceResponse(original=request.prompt, enhanced=enhanced, tokens=enhanced.split(", "))


@app.get("/api/v1/models/conditioning", tags=["models"])
def conditioning_models() -> list[dict[str, str]]:
    return catalog()


@app.get("/api/v1/knowledge", response_model=list[KnowledgeResponse], tags=["knowledge"])
def knowledge(
    query: str | None = None,
    category: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeResponse]:
    """Search the knowledge base (PR002: identity required).

    The base contains persona PII (e.g. CHAR_PETRICK's full profile), so it
    is no longer publicly readable; the seed content is global and shared by
    every authenticated tenant, which is why there is no workspace filter
    here.
    """
    entries = resolve_knowledge(db, query=query, category=category)
    return [KnowledgeResponse.model_validate(entry, from_attributes=True) for entry in entries]


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
def register_user(
    request: RegisterRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    _rate_limited: None = Depends(auth_rate_limiter),
) -> TokenResponse:
    """Create an account (PR002: rate-limited and audited)."""
    try:
        result = register(request, db)
    except HTTPException:
        audit(db, actor=None, action="auth.register.failed", detail={"email": request.email}, request=http_request)
        raise
    audit(db, actor=result.user, action="auth.register", resource_type="user", resource_id=result.user.id, detail={"email": request.email}, request=http_request)
    return result


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["auth"])
def login_user(
    request: LoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    _rate_limited: None = Depends(auth_rate_limiter),
) -> TokenResponse:
    """Sign in (PR002: rate-limited, and every attempt — success or failure — audited)."""
    try:
        result = login(request, db)
    except HTTPException:
        audit(db, actor=None, action="auth.login.failed", detail={"email": request.email}, request=http_request)
        raise
    audit(db, actor=result.user, action="auth.login", resource_type="user", resource_id=result.user.id, request=http_request)
    return result


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["auth"])
def get_current_user(user: User = Depends(current_user)) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)


def _workspace_for(db: Session, user: User) -> Workspace | None:
    return db.scalar(select(Workspace).where(Workspace.owner_id == user.id))


def _queue_job(kind: GenerationType, prompt: str, parameters: dict | None = None, user: User | None = None, request: Request | None = None) -> Job:
    # PR004-prep: creation goes through the Core's JobService and its
    # injected JobRepository (default: the jobs table). The API object is
    # still what the route returns — only the path to persistence changed.
    job = Job(type=kind, prompt=prompt, parameters=parameters or {})
    job_service.create(to_core_job(job))
    # PR002: job creation is a critical action and is audited with the acting
    # user (or an anonymous mark) and the client address.
    audit(
        SessionLocal(),
        actor=user,
        action="job.created",
        resource_type="job",
        resource_id=str(job.id),
        workspace_id=job.parameters.get("workspace_id"),
        detail={"type": kind.value, "model": (parameters or {}).get("model")},
        request=request,
    )
    # Redis/Celery is optional in local development; the job remains inspectable.
    enqueue(str(job.id))
    return job


def _generation_parameters(request: ImageGenerationRequest | VideoGenerationRequest, user: User | None, db: Session) -> dict:
    parameters = request.model_dump(mode="json")
    if user:
        workspace = _workspace_for(db, user)
        if workspace:
            parameters["workspace_id"] = workspace.id
            # PR003: a request scoped to a persona inherits the persona's
            # trained LoRA (asset id) unless the caller picked one explicitly.
            # The worker resolves the asset workspace-scoped and puts the real
            # path on the spec — the same path user-selected LoRAs already use.
            if request.persona_id and parameters.get("lora_id") is None:
                persona = persona_repo.find_by_id(request.persona_id, workspace_id=workspace.id)
                if persona is not None and persona.lora_id:
                    parameters["lora_id"] = persona.lora_id
    return parameters


def _job_for_user(job_id: UUID, user: User, db: Session) -> Job:
    """Fetch a job and refuse anything the caller does not own.

    PR002: 404 rather than 403 so a token cannot be used to enumerate other
    tenants' job ids — the same rule the asset routes already apply.
    """

    core_job = job_service.get(str(job_id))
    job = to_api_job(core_job) if core_job is not None else None
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found")
    workspace = _workspace_for(db, user)
    if not workspace or job.parameters.get("workspace_id") != workspace.id:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


@app.post("/api/v1/generations/images", response_model=Job, status_code=202, tags=["generations"])
def create_image_generation(
    request: ImageGenerationRequest,
    http_request: Request,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> Job:
    """Create an image job. Authenticated jobs are persisted to the user's asset library."""
    return _queue_job(GenerationType.IMAGE, request.prompt, _generation_parameters(request, user, db), user=user, request=http_request)


@app.post("/api/v1/generations/videos", response_model=Job, status_code=202, tags=["generations"])
def create_video_generation(
    request: VideoGenerationRequest,
    http_request: Request,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> Job:
    """Create an H.264 video job for the configured video provider."""
    return _queue_job(GenerationType.VIDEO, request.prompt, _generation_parameters(request, user, db), user=user, request=http_request)


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse, tags=["generations"])
def get_job(job_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> JobResponse:
    """Read one of the caller's jobs (PR002: identity required)."""
    return JobResponse.from_job(_job_for_user(job_id, user, db))


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse, tags=["queue"])
def cancel_job(request: Request, job_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> JobResponse:
    """Cancel one of the caller's jobs (PR002: identity required).

    The cancellation goes through `transition()`, the single point where a
    job moves, so it is persisted and announced to any watching client —
    before PR002 a cancel mutated the in-memory object without emitting
    anything.
    """

    job = _job_for_user(job_id, user, db)
    if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
        transition(job, JobStatus.CANCELLED, event=EVENT_CANCELLED)
        audit(
            db,
            actor=user,
            action="job.cancelled",
            resource_type="job",
            resource_id=str(job.id),
            workspace_id=job.parameters.get("workspace_id"),
            request=request,
        )
    return JobResponse.from_job(job)


@app.websocket("/api/v1/queue/events/{job_id}")
async def queue_events(websocket: WebSocket, job_id: UUID) -> None:
    """Stream a job's transitions until it reaches a terminal state.

    ETAPA 11: this route used to send one snapshot and then block in
    `await websocket.receive_text()` — a read loop, not a push. The job could
    finish and the client would never hear about it, because nothing ever called
    `hub.publish`. It now drains the hub's event buffer and closes on a terminal
    status, so a client that connects late still gets the history and a clean end.

    PR002: the socket is authenticated before it is accepted. Browsers cannot
    set headers on a WebSocket handshake, so the bearer token rides the
    `token` query parameter (`auth.ws_identity`). A client that does not own
    the job is closed with the same 1008 reason an unknown job gets — a token
    must not let another tenant enumerate job ids.
    """

    with SessionLocal() as db:
        user = ws_identity(websocket.query_params.get("token"), db)
        if not user:
            await websocket.close(code=1008, reason="Authentication required")
            return
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
        if not workspace:
            await websocket.close(code=1008, reason="Authentication required")
            return
        _ws_core = job_service.get(str(job_id))
        job = to_api_job(_ws_core) if _ws_core is not None else None
        if not job or job.parameters.get("workspace_id") != workspace.id:
            await websocket.close(code=1008, reason="Generation job not found")
            return
        # External contract on the wire: the snapshot says `completed`, not
        # the internal `complete` (see schemas.JobResponse).
        snapshot = JobResponse.from_job(job).model_dump(mode="json")
    await hub.connect(job_id, websocket)
    try:
        # The current state first: a client must never have to wait for the next
        # transition to learn where the job already is.
        await websocket.send_json(snapshot)
        cursor = 0
        sent_terminal = False
        while True:
            events = hub.history(job_id, cursor)
            for event in events:
                await websocket.send_json(event)
                if event.get("event") in TERMINAL_STATUSES:
                    sent_terminal = True
            cursor += len(events)

            _current_core = job_service.get(str(job_id))
            current = to_api_job(_current_core) if _current_core is not None else None
            status = current.status.value if current else job.status.value
            if status in TERMINAL_STATUSES:
                # Only synthesise a closing event if the buffer did not already
                # carry one — otherwise a client sees `complete` twice.
                if not sent_terminal:
                    await websocket.send_json(
                        job_event(
                            job_id,
                            status=status,
                            progress=int(current.progress if current else job.progress),
                            event=status,
                            output_url=current.output_url if current else None,
                        )
                    )
                break
            await asyncio.sleep(QUEUE_EVENT_POLL_SECONDS)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(job_id, websocket)
        hub.forget(job_id)


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
    return [
        AssetResponse(
            id=a.id,
            name=a.name,
            kind=a.kind,
            object_key=a.object_key,
            url=storage.signed_url(a.object_key),
            created_at=a.created_at,
            # V3.4: the latest quality verdict rides along (ETAPA 6).
            quality_score=a.quality_score,
            quality_status=a.quality_status,
            quality_version=a.quality_version,
        )
        for a in assets
    ]


# ---------------------------------------------------------------------------
# PR013 — V4.0.1 Cinematic Asset Studio: the library surface.
#
# Additive by contract: the legacy `/assets/upload`, `/assets` and the
# download/conditioning/export flows keep their exact contracts, and the
# library's LEFT JOIN keeps every asset written before this PR visible
# (with `has_metadata = False` instead of invented fields). The three
# routes are declared **before** `/assets/download/{object_key:path}` on
# purpose: that route's path converter would otherwise swallow
# `/assets/library/...` and the library would answer 404 to itself.
# ---------------------------------------------------------------------------


@app.post("/api/v1/assets/library/upload", response_model=AssetLibraryEntryResponse, status_code=201, tags=["asset-library"])
async def upload_library_asset(
    request: Request,
    file: UploadFile = File(...),
    project: str = Form(""),
    persona: str = Form(""),
    provider: str = Form("upload"),
    seed: int | None = Form(None),
    tags: str = Form(""),
    before_asset_id: str | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AssetLibraryEntryResponse:
    """Upload a PNG/JPG/WEBP/MP4/MOV (multipart) with library metadata.

    Bytes go through the existing `StorageService`; the service probes the
    image, mints a thumbnail and persists `Asset` + `AssetMetadata` in one
    transaction. Nothing travels as JSON — this endpoint is multipart only.
    """
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    record = await asset_library.ingest(
        db,
        workspace.id,
        file=file,
        project=project,
        persona=persona,
        provider=provider,
        seed=seed,
        tags=parse_tags(tags),
        before_asset_id=before_asset_id,
    )
    audit(
        db,
        actor=user,
        action="asset.uploaded",
        resource_type="asset",
        resource_id=record.asset.id,
        workspace_id=workspace.id,
        detail={
            "content_type": record.metadata.content_type if record.metadata else None,
            "size_bytes": record.metadata.size_bytes if record.metadata else None,
            "thumbnail": record.metadata.thumbnail_key is not None if record.metadata else False,
        },
        request=request,
    )
    return build_entry_response(record, asset_library.url_for)


@app.get("/api/v1/assets/library", response_model=list[AssetLibraryEntryResponse], tags=["asset-library"])
def list_library_assets(
    kind: str | None = Query(None, pattern="^(image|video|audio|lora|metadata)$"),
    project: str | None = Query(None),
    persona: str | None = Query(None),
    provider: str | None = Query(None),
    min_score: int | None = Query(None, ge=0, le=100),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    q: str | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[AssetLibraryEntryResponse]:
    """List the workspace library with the ETAPA 5 filters applied.

    Every parameter is optional; omitted means unfiltered. `q` matches the
    asset name, its kind and every stored tag, case-insensitively.
    """
    workspace = _workspace_for(db, user)
    if not workspace:
        return []
    filters = LibraryFilters(
        kind=kind,
        project=project,
        persona=persona,
        provider=provider,
        min_score=min_score,
        date_from=date_from,
        date_to=date_to,
        query=q,
    )
    records = asset_library.list_records(db, workspace.id, filters)
    return [build_entry_response(record, asset_library.url_for) for record in records]


@app.get("/api/v1/assets/library/{asset_id}", response_model=AssetLibraryEntryResponse, tags=["asset-library"])
def get_library_asset(asset_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> AssetLibraryEntryResponse:
    """One library entry, with its before/after pair resolved when paired."""
    workspace = _workspace_for(db, user)
    record = asset_library.get_record(db, workspace.id, asset_id) if workspace else None
    if record is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    before = None
    if record.metadata is not None and record.metadata.before_asset_id:
        before = asset_library.get_record(db, workspace.id, record.metadata.before_asset_id)
    return build_entry_response(record, asset_library.url_for, before=before)


@app.get("/api/v1/assets/download/{object_key:path}", tags=["assets"])
def download_local_asset(
    object_key: str,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Serve a stored file (PR002: identity and tenant required).

    Object keys are namespaced `{workspace_id}/...`; the key must belong to
    the caller's workspace, so a token cannot be used to walk another
    tenant's files.
    """
    if settings.storage_enabled:
        raise HTTPException(status_code=404, detail="Use the signed MinIO URL")
    # Shape first, ownership second: an absolute or escaping key is rejected
    # by the path guard (400) before any tenant rule can classify it.
    try:
        path = storage.local_path(object_key)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid asset path") from error
    workspace = _workspace_for(db, user)
    if not workspace or object_key.split("/", 1)[0] != workspace.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    audit(db, actor=user, action="asset.downloaded", resource_type="asset", resource_id=object_key, workspace_id=workspace.id, request=request)
    return FileResponse(path)


@app.post("/api/v1/assets/{asset_id}/conditioning", response_model=AssetResponse, status_code=201, tags=["assets"])
def create_conditioning_asset(asset_id: str, request: ConditioningRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> AssetResponse:
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
    asset = db.get(Asset, asset_id)
    if not workspace or not asset or asset.workspace_id != workspace.id or asset.kind != "image":
        raise HTTPException(status_code=404, detail="Reference image not found")
    if request.mode == "pose":
        raise HTTPException(status_code=501, detail="OpenPose preprocessing requires the GPU worker")
    try:
        from PIL import Image, ImageFilter
        # ETAPA 12: `storage.download` serves both backends, so object storage
        # is no longer a reason to refuse. In local mode it returns the stored
        # file itself; from S3 it fetches to the same path.
        source = storage.download(asset.object_key, storage.local_path(asset.object_key))
        image = Image.open(source).convert("RGB")
        processed = image.convert("L") if request.mode == "depth" else image.filter(ImageFilter.FIND_EDGES) if request.mode == "edges" else image
        output = source.with_name(f"{source.stem}-{request.mode}.png")
        processed.save(output, format="PNG")
        key, url = storage.save_path(str(output), workspace.id, "image/png")
        derived = Asset(workspace_id=workspace.id, name=f"{asset.name}-{request.mode}.png", kind="image", object_key=key)
        db.add(derived)
        db.commit()
        db.refresh(derived)
        return AssetResponse(id=derived.id, name=derived.name, kind=derived.kind, object_key=key, url=url, created_at=derived.created_at)
    except ImportError as error:
        raise HTTPException(status_code=503, detail="Pillow is required for preprocessing") from error


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
    try:
        # ETAPA 12: the source is fetched through `storage.download` and the
        # result is pushed back with `upload_path`, so an export works the same
        # way on local disk and on S3. Before this the route answered 501 as
        # soon as object storage was on.
        output_key = f"{workspace.id}/exports/{asset.id}-{request.quality}.mp4"
        source = str(storage.download(asset.object_key, storage.local_path(asset.object_key)))
        destination = str(storage.local_path(output_key))
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        media.export_h264(source, destination, request.quality, request.fps)
        storage.upload_path(destination, output_key, "video/mp4")
        output_asset = Asset(workspace_id=workspace.id, name=f"{asset.name}-{request.quality}.mp4", kind="video", object_key=output_key)
        db.add(output_asset)
        db.commit()
        return ExportResponse(asset_id=output_asset.id, status="complete", output_url=storage.signed_url(output_key), message="H.264 export complete")
    except MediaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/v1/personas", response_model=Persona, status_code=202, tags=["personas"])
def create_persona(request: PersonaCreateRequest, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Persona:
    """Register a persona and reserve a future LoRA training job.

    PR002: identity required. PR003: the persona is persisted in PostgreSQL
    (`personas` + `persona_images` + the first `persona_identity_revision`
    row) — the response contract is unchanged, so PersonaStudio and the
    training flow keep working untouched. Reference ids are stored as-is
    (the legacy flow may reference assets created afterwards); the dedicated
    `/images` endpoint is the one that validates existence.
    """
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        row = persona_repo.create(
            workspace.id,
            name=request.name,
            age=request.age,
            height=request.height_m,
            body_type=request.appearance,
            eyes=request.eye_color,
            beard=request.beard,
            hair=request.hair,
            default_style=request.style,
            reference_asset_ids=[str(asset_id) for asset_id in request.reference_asset_ids],
            actor_id=user.id,
        )
    except PersonaRepositoryError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    persona = Persona(id=UUID(row.id), status="training", created_at=row.created_at, details=request, workspace_id=workspace.id)
    audit(db, actor=user, action="persona.created", resource_type="persona", resource_id=row.id, workspace_id=workspace.id, detail={"name": request.name, "slug": row.slug}, request=http_request)
    return persona


def _persona_profile_response(row, db: Session) -> PersonaProfileResponse:
    """Map a persona row (plus its children) onto the API response.

    Asset names/URLs are joined on the fly; a referenced asset that no longer
    exists still shows up (with null name/url) — references are historical.
    """
    images = [_persona_image_response(image, db) for image in persona_repo.images(row.id)]
    wardrobe = [PersonaWardrobeResponse(id=item.id, name=item.name, category=item.category, metadata=_wardrobe_metadata(item.metadata_json)) for item in persona_repo.wardrobe(row.id)]
    revisions = [
        PersonaRevisionResponse(
            id=revision.id,
            revision=revision.revision,
            notes=_wardrobe_metadata(revision.notes),
            created_by=revision.created_by,
            created_at=revision.created_at,
        )
        for revision in persona_repo.revisions(row.id)
    ]
    return PersonaProfileResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        slug=row.slug,
        age=row.age,
        height=row.height,
        body_type=row.body_type,
        skin_tone=row.skin_tone,
        hair=row.hair,
        beard=row.beard,
        eyes=row.eyes,
        voice=row.voice,
        default_style=row.default_style,
        lora_id=row.lora_id,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
        wardrobe=wardrobe,
        images=images,
        revisions=revisions,
    )


def _wardrobe_metadata(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


@app.get("/api/v1/personas", response_model=list[PersonaProfileResponse], tags=["personas"])
def list_persona_profiles(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[PersonaProfileResponse]:
    """List the caller's persistent persona profiles (PR003)."""
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return [_persona_profile_response(row, db) for row in persona_repo.list_workspace(workspace.id)]


@app.get("/api/v1/personas/{persona_id}", response_model=PersonaProfileResponse, tags=["personas"])
def get_persona_profile(persona_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PersonaProfileResponse:
    """Read one of the caller's persona profiles (PR003; foreign ids 404)."""
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    row = persona_repo.find_by_id(persona_id, workspace_id=workspace.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return _persona_profile_response(row, db)


@app.patch("/api/v1/personas/{persona_id}", response_model=PersonaProfileResponse, tags=["personas"])
def update_persona_profile(persona_id: str, request: PersonaUpdateRequest, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PersonaProfileResponse:
    """Partially update a persona profile (PR003).

    Identity changes bump ``revision`` and append an immutable
    ``persona_identity_revision`` row; ``wardrobe`` (when present) replaces
    the whole wardrobe. The slug is the stable identifier and never changes.
    """
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if persona_repo.find_by_id(persona_id, workspace_id=workspace.id) is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    changes = request.model_dump(exclude_unset=True)
    wardrobe_items = changes.pop("wardrobe", None)
    row = persona_repo.update(persona_id, changes, actor_id=user.id, wardrobe_items=wardrobe_items)
    if row is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    audit(db, actor=user, action="persona.updated", resource_type="persona", resource_id=row.id, workspace_id=workspace.id, detail={"fields": sorted(changes), "revision": row.revision}, request=http_request)
    return _persona_profile_response(row, db)


@app.delete("/api/v1/personas/{persona_id}", status_code=204, tags=["personas"])
def delete_persona_profile(persona_id: str, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete a persona profile and its children (PR003).

    Referenced assets and training-run history are untouched: the persona
    only pointed at them (append-only principle).
    """
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if persona_repo.find_by_id(persona_id, workspace_id=workspace.id) is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    persona_repo.delete(persona_id)
    audit(db, actor=user, action="persona.deleted", resource_type="persona", resource_id=persona_id, workspace_id=workspace.id, detail={}, request=http_request)


@app.get("/api/v1/personas/{persona_id}/images", response_model=list[PersonaImageResponse], tags=["personas"])
def list_persona_images(persona_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[PersonaImageResponse]:
    """List a persona's image references (PR003)."""
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    row = persona_repo.find_by_id(persona_id, workspace_id=workspace.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return [_persona_image_response(image, db) for image in persona_repo.images(row.id)]


def _persona_image_response(image, db: Session) -> PersonaImageResponse:
    asset = db.get(Asset, image.asset_id) if image.asset_id else None
    return PersonaImageResponse(
        id=image.id,
        asset_id=image.asset_id,
        image_type=image.image_type,
        order_index=image.order_index,
        name=asset.name if asset is not None else None,
        url=storage.signed_url(asset.object_key) if asset is not None else None,
    )


@app.post("/api/v1/personas/{persona_id}/images", response_model=PersonaImageResponse, status_code=201, tags=["personas"])
def add_persona_image(persona_id: str, request: PersonaImageAddRequest, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PersonaImageResponse:
    """Attach a stored image asset to a persona (PR003).

    The persona only references existing assets — no upload happens here.
    The asset must belong to the caller's workspace and be an image
    (404 otherwise); re-attaching the same asset is 409.
    """
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    row = persona_repo.find_by_id(persona_id, workspace_id=workspace.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    asset = db.get(Asset, request.asset_id)
    if asset is None or asset.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.kind != "image":
        raise HTTPException(status_code=422, detail="Only image assets can be attached to a persona")
    image = persona_repo.attach_image(persona_id, request.asset_id, request.image_type, request.order_index)
    if image is None:
        raise HTTPException(status_code=409, detail="Asset already attached to this persona")
    audit(db, actor=user, action="persona.image.attached", resource_type="persona_image", resource_id=image.id, workspace_id=workspace.id, detail={"persona_id": persona_id, "asset_id": request.asset_id, "image_type": request.image_type}, request=http_request)
    return PersonaImageResponse(id=image.id, asset_id=image.asset_id, image_type=image.image_type, order_index=image.order_index, name=asset.name, url=storage.signed_url(asset.object_key))


@app.post("/api/v1/personas/{persona_id}/train", response_model=PersonaTrainResponse, status_code=202, tags=["personas"])
def train_persona(persona_id: UUID, request: PersonaTrainRequest, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PersonaTrainResponse:
    """Queue LoRA training for one of the caller's personas (PR002: identity required).

    The route used to accept anonymous training (the last `optional_user` on
    a route that creates GPU work). Personas now carry the workspace that
    created them, and only that tenant can train them.
    """
    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    # PR003: personas live in PostgreSQL now — training reads the row, so it
    # survives restarts and every tenant's personas are isolated by the
    # workspace-scoped lookup (foreign ids 404, same as before).
    persona = persona_repo.find_by_id(str(persona_id), workspace_id=workspace.id)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    try:
        plan = lora_trainer.build_plan(str(persona_id), request.reference_asset_ids, persona.name, request.style)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    # Legacy contract: queueing a run refreshes the persona's reference set
    # with the exact assets the run will train on (face/body/style images
    # chosen through the profile screen are untouched).
    persona_repo.replace_references(str(persona_id), [str(asset_id) for asset_id in request.reference_asset_ids])
    run = TrainingRun(persona_id=str(persona_id), workspace_id=workspace.id, status="queued", progress=0, log="Training plan created")
    db.add(run)
    db.commit()
    db.refresh(run)
    queued = enqueue_lora_training(run.id, str(persona_id), run.workspace_id, [str(asset_id) for asset_id in request.reference_asset_ids], persona.name, request.style)
    message = "LoRA training job queued for a GPU worker" if queued else "Training run created; enable Redis and the GPU worker to execute it"
    audit(db, actor=user, action="persona.training.queued", resource_type="training_run", resource_id=run.id, workspace_id=workspace.id, detail={"persona_id": str(persona_id), "references": len(request.reference_asset_ids)}, request=http_request)
    return PersonaTrainResponse(persona_id=persona_id, run_id=UUID(run.id), status=run.status, progress=run.progress, image_count=plan.image_count, message=message)


@app.get("/api/v1/personas/{persona_id}/training/{run_id}", response_model=TrainingStatusResponse, tags=["personas"])
def training_status(persona_id: UUID, run_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> TrainingStatusResponse:
    """Read one of the caller's training runs (PR002: identity required)."""
    run = db.get(TrainingRun, str(run_id))
    if not run or run.persona_id != str(persona_id):
        raise HTTPException(status_code=404, detail="Training run not found")
    workspace = _workspace_for(db, user)
    if not workspace or run.workspace_id != workspace.id:
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
    # PR002: authenticate before accepting, same `token` query parameter as
    # the queue events socket, and require the run to belong to the caller's
    # tenant.
    with SessionLocal() as db:
        user = ws_identity(websocket.query_params.get("token"), db)
        if not user:
            await websocket.close(code=1008, reason="Authentication required")
            return
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
        run = db.get(TrainingRun, str(run_id)) if workspace else None
        if not workspace or not run or run.persona_id != str(persona_id) or run.workspace_id != workspace.id:
            await websocket.close(code=1008, reason="Training run not found")
            return
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
    """Expand a brief into connected, independently renderable scene prompts.

    Direction lives in the Core (`DirectorAgent.expand`) and prompt text lives
    in the Core (`PromptCompiler`). This route only maps Core output onto the
    API contract; the camera ladder and continuity lighting it used to build
    inline are now Core behaviour.
    """
    beats = director_agent.expand(
        request.brief,
        scene_count=request.scene_count,
        persona=request.persona,
        style=request.style,
        camera_language=request.camera_language,
    )
    scenes = [
        StoryboardScene(
            number=beat.number,
            title=f"Scene {beat.number:02d}",
            prompt=prompt_engine.compose_scene_prompt(
                request.brief,
                beat,
                persona=request.persona,
                style=request.style,
                scene_count=request.scene_count,
            ),
            duration_seconds=int(beat.duration_seconds),
        )
        for beat in beats
    ]
    return StoryboardResponse(brief=request.brief, scenes=scenes)


@app.post("/api/v1/core/direct", response_model=DirectorBriefResponse, tags=["core"])
def direct_intent(request: DirectorRequest) -> DirectorBriefResponse:
    """Turn a plain-language intention into direction.

    The caller never sends technical vocabulary and never receives a prompt:
    the answer is concept, script, scenes, cameras, music and duration. When
    the intention could follow more than one language, `clarification` carries
    one short question instead of a guess.
    """
    brief = director_agent.direct(
        request.intent,
        scene_count=request.scene_count,
        style=request.style,
        camera_language=request.camera_language,
        duration_per_scene=request.duration_per_scene,
    )
    return DirectorBriefResponse(
        concept=brief.concept,
        format=brief.format,
        logline=brief.logline,
        script=brief.script,
        beats=[SceneBeatResponse(**beat.to_dict()) for beat in brief.beats],
        camera_language=brief.camera_language,
        lighting_language=brief.lighting_language,
        music=brief.music,
        pacing=brief.pacing,
        style_hint=brief.style_hint,
        duration_seconds=brief.duration_seconds,
        scene_count=brief.scene_count,
        clarification=brief.clarification,
    )


@app.post(
    "/api/v1/core/director/production-plan",
    response_model=DirectorProductionPlanResponse,
    tags=["core"],
)
def create_director_production_plan(request: DirectorProductionPlanRequest) -> DirectorProductionPlanResponse:
    """Create a Director AI production plan. Planning only; no image generation."""

    plan = production_director_agent.create_production_plan(
        user_intent=request.user_intent,
        persona_id=request.persona_id,
        platform=request.platform,
        duration=request.duration,
        mood=request.mood,
    )
    payload = plan.to_dict()
    payload["shots"] = [DirectorShotPlanResponse(**shot.to_dict()) for shot in plan.shots]
    return DirectorProductionPlanResponse(**payload)


@app.post("/api/v1/core/compile", response_model=GenerationSpecResponse, tags=["core"])
def compile_generation_spec(
    request: GenerationSpecRequest,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> GenerationSpecResponse:
    """Compile a GenerationSpec without executing it (dry run).

    This is the observable boundary of the Core: it proves persona memory,
    style, shot and prompt compilation are actually wired together, and it is
    the object ETAPA 3 will hand to the providers. No media is generated.
    """
    workspace_id: str | None = None
    if user:
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
        workspace_id = workspace.id if workspace else None

    result = spec_builder.build_traced(
        prompt=request.prompt,
        kind=request.kind,
        project_id=request.project_id,
        user_id=workspace_id,
        persona_id=request.persona_id,
        # PR004: the compiler resolves identity, default style, LoRA and the
        # wardrobe automatically from the persona; `wardrobe` only narrows
        # the wardrobe block to the project's selection.
        wardrobe=request.wardrobe,
        style=request.style,
        shot=request.shot,
        provider=request.provider,
        aspect_ratio=request.aspect_ratio,
        fps=request.fps,
        duration=request.duration,
        seed=request.seed,
        lora=request.lora,
        controlnet=request.controlnet,
        camera=request.camera,
        lens=request.lens,
        lighting=request.lighting,
        motion=request.motion,
        weather=request.weather,
        negative_prompt=request.negative_prompt,
        resolution=request.resolution,
        guidance_scale=request.guidance_scale,
        steps=request.steps,
        ip_adapter_scale=request.ip_adapter_scale,
        mode=request.mode,
        cinematic_mode=request.cinematic_mode,
        slow_motion=request.slow_motion,
        native_audio=request.native_audio,
    )
    spec = result.spec
    return GenerationSpecResponse(
        **{key: value for key, value in spec.to_dict().items()},
        tokens=list(prompt_compiler.tokenize(spec.prompt_compiled)),
        trace=result.trace.to_dict(),
    )


@app.get("/api/v1/queue", response_model=list[JobResponse], tags=["queue"])
def list_queue(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[JobResponse]:
    """List the caller's generation queue (PR001: real data, no seed; PR002: identity required)."""
    workspace = _workspace_for(db, user)
    # PR004-prep: the listing comes from the JobRepository (workspace-scoped
    # by construction). A user without a workspace lists nothing — before the
    # refactor that edge case fell back to an unscoped query.
    if not workspace:
        return []
    return [JobResponse.from_job(to_api_job(core_job)) for core_job in job_service.list_by_workspace(workspace.id)]


# ---------------------------------------------------------------------------
# ETAPA 4 — persona memory: versioned, governed, attributed identity
#
# These routes only translate HTTP <-> engine calls and map MemoryError_ onto
# status codes. No identity rule is decided here.
# ---------------------------------------------------------------------------


def _persona_memory(persona_id: str) -> PersonaMemoryResponse:
    persona = persona_engine.resolve(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    return PersonaMemoryResponse(
        persona_id=persona.persona_id,
        name=persona.name,
        status=persona.status.value,
        version=persona.version,
        generable=persona_engine.is_generable(persona.persona_id),
        identity_phrase=persona_engine.identity_phrase(persona.persona_id),
        default_style=persona_engine.default_style(persona.persona_id),
        lora_path=persona_engine.lora_path(persona.persona_id),
        persona=persona.to_dict(),
    )


def _persona_history(persona_id: str) -> PersonaHistoryResponse:
    persona = persona_engine.resolve(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    report = persona_engine.drift(persona_id)
    return PersonaHistoryResponse(
        persona_id=persona.persona_id,
        name=persona.name,
        status=persona.status.value,
        version=persona.version,
        generable=persona_engine.is_generable(persona.persona_id),
        identity_versions=list(report["identity_versions"]),  # type: ignore[arg-type]
        changed_fields=dict(report["changed_fields"]),  # type: ignore[arg-type]
        identity_changed=bool(report["identity_changed"]),
        persona=persona.to_dict(),
        history=[PersonaVersionResponse(**entry.to_dict()) for entry in persona_engine.history(persona_id)],
    )


@app.get("/api/v1/core/personas", response_model=list[PersonaMemoryResponse], tags=["core"])
def list_persona_memory(query: str = "", user: User = Depends(current_user)) -> list[PersonaMemoryResponse]:
    """Current identities in the character library, with their version (PR002: identity required)."""

    return [_persona_memory(persona.persona_id) for persona in persona_engine.catalog(query)]


@app.get("/api/v1/core/personas/{persona_id}", response_model=PersonaHistoryResponse, tags=["core"])
def read_persona_memory(persona_id: str, user: User = Depends(current_user)) -> PersonaHistoryResponse:
    """A character's full history: every revision, who made it and why (PR002: identity required).

    Nothing is overwritten, so `history` grows monotonically and identity
    versions stay retrievable.
    """

    return _persona_history(persona_id)


@app.post("/api/v1/core/personas/{persona_id}/revise", response_model=PersonaVersionResponse, tags=["core"])
def revise_persona_memory(persona_id: str, request: PersonaRevisionRequest, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PersonaVersionResponse:
    """Apply an attributed edit (PR002: identity required, audited).

    Identity fields require `authorized: true`; without it the change is
    rejected with 409, because identity may never change silently.
    """

    changes = {
        name: value
        for name, value in request.model_dump(exclude={"actor", "reason", "authorized"}).items()
        if value is not None
    }
    try:
        entry = persona_engine.revise(
            persona_id,
            actor=request.actor,
            reason=request.reason,
            authorized=request.authorized,
            **changes,
        )
    except PersonaNotFound:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from None
    except MemoryError_ as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    audit(db, actor=user, action="persona.identity.revised", resource_type="persona", resource_id=persona_id, detail={"actor": request.actor, "reason": request.reason, "fields": sorted(changes)}, request=http_request)
    return PersonaVersionResponse(**entry.to_dict())


@app.post("/api/v1/core/personas/{persona_id}/approve", response_model=PersonaMemoryResponse, tags=["core"])
def approve_persona_memory(persona_id: str, request: PersonaTransitionRequest, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PersonaMemoryResponse:
    """Promote a planned character to approved (PR002: identity required, audited).

    Refuses with 409 when no identity attribute is defined: approval certifies
    an identity, it never invents one.
    """

    try:
        persona_engine.approve(persona_id, actor=request.actor, reason=request.reason or "identity approved")
    except PersonaNotFound:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from None
    except MemoryError_ as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    audit(db, actor=user, action="persona.identity.approved", resource_type="persona", resource_id=persona_id, detail={"actor": request.actor}, request=http_request)
    return _persona_memory(persona_id)


@app.post("/api/v1/core/personas/{persona_id}/retire", response_model=PersonaMemoryResponse, tags=["core"])
def retire_persona_memory(persona_id: str, request: PersonaTransitionRequest, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PersonaMemoryResponse:
    """Retire a character (PR002: identity required, audited). Episodes already made keep their memory snapshots."""

    try:
        persona_engine.retire(persona_id, actor=request.actor, reason=request.reason or "retired")
    except PersonaNotFound:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from None
    except MemoryError_ as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    audit(db, actor=user, action="persona.identity.retired", resource_type="persona", resource_id=persona_id, detail={"actor": request.actor}, request=http_request)
    return _persona_memory(persona_id)


@app.post("/api/v1/core/personas/{persona_id}/episodes/{episode_id}/snapshot", response_model=dict, tags=["core"])
def snapshot_persona_for_episode(persona_id: str, episode_id: str, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Bind the current identity to an episode (PR002: identity required, audited).

    This is what makes "existing episodes keep their original memory snapshot"
    true: later revisions do not reach back into this episode.
    """

    try:
        snapshot = persona_engine.remember(persona_id, episode_id=episode_id)
    except PersonaNotFound:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from None
    audit(db, actor=user, action="persona.identity.snapshot", resource_type="persona_episode", resource_id=episode_id, detail={"persona_id": persona_id}, request=http_request)
    return snapshot


@app.get("/api/v1/core/personas/{persona_id}/episodes/{episode_id}/memory", response_model=PersonaMemoryResponse, tags=["core"])
def recall_episode_memory(persona_id: str, episode_id: str, user: User = Depends(current_user)) -> PersonaMemoryResponse:
    """The identity an episode was actually made with, not the current one (PR002: identity required)."""

    persona = persona_engine.recall(episode_id, persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"{persona_id} has no memory snapshot for {episode_id}")
    return PersonaMemoryResponse(
        persona_id=persona.persona_id,
        name=persona.name,
        status=persona.status.value,
        version=persona.version,
        generable=persona.status.value == "approved",
        identity_phrase=persona_engine.memory.identity_phrase(persona),
        default_style=persona.default_style,
        lora_path=persona.lora_path,
        persona=persona.to_dict(),
    )


@app.get("/api/v1/core/personas/{persona_id}/continuity", response_model=dict, tags=["core"])
def persona_continuity(persona_id: str, episodes: list[str] = Query(default_factory=list), user: User = Depends(current_user)) -> dict:
    """Whether a character stayed consistent across the given episodes (PR002: identity required)."""

    if persona_engine.resolve(persona_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    return persona_engine.continuity(persona_id, episodes)

# ---------------------------------------------------------------------------
# ETAPA 5 — cinematic library: the grammar of the Bible and the rules it states
#
# Read-only. These routes expose reference data and normative checks; the rules
# themselves live in CinematicLibrary, and the vocabulary in the knowledge base.
# ---------------------------------------------------------------------------


@app.get("/api/v1/core/cinematic/lenses", response_model=list[LensProfileResponse], tags=["core"])
def cinematic_lenses() -> list[LensProfileResponse]:
    """The lens language: what each focal length is for."""

    return [LensProfileResponse(**profile.to_dict()) for profile in cinematic_library.lenses()]


@app.get("/api/v1/core/cinematic/lenses/for", response_model=list[LensProfileResponse], tags=["core"])
def cinematic_lenses_for(purpose: str = "") -> list[LensProfileResponse]:
    """Which focal lengths serve a purpose. `purpose=isolation` -> 135mm."""

    return [LensProfileResponse(**profile.to_dict()) for profile in cinematic_library.lens_for(purpose)]


@app.get("/api/v1/core/cinematic/framing", response_model=FramingResponse, tags=["core"])
def cinematic_framing() -> FramingResponse:
    """Shot sizes and angles. Angle is meaning: low angle creates presence."""

    return FramingResponse(
        frames=[FrameProfileResponse(**frame.to_dict()) for frame in cinematic_library.framing()],
        angles=[AngleProfileResponse(**angle.to_dict()) for angle in cinematic_library.angles()],
    )


@app.get("/api/v1/core/cinematic/lighting", response_model=LightingResponse, tags=["core"])
def cinematic_lighting() -> LightingResponse:
    """Light roles and the tone each light quality supports."""

    return LightingResponse(
        lights=[LightingProfileResponse(**light.to_dict()) for light in cinematic_library.lighting()],
        time_qualities=[
            TimeQualityResponse(**quality.to_dict()) for quality in cinematic_library.time_qualities()
        ],
    )


@app.get("/api/v1/core/cinematic/motivations", response_model=list[MotivationResponse], tags=["core"])
def cinematic_motivations() -> list[MotivationResponse]:
    """The five legitimate reasons to move the camera."""

    return [MotivationResponse(**motivation.to_dict()) for motivation in cinematic_library.motivations()]


@app.get("/api/v1/core/cinematic/motivations/of", response_model=dict, tags=["core"])
def cinematic_motivation_of(motion: str) -> dict:
    """Which motivations a camera move can claim, and whether it is still."""

    return {
        "motion": motion,
        "motivations": list(cinematic_library.motivation_of(motion)),
        "still": cinematic_library.is_still(motion),
        "motivated": cinematic_library.is_motivated(motion),
        "claims_without_naming": cinematic_library.claims_motivation_without_naming(motion),
    }


@app.get("/api/v1/core/cinematic/audit", response_model=LibraryAuditResponse, tags=["core"])
def cinematic_audit() -> LibraryAuditResponse:
    """Audit the library against the Bible and report what does not comply.

    The library's own exceptions are reported rather than hidden: a rule that is
    never checked against the seeds is a rule nobody follows.
    """

    report = cinematic_library.audit_library(
        style_resolver.catalog(), shot_resolver.catalog()
    )
    return LibraryAuditResponse(
        styles_audited=int(report["styles_audited"]),  # type: ignore[arg-type]
        shots_audited=int(report["shots_audited"]),  # type: ignore[arg-type]
        rules=list(report["rules"]),  # type: ignore[arg-type]
        compliant=list(report["compliant"]),  # type: ignore[arg-type]
        flagged={
            identifier: [RuleFindingResponse(**item) for item in items]
            for identifier, items in dict(report["flagged"]).items()  # type: ignore[arg-type]
        },
    )


@app.get("/api/v1/core/cinematic/explain", response_model=StyleExplanationResponse, tags=["core"])
def cinematic_explain(style: str = "") -> StyleExplanationResponse:
    """Director-facing prose for a style: what it is and why it looks that way.

    An unknown style resolves to the neutral fallback, exactly as the compiler
    would resolve it, so the explanation never describes a look that will not
    be rendered.
    """

    preset = style_resolver.resolve(style)
    return StyleExplanationResponse(
        style_id=preset.style_id,
        name=preset.name,
        explanation=cinematic_library.explain(preset),
        motivations=list(cinematic_library.motivation_of(preset.camera_motion)),
        lens_mm=cinematic_library.focal_of(preset.lens),
        findings=[
            RuleFindingResponse(**finding.to_dict()) for finding in cinematic_library.audit_style(preset)
        ],
    )


@app.get("/api/v1/core/cinematic/consistency", response_model=EpisodeConsistencyResponse, tags=["core"])
def cinematic_consistency(styles: list[str] = Query(default_factory=list)) -> EpisodeConsistencyResponse:
    """"Grain is subtle and consistent across an episode."

    Pass the styles of the scenes in order. Grain drift is a violation because
    the Bible states it outright; grade and palette drift are attention.
    """

    presets = [style_resolver.resolve(style_id) for style_id in styles]
    report = cinematic_library.episode_consistency(presets)
    return EpisodeConsistencyResponse(
        scenes=int(report["scenes"]),  # type: ignore[arg-type]
        consistent=bool(report["consistent"]),
        grain=list(report["grain"]),  # type: ignore[arg-type]
        lut=list(report["lut"]),  # type: ignore[arg-type]
        palette=list(report["palette"]),  # type: ignore[arg-type]
        findings=[RuleFindingResponse(**item) for item in report["findings"]],  # type: ignore[arg-type]
    )

# ---------------------------------------------------------------------------
# ETAPA 6 — shot library: the visual shot browser SHOT_LIBRARY.md calls for
#
# "A shot is a reusable direction preset, not a prompt blob." These routes let a
# director pick a function instead of typing a code. Read-only: the library is a
# reference, and shot codes are stable identifiers.
# ---------------------------------------------------------------------------


@app.get("/api/v1/core/shots", response_model=list[ShotPresetResponse], tags=["core"])
def list_shots(
    q: str = "",
    family: str = "",
    lens_mm: int | None = None,
    frame: str = "",
    motivation: str = "",
    limit: int = 50,
) -> list[ShotPresetResponse]:
    """Browse the 300-shot library by function, lens, frame or motivation.

    Filters combine. `limit` keeps the payload sane for a picker UI; the full
    library is reachable through the filters.
    """

    shots = shot_library.search(q)
    if family:
        shots = [shot for shot in shots if shot.family == family]
    if lens_mm is not None:
        shots = [shot for shot in shots if shot_library.grammar.focal_of(shot.lens) == lens_mm]
    if frame:
        shots = [shot for shot in shots if shot.frame.casefold() == frame.casefold()]
    if motivation:
        shots = [shot for shot in shots if motivation.casefold() in shot_library.motivations_of(shot)]
    return [ShotPresetResponse(**shot_library.as_directable(shot)) for shot in shots[: max(0, limit)]]


@app.get("/api/v1/core/shots/families", response_model=list[ShotFamilyResponse], tags=["core"])
def list_shot_families() -> list[ShotFamilyResponse]:
    """The narrative families and how many shots each holds."""

    counts = shot_library.family_counts()
    return [
        ShotFamilyResponse(family=family, label=FAMILY_LABELS.get(family, family.title()), count=counts.get(family, 0))
        for family in shot_library.families()
    ] + (
        [ShotFamilyResponse(family="published", label="Published presets", count=counts.get("published", 0))]
        if counts.get("published")
        else []
    )


@app.get("/api/v1/core/shots/audit", response_model=ShotLibraryAuditResponse, tags=["core"])
def audit_shot_library() -> ShotLibraryAuditResponse:
    """Library-wide compliance report against the CINEMATIC_BIBLE.

    Size is worthless if the entries contradict the document, so the report
    states total, target, per-family counts and every violation.
    """

    report = shot_library.audit()
    return ShotLibraryAuditResponse(
        total=int(report["total"]),  # type: ignore[arg-type]
        target=int(report["target"]),  # type: ignore[arg-type]
        meets_target=bool(report["meets_target"]),
        published=int(report["published"]),  # type: ignore[arg-type]
        expanded=int(report["expanded"]),  # type: ignore[arg-type]
        families={key: int(value) for key, value in dict(report["families"]).items()},  # type: ignore[arg-type]
        violations={code: list(issues) for code, issues in dict(report["violations"]).items()},  # type: ignore[arg-type]
        duplicates=list(report["duplicates"]),  # type: ignore[arg-type]
    )


@app.get("/api/v1/core/shots/{shot_code}", response_model=ShotPresetResponse, tags=["core"])
def read_shot(shot_code: str) -> ShotPresetResponse:
    """One shot, with the grammar read off it. 404 rather than a silent fallback."""

    shot = shot_library.get(shot_code)
    if shot is None:
        raise HTTPException(status_code=404, detail=f"unknown shot code: {shot_code}")
    return ShotPresetResponse(**shot_library.as_directable(shot))

# ---------------------------------------------------------------------------
# ETAPA 8 — storyboard engine: a brief cast into real shots from the library
#
# The pre-existing POST /api/v1/storyboards/expand is untouched. This endpoint
# returns a *cast* storyboard: every scene names a shot code, and lens,
# lighting, movement and continuity come from the library rather than from a
# placeholder string.
# ---------------------------------------------------------------------------


@app.post("/api/v1/core/storyboard", response_model=CoreStoryboardResponse, tags=["core"])
def build_core_storyboard(request: CoreStoryboardRequest) -> CoreStoryboardResponse:
    """Cast a brief into an ordered shot sequence and validate it.

    The Director supplies the beats and the detected format; the engine supplies
    the shot for each beat and reports whether the sequence holds together. No
    prompt text is produced here — that stays with the PromptCompiler.
    """

    storyboard = storyboard_engine.build(
        request.brief,
        scene_count=request.scene_count,
        persona=request.persona,
        style=request.style,
        camera_language=request.camera_language,
        duration_per_scene=request.duration_per_scene,
    )
    report = storyboard_engine.validate(storyboard)
    return CoreStoryboardResponse(
        brief=storyboard.brief,
        format=storyboard.format,
        scene_count=storyboard.scene_count,
        runtime_seconds=storyboard.runtime_seconds,
        lens_progression=list(storyboard.lens_progression),
        family_sequence=list(storyboard.family_sequence),
        shot_codes=list(storyboard.shot_codes),
        shots=[CoreStoryboardShotResponse(**shot.to_dict()) for shot in storyboard.shots],
        valid=bool(report["valid"]),
        violations=[CoreStoryboardFindingResponse(**item) for item in report["violations"]],  # type: ignore[arg-type]
        attention=[CoreStoryboardFindingResponse(**item) for item in report["attention"]],  # type: ignore[arg-type]
        beat_sheet=storyboard_engine.beat_sheet(storyboard),
    )

# ---------------------------------------------------------------------------
# ETAPA 9 — prompt compiler: the storyboard cast in ETAPA 8, compiled per scene
#
# The route only wires two Core components together. All composition happens in
# StoryboardEngine and PromptCompiler.
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/core/storyboard/compile",
    response_model=CoreStoryboardCompileResponse,
    tags=["core"],
)
def compile_core_storyboard(request: CoreStoryboardCompileRequest) -> CoreStoryboardCompileResponse:
    """Cast a brief into shots, then compile one prompt per scene.

    Persona identity, style name and colour grade are resolved here and handed to
    the compiler as finished phrases, because the compiler never calls a resolver
    — that independence is a guarded invariant.
    """

    storyboard = storyboard_engine.build(
        request.brief,
        scene_count=request.scene_count,
        persona=request.persona_id,
        style=request.style,
        camera_language=request.camera_language,
        duration_per_scene=request.duration_per_scene,
    )
    persona = memory_resolver.resolve(request.persona_id) if request.persona_id else None
    style = style_resolver.resolve(request.style) if request.style else style_resolver.resolve_default()
    provider_budget = prompt_budget_for_provider(
        request.provider,
        default_budget=prompt_compiler.budget_for(),
    )
    compiled = prompt_compiler.compile_beats(
        storyboard_engine.as_beats(storyboard),
        brief=storyboard.brief,
        persona=memory_resolver.identity_phrase(persona),
        environment=style_resolver.environment_phrase(style),
        color=style_resolver.color_phrase(style),
        style=style_resolver.style_phrase(style),
        negative=request.negative_prompt,
        provider=request.provider,
        budget=provider_budget,
    )
    report = storyboard_engine.validate(storyboard)
    return CoreStoryboardCompileResponse(
        brief=storyboard.brief,
        format=storyboard.format,
        provider=request.provider,
        budget=prompt_compiler.budget_for(request.provider, budget=provider_budget),
        scene_count=storyboard.scene_count,
        runtime_seconds=storyboard.runtime_seconds,
        valid=bool(report["valid"]),
        shot_codes=list(storyboard.shot_codes),
        scenes=[
            CompiledSceneResponse(
                number=shot.number,
                shot_code=shot.shot_code,
                prompt=item.prompt,
                negative_prompt=item.negative_prompt,
                tokens=list(item.tokens),
                dropped=list(item.dropped),
            )
            for shot, item in zip(storyboard.shots, compiled)
        ],
        violations=[CoreStoryboardFindingResponse(**item) for item in report["violations"]],  # type: ignore[arg-type]
        attention=[CoreStoryboardFindingResponse(**item) for item in report["attention"]],  # type: ignore[arg-type]
    )

# ---------------------------------------------------------------------------
# ETAPA 13 — video timeline: the assembly of a cast sequence into one cut
#
# The route wires the engine's shots into the timeline and returns the plan plus
# its validation. It contains no timing or transition logic of its own — that is
# VideoTimeline's, and no rendering: a plan is not a file.
# ---------------------------------------------------------------------------


@app.post("/api/v1/core/timeline", response_model=TimelineResponse, tags=["core"])
def build_timeline(request: TimelineRequest) -> TimelineResponse:
    """Assemble a brief into an ordered cut and report whether it holds.

    Nothing is rendered here. Scenes whose media has not been produced yet come
    back as unrendered clips, and `complete` stays false until every one of them
    has a real source — the response never claims a file that does not exist.
    """

    storyboard = storyboard_engine.build(
        request.brief,
        scene_count=request.scene_count,
        persona=request.persona,
        style=request.style,
        camera_language=request.camera_language,
        duration_per_scene=request.duration_per_scene,
    )
    intent = director_agent.direct(
        request.brief,
        scene_count=request.scene_count,
        style=request.style,
        camera_language=request.camera_language,
        duration_per_scene=request.duration_per_scene,
    )
    timeline = video_timeline.from_storyboard(
        storyboard,
        intent=intent,
        sources=request.sources,
        resolution=request.resolution,
        fps=request.fps,
    )
    report = video_timeline.validate(timeline)
    return TimelineResponse(
        format=timeline.format,
        clip_count=timeline.clip_count,
        duration_seconds=timeline.duration_seconds,
        aspect_ratio=timeline.aspect_ratio,
        resolution=timeline.resolution,
        width=timeline.width,
        height=timeline.height,
        fps=timeline.fps,
        complete=timeline.is_complete,
        rendered_clips=len(timeline.rendered_clips),
        unrendered_clips=[clip.index for clip in timeline.unrendered_clips],
        valid=bool(report["valid"]),
        violations=[TimelineFindingResponse(**item) for item in report["violations"]],  # type: ignore[arg-type]
        warnings=[TimelineFindingResponse(**item) for item in report["warnings"]],  # type: ignore[arg-type]
        audio=TimelineAudioResponse(**timeline.audio.to_dict()),
        clips=[TimelineClipResponse(**clip.to_dict()) for clip in timeline.clips],
    )


@app.get("/api/v1/core/timeline/formats", response_model=TimelineCatalogueResponse, tags=["core"])
def list_timeline_formats() -> TimelineCatalogueResponse:
    """Which frame each narrative format ships in, and what the cut can be.

    Read straight off the Core tables; the route holds no mapping of its own.
    """

    return TimelineCatalogueResponse(
        default_aspect_ratio=DEFAULT_ASPECT_RATIO,
        default_resolution=DEFAULT_RESOLUTION,
        resolutions={name: [width, height] for name, (width, height) in RESOLUTIONS.items()},
        transitions=list(TRANSITIONS),
        formats=[
            TimelineFormatResponse(
                format=name,
                aspect_ratio=aspect,
                label=FAMILY_LABELS.get(name, name),
            )
            for name, aspect in ASPECT_BY_FORMAT.items()
        ],
    )


# ---------------------------------------------------------------------------
# ETAPA 14 — quality gate: does the artifact match what was asked for
#
# The route resolves the object key through the storage guard and hands the
# result to the Core gate. It holds no thresholds and makes no judgement of its
# own, and it never assesses aesthetics — the capabilities endpoint says so.
# ---------------------------------------------------------------------------


@app.post("/api/v1/core/quality/assess", response_model=QualityReportResponse, tags=["core"])
def assess_quality(request: QualityAssessRequest) -> QualityReportResponse:
    """Check a rendered artifact against the spec it was supposed to satisfy.

    Structural checks only: the file, its size, the reported geometry against the
    requested ratio, and — for video — duration and frame rate. No model is
    loaded and no aesthetic score is produced.
    """

    try:
        resolved = str(storage.local_path(request.object_key))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid asset path") from error

    spec = GenerationSpec(
        prompt_original="",
        prompt_compiled="",
        aspect_ratio=request.aspect_ratio,
        duration=request.requested_duration,
        fps=request.requested_fps,
        kind=GenerationKind.VIDEO if request.kind == "video" else GenerationKind.IMAGE,
    )
    measured = MeasuredOutput(
        path=resolved,
        width=request.width,
        height=request.height,
        duration_seconds=request.duration_seconds,
        fps=request.fps,
        size_bytes=quality_gate.size_of(resolved),
    )
    report = quality_gate.assess(spec, measured)
    return QualityReportResponse(
        kind=report.kind,
        verdict=report.verdict,
        ok=report.ok,
        structural_score=report.structural_score,
        checks_run=report.checks_run,
        checks_passed=report.checks_passed,
        violations=[QualityFindingResponse(**item) for item in report.violations],
        warnings=[QualityFindingResponse(**item) for item in report.warnings],
        facts=report.facts,
    )


@app.get("/api/v1/core/quality/rules", response_model=QualityCapabilitiesResponse, tags=["core"])
def list_quality_rules() -> QualityCapabilitiesResponse:
    """What the gate checks, what it explicitly does not, and why.

    The `does_not_assess` list is the point: composition, prompt adherence and
    aesthetic quality are not judged here, because nothing in this process can
    see the image. Saying so is better than a number that implies otherwise.
    """

    capabilities = quality_gate.capabilities()
    return QualityCapabilitiesResponse(
        assesses=list(capabilities["assesses"]),  # type: ignore[arg-type]
        does_not_assess=list(capabilities["does_not_assess"]),  # type: ignore[arg-type]
        model_loaded=bool(capabilities["model_loaded"]),
        note=str(capabilities["note"]),
        spec_fields_known=int(capabilities["spec_fields_known"]),  # type: ignore[arg-type]
        rules=[QualityRuleResponse(**rule) for rule in quality_gate.rules()],
    )


# ---------------------------------------------------------------------------
# ETAPA 10 / PR007 — provider adapters: what can run, and what it would run
#
# The registries are the single source of truth for adapter selection. These
# routes expose them; they contain no model-name selection logic of their own.
# ---------------------------------------------------------------------------


@app.get("/api/v1/providers", response_model=list[UniversalProviderResponse], tags=["providers"])
def list_universal_providers() -> list[UniversalProviderResponse]:
    """Universal provider health, latency, version and capabilities (PR007)."""

    return list_universal_provider_responses()


@app.post("/api/v1/providers/{provider_id}/test", response_model=ProviderTestResponse, tags=["providers"])
def run_provider_real_test(provider_id: str) -> ProviderTestResponse:
    """PR009 real test: run a deterministic test spec through the full path.

    The spec crosses the same executor every render uses — registry, health
    gate, retry engine, timeout manager, fallback chain and telemetry — so the
    answer describes what would really happen to a job, not what the health
    probe hopes.
    """

    kind = _provider_test_kind(provider_id)
    spec = _provider_test_spec(provider_id, kind)
    output_dir = Path(settings.local_media_dir) / "provider-tests"
    output_dir.mkdir(parents=True, exist_ok=True)
    execution = provider_test_executor.execute(
        spec, output_dir, provider_id=provider_id, job_id=f"provider-test-{spec.spec_id}"
    )
    telemetry = execution.telemetry
    asset_path = Path(execution.asset.path)
    return ProviderTestResponse(
        provider_id=provider_id,
        executed_provider_id=execution.job.provider_id,
        kind=kind.value,
        success=telemetry.success if telemetry is not None else True,
        fallback=execution.job.fallback,
        fallback_reason=execution.job.fallback_reason,
        error_code=telemetry.error_code if telemetry is not None else None,
        attempts=execution.job.attempts,
        latency_ms=telemetry.latency_ms if telemetry is not None else 0.0,
        queue_time_ms=telemetry.queue_time_ms if telemetry is not None else 0.0,
        render_time_ms=telemetry.render_time_ms if telemetry is not None else 0.0,
        asset_kind=execution.asset.kind,
        asset_bytes=asset_path.stat().st_size if asset_path.is_file() else 0,
    )


@app.get("/api/v1/providers/telemetry", response_model=list[ProviderTelemetryResponse], tags=["providers"])
def list_provider_telemetry(limit: int = 50) -> list[ProviderTelemetryResponse]:
    """Recent provider telemetry records, newest first (PR009).

    Each record carries provider, latency, queue/render time, success and the
    machine-readable error code the executor classified.
    """

    bounded = max(1, min(limit, 500))
    return [
        ProviderTelemetryResponse(**record.to_dict())
        for record in default_telemetry_store().recent(bounded)
    ]


@app.get("/api/v1/core/providers", response_model=ProviderCatalogueResponse, tags=["core"])
def list_provider_adapters(kind: str | None = None) -> ProviderCatalogueResponse:
    """Every registered adapter, with its kind, status and checkpoint.

    `status` distinguishes a provider that can run here from one that is
    remote-only or merely planned. That distinction is what stops a caller from
    assuming an advertised model is available.
    """

    wanted = GenerationKind(kind) if kind in ("image", "video") else None
    return ProviderCatalogueResponse(
        adapters=[ProviderAdapterResponse(**entry) for entry in provider_registry.describe(wanted)],
        defaults={key.value: value for key, value in provider_registry.DEFAULTS.items()},
    )


@app.get("/api/v1/core/providers/health", response_model=list[ProviderHealthResponse], tags=["core"])
def check_provider_health() -> list[ProviderHealthResponse]:
    """Whether each local adapter could run on this machine, right now.

    A health check must not raise: an adapter with no CUDA reports
    `available: false` and says why.
    """

    reports: list[ProviderHealthResponse] = []
    for provider_id in provider_registry.ids():
        entry = provider_registry.lookup(provider_id)
        if entry is None or not entry.runnable:
            reports.append(
                ProviderHealthResponse(
                    id=provider_id, available=False, reason=f"no local adapter ({entry.status})", model_id=""
                )
            )
            continue
        adapter = provider_registry.adapter_class(entry)()
        report = adapter.health()
        reports.append(
            ProviderHealthResponse(
                id=provider_id,
                available=bool(report.get("available")),
                reason=report.get("reason"),
                model_id=str(report.get("model_id", "")),
                loaded=bool(report.get("loaded", False)),
            )
        )
    return reports


# ---------------------------------------------------------------------------
# PR008 — Cinematic Render Engine: storyboard in, real assets out
#
# These routes only translate HTTP <-> orchestrator calls. Planning lives in
# the Director, prompt text in the PromptCompiler, execution in the
# GenerationExecutor and bytes in the AssetStore — nothing is decided here.
# ---------------------------------------------------------------------------


def _render_inputs_for_request(request: RenderBatchCreateRequest) -> list[SceneRenderInput]:
    """Map the inline Director plan onto per-scene render inputs."""

    phrase = render_orchestrator.persona_phrase_for(request.persona_id)
    return [
        SceneRenderInput(
            scene_number=scene.scene_number,
            title=scene.title,
            objective=scene.objective,
            persona=phrase,
            style=request.style,
            mood=scene.mood or request.mood,
            camera=scene.camera,
            lens=scene.lens,
            lighting=scene.lighting,
            motion=scene.motion,
            environment=scene.environment,
            negative_prompt=scene.negative_prompt,
            seed=scene.seed,
            aspect_ratio=request.aspect_ratio,
            duration=scene.duration,
        )
        for scene in request.scenes
    ]


@app.post("/api/v1/render/batches", response_model=RenderBatchResponse, status_code=201, tags=["render"])
def create_render_batch(
    request: RenderBatchCreateRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RenderBatchResponse:
    """Create a render batch from a Director storyboard (PR008: identity required).

    The batch is planning plus queued scenes — nothing renders until `start`.
    Assets are persisted to the caller's workspace, so anonymous callers are
    refused (a render without a tenant would have nowhere to store).
    """

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        batch = render_orchestrator.create_batch(
            _render_inputs_for_request(request),
            workspace_id=workspace.id,
            project_id=request.project_id,
            kind=request.kind,
            provider=request.provider,
            production_plan_id=request.production_plan_id,
            storyboard_version=request.storyboard_version,
            persona_id=request.persona_id,
            style=request.style,
            aspect_ratio=request.aspect_ratio,
            fps=request.fps,
            seed=request.seed,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="render.batch.created",
        resource_type="render_batch",
        resource_id=batch.batch_id,
        workspace_id=workspace.id,
        detail={"scenes": batch.scene_count, "kind": batch.kind, "provider": batch.provider},
        request=http_request,
    )
    return RenderBatchResponse(**batch.to_dict())


@app.get("/api/v1/render/batches", response_model=list[RenderBatchSummaryResponse], tags=["render"])
def list_render_batches(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[RenderBatchSummaryResponse]:
    """List the caller's render batches, newest first (PR008: identity required)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        return []
    summaries: list[RenderBatchSummaryResponse] = []
    for batch in render_store.list_for_workspace(workspace.id):
        payload = batch.to_dict()
        summaries.append(
            RenderBatchSummaryResponse(
                batch_id=batch.batch_id,
                project_id=batch.project_id,
                kind=batch.kind,
                provider=batch.provider,
                status=batch.status,
                progress=batch.progress,
                scene_count=batch.scene_count,
                completed_scenes=batch.completed_scenes,
                failed_scenes=batch.failed_scenes,
                current_scene_number=payload["current_scene_number"],  # type: ignore[arg-type]
                eta_seconds=batch.eta_seconds,
                created_at=batch.created_at,
                started_at=batch.started_at,
                finished_at=batch.finished_at,
            )
        )
    return summaries


@app.get("/api/v1/render/batches/{batch_id}", response_model=RenderBatchResponse, tags=["render"])
def get_render_batch(batch_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> RenderBatchResponse:
    """Read one of the caller's render batches with per-scene progress (PR008)."""

    workspace = _workspace_for(db, user)
    batch = render_store.get_for_workspace(batch_id, workspace.id) if workspace else None
    if batch is None:
        raise HTTPException(status_code=404, detail="Render batch not found")
    return RenderBatchResponse(**batch.to_dict())


@app.post("/api/v1/render/batches/{batch_id}/start", response_model=RenderBatchResponse, status_code=202, tags=["render"])
def start_render_batch(
    batch_id: str,
    http_request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RenderBatchResponse:
    """Start rendering a queued batch in the background (PR008: identity required).

    202 means accepted, not finished: the response shows the batch as queued
    and progress arrives over `/ws/render/{batch_id}`. A batch that already
    started is refused with 409 — finished batches go through `retry`.
    """

    workspace = _workspace_for(db, user)
    batch = render_store.get_for_workspace(batch_id, workspace.id) if workspace else None
    if batch is None:
        raise HTTPException(status_code=404, detail="Render batch not found")
    if batch.status != "queued":
        raise HTTPException(status_code=409, detail=f"Batch is {batch.status}; only queued batches can start")
    background_tasks.add_task(render_orchestrator.run_batch, batch_id, db_session_factory=SessionLocal)
    audit(
        db,
        actor=user,
        action="render.batch.started",
        resource_type="render_batch",
        resource_id=batch.batch_id,
        workspace_id=workspace.id if workspace else None,
        request=http_request,
    )
    return RenderBatchResponse(**batch.to_dict())


@app.post("/api/v1/render/batches/{batch_id}/cancel", response_model=RenderBatchResponse, tags=["render"])
def cancel_render_batch(
    batch_id: str, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> RenderBatchResponse:
    """Cancel a render batch (PR008: identity required).

    Idempotent: cancelling a finished batch returns its state unchanged. The
    running scene finishes; every other pending scene is marked cancelled.
    """

    workspace = _workspace_for(db, user)
    batch = render_orchestrator.cancel(batch_id, workspace.id) if workspace else None
    if batch is None:
        raise HTTPException(status_code=404, detail="Render batch not found")
    audit(
        db,
        actor=user,
        action="render.batch.cancelled",
        resource_type="render_batch",
        resource_id=batch.batch_id,
        workspace_id=workspace.id if workspace else None,
        request=http_request,
    )
    return RenderBatchResponse(**batch.to_dict())


@app.post("/api/v1/render/batches/{batch_id}/retry", response_model=RenderRetryResponse, tags=["render"])
def retry_render_batch(
    batch_id: str,
    http_request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RenderRetryResponse:
    """Retry the failed/cancelled scenes of a finished batch (PR008).

    Completed scenes are never re-rendered. Refused with 409 while the batch
    is still active, or when there is nothing left to retry.
    """

    workspace = _workspace_for(db, user)
    batch = render_store.get_for_workspace(batch_id, workspace.id) if workspace else None
    if batch is None:
        raise HTTPException(status_code=404, detail="Render batch not found")
    if not batch.is_terminal:
        raise HTTPException(status_code=409, detail=f"Batch is {batch.status}; only finished batches can retry")
    _, reset = render_orchestrator.retry(batch_id, workspace.id)
    if not reset:
        raise HTTPException(status_code=409, detail="Nothing to retry: every scene already completed")
    background_tasks.add_task(render_orchestrator.run_batch, batch_id, db_session_factory=SessionLocal)
    audit(
        db,
        actor=user,
        action="render.batch.retried",
        resource_type="render_batch",
        resource_id=batch.batch_id,
        workspace_id=workspace.id if workspace else None,
        detail={"retried_scenes": reset},
        request=http_request,
    )
    return RenderRetryResponse(
        batch_id=batch.batch_id,
        status=batch.status,
        retried_scenes=reset,
        message=f"Retrying {reset} scene(s); completed scenes are kept",
    )


@app.websocket("/ws/render/{batch_id}")
async def render_progress(websocket: WebSocket, batch_id: str) -> None:
    """Push a batch's render events until the terminal one. No polling.

    The client sends nothing: it receives a `snapshot` with the full batch,
    replays the buffered history, then awaits live events (`batch_started`,
    `scene_started`, `scene_progress`, `scene_completed`, `batch_completed`)
    until `batch_completed` closes the stream.

    PR008: authenticated like the other sockets — the bearer token rides the
    `token` query parameter and a batch the caller does not own closes with
    the same 1008 reason an unknown batch gets.
    """

    with SessionLocal() as db:
        user = ws_identity(websocket.query_params.get("token"), db)
        if not user:
            await websocket.close(code=1008, reason="Authentication required")
            return
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
        batch = render_store.get_for_workspace(batch_id, workspace.id) if workspace else None
        if batch is None:
            await websocket.close(code=1008, reason="Render batch not found")
            return
    # Subscribe before reading history: anything published in between lands in
    # both, and the identity filter below drops the duplicate. Missing an
    # event is not an option; a duplicate would be.
    queue = render_hub.subscribe(batch_id)
    try:
        await websocket.accept()
        try:
            await websocket.send_json({"event": "snapshot", "batch": batch.to_dict()})
            history = render_hub.history(batch_id)
            seen = {id(event) for event in history}
            for event in history:
                await websocket.send_json(event)
            if batch.is_terminal:
                return
            while True:
                event = await queue.get()
                if id(event) in seen:
                    continue
                seen.add(id(event))
                await websocket.send_json(event)
                if event.get("event") == RENDER_TERMINAL_EVENT:
                    return
        except WebSocketDisconnect:
            return
    finally:
        render_hub.unsubscribe(batch_id, queue)


# ---------------------------------------------------------------------------
# V3.1 — Cinematic Knowledge Graph: memory as relational knowledge
#
# These routes only translate HTTP <-> repository/engine calls. The relation
# vocabulary lives in the RelationshipEngine, persistence in the
# GraphRepository, and scoring in SemanticQuery — nothing is decided here.
# Every route requires identity: graph rows are tenant product data, like
# personas (PR003), so anonymous callers are refused and foreign ids 404.
# ---------------------------------------------------------------------------


class _GraphContextSource:
    """V3.1: `GraphContextSource` adapter over one workspace's graph.

    Lets a `MemoryResolver` serve graph phrases for a persona name without
    the Core importing SQLAlchemy — the same adapter pattern PR003 uses for
    persona profiles. Workspace-bound by construction: unlike the global
    persona fallback, graph rows must never leak across tenants, so this
    adapter is composed per request, never on the global resolver.
    """

    def __init__(self, workspace_id: str) -> None:
        self._characters = character_graph_for(workspace_id)

    def get_context(self, subject: str):
        context = self._characters.context(subject)
        if context is None:
            return None
        return GraphContext(
            subject=context.node.name,
            phrases=context.phrases,
            relation_count=len(context.relations),
        )


def _graph_node_payload(view) -> GraphNodeResponse:
    return GraphNodeResponse(
        id=view.id,
        workspace_id=view.workspace_id,
        entity_type=view.entity_type,
        name=view.name,
        slug=view.slug,
        attributes=dict(view.attributes),
        aliases=list(view.aliases),
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def _graph_edge_payload(view) -> GraphEdgeResponse:
    return GraphEdgeResponse(
        id=view.id,
        workspace_id=view.workspace_id,
        source_id=view.source_id,
        target_id=view.target_id,
        relation=view.relation,
        inverse=inverse_of(view.relation),
        created_at=view.created_at,
    )


@app.post("/api/v1/graph/nodes", response_model=GraphNodeResponse, status_code=201, tags=["graph"])
def create_graph_node(
    request: GraphNodeCreate,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GraphNodeResponse:
    """Create a knowledge-graph node in the caller's workspace (V3.1: identity required)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        row = graph_repo.create_node(
            workspace.id,
            name=request.name,
            entity_type=request.entity_type,
            attributes=request.attributes,
            aliases=request.aliases,
            slug=request.slug,
        )
    except GraphRepositoryError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (GraphValidationError, RelationshipError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="graph.node.created",
        resource_type="graph_node",
        resource_id=row.id,
        workspace_id=workspace.id,
        detail={"entity_type": row.entity_type, "slug": row.slug},
        request=http_request,
    )
    return _graph_node_payload(node_view(row))


@app.get("/api/v1/graph/nodes", response_model=list[GraphNodeResponse], tags=["graph"])
def list_graph_nodes(
    entity_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[GraphNodeResponse]:
    """List the caller's graph nodes, optionally filtered by entity type (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        return []
    try:
        rows = graph_repo.list_nodes(workspace.id, entity_type=entity_type, limit=limit, offset=offset)
    except (GraphValidationError, RelationshipError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return [_graph_node_payload(node_view(row)) for row in rows]


@app.get("/api/v1/graph/nodes/{node_id}", response_model=GraphNodeResponse, tags=["graph"])
def get_graph_node(node_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> GraphNodeResponse:
    """Read one of the caller's graph nodes (V3.1; foreign ids 404)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    row = graph_repo.get_node(node_id, workspace.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Graph node not found")
    return _graph_node_payload(node_view(row))


@app.patch("/api/v1/graph/nodes/{node_id}", response_model=GraphNodeResponse, tags=["graph"])
def update_graph_node(
    node_id: str,
    request: GraphNodeUpdate,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GraphNodeResponse:
    """Partially update a graph node; attributes/aliases replace wholesale (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        row = graph_repo.update_node(node_id, workspace.id, request.model_dump(exclude_unset=True))
    except (GraphValidationError, RelationshipError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if row is None:
        raise HTTPException(status_code=404, detail="Graph node not found")
    audit(
        db,
        actor=user,
        action="graph.node.updated",
        resource_type="graph_node",
        resource_id=row.id,
        workspace_id=workspace.id,
        detail={"fields": sorted(request.model_dump(exclude_unset=True))},
        request=http_request,
    )
    return _graph_node_payload(node_view(row))


@app.delete("/api/v1/graph/nodes/{node_id}", status_code=204, tags=["graph"])
def delete_graph_node(node_id: str, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete a graph node and its incident edges in both directions (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not graph_repo.delete_node(node_id, workspace.id):
        raise HTTPException(status_code=404, detail="Graph node not found")
    audit(
        db,
        actor=user,
        action="graph.node.deleted",
        resource_type="graph_node",
        resource_id=node_id,
        workspace_id=workspace.id,
        detail={},
        request=http_request,
    )


@app.post("/api/v1/graph/edges", response_model=GraphEdgeResponse, status_code=201, tags=["graph"])
def create_graph_edge(
    request: GraphEdgeCreate,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GraphEdgeResponse:
    """Relate two nodes; the verb is normalised onto the engine vocabulary (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if (
        graph_repo.get_node(request.source_id, workspace.id) is None
        or graph_repo.get_node(request.target_id, workspace.id) is None
    ):
        raise HTTPException(status_code=404, detail="Graph node not found")
    try:
        row = graph_repo.create_edge(
            workspace.id,
            source_id=request.source_id,
            target_id=request.target_id,
            relation=request.relation,
        )
    except GraphRepositoryError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (GraphValidationError, RelationshipError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="graph.edge.created",
        resource_type="graph_edge",
        resource_id=row.id,
        workspace_id=workspace.id,
        detail={"relation": row.relation},
        request=http_request,
    )
    return _graph_edge_payload(edge_view(row))


@app.get("/api/v1/graph/edges", response_model=list[GraphEdgeResponse], tags=["graph"])
def list_graph_edges(
    source_id: str | None = None,
    target_id: str | None = None,
    relation: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[GraphEdgeResponse]:
    """List the caller's graph edges, filterable by endpoint or relation (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        return []
    try:
        rows = graph_repo.list_edges(
            workspace.id,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            limit=limit,
            offset=offset,
        )
    except (GraphValidationError, RelationshipError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return [_graph_edge_payload(edge_view(row)) for row in rows]


@app.delete("/api/v1/graph/edges/{edge_id}", status_code=204, tags=["graph"])
def delete_graph_edge(edge_id: str, http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete one graph edge; the endpoint nodes are untouched (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not graph_repo.delete_edge(edge_id, workspace.id):
        raise HTTPException(status_code=404, detail="Graph edge not found")
    audit(
        db,
        actor=user,
        action="graph.edge.deleted",
        resource_type="graph_edge",
        resource_id=edge_id,
        workspace_id=workspace.id,
        detail={},
        request=http_request,
    )


@app.get("/api/v1/graph/query", response_model=GraphQueryResponse, tags=["graph"])
def query_graph(
    q: str = Query(min_length=1, max_length=200),
    entity_type: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GraphQueryResponse:
    """Semantic search over the caller's graph: names, aliases, attributes (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        return GraphQueryResponse(query=q, entity_type=entity_type, count=0, matches=[])
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query must not be blank")
    try:
        matches = semantic_query_for(workspace.id).query(q, entity_type=entity_type, limit=limit)
    except (GraphValidationError, RelationshipError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return GraphQueryResponse(
        query=q,
        entity_type=entity_type,
        count=len(matches),
        matches=[
            GraphQueryMatchResponse(
                node=_graph_node_payload(match.node),
                score=match.score,
                matched_fields=list(match.matched_fields),
            )
            for match in matches
        ],
    )


@app.get("/api/v1/graph/neighbors/{node_id}", response_model=GraphNeighborsResponse, tags=["graph"])
def graph_neighbors(
    node_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    direction: str = Query(default="both"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> GraphNeighborsResponse:
    """Walk the graph around one node: depth 1-3, in/out/both directions (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        subgraph = relationship_engine_for(workspace.id).neighbors(node_id, depth=depth, direction=direction)
    except (GraphValidationError, RelationshipError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if subgraph.center is None:
        raise HTTPException(status_code=404, detail="Graph node not found")
    return GraphNeighborsResponse(
        node=_graph_node_payload(subgraph.center),
        depth=depth,
        direction=direction,
        nodes=[_graph_node_payload(node) for node in subgraph.nodes],
        edges=[_graph_edge_payload(edge) for edge in subgraph.edges],
    )


@app.get("/api/v1/graph/characters/{name}/context", response_model=GraphCharacterContextResponse, tags=["graph"])
def graph_character_context(name: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> GraphCharacterContextResponse:
    """CharacterGraph: identity, relations and phrases for one character (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    characters = character_graph_for(workspace.id)
    context = characters.context(name)
    # ETAPA 5: the phrases travel through a MemoryResolver composed with the
    # workspace-bound graph source — the same seam the spec builder will use.
    # Graph-only names (no ledger persona) read the character context
    # directly; names known nowhere come back empty, with found=false.
    scoped_resolver = MemoryResolver(context_source=_GraphContextSource(workspace.id))
    persona = scoped_resolver.resolve_by_name(name)
    if persona is not None:
        phrases = list(scoped_resolver.context_phrases(persona.persona_id))
    elif context is not None:
        phrases = list(context.phrases)
    else:
        phrases = []
    relations = (
        [
            GraphCharacterRelationResponse(
                relation=item.relation,
                direction=item.direction,
                peer=_graph_node_payload(item.peer),
                phrase=item.phrase,
            )
            for item in context.relations
        ]
        if context is not None
        else []
    )
    return GraphCharacterContextResponse(
        name=name,
        found=context is not None,
        persona_id=persona.persona_id if persona is not None else None,
        node=_graph_node_payload(context.node) if context is not None else None,
        phrases=phrases,
        relations=relations,
        relation_counts=dict(context.relation_counts) if context is not None else {},
    )


@app.post("/api/v1/graph/seed", response_model=GraphSeedResponse, tags=["graph"])
def seed_graph_demo(http_request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> GraphSeedResponse:
    """Load the demonstration graph into the caller's workspace, idempotently (V3.1)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    report = graph_repo.seed_demo(workspace.id)
    audit(
        db,
        actor=user,
        action="graph.seeded",
        resource_type="graph",
        resource_id=workspace.id,
        workspace_id=workspace.id,
        detail=report,
        request=http_request,
    )
    return GraphSeedResponse(**report)


# ---------------------------------------------------------------------------
# V3.2 — Character Continuity Engine
#
# Five locks (identity, wardrobe, location, vehicle, voice) plus the resolver
# and the episode history. Every route requires identity: continuity rows are
# tenant product data, like personas and graph rows — a foreign id reads as a
# 404, never a 403. The Director, the Provider Registry and the Render Engine
# are untouched; the resolver returns a ContinuityContext and never rewrites
# the GenerationSpec.
# ---------------------------------------------------------------------------


def _continuity_identity_payload(persona_id: str, view) -> ContinuityIdentityResponse:
    payload = dict(view.payload)
    return ContinuityIdentityResponse(
        persona_id=persona_id,
        face=str(payload.get("face", "")),
        hair=str(payload.get("hair", "")),
        beard=str(payload.get("beard", "")),
        body=str(payload.get("body", "")),
        skin=str(payload.get("skin", "")),
        age_appearance=str(payload.get("age_appearance", "")),
        fingerprint=view.fingerprint,
        version=view.version,
        updated_at=view.updated_at,
    )


def _continuity_wardrobe_payload(persona_id: str, campaign_id: str, view) -> ContinuityWardrobeResponse:
    payload = dict(view.payload)
    return ContinuityWardrobeResponse(
        persona_id=persona_id,
        campaign_id=campaign_id,
        source_episode=view.episode,
        outfit=str(payload.get("outfit", "")),
        accessories=str(payload.get("accessories", "")),
        colors=str(payload.get("colors", "")),
        shoes=str(payload.get("shoes", "")),
        watch=str(payload.get("watch", "")),
        fingerprint=view.fingerprint,
        version=view.version,
        updated_at=view.updated_at,
    )


def _continuity_location_payload(persona_id: str, campaign_id: str, view) -> ContinuityLocationResponse:
    payload = dict(view.payload)
    return ContinuityLocationResponse(
        persona_id=persona_id,
        campaign_id=campaign_id,
        source_episode=view.episode,
        showroom=str(payload.get("showroom", "")),
        studio=str(payload.get("studio", "")),
        street=str(payload.get("street", "")),
        city=str(payload.get("city", "")),
        base_lighting=str(payload.get("base_lighting", "")),
        fingerprint=view.fingerprint,
        version=view.version,
        updated_at=view.updated_at,
    )


def _continuity_vehicle_payload(persona_id: str, campaign_id: str, view) -> ContinuityVehicleResponse:
    payload = dict(view.payload)
    return ContinuityVehicleResponse(
        persona_id=persona_id,
        campaign_id=campaign_id,
        source_episode=view.episode,
        vehicle=str(payload.get("vehicle", "")),
        color=str(payload.get("color", "")),
        plate=str(payload.get("plate", "")),
        wheels=str(payload.get("wheels", "")),
        finish=str(payload.get("finish", "")),
        fingerprint=view.fingerprint,
        version=view.version,
        updated_at=view.updated_at,
    )


def _continuity_voice_payload(persona_id: str, view) -> ContinuityVoiceResponse:
    payload = dict(view.payload)
    return ContinuityVoiceResponse(
        persona_id=persona_id,
        voice_profile=str(payload.get("voice_profile", "")),
        default_emotion=str(payload.get("default_emotion", "")),
        speed=str(payload.get("speed", "")),
        intensity=str(payload.get("intensity", "")),
        fingerprint=view.fingerprint,
        version=view.version,
        updated_at=view.updated_at,
    )


def _continuity_episode_payload(view) -> ContinuityEpisodeResponse:
    return ContinuityEpisodeResponse(
        id=view.id,
        workspace_id=view.workspace_id,
        persona_id=view.persona_id,
        campaign_id=view.campaign_id,
        episode=view.episode,
        title=view.title,
        notes=view.notes,
        snapshot=dict(view.snapshot),
        created_at=view.created_at,
    )


@app.put("/api/v1/continuity/identity", response_model=ContinuityIdentityResponse, tags=["continuity"])
def lock_continuity_identity(
    request: ContinuityIdentityRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityIdentityResponse:
    """Freeze a character's visual identity and fingerprint it (V3.2: identity required)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        snapshot = IdentityLock.lock(
            request.persona_id,
            face=request.face,
            hair=request.hair,
            beard=request.beard,
            body=request.body,
            skin=request.skin,
            age_appearance=request.age_appearance,
        )
        view = continuity_repo.upsert_lock(
            workspace.id,
            lock_type="identity",
            persona_id=snapshot.persona_id,
            payload={
                "face": snapshot.face,
                "hair": snapshot.hair,
                "beard": snapshot.beard,
                "body": snapshot.body,
                "skin": snapshot.skin,
                "age_appearance": snapshot.age_appearance,
            },
            fingerprint=snapshot.fingerprint,
        )
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="continuity.identity.locked",
        resource_type="continuity_lock",
        resource_id=f"{snapshot.persona_id}:identity",
        workspace_id=workspace.id,
        detail={"persona_id": snapshot.persona_id, "fingerprint": snapshot.fingerprint},
        request=http_request,
    )
    return _continuity_identity_payload(snapshot.persona_id, view)


@app.get("/api/v1/continuity/identity/{persona_id}", response_model=ContinuityIdentityResponse, tags=["continuity"])
def get_continuity_identity(
    persona_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> ContinuityIdentityResponse:
    """Read a character's frozen visual identity, or 404 when unlocked (V3.2)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        view = continuity_repo.get_lock(workspace.id, "identity", persona_id)
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if view is None:
        raise HTTPException(status_code=404, detail=f"no identity lock for {persona_id}")
    return _continuity_identity_payload(view.persona_id, view)


@app.put("/api/v1/continuity/wardrobe", response_model=ContinuityWardrobeResponse, tags=["continuity"])
def lock_continuity_wardrobe(
    request: ContinuityWardrobeRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityWardrobeResponse:
    """Freeze a costume for a campaign, optionally for one episode only (V3.2: identity required)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        snapshot = WardrobeLock.lock(
            outfit=request.outfit,
            accessories=request.accessories,
            colors=request.colors,
            shoes=request.shoes,
            watch=request.watch,
        )
        view = continuity_repo.upsert_lock(
            workspace.id,
            lock_type="wardrobe",
            persona_id=request.persona_id,
            campaign_id=request.campaign_id,
            episode=request.episode,
            payload={
                "outfit": snapshot.outfit,
                "accessories": snapshot.accessories,
                "colors": snapshot.colors,
                "shoes": snapshot.shoes,
                "watch": snapshot.watch,
            },
            fingerprint=snapshot.fingerprint,
        )
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="continuity.wardrobe.locked",
        resource_type="continuity_lock",
        resource_id=f"{view.persona_id}:{view.campaign_id}:{view.episode}:wardrobe",
        workspace_id=workspace.id,
        detail={"persona_id": view.persona_id, "campaign_id": view.campaign_id, "fingerprint": snapshot.fingerprint},
        request=http_request,
    )
    return _continuity_wardrobe_payload(view.persona_id, view.campaign_id, view)


@app.get("/api/v1/continuity/wardrobe", response_model=ContinuityWardrobeResponse, tags=["continuity"])
def get_continuity_wardrobe(
    persona_id: str,
    campaign_id: str = "default",
    episode: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityWardrobeResponse:
    """Read the resolved costume: episode override or campaign default (V3.2)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        view = continuity_repo.get_lock(workspace.id, "wardrobe", persona_id, campaign_id, episode)
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if view is None:
        raise HTTPException(status_code=404, detail=f"no wardrobe lock for {persona_id}")
    return _continuity_wardrobe_payload(view.persona_id, view.campaign_id, view)


@app.put("/api/v1/continuity/location", response_model=ContinuityLocationResponse, tags=["continuity"])
def lock_continuity_location(
    request: ContinuityLocationRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityLocationResponse:
    """Freeze the set for a campaign, optionally for one episode only (V3.2: identity required)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        snapshot = LocationLock.lock(
            showroom=request.showroom,
            studio=request.studio,
            street=request.street,
            city=request.city,
            base_lighting=request.base_lighting,
        )
        view = continuity_repo.upsert_lock(
            workspace.id,
            lock_type="location",
            persona_id=request.persona_id,
            campaign_id=request.campaign_id,
            episode=request.episode,
            payload={
                "showroom": snapshot.showroom,
                "studio": snapshot.studio,
                "street": snapshot.street,
                "city": snapshot.city,
                "base_lighting": snapshot.base_lighting,
            },
            fingerprint=snapshot.fingerprint,
        )
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="continuity.location.locked",
        resource_type="continuity_lock",
        resource_id=f"{view.persona_id}:{view.campaign_id}:{view.episode}:location",
        workspace_id=workspace.id,
        detail={"persona_id": view.persona_id, "campaign_id": view.campaign_id, "fingerprint": snapshot.fingerprint},
        request=http_request,
    )
    return _continuity_location_payload(view.persona_id, view.campaign_id, view)


@app.get("/api/v1/continuity/location", response_model=ContinuityLocationResponse, tags=["continuity"])
def get_continuity_location(
    persona_id: str,
    campaign_id: str = "default",
    episode: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityLocationResponse:
    """Read the resolved set: episode override or campaign default (V3.2)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        view = continuity_repo.get_lock(workspace.id, "location", persona_id, campaign_id, episode)
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if view is None:
        raise HTTPException(status_code=404, detail=f"no location lock for {persona_id}")
    return _continuity_location_payload(view.persona_id, view.campaign_id, view)


@app.put("/api/v1/continuity/vehicle", response_model=ContinuityVehicleResponse, tags=["continuity"])
def lock_continuity_vehicle(
    request: ContinuityVehicleRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityVehicleResponse:
    """Freeze the hero vehicle for a campaign, optionally for one episode (V3.2: identity required)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        snapshot = VehicleLock.lock(
            vehicle=request.vehicle,
            color=request.color,
            plate=request.plate,
            wheels=request.wheels,
            finish=request.finish,
        )
        view = continuity_repo.upsert_lock(
            workspace.id,
            lock_type="vehicle",
            persona_id=request.persona_id,
            campaign_id=request.campaign_id,
            episode=request.episode,
            payload={
                "vehicle": snapshot.vehicle,
                "color": snapshot.color,
                "plate": snapshot.plate,
                "wheels": snapshot.wheels,
                "finish": snapshot.finish,
            },
            fingerprint=snapshot.fingerprint,
        )
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="continuity.vehicle.locked",
        resource_type="continuity_lock",
        resource_id=f"{view.persona_id}:{view.campaign_id}:{view.episode}:vehicle",
        workspace_id=workspace.id,
        detail={"persona_id": view.persona_id, "campaign_id": view.campaign_id, "fingerprint": snapshot.fingerprint},
        request=http_request,
    )
    return _continuity_vehicle_payload(view.persona_id, view.campaign_id, view)


@app.get("/api/v1/continuity/vehicle", response_model=ContinuityVehicleResponse, tags=["continuity"])
def get_continuity_vehicle(
    persona_id: str,
    campaign_id: str = "default",
    episode: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityVehicleResponse:
    """Read the resolved hero vehicle: episode override or campaign default (V3.2)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        view = continuity_repo.get_lock(workspace.id, "vehicle", persona_id, campaign_id, episode)
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if view is None:
        raise HTTPException(status_code=404, detail=f"no vehicle lock for {persona_id}")
    return _continuity_vehicle_payload(view.persona_id, view.campaign_id, view)


@app.put("/api/v1/continuity/voice", response_model=ContinuityVoiceResponse, tags=["continuity"])
def lock_continuity_voice(
    request: ContinuityVoiceRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityVoiceResponse:
    """Freeze a character's voice profile, emotion, speed and intensity (V3.2: identity required)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        snapshot = VoiceLock.lock(
            voice_profile=request.voice_profile,
            default_emotion=request.default_emotion,
            speed=request.speed,
            intensity=request.intensity,
        )
        view = continuity_repo.upsert_lock(
            workspace.id,
            lock_type="voice",
            persona_id=request.persona_id,
            payload={
                "voice_profile": snapshot.voice_profile,
                "default_emotion": snapshot.default_emotion,
                "speed": snapshot.speed,
                "intensity": snapshot.intensity,
            },
            fingerprint=snapshot.fingerprint,
        )
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="continuity.voice.locked",
        resource_type="continuity_lock",
        resource_id=f"{request.persona_id.strip()}:voice",
        workspace_id=workspace.id,
        detail={"persona_id": request.persona_id.strip(), "fingerprint": snapshot.fingerprint},
        request=http_request,
    )
    return _continuity_voice_payload(view.persona_id, view)


@app.get("/api/v1/continuity/voice/{persona_id}", response_model=ContinuityVoiceResponse, tags=["continuity"])
def get_continuity_voice(
    persona_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> ContinuityVoiceResponse:
    """Read a character's frozen voice, or 404 when unlocked (V3.2)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        view = continuity_repo.get_lock(workspace.id, "voice", persona_id)
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if view is None:
        raise HTTPException(status_code=404, detail=f"no voice lock for {persona_id}")
    return _continuity_voice_payload(view.persona_id, view)


@app.get("/api/v1/continuity/resolve", response_model=ContinuityResolveResponse, tags=["continuity"])
def resolve_continuity(
    persona_id: str,
    campaign_id: str = "default",
    episode: int = 1,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityResolveResponse:
    """Resolve one ContinuityContext: persona + campaign + episode (V3.2)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        resolver = ContinuityResolver(continuity_store_for(workspace.id))
        context = resolver.resolve(persona_id, campaign_id, episode)
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    identity = ContinuityIdentityResponse(
        persona_id=context.persona_id,
        face=context.identity.face,
        hair=context.identity.hair,
        beard=context.identity.beard,
        body=context.identity.body,
        skin=context.identity.skin,
        age_appearance=context.identity.age_appearance,
        fingerprint=context.identity.fingerprint,
    ) if context.identity else None
    wardrobe = ContinuityWardrobeResponse(
        persona_id=context.persona_id,
        campaign_id=context.campaign_id,
        outfit=context.wardrobe.outfit,
        accessories=context.wardrobe.accessories,
        colors=context.wardrobe.colors,
        shoes=context.wardrobe.shoes,
        watch=context.wardrobe.watch,
        fingerprint=context.wardrobe.fingerprint,
    ) if context.wardrobe else None
    location = ContinuityLocationResponse(
        persona_id=context.persona_id,
        campaign_id=context.campaign_id,
        showroom=context.location.showroom,
        studio=context.location.studio,
        street=context.location.street,
        city=context.location.city,
        base_lighting=context.location.base_lighting,
        fingerprint=context.location.fingerprint,
    ) if context.location else None
    vehicle = ContinuityVehicleResponse(
        persona_id=context.persona_id,
        campaign_id=context.campaign_id,
        vehicle=context.vehicle.vehicle,
        color=context.vehicle.color,
        plate=context.vehicle.plate,
        wheels=context.vehicle.wheels,
        finish=context.vehicle.finish,
        fingerprint=context.vehicle.fingerprint,
    ) if context.vehicle else None
    voice = ContinuityVoiceResponse(
        persona_id=context.persona_id,
        voice_profile=context.voice.voice_profile,
        default_emotion=context.voice.default_emotion,
        speed=context.voice.speed,
        intensity=context.voice.intensity,
        fingerprint=context.voice.fingerprint,
    ) if context.voice else None
    return ContinuityResolveResponse(
        persona_id=context.persona_id,
        campaign_id=context.campaign_id,
        episode=context.episode,
        identity=identity,
        wardrobe=wardrobe,
        location=location,
        vehicle=vehicle,
        voice=voice,
        phrases=list(context.phrases),
        fingerprints=context.fingerprint_map(),
        missing=list(context.missing),
        drift=list(context.drift),
        consistent=context.consistent,
        block=context.block(),
    )


@app.post("/api/v1/continuity/episodes", response_model=ContinuityEpisodeResponse, status_code=201, tags=["continuity"])
def create_continuity_episode(
    request: ContinuityEpisodeCreate,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ContinuityEpisodeResponse:
    """Freeze a new episode with the currently resolved continuity (V3.2: identity required)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        persona_id = request.persona_id.strip()
        campaign_id = request.campaign_id.strip() or "default"
        episode = request.episode
        if episode is None:
            episode = continuity_repo.next_episode_number(workspace.id, persona_id, campaign_id)
        resolver = ContinuityResolver(continuity_store_for(workspace.id))
        context = resolver.resolve(persona_id, campaign_id, episode)
        view = continuity_repo.create_episode(
            workspace.id,
            persona_id=persona_id,
            campaign_id=campaign_id,
            episode=episode,
            title=request.title,
            notes=request.notes,
            snapshot=resolver.snapshot_dict(context),
        )
    except ContinuityRepositoryError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ContinuityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="continuity.episode.created",
        resource_type="continuity_episode",
        resource_id=view.id,
        workspace_id=workspace.id,
        detail={"persona_id": persona_id, "campaign_id": campaign_id, "episode": episode},
        request=http_request,
    )
    return _continuity_episode_payload(view)


@app.get("/api/v1/continuity/episodes", response_model=list[ContinuityEpisodeResponse], tags=["continuity"])
def list_continuity_episodes(
    persona_id: str | None = None,
    campaign_id: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ContinuityEpisodeResponse]:
    """List frozen episode snapshots, optionally filtered (V3.2)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        return []
    views = continuity_repo.list_episodes(workspace.id, persona_id=persona_id, campaign_id=campaign_id)
    return [_continuity_episode_payload(view) for view in views]


# ---------------------------------------------------------------------------
# V3.3 — Campaign Builder: one briefing in, a complete campaign out.
#
# The service (`app/campaign/campaign_service.py`) owns every decision; these
# routes only map domain results onto the API contract, resolve the caller's
# workspace and audit mutations — the same boundary discipline as the
# continuity block above. All seven routes require identity: campaigns are
# tenant product data, like personas, graph rows and continuity locks.
# ---------------------------------------------------------------------------


def _campaign_payload(view) -> CampaignResponse:
    return CampaignResponse(**view.to_dict())


def _campaign_brief_payload(view) -> CampaignBriefResponse:
    return CampaignBriefResponse(**view.to_dict())


def _campaign_asset_payload(view) -> CampaignAssetResponse:
    return CampaignAssetResponse(**view.to_dict())


def _campaign_episode_payload(view) -> CampaignEpisodeResponse:
    return CampaignEpisodeResponse(**view.to_dict())


def _campaign_export_payload(view) -> CampaignExportResponse:
    return CampaignExportResponse(
        **{key: value for key, value in view.to_dict().items() if key != "manifest"},
        download_url=f"/api/v1/assets/download/{view.object_key}",
    )


def _campaign_detail_payload(detail) -> CampaignDetailResponse:
    return CampaignDetailResponse(
        **_campaign_payload(detail.campaign).model_dump(),
        brief=_campaign_brief_payload(detail.brief) if detail.brief else None,
        assets=[_campaign_asset_payload(asset) for asset in detail.assets],
        episodes=[_campaign_episode_payload(episode) for episode in detail.episodes],
        exports=[_campaign_export_payload(export) for export in detail.exports],
    )


@app.post("/api/v1/campaigns/interpret", response_model=CampaignInterpretationResponse, tags=["campaign"])
def interpret_campaign_briefing(
    request: CampaignBriefingRequest,
    user: User = Depends(current_user),
) -> CampaignInterpretationResponse:
    """Read one briefing line into the six brief fields — nothing persisted (V3.3)."""

    try:
        brief = campaign_service.interpret(request.briefing)
    except CampaignValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return CampaignInterpretationResponse(
        raw_text=brief.raw_text,
        name=brief.display_name,
        product=brief.product,
        product_type=brief.product_type,
        audience=brief.audience,
        platform=brief.platform,
        objective=brief.objective,
        duration_seconds=brief.duration_seconds,
        missing=list(brief.missing),
        matched=list(brief.matched),
    )


@app.post("/api/v1/campaigns", response_model=CampaignDetailResponse, status_code=201, tags=["campaign"])
def create_campaign(
    request: CampaignCreateRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CampaignDetailResponse:
    """Build the complete campaign from one briefing (V3.3: brief → deliverables → timeline)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        bundle = campaign_service.create_from_briefing(workspace.id, request.briefing, name=request.name)
    except CampaignValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="campaign.created",
        resource_type="campaign",
        resource_id=bundle.campaign.id,
        workspace_id=workspace.id,
        detail={
            "name": bundle.campaign.name,
            "product": bundle.campaign.product,
            "objective": bundle.campaign.objective,
            "primary_cta": bundle.campaign.primary_cta,
            "assets": len(bundle.assets),
        },
        request=http_request,
    )
    detail = campaign_service.get_detail(workspace.id, bundle.campaign.id)
    return _campaign_detail_payload(detail)


@app.get("/api/v1/campaigns", response_model=list[CampaignResponse], tags=["campaign"])
def list_campaigns(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[CampaignResponse]:
    """List the workspace's campaigns, newest first (V3.3)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        return []
    return [_campaign_payload(view) for view in campaign_service.list_campaigns(workspace.id)]


@app.get("/api/v1/campaigns/{campaign_id}", response_model=CampaignDetailResponse, tags=["campaign"])
def get_campaign(
    campaign_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CampaignDetailResponse:
    """One campaign with its brief, seven assets, five-day timeline and exports (V3.3)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        detail = campaign_service.get_detail(workspace.id, campaign_id)
    except UnknownCampaignError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _campaign_detail_payload(detail)


@app.post(
    "/api/v1/campaigns/{campaign_id}/duplicate",
    response_model=CampaignDetailResponse,
    status_code=201,
    tags=["campaign"],
)
def duplicate_campaign(
    campaign_id: str,
    request: CampaignDuplicateRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CampaignDetailResponse:
    """Copy a campaign with freshly armed CTAs and deliveries reset (V3.3)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        bundle = campaign_service.duplicate(workspace.id, campaign_id, name=request.name)
    except UnknownCampaignError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="campaign.duplicated",
        resource_type="campaign",
        resource_id=bundle.campaign.id,
        workspace_id=workspace.id,
        detail={"source_campaign_id": campaign_id, "name": bundle.campaign.name, "seed": bundle.campaign.seed},
        request=http_request,
    )
    detail = campaign_service.get_detail(workspace.id, bundle.campaign.id)
    return _campaign_detail_payload(detail)


@app.post(
    "/api/v1/campaigns/{campaign_id}/assets/{asset_id}/deliver",
    response_model=CampaignAssetResponse,
    tags=["campaign"],
)
def deliver_campaign_asset(
    campaign_id: str,
    asset_id: str,
    request: CampaignDeliverRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CampaignAssetResponse:
    """Attach a real stored file to a planned asset — planned → delivered (V3.3)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        asset = campaign_service.deliver(
            workspace.id,
            campaign_id,
            asset_id,
            output_key=request.output_key,
            thumbnail_key=request.thumbnail_key,
        )
    except UnknownCampaignError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UnknownAssetError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidDeliveryError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="campaign.asset.delivered",
        resource_type="campaign_asset",
        resource_id=asset.id,
        workspace_id=workspace.id,
        detail={"campaign_id": campaign_id, "kind": asset.kind, "output_key": asset.output_key},
        request=http_request,
    )
    return _campaign_asset_payload(asset)


@app.post(
    "/api/v1/campaigns/{campaign_id}/export",
    response_model=CampaignExportResponse,
    status_code=201,
    tags=["campaign"],
)
def export_campaign(
    campaign_id: str,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CampaignExportResponse:
    """Build the Export Center ZIP: manifest, prompts, metadata and delivered files (V3.3)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        export = campaign_service.export(workspace.id, campaign_id)
    except UnknownCampaignError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="campaign.exported",
        resource_type="campaign_export",
        resource_id=export.id,
        workspace_id=workspace.id,
        detail={"campaign_id": campaign_id, "object_key": export.object_key, "file_count": export.file_count},
        request=http_request,
    )
    return _campaign_export_payload(export)


# ---------------------------------------------------------------------------
# V3.4 — Quality AI Engine: score, report, recommendation. Never execution.
#
# The engine composes the quality domain (`app/quality/*`); these routes hand
# facts in and map reports out, so no scoring logic lives in the HTTP layer.
# The structural gate (`/core/quality/*`, ETAPA 14) is untouched: it says
# whether an artifact exists at all, this block says how good it is — and
# every recommendation waits for a human at /studio/quality.
# ---------------------------------------------------------------------------


def _quality_report_payload(view) -> QualityAssetReportResponse:
    report = view.report
    return QualityAssetReportResponse(
        id=view.id,
        asset_id=view.asset_id,
        kind=view.kind,
        overall_score=view.overall_score,
        status=view.status,
        retry_recommended=view.retry_recommended,
        upscale_recommended=view.upscale_recommended,
        issues=list(report.get("issues", [])),
        strengths=list(report.get("strengths", [])),
        suggestions=list(report.get("suggestions", [])),
        criteria=[QualityCriterionResponse(**item) for item in report.get("criteria", [])],
        unmeasured=list(report.get("unmeasured", [])),
        engine_version=view.engine_version,
        operator_decision=report.get("operator_decision"),
        facts=dict(report.get("facts", {})),
        created_at=view.created_at,
    )


def _quality_facts_for(asset: Asset, request: QualityAssessAssetRequest) -> MediaFacts:
    """Assemble MediaFacts from the stored asset plus the caller's facts."""

    if asset.kind not in (KIND_IMAGE, KIND_VIDEO):
        raise HTTPException(status_code=422, detail="Only image and video assets can be assessed")
    try:
        resolved = str(storage.local_path(asset.object_key))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid asset path") from error
    expected_ratio = 0.0
    if request.aspect_ratio:
        expected_ratio = CORE_ASPECT_RATIOS.get(request.aspect_ratio, 0.0)
        if expected_ratio == 0.0:
            raise HTTPException(status_code=422, detail=f"Unknown aspect ratio {request.aspect_ratio!r}")
    return MediaFacts(
        kind=asset.kind,
        path=resolved,
        width=request.width,
        height=request.height,
        duration_seconds=request.duration_seconds,
        fps=request.fps,
        aspect_ratio_expected=expected_ratio,
        requested_duration=request.requested_duration,
        requested_fps=request.requested_fps,
        prompt_original=request.prompt_original,
        prompt_compiled=request.prompt_compiled,
    )


@app.post(
    "/api/v1/quality/assets/{asset_id}/assess",
    response_model=QualityAssetReportResponse,
    status_code=201,
    tags=["quality"],
)
def assess_asset_quality(
    asset_id: str,
    request: QualityAssessAssetRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> QualityAssetReportResponse:
    """Score one asset 0–100 on the eight weighted criteria and persist the report (V3.4).

    Unmeasured criteria are excluded and named, never averaged in as invented
    numbers; the verdict is a recommendation — nothing regenerates, upscales
    or approves automatically.
    """

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        asset = quality_repo.asset_for(workspace.id, asset_id)
    except UnknownQualityAssetError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    try:
        engine = QualityEngine(QualityScorer(request.weights)) if request.weights else quality_engine
        facts = engine.with_probed_geometry(_quality_facts_for(asset, request))
        assessment = engine.assess(facts, signals=request.signals)
        view = quality_repo.save_assessment(workspace.id, asset_id, assessment)
    except QualityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="quality.assessed",
        resource_type="quality_report",
        resource_id=view.id,
        workspace_id=workspace.id,
        detail={
            "asset_id": asset_id,
            "overall_score": view.overall_score,
            "status": view.status,
            "engine_version": view.engine_version,
        },
        request=http_request,
    )
    return _quality_report_payload(view)


@app.get(
    "/api/v1/quality/assets/{asset_id}/report",
    response_model=QualityAssetReportResponse,
    tags=["quality"],
)
def get_asset_quality_report(
    asset_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> QualityAssetReportResponse:
    """The asset's latest persisted quality report (V3.4)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        view = quality_repo.latest_report(workspace.id, asset_id)
    except (UnknownQualityAssetError, UnknownReportError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _quality_report_payload(view)


@app.get(
    "/api/v1/quality/assets/{asset_id}/history",
    response_model=list[QualityAssetReportResponse],
    tags=["quality"],
)
def get_asset_quality_history(
    asset_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[QualityAssetReportResponse]:
    """Every assessment of one asset, newest first — history is append-only (V3.4)."""

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        views = quality_repo.history(workspace.id, asset_id)
    except UnknownQualityAssetError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return [_quality_report_payload(view) for view in views]


@app.post(
    "/api/v1/quality/assets/{asset_id}/decision",
    response_model=QualityAssetReportResponse,
    tags=["quality"],
)
def record_asset_quality_decision(
    asset_id: str,
    request: QualityDecisionRequest,
    http_request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> QualityAssetReportResponse:
    """Record the operator's choice — regenerate, upscale or approve (V3.4).

    Recording is all that happens: the sprint forbids executing a retry
    automatically, so the buttons write intent and the operator drives the
    render/export flows they already have.
    """

    workspace = _workspace_for(db, user)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        view = quality_repo.record_decision(workspace.id, asset_id, request.decision)
    except (UnknownQualityAssetError, UnknownReportError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except QualityValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit(
        db,
        actor=user,
        action="quality.decision",
        resource_type="quality_report",
        resource_id=view.id,
        workspace_id=workspace.id,
        detail={"asset_id": asset_id, "decision": request.decision},
        request=http_request,
    )
    return _quality_report_payload(view)


@app.get("/api/v1/quality/config", response_model=QualityConfigResponse, tags=["quality"])
def get_quality_config() -> QualityConfigResponse:
    """The engine's public contract: criteria, default weights, bands, sources (V3.4).

    Reference data with no tenant state, public by design like `/core/quality/*`.
    """

    return QualityConfigResponse(
        criteria=list(QUALITY_CRITERIA),
        image_criteria=list(IMAGE_CRITERIA),
        video_criteria=list(VIDEO_CRITERIA),
        weights=dict(QUALITY_DEFAULT_WEIGHTS),
        retry_below=RETRY_BELOW,
        approved_at=APPROVED_AT,
        masterpiece_at=MASTERPIECE_AT,
        issue_below=ISSUE_BELOW,
        strength_at=STRENGTH_AT,
        upscale_short_side_below=UPSCALE_SHORT_SIDE_BELOW,
        statuses=list(QUALITY_STATUSES),
        sources=list(QUALITY_SOURCES),
        engine_version=QUALITY_ENGINE_VERSION,
    )
