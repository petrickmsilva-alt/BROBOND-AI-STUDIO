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
   - `brobond-studio-web` — Web Service Node (`npm ci` + `npm start`), URL `https://brobond-studio-web.onrender.com`
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

1. Render → *New → Web Service* → selecione o repositório → runtime **Node**, build `npm ci`, start `npm start`, health check `/`, env var `NEXT_PUBLIC_API_URL=https://brobond-ai-api.onrender.com`.
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
