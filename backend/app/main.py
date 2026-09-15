"""FastAPI entrypoint for BROBOND AI STUDIO's local service boundary."""
import asyncio
from pathlib import Path
import time
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse, current_user, login, optional_user, register
from .conditioning import catalog
from .core.contracts import GenerationKind, GenerationSpec
from .core import (
    ASPECT_BY_FORMAT,
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
from .core.config import settings
from .db import Base, SessionLocal, engine, get_db
from .events import TERMINAL_STATUSES, hub, job_event
from .knowledge import resolve as resolve_knowledge, seed_knowledge
from .lora import lora_trainer
from .media import MediaError, media
from .models import Asset, TrainingRun, User, Workspace
from .providers import registry as provider_registry
from .prompt_engine import prompt_engine
from .queue import enqueue, enqueue_lora_training
from .readiness import readiness
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
    AssetResponse, ConditioningRequest, DirectorBriefResponse, DirectorRequest, ExportRequest, ExportResponse,
    EpisodeConsistencyResponse,
    FrameProfileResponse,
    FramingResponse,
    GenerationSpecRequest, GenerationSpecResponse, GenerationType, KnowledgeResponse, LoraVersionResponse,
    ImageGenerationRequest, Job, JobStatus, Persona, PersonaCreateRequest,
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
    CoreStoryboardFindingResponse, CoreStoryboardRequest, CoreStoryboardResponse,
    CoreStoryboardShotResponse,
    StoryboardRequest, StoryboardResponse, StoryboardScene, VideoGenerationRequest,
    StyleExplanationResponse,
    TimeQualityResponse,
    TrainingStatusResponse,
)
from .store import store

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
    """Create tables and seed knowledge, retrying while the database is still
    booting. On Render the managed Postgres can take a few minutes to become
    reachable after a fresh blueprint deploy; retrying here avoids a
    crash-loop on first boot. Development deployments should run Alembic
    migrations instead of create_all."""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            # Lightweight local migration for existing SQLite development databases.
            if "training_runs" in inspect(engine).get_table_names():
                columns = {column["name"] for column in inspect(engine).get_columns("training_runs")}
                if "workspace_id" not in columns:
                    with engine.begin() as connection:
                        connection.execute(text("ALTER TABLE training_runs ADD COLUMN workspace_id VARCHAR(36)"))
            with SessionLocal() as seed_db:
                seed_knowledge(seed_db)
            return
        except Exception as exc:  # pragma: no cover - depends on DB availability
            last_error = exc
            print(f"[brobond] database not ready (attempt {attempt}/{retries}): {exc}", flush=True)
            time.sleep(delay_seconds)
    raise RuntimeError(f"database bootstrap failed after {retries} attempts: {last_error}")


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
memory_resolver = MemoryResolver(persona_ledger)
style_resolver = StyleResolver()
# ETAPA 6: the resolver serves the full 300-shot library. SEED_SHOTS (the ten
# published presets) stays untouched; the expansion is composed in here, at the
# application boundary, so shot_resolver.py never imports shot_library.py.
shot_library = ShotLibrary()
shot_resolver = ShotResolver(SeedShotSource(FULL_SHOT_LIBRARY))
prompt_compiler = PromptCompiler()
director_agent = DirectorAgent()
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
)


