# BROBOND API

## BROBOND CORE

`backend/app/core/` is the decision layer. Routes delegate to it; they never compose
prompts, pick cameras or resolve identities themselves.

```python
from app.core import DirectorAgent, GenerationSpecBuilder, MemoryResolver, PromptCompiler, ShotResolver, StyleResolver

spec_builder = GenerationSpecBuilder(
    memory=MemoryResolver(), styles=StyleResolver(), shots=ShotResolver(), compiler=PromptCompiler()
)
result = spec_builder.build_traced(prompt="hero product shot", persona_id="CHAR_PETRICK", style="john-wick", shot="SH122")
result.spec.prompt_compiled   # what a provider will receive
result.trace.sources          # which source won each contested field
```

The independent seed components import only `core/contracts.py`. Persistence is injected
through the `PersonaSource` / `StyleSource` / `ShotSource` protocols, so the Core never
imports SQLAlchemy — ETAPA 4/5/6 plug a PostgreSQL source in without touching Core code.
PR005's Director AI package composes those pure pieces into a planning artifact, and PR006
adds a versioned `StoryboardState` editor model. Both stay planning/editing-only without
importing providers or framework code.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/core/direct` | Intention → concept, script, scenes, cameras, music, duration. Never returns a prompt. |
| `POST /api/v1/core/director/production-plan` | PR005: immutable `ProductionPlan` with 4–8 `ShotPlan` scenes. Planning only; no render. |
| `/studio/director` | PR006: visual `StoryboardState` editor over the plan — drag/drop, timeline, camera/mood panels, undo/redo and duplicate scene. |
| `POST /api/v1/core/compile` | Dry run → compiled `GenerationSpec` + resolution trace. Generates nothing. |

`POST /api/v1/storyboards/expand` and `POST /api/v1/prompts/enhance` are unchanged at the
contract level. `prompt_engine.py` is now a facade over `PromptCompiler`, keeping
`PromptEnhancer`, `default_style` and `enhance(...)` for existing callers.

## Provider adapters

PR007 adds the universal GPU Provider Orchestrator. `providers/base_provider.py` defines the
single runtime contract (`BaseProvider`, capabilities, estimates, health and assets),
`providers/provider_registry.py` resolves provider IDs/aliases through registrations, and
`providers/generation_executor.py` executes `GenerationSpec -> Provider -> Asset -> Job`
without knowing model names.

```python
from app.providers import ProviderRegistry, ProviderRegistration, GenerationExecutor

registry = ProviderRegistry()
registry.register(ProviderRegistration("mock", "Mock", factory=lambda model_id=None: MockProvider()))
execution = GenerationExecutor(registry).execute(spec, output_dir="/tmp/out")
```

The legacy Core catalog remains in `providers/registry.py`: it documents adapter kind,
status, checkpoint and conditioning compatibility for `/api/v1/core/providers`. Runtime
health/capability discovery for the universal layer is exposed at `/api/v1/providers` and
returns status, latency, version and capabilities without secrets.

A provider that cannot run raises `ProviderUnavailable` rather than falling back. Running a
different model than the one requested is the failure this design exists to prevent. The
required `MockProvider` returns fake image/video/upscale artifacts so tests do not need GPU
weights.

## Prompt compiler

`core/prompt_compiler.py` is the only place prompt text is produced. It emits the twelve
blocks `SYSTEM_PROMPT.md` declares, in that order, and keeps the negative prompt separate.

```python
compiler = PromptCompiler()
compiler.budget_for("any-provider")      # 1000 — provider names are opaque to Core
compiler.budget_for(budget=1200)         # provider capability resolved at the boundary
compiler.compile_beats(                  # one prompt per cast scene
    storyboard_engine.as_beats(board),
    brief=board.brief,
    color=style_resolver.color_phrase(style),
    style=style_resolver.style_phrase(style),
    provider="flux-dev",
)
```

`compile_beats` is typed on `SceneBeat` — a contract type — rather than on `Storyboard`,
because the compiler imports `contracts` and nothing else. That independence is enforced by
`test_core_independence.py`, not by convention. Served by
`POST /api/v1/core/storyboard/compile`.

## Storyboard engine

`core/storyboard_engine.py` casts beats into shots. The Director still owns the beats
(objective, emotion, duration) and the format; the engine owns which shot plays which beat,
in what order, and whether the sequence holds together.

```python
engine = StoryboardEngine(director=DirectorAgent(), shots=ShotLibrary(), grammar=CinematicLibrary())
board = engine.build("Quero um comercial de 30 segundos para uma camiseta artesanal.", scene_count=5)
engine.validate(board)   # {'valid': True, 'violations': [], 'attention': [], ...}
```

`as_beats()` projects the cast storyboard back onto `SceneBeat` with `shot_code` filled in,
which is what makes the 300-shot library reachable from the existing prompt path. Served by
`POST /api/v1/core/storyboard`; the pre-existing `/api/v1/storyboards/expand` is unchanged.

## Director AI Engine (PR005)

`core/director/` turns a human brief into a full production plan:

```python
from app.core.director import DirectorAgent

