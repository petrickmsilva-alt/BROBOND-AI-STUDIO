# BROBOND AI STUDIO

A local-first generative visual workspace for images, cinematic video, motion control, personas and storyboards.

## Current slice

The first vertical slice is a polished Next.js dashboard with independent module views:

- Overview dashboard with creative tools, recent projects and GPU status
- Image generation controls (prompt, negative prompt, model, ratio, resolution, seed, guidance, steps and LoRA/reference actions)
- Video generation (text/image-to-video tabs, duration, format, camera motion, native audio)
- Motion control preset browser and keyframe controls
- Persona Lab with identity profile and LoRA training status
- Storyboard with brief expansion and four scene cards
- Asset library with filters and visual previews

The generation result is intentionally a local UI simulation. Model inference should be connected through the backend contract described below rather than hidden behind fake network calls.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Architecture target

```text
BROBOND-AI-STUDIO/
├── app/                  # Next.js App Router UI
│   ├── page.tsx          # workspace shell and module slices
│   └── globals.css       # design system
├── backend/              # planned FastAPI service boundary
│   ├── app/api/          # REST + WebSocket endpoints
│   ├── app/core/         # settings, auth, queue
│   ├── app/models/       # SQLAlchemy models
│   └── app/services/     # inference providers and storage adapters
├── docker-compose.yml    # local Postgres, Redis and MinIO (next integration)
└── requirements.txt      # Python service dependencies (next integration)
```

## Inference boundary

The frontend is ready to consume these future endpoints:

- `POST /api/v1/generations/images`
- `POST /api/v1/generations/videos`
- `POST /api/v1/personas`
- `POST /api/v1/storyboards/expand`
- `GET /api/v1/assets`
- `WS /api/v1/queue/events`

Each generation should become a persisted job, be processed by Celery workers, and publish progress through Redis/WebSocket. Files belong in MinIO; PostgreSQL stores metadata; FFmpeg handles transcode/export.

## Design principles

- Local-first, SaaS-ready boundaries
- Provider adapters for Flux / Wan / Hunyuan rather than model logic in API routes
- Explicit job states: `queued`, `running`, `complete`, `failed`, `cancelled`
- JWT authentication and workspace-scoped resources before exposing network access
- Never commit model weights, generated media, secrets or `.env` files

## Next implementation milestones

1. Add FastAPI service and typed OpenAPI client.
2. Add Postgres migrations for workspaces, projects, assets, generations and personas.
3. Add Redis/Celery queue with GPU worker capability detection.
4. Add MinIO signed upload/download URLs and FFmpeg export pipeline.
5. Replace local UI simulation with WebSocket job updates and real provider adapters.
6. Add unit/API tests and local Docker profiles.

## Validation

The repository includes backend and frontend CI in `.github/workflows/ci.yml`. Run the full local validation with:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm run build
```

The end-to-end backend test covers registration, authenticated upload, generation job creation, storyboard expansion and asset listing.