@app.get("/health", tags=["system"])
@app.get("/api/v1/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "brobond-api", "mode": "local"}


@app.get("/api/v1/system/gpu", tags=["system"])
def system_gpu() -> dict:
    return gpu_info()


@app.get("/api/v1/system/readiness", tags=["system"])
def system_readiness() -> dict:
    return readiness()


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
def knowledge(query: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> list[KnowledgeResponse]:
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
    """Stream a job's transitions until it reaches a terminal state.

    ETAPA 11: this route used to send one snapshot and then block in
    `await websocket.receive_text()` — a read loop, not a push. The job could
    finish and the client would never hear about it, because nothing ever called
    `hub.publish`. It now drains the hub's event buffer and closes on a terminal
    status, so a client that connects late still gets the history and a clean end.
    """

    job = store.get_job(job_id)
    if not job:
        await websocket.close(code=1008, reason="Generation job not found")
        return
    await hub.connect(job_id, websocket)
    try:
        # The current state first: a client must never have to wait for the next
        # transition to learn where the job already is.
        await websocket.send_json(job.model_dump(mode="json"))
        cursor = 0
        sent_terminal = False
        while True:
            events = hub.history(job_id, cursor)
            for event in events:
                await websocket.send_json(event)
                if event.get("event") in TERMINAL_STATUSES:
                    sent_terminal = True
            cursor += len(events)

            current = store.get_job(job_id)
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


@app.get("/api/v1/queue", response_model=list[Job], tags=["queue"])
def list_queue() -> list[Job]:
    return list(store.jobs.values())


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
def list_persona_memory(query: str = "") -> list[PersonaMemoryResponse]:
    """Current identities in the character library, with their version."""

    return [_persona_memory(persona.persona_id) for persona in persona_engine.catalog(query)]


@app.get("/api/v1/core/personas/{persona_id}", response_model=PersonaHistoryResponse, tags=["core"])
def read_persona_memory(persona_id: str) -> PersonaHistoryResponse:
    """A character's full history: every revision, who made it and why.

    Nothing is overwritten, so `history` grows monotonically and identity
    versions stay retrievable.
    """

    return _persona_history(persona_id)


@app.post("/api/v1/core/personas/{persona_id}/revise", response_model=PersonaVersionResponse, tags=["core"])
def revise_persona_memory(persona_id: str, request: PersonaRevisionRequest) -> PersonaVersionResponse:
    """Apply an attributed edit.

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
    return PersonaVersionResponse(**entry.to_dict())


@app.post("/api/v1/core/personas/{persona_id}/approve", response_model=PersonaMemoryResponse, tags=["core"])
def approve_persona_memory(persona_id: str, request: PersonaTransitionRequest) -> PersonaMemoryResponse:
    """Promote a planned character to approved.

    Refuses with 409 when no identity attribute is defined: approval certifies
    an identity, it never invents one.
    """

    try:
        persona_engine.approve(persona_id, actor=request.actor, reason=request.reason or "identity approved")
    except PersonaNotFound:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from None
    except MemoryError_ as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    return _persona_memory(persona_id)


@app.post("/api/v1/core/personas/{persona_id}/retire", response_model=PersonaMemoryResponse, tags=["core"])
def retire_persona_memory(persona_id: str, request: PersonaTransitionRequest) -> PersonaMemoryResponse:
    """Retire a character. Episodes already made keep their memory snapshots."""

    try:
        persona_engine.retire(persona_id, actor=request.actor, reason=request.reason or "retired")
    except PersonaNotFound:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from None
    except MemoryError_ as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    return _persona_memory(persona_id)


@app.post("/api/v1/core/personas/{persona_id}/episodes/{episode_id}/snapshot", response_model=dict, tags=["core"])
def snapshot_persona_for_episode(persona_id: str, episode_id: str) -> dict:
    """Bind the current identity to an episode.

    This is what makes "existing episodes keep their original memory snapshot"
    true: later revisions do not reach back into this episode.
    """

    try:
        return persona_engine.remember(persona_id, episode_id=episode_id)
    except PersonaNotFound:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from None


@app.get("/api/v1/core/personas/{persona_id}/episodes/{episode_id}/memory", response_model=PersonaMemoryResponse, tags=["core"])
def recall_episode_memory(persona_id: str, episode_id: str) -> PersonaMemoryResponse:
    """The identity an episode was actually made with, not the current one."""

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
def persona_continuity(persona_id: str, episodes: list[str] = Query(default_factory=list)) -> dict:
    """Whether a character stayed consistent across the given episodes."""

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
    compiled = prompt_compiler.compile_beats(
        storyboard_engine.as_beats(storyboard),
        brief=storyboard.brief,
        persona=memory_resolver.identity_phrase(persona),
        environment=style_resolver.environment_phrase(style),
        color=style_resolver.color_phrase(style),
        style=style_resolver.style_phrase(style),
        negative=request.negative_prompt,
        provider=request.provider,
    )
    report = storyboard_engine.validate(storyboard)
    return CoreStoryboardCompileResponse(
        brief=storyboard.brief,
        format=storyboard.format,
        provider=request.provider,
        budget=prompt_compiler.budget_for(request.provider),
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
# ETAPA 10 — provider adapters: what can run, and what it would run
#
# The registry is the single source of truth for adapter selection. These routes
# expose it; they contain no selection logic of their own.
# ---------------------------------------------------------------------------


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