plan = DirectorAgent().create_production_plan(
    user_intent="Criar um comercial épico para tênis de corrida",
    persona_id="persona-123",
    platform="youtube",
    duration=45,
    mood="Epic",
)
plan.shots[0].camera     # Dolly, Orbit, Crane, Tracking, Static or Drone
plan.shots[0].prompt     # planned text only; nothing rendered
```

`MoodEngine` resolves the six presets declared in `mood_config.py`; `CameraDirector` consumes
`ShotLibrary` and returns an editable first camera pass. `ProductionPlan` and `ShotPlan` are
frozen dataclasses, so a created plan is immutable at the backend boundary. Served by
`POST /api/v1/core/director/production-plan` and documented in `docs/DIRECTOR_AI.md`.

## Storyboard Cinematic Engine (PR006)

`core/director/storyboard_state.py` adds the editable state that sits after a production plan:

```python
from app.core.director import StoryboardState

state = StoryboardState.from_production_plan(plan, project_id="project-1")
state = state.reorder_scene(state.scenes[3].id, state.scenes[1].id)
state = state.apply_mood(state.scenes[0].id, "Neo")
```

`StoryboardState` carries `project_id`, `production_plan_id`, `scenes`, `version` and
`updated_at`; every real edit returns a new frozen state with `version + 1`. Scene updates are
field patches, not scene regeneration. Reorder recalculates `scene_number`, timeline markers
and total duration. `StoryboardHistory` provides undo/redo with a 50-state cap. Documented in
`docs/STORYBOARD_ENGINE.md`.

## Shot library

300 direction presets in 12 narrative families. A shot is a reusable direction preset, not a
prompt blob.

```python
from app.core import ShotLibrary

lib = ShotLibrary()
lib.count()                          # -> 300
lib.by_family("tension")             # 24 presets
lib.by_lens(135)                     # every 135mm shot
lib.by_motivation("approach")        # every motivated approach
lib.violations()                     # -> {} : all 300 obey the CINEMATIC_BIBLE
lib.audit()                          # total, target, per-family counts, violations
```

`speed`, `focus`, `shake` and `depth` are derived from frame, lens and movement, so 300
entries cannot contradict each other. The ten published presets are untouched and carry no
invented values.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/core/shots?q=&family=&lens_mm=&frame=&motivation=&limit=` | the visual shot browser |
| `GET /api/v1/core/shots/families` | the 12 families and their counts |
| `GET /api/v1/core/shots/audit` | size, target and Bible compliance |
| `GET /api/v1/core/shots/{shot_code}` | one preset, with the grammar read off it |

An unknown code answers `404` — inventing camera language is worse than omitting it.

## Cinematic library

`knowledge_base/CINEMATIC_BIBLE.md` is queryable grammar plus enforceable rules:

```python
from app.core import CinematicLibrary

lib = CinematicLibrary()
lib.lens_for("isolation")                    # -> [135mm]
lib.light_for("legacy")                      # -> warm side light
lib.motivation_of("slow dolly-in")           # -> ("approach",)
lib.is_still("static")                       # -> True (no movement, no motivation owed)
lib.audit_library(styles, shots)              # -> the library's own exceptions
lib.episode_consistency([style_a, style_b])  # -> grain drift is a violation
```

