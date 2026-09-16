# BROBOND AI STUDIO

A local-first generative visual workspace for images, cinematic video, motion control, personas and storyboards.

## Product constitution and Knowledge Base

The product constitution lives in `SYSTEM_PROMPT.md`, `ARCHITECTURE.md`, `STYLE_GUIDE.md` and `ROADMAP.md`. The initial persistent knowledge source is organized under `knowledge_base/`:

- `CINEMATIC_BIBLE.md`
- `BROBOND_STYLE_GUIDE.md`
- `CHARACTER_LIBRARY.md`
- `SHOT_LIBRARY.md`
- `PROMPT_LIBRARY.md`

These files are versioned design knowledge today. The next Core milestone is migrating them into PostgreSQL-backed, workspace-scoped records while preserving these documents as seed and governance sources.

## Current slice

A Next.js studio whose front door is the **Director**: the user states an intention in plain
language and receives direction — concept, logline, script, beats, cameras, music, pacing and
duration — instead of being handed a prompt field.

- **Director** — `POST /api/v1/core/direct`, the default view
- Overview dashboard with creative tools and **live** system state from `/api/v1/system/*`
- Image generation (model, ratio, resolution, LoRA, ControlNet and reference), wired to what it renders
- Video generation (model, duration, format, native audio, cinematic mode)
- Persona Lab with identity profile and LoRA training status over WebSocket
- Storyboard cast through `/api/v1/core/storyboard`, showing the shots chosen **and** the findings
- `/studio/director` now opens a versioned visual storyboard editor with drag/drop, timeline, per-scene camera/mood panels, undo/redo and duplicate scene — editing only, no render
- Asset library with counts read from the API

The canvas shows the **real** `output_url` of the job, or says plainly that the render failed.
ETAPA 15 removed the CSS figure that used to stand in for a generated image — a `failed` and a
`complete` job no longer look the same.

Nothing is simulated any more, and nothing is invented: when a dependency is missing the UI
says which one. See `docs/LIMITATIONS.md` for what still cannot run on a machine without a GPU.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Deploy no Render (CI/CD automático)