The library describes and judges; it never composes prompts and never picks a style — those
belong to `PromptCompiler` and `DirectorAgent`.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/core/cinematic/lenses` | the five focal lengths and what each is for |
| `GET /api/v1/core/cinematic/lenses/for?purpose=isolation` | focal lengths serving a purpose |
| `GET /api/v1/core/cinematic/framing` | shot sizes and what each angle creates |
| `GET /api/v1/core/cinematic/lighting` | light roles and the tone each quality supports |
| `GET /api/v1/core/cinematic/motivations` | the five legitimate reasons to move the camera |
| `GET /api/v1/core/cinematic/motivations/of?motion=…` | is this move motivated? |
| `GET /api/v1/core/cinematic/audit` | the published library checked against the Bible |
| `GET /api/v1/core/cinematic/explain?style=…` | director-facing prose for a style |
| `GET /api/v1/core/cinematic/consistency?styles=a&styles=b` | episode visual cohesion |

All nine are read-only: a reference library is not mutated over HTTP.

## Persona memory

Character identity is permanent, versioned and attributed:

```python
from app.core import PersonaMemoryEngine

engine = PersonaMemoryEngine()
engine.remember("CHAR_PETRICK", episode_id="EP01")          # bind identity to an episode
engine.revise("CHAR_PETRICK", actor="diretor", reason="novo arco em EP2",
              authorized=True, eyes="green eyes")           # new version, recorded
engine.recall("EP01", "CHAR_PETRICK").eyes                  # -> "dark brown eyes"
engine.continuity("CHAR_PETRICK", ["EP01", "EP02"])         # drift report
```

An identity change without `authorized=True` is rejected and nothing is written. Approval of
a character with no defined attributes is rejected too: approval certifies an identity, it
never invents one.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/core/personas` | current identities, with version and `generable` |
| `GET /api/v1/core/personas/{id}` | full attributed history + drift |
| `POST /api/v1/core/personas/{id}/revise` | attributed edit (identity fields need `authorized`) |
| `POST /api/v1/core/personas/{id}/approve` | promote a defined character |
| `POST /api/v1/core/personas/{id}/retire` | stop generation, keep history |
| `POST /api/v1/core/personas/{id}/episodes/{ep}/snapshot` | bind identity to an episode |
| `GET /api/v1/core/personas/{id}/episodes/{ep}/memory` | the identity that episode used |
| `GET /api/v1/core/personas/{id}/continuity?episodes=EP01&episodes=EP02` | consistency report |

Errors: `404` unknown persona, `409` rule violation, `422` validation.

## Provider contract

Since ETAPA 3 a provider receives **only** a `GenerationSpec`; PR007 universalizes that rule
for image, video and upscale:

```python
class BaseProvider(ABC):
    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset: ...
    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset: ...
    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset: ...
    def health(self) -> ProviderHealth: ...
    def estimate(self, spec: GenerationSpec) -> ProviderEstimate: ...
```

The worker builds the spec with `app.spec_adapter.compile_job(job)`, folds in the resolved
LoRA and reference paths after validating workspace ownership, and hands that single object
to `GenerationExecutor`. `app/spec_adapter.py` is the only module that knows both
`app.schemas.Job` and the Core, which is what keeps the Core free of API imports.

Sampling parameters (`resolution`, `guidance_scale`, `steps`, `ip_adapter_scale`, `mode`,
`cinematic_mode`, `slow_motion`, `native_audio`) travel inside the spec as typed extras
beyond the 19 mandatory fields — a provider cannot receive a loose `dict` beside it.

Each provider declares `CONSUMED_SPEC_FIELDS` and `UNSUPPORTED_SPEC_FIELDS`, so "not
supported here" is stated instead of silently dropped.

## Run

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

Open the interactive contract at `http://localhost:8000/docs`.

The default database is local SQLite (`brobond.db`). Set `BROBOND_DATABASE_URL` to a PostgreSQL URL and `BROBOND_JWT_SECRET` in `.env` for a hosted environment. Authentication endpoints are `/api/v1/auth/register`, `/api/v1/auth/login`, and `/api/v1/auth/me`.

Queue mode is disabled by default for offline development. Start Redis and set `BROBOND_QUEUE_ENABLED=true` to send tasks through Celery. Queue observability is available through `POST /api/v1/jobs/{job_id}/cancel` and `WS /api/v1/queue/events/{job_id}`.

Storage mode is local by default: uploaded files are written to `media/` and exposed through the API. For MinIO, set `BROBOND_STORAGE_ENABLED=true`, configure `BROBOND_MINIO_ENDPOINT`, `BROBOND_MINIO_ACCESS_KEY`, `BROBOND_MINIO_SECRET_KEY`, and create the configured bucket before uploading. Asset endpoints are `POST /api/v1/assets/upload` and `GET /api/v1/assets`.

Image inference is orchestration-only by default. On a CUDA worker, install `requirements-gpu.txt`, set `BROBOND_INFERENCE_ENABLED=true`, and use the Celery worker. The FLUX provider then loads weights from `BROBOND_WEIGHTS_DIR`, uploads generated output through the active storage adapter, creates an `Asset` record, and exposes the final URL on the job. Authenticated generation requests carry the user's workspace into this output pipeline.

Worker readiness is exposed at `GET /api/v1/system/readiness`; it reports CUDA, FFmpeg, Torch, Diffusers, Redis client and Celery availability before a real render. Copy `.env.example` to `.env` and enable providers only after the readiness response is healthy.

FFmpeg capability is exposed at `GET /api/v1/system/media`. Local video assets can be exported to H.264 MP4 with `POST /api/v1/assets/{asset_id}/export` using `quality` (`720p`, `1080p`, `2k`, `4k`) and `fps` (`24` or `30`). Video model options are exposed at `GET /api/v1/models/video`. For local Wan inference, install `requirements-video-gpu.txt`; the Celery worker will use `BROBOND_VIDEO_MODEL_ID` and persist the resulting MP4 as a workspace Asset.

Conditioning options are exposed at `GET /api/v1/models/conditioning`. Image jobs accept `controlnet`, `controlnet_scale`, `ip_adapter_scale`, and `reference_asset_id`; the worker validates workspace ownership before passing local references to a compatible provider pipeline. Reference preprocessing is available at `POST /api/v1/assets/{asset_id}/conditioning` for `edges`, `depth`, and `tile`; `pose` is reserved for the GPU OpenPose worker. The Celery task `brobond.preprocess_reference` provides the asynchronous provider boundary; install `requirements-preprocess-gpu.txt` for OpenPose and GPU preprocessing dependencies.

Persona training is validated through `POST /api/v1/personas/{persona_id}/train` and requires 20–50 reference asset IDs. Each execution is persisted as a `TrainingRun` and can be read from `GET /api/v1/personas/{persona_id}/training/{run_id}` or streamed through `WS /api/v1/personas/{persona_id}/training/events/{run_id}`. The Celery `train_lora` task prepares `metadata.jsonl`, validates image files, and calls the configured trainer without ever fabricating a model file. For a GPU worker, install `requirements-training-gpu.txt`, set `BROBOND_TRAINING_ENABLED=true`, `BROBOND_QUEUE_ENABLED=true`, and configure `BROBOND_LORA_TRAINER_COMMAND`.

## Test

```bash
PYTHONPATH=backend pytest backend/tests -q          # 1,955 tests
```

Coverage:

```bash
coverage run --source=backend/app -m pytest backend/tests -q
coverage report --skip-empty                        # backend/app at 96%, core at 98%, providers at 99%
```

`core/persona_memory.py`, `core/cinematic_library.py`, `core/shot_library.py`,
`core/storyboard_engine.py`, `core/prompt_compiler.py` and `core/style_resolver.py` are each
at 100%, as are the legacy provider catalog modules `providers/registry.py` and
`providers/conditioning.py`. The universal PR007 provider layer is covered by
`test_pr007_provider_orchestrator.py`; the remaining gaps are defensive/provider-unavailable
branches and GPU inference paths that cannot run without torch and diffusers. The directory
total is held back by the pre-existing unused `core/security.py` at 0% (see `AUDIT.md`).

The Core test suite is hermetic: `test_core_independence.py` spawns subprocesses with the
backend root injected explicitly, so it passes with `PYTHONPATH=backend`, without it, and
from inside `backend/`.

The current store is intentionally in-memory. The API boundary is stable so the next infrastructure step can replace it with SQLAlchemy repositories and Celery tasks.