O repositório inclui um [Render Blueprint](https://render.com/docs/blueprint-spec) em
`render.yaml` com tudo o que o studio precisa: UI Next.js (`brobond-studio-web`),
API FastAPI em Docker (`brobond-ai-api`) e um PostgreSQL gerenciado
(`brobond-studio-db`). Com o auto-deploy habilitado, **todo push para `main` é
publicado automaticamente** — não é necessário nenhum step extra no GitHub
Actions (o workflow existente continua rodando testes e build a cada push/PR).

### Passo a passo (Render CLI)

Pré-requisito: repositório público no GitHub conectado ao seu plano Render
(planos free aceitam repositórios públicos).

1. **Instale e faça login no CLI**

   ```bash
   npm install -g render
   render login
   ```

2. **Publique o blueprint (cria os serviços + banco de uma vez)**

   ```bash
   render blueprint deploy --path render.yaml
   ```

   O comando cria/atualiza:
   - `brobond-studio-web` — Web Service Node (`npm ci && npm run build` + `npm start`), URL `https://brobond-studio-web.onrender.com`
   - `brobond-ai-api` — Web Service Docker (`Dockerfile.api`), URL `https://brobond-ai-api.onrender.com`, health check em `/api/v1/health`
   - `brobond-studio-db` — PostgreSQL free, com a connection string injetada como `BROBOND_DATABASE_URL`

3. **Confira o deploy**

   ```bash
   render deployments list --service brobond-ai-api
   curl https://brobond-ai-api.onrender.com/api/v1/health
   ```

   Na primeira publicação o Postgres demora alguns minutos para ficar pronto; a
   API faz retry no bootstrap e o Render reinicia o container até subir.

4. **A partir daí: push = publish**

   ```bash
   git push origin main
   ```

   Cada push em `main` gera um novo deploy dos dois serviços (auto-deploy).
   Para publicar a partir de outra branch, ajuste *Root Directory/Repo* e a
   branch em Settings do serviço no dashboard Render.

### Variáveis de ambiente

| Serviço | Variável | Origem |
| --- | --- | --- |
| web | `NEXT_PUBLIC_API_URL` | `https://brobond-ai-api.onrender.com` (fixada no blueprint; `NEXT_PUBLIC_*` é assada no build, então alterar exige novo deploy) |
| api | `BROBOND_DATABASE_URL` | sincronizada do `brobond-studio-db` (normalizada para `postgresql+psycopg://` automaticamente) |
| api | `BROBOND_JWT_SECRET` | gerada pelo Render (`generateValue`) |
| api | `BROBOND_CORS_ORIGINS` | origem pública da web + localhost (padrão de desenvolvimento) |
| api | `BROBOND_QUEUE_ENABLED` / `BROBOND_STORAGE_ENABLED` / `BROBOND_INFERENCE_ENABLED` | `false` (modo orquestração, sem GPU) |

### Alternativa: pelo dashboard (sem CLI)

1. Render → *New → Web Service* → selecione o repositório → runtime **Node**, build `npm ci && npm run build`, start `npm start`, health check `/`, env var `NEXT_PUBLIC_API_URL=https://brobond-ai-api.onrender.com`. O `npm run build` é obrigatório: `.next/` está no `.gitignore`, então sem ele o `next start` falha com *Could not find a production build in the '.next' directory*.
2. *New → Web Service* → runtime **Docker**, Dockerfile `Dockerfile.api`, health check `/api/v1/health`, env vars: `BROBOND_DATABASE_URL` (connection string do Postgres), `BROBOND_JWT_SECRET` (qualquer string longa), `BROBOND_CORS_ORIGINS=https://brobond-studio-web.onrender.com`.
3. *New → PostgreSQL* (free) e copie a connection string para `BROBOND_DATABASE_URL` do serviço da API.
4. Em cada serviço, mantenha **Auto-Deploy** habilitado.

### Limitações do plano free (leia antes de publicar)

- Instâncias inativas são suspensas; a primeira requisição após o idle demora
  alguns segundos (cold start) e o serviço exige health check 200 para não ser
  reciclado — por isso os paths de health check acima.
- Redis não está disponível em blueprints do Render. Com
  `BROBOND_QUEUE_ENABLED=false` a API executa jobs in-process (o bastante para
  o modo orquestração). Quando adicionar workers Celery, crie um Redis no
  dashboard e defina `BROBOND_REDIS_URL` manualmente.
- O filesystem do container é efêmero: assets salvos em `media/` locais somem
  em cada deploy. Para persistência real, habilite o storage S3/MinIO
  (`BROBOND_STORAGE_ENABLED=true` + credenciais).
- Inferência de GPU (Flux/Wan, treino de LoRA) não roda no Render: mantenha
  `BROBOND_INFERENCE_ENABLED=false` e ligue os providers por adapter quando
  houver um worker GPU próprio (ver `ROADMAP.md`).

## BROBOND CORE

The decision layer lives in `backend/app/core/` and is the only place where creative
decisions are made. The original independent Core components remain in place; PR005
adds `backend/app/core/director/` for full production planning and PR006 extends it with
versioned storyboard editing:

| Component | What it owns |
| --- | --- |
| `MemoryResolver` | Permanent character identity, identity phrase, versioned revisions |
| `StyleResolver` | Style → lens, LUT, lighting, contrast, grain, camera motion, particles, fps |
| `ShotResolver` | Stable `SH###` codes → camera path, speed, lens, focus, shake, depth |
| `PromptCompiler` | The only place prompt text is produced: ordered blocks + negative prompt |
| `DirectorAgent` | Plain-language intention → concept, script, scenes, cameras, music, duration |
| `GenerationSpecBuilder` | The composition root: combines the four above into a `GenerationSpec` |
| `core/director/ProductionPlan` | Immutable plan: concept, mood, audience, platform, duration, music, voice and shots |
| `core/director/ShotPlan` | Required scene contract: objective, emotion, camera, lens, lighting, motion and prompt |
| `core/director/MoodEngine` | Internal presets `Luxury`, `Epic`, `Dark`, `Minimal`, `Sport`, `Neo` from config |
| `core/director/CameraDirector` | Selects Dolly/Orbit/Crane/Tracking/Static/Drone from the existing Shot Library |
| `core/director/StoryboardState` | PR006 editor state: versioned scenes, timeline, drag reorder, mood/camera patches and history |

Two rules the test suite enforces:

- **No route contains generation logic.** `POST /api/v1/storyboards/expand` and
  `POST /api/v1/prompts/enhance` keep their exact previous contracts; only the
  composition moved out of the route and into the Core.
- **No original independent component imports a peer.** `backend/tests/test_core_independence.py`
  imports each listed module in a fresh interpreter with `app.core.__init__` stubbed out and
  fails if a sibling is pulled in. `GenerationSpecBuilder` remains the single declared
  composition root for `GenerationSpec`; PR005/PR006's Director AI package composes
  planning/editing-only pieces and never calls providers.

New endpoints:

- `POST /api/v1/core/direct` — send an intention such as `"Quero vender uma camiseta"`,
  receive concept, script, scenes, cameras, music and duration. No technical prompt is
  ever returned. When the intention could follow more than one language, the response
  carries one short `clarification` question instead of a guess.
- `POST /api/v1/core/director/production-plan` — PR005 Director AI Engine: returns an
  immutable `ProductionPlan` with 4–8 editable `ShotPlan` scenes. Planning only; no image
  generation and no provider call.
- `POST /api/v1/core/compile` — dry run that returns the compiled `GenerationSpec` plus
  the resolution trace (which source won each contested field). Generates no media.

`GenerationSpec` declares 19 mandatory fields in one place
(`core/contracts.py:GENERATION_SPEC_FIELDS`): `project_id`, `user_id`, `persona_id`,
`style_id`, `prompt_original`, `prompt_compiled`, `negative_prompt`, `camera`, `lens`,
`lighting`, `motion`, `weather`, `aspect_ratio`, `fps`, `duration`, `provider`, `seed`,
`lora`, `controlnet`.

**Every provider receives only this object.** `ImageProvider` and `VideoProvider` are
abstract classes whose single entry point is `generate(spec, output_dir)` — there is no
signature through which a loose prompt string or a `parameters` dict can reach a model.
Sampling parameters ride inside the spec as typed extras rather than beside it in a dict.
`app/spec_adapter.py` translates a queued `Job` into a spec and is the only module that
knows both the API schemas and the Core.

## Provider adapters

`SYSTEM_PROMPT.md` calls the providers *swappable adapters*. PR007 makes that literal in two
layers:

1. the legacy Core catalog (`GET /api/v1/core/providers`) still documents adapter kind,
   status, checkpoint and conditioning compatibility; and
2. the universal GPU Provider Orchestrator (`GET /api/v1/providers`) exposes runtime health,
   latency, version and capabilities through one `BaseProvider` contract.

```text
GET /api/v1/providers

  flux-dev      Flux  image:true  video:false  upscale:false  status: ready|unavailable
  wan-2.1-t2v   Wan   image:false video:true   upscale:false  status: ready|unavailable
  mock          Mock  image:true  video:true   upscale:true   status: ready
```

The Core never knows provider-specific model names or prompt budgets. It emits a
`GenerationSpec`; `GenerationExecutor` resolves the requested provider in
`ProviderRegistry`, calls only `BaseProvider`, and returns a `ProviderAsset` for the persisted
job. Flux and Wan receive the full spec, never a raw prompt string. The required
`MockProvider` stays in the registry so tests and local development can run without GPU
weights or credentials.

A provider that cannot run is **refused**, not silently replaced — asking for a remote-only,
planned or incompatible provider fails with a reason instead of quietly rendering with a
different model. Health/capability discovery never exposes secrets.

Adding a provider is one registration, not another branch in the worker:

```python
provider_registry.register(ProviderRegistration(
    provider_id="acme-image",
    label="Acme",
    factory=lambda model_id=None: AcmeProvider(model_id=model_id),
    aliases=("acme",),
))
```

Full PR007 notes: `docs/PROVIDERS.md`.

## Prompt compiler

`SYSTEM_PROMPT.md` declares thirteen internal blocks. The compiler emits twelve of them in
that order and keeps `NEGATIVE` separate, because diffusion providers take it as its own
argument:

```text
SUBJECT · CHARACTER · ENVIRONMENT · ACTION · CAMERA · LENS · LIGHT · COLOR
        · MOTION · STYLE · CONTINUITY · OUTPUT
```

Blocks are deduplicated on join, so a shot preset no longer makes the focal length appear
twice. Colour is its own block rather than part of `STYLE`, which means a prompt over budget
drops an adjective before it drops the grade. PR007 keeps provider-specific budgets in
`ProviderCapabilities.prompt_budget`; the Core compiler accepts only the resolved numeric
budget and otherwise uses its conservative default. Anything trimmed is reported in
`dropped` — never silently.

`POST /api/v1/core/storyboard/compile` puts the two together: it casts a brief into shots and
returns one compiled prompt per scene.

```text
POST /api/v1/core/storyboard/compile  { "brief": "...", "scene_count": 3 }

  scenes[0].shot_code  SH002
  scenes[0].prompt     "..., the world before the story, slow crane reveal descending to
                        street level, 24mm, blue hour ambience, ..."
  scenes[0].dropped    []
```

## Storyboard engine

A storyboard is a **cast**, not a list of camera phrases. `POST /api/v1/core/storyboard`
takes a brief and returns a shot sequence where every scene names a real preset from the
300-shot library, with its own lens, lighting, movement and continuity note:

```text
POST /api/v1/core/storyboard  { "brief": "...", "scene_count": 5 }

  COMMERCIAL — 5 scenes, 25.0s
  01. SH002 City Wakes        [establishing]  24mm
  02. SH028 First Silhouette  [introduction]  50mm
  03. SH157 Hero Product Reveal [product]     85mm
  04. SH158 Material Macro    [product]      135mm
  05. SH253 Walk Into Distance [resolution]   24mm
```

The narrative arc follows the detected format, opens on geography and closes on a resolution,
and the sequence is validated against the cinematic grammar — the response carries
`valid`, `violations` and `attention` so a director sees *what* is wrong with a cut rather
than just that it failed. `POST /api/v1/storyboards/expand` is untouched and still returns
prompt text; this endpoint casts shots and never produces a prompt.

## Shot library

300 direction presets across 12 narrative families — establishing, introduction, dialogue,
action, tension, intimacy, product, fashion, transition, atmosphere, resolution and
documentary. A shot is a reusable direction preset, not a prompt blob.

Every one of the 300 is validated against the `CINEMATIC_BIBLE` grammar: declared focal
length, motivated movement, known shot size, declared intention. The report is available at
`GET /api/v1/core/shots/audit`.

The ten originally published presets are untouched and keep their stable codes. See
`ETAPA6_REPORT.md` for the full breakdown, including the honest finding that `transformation`
motivation is covered by only 2 of the 300.

## Cinematic library

`knowledge_base/CINEMATIC_BIBLE.md` is queryable grammar plus enforceable rules. What each
focal length means, what each light does, which motivations justify moving the camera, and
whether a grade obeys the Bible — all of it is now data the code can check, not prose only a
human reads.

The library describes and judges. It never composes prompts and never picks a style: those
stay with `PromptCompiler` and `DirectorAgent`.

Running the rules over the published presets reports the library's own exceptions instead of
hiding them — see `ETAPA5_REPORT.md` for the findings.

## Persona memory

Character identity is permanent, versioned and attributed. Every edit records who made it
and why; an identity change without explicit authorisation is rejected and **nothing is
written**; a published episode keeps the identity snapshot it was made with.

A character with no defined attributes cannot be approved — approval certifies an identity,
it never invents one. `CHAR_JEFFERSON` remains `planned` for exactly that reason.

See `ETAPA4_REPORT.md` for the technical report and `ARCHITECTURE.md` for the model.

## Architecture target

```text
BROBOND-AI-STUDIO/
├── app/                  # Next.js App Router UI
│   ├── page.tsx          # workspace shell and module slices
│   └── globals.css       # design system
├── backend/              # FastAPI service boundary
│   ├── app/core/         # BROBOND CORE: director, memory, prompt, style, shot, spec
│   ├── app/api/          # versioned route package (see AUDIT.md: currently unused)
│   ├── app/providers/    # FLUX and Wan adapters
│   ├── app/services/     # service adapters
│   ├── app/main.py       # composition root: wires the Core, exposes the routes
│   ├── app/models.py     # SQLAlchemy models
│   └── tests/            # pytest suite (1,495 tests)
├── docker-compose.yml    # local Postgres, Redis and MinIO
└── requirements.txt      # Python service dependencies
```

## Inference boundary

The frontend is ready to consume these future endpoints:

- `POST /api/v1/generations/images`
- `POST /api/v1/generations/videos`
- `POST /api/v1/personas`
- `POST /api/v1/storyboards/expand`
- `GET /api/v1/assets`
- `WS /api/v1/queue/events`

Each generation is a persisted job (Postgres, via Alembic-managed schema), is processed by Celery workers, and publishes progress through Redis/WebSocket. Files belong in MinIO; PostgreSQL stores metadata; FFmpeg handles transcode/export.

## Design principles

- Local-first, SaaS-ready boundaries
- Provider adapters for Flux / Wan / Hunyuan rather than model logic in API routes
- Explicit job states: `queued`, `running`, `complete`, `failed`, `cancelled` (answered as `completed` on the wire — PR002)
- JWT authentication (secret validated at boot, ≥32 bytes) and workspace-scoped resources on every protected route, with a configurable rate limit on the credential endpoints and an append-only audit log for critical actions (PR002)
- Never commit model weights, generated media, secrets or `.env` files

## What is not built yet

The six items that used to live here as "next milestones" — FastAPI service, Postgres models,
Redis/Celery queue, MinIO signed URLs, WebSocket job updates and a test suite — were all
delivered by ETAPA 12 and removed from this list in ETAPA 17 rather than left as a to-do list
of finished work.

What genuinely remains is tracked in two places, both kept honest by tests:

- **`ROADMAP.md`** — the `- [ ]` items: first GPU-validated render, persisted Personas/Styles/
  Shots, Character and Prompt libraries, episode continuity, multi-tenancy, billing.
- **`docs/LIMITATIONS.md`** — what cannot be verified on a machine without a GPU, the state
  that still lives in memory, the 35 of 66 routes without authentication, and the four dead
  modules from `AUDIT.md` P0-1.

## Validation

The repository includes backend and frontend CI in `.github/workflows/ci.yml`. Run the full local validation with:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm run build
```

The end-to-end backend test covers registration, authenticated upload, generation job creation, storyboard expansion and asset listing.

The backend suite is **1,495 tests** and total backend coverage is **97%**, held by a `--fail-under=95` gate in CI. The whole
`backend/app/core/` directory reads 98%, with PR005 Director AI and PR006 StoryboardState covered above the 95% floor. The remainder of the gap is the pre-existing dead
cluster from `AUDIT.md` P0-1 — four modules, 100 statements, that do not import at all; see
`docs/LIMITATIONS.md` §5. `core/persona_memory.py`,
`core/cinematic_library.py`, `core/shot_library.py` and `core/storyboard_engine.py` are all
at 100%.

Suites by area: `test_core_contracts.py`, `test_core_memory_resolver.py`,
`test_core_style_resolver.py`, `test_core_shot_resolver.py`,
`test_core_prompt_compiler.py`, `test_core_director_agent.py`,
`test_core_spec_builder.py`, `test_core_api.py`, `test_core_independence.py`,
`test_spec_adapter.py`, `test_generation_spec_providers.py`,
`test_core_persona_memory.py`, `test_core_persona_api.py`,
`test_core_cinematic_library.py`, `test_core_cinematic_api.py`,
`test_core_shot_library.py`, `test_core_shot_api.py`,
`test_core_storyboard_engine.py`, `test_core_storyboard_api.py`,
`test_core_prompt_blocks.py`, `test_core_storyboard_compile_api.py`,
`test_pr005_director_ai.py` and `test_provider_adapters.py`. The independence tests
spawn subprocesses, so the suite takes a few seconds longer than a pure in-process run.
