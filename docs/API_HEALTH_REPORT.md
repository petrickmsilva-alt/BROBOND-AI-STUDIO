# API HEALTH REPORT — PR009.1 (Health Check Reconciliation)

Reconciliação entre as rotas de health do FastAPI e o `healthCheckPath` do
Render Blueprint. **Nenhuma funcionalidade nova**; medição feita contra a
aplicação em execução e o blueprint em `render.yaml`.

**Veredito: sem divergência.** O `render.yaml` já aponta para uma rota real,
pública (sem token) e 200-OK do FastAPI — nada foi alterado nele, e o prefixo
global `/api/v1` permanece intacto. O resultado agora é fixado por testes
(`backend/tests/test_health_reconciliation.py`) para não voltar a divergir.

---

## Resumo (medido)

| Verificação | Resultado |
|---|---|
| Rota correta de health (API) | `GET /api/v1/health` |
| Alias raiz | `GET /health` |
| Status code | **200** — corpo `{"status":"ok","service":"brobond-api","mode":"local"}` |
| Autenticação | **Pública** — sem `Depends(current_user)`; o probe do Render passa sem token |
| `healthCheckPath` (API `brobond-ai-api`) | `/api/v1/health` → **existe, 200** |
| `healthCheckPath` (Web `brobond-studio-web`) | `/` → Next.js, **200** |
| Swagger (UI interativa) | `GET /docs` → **200** |
| ReDoc | `GET /redoc` → **200** |
| OpenAPI JSON | `GET /openapi.json` → **200** |
| Proxy do front (`/api/v1/*` via Next) | `GET /api/v1/health` → **200** no mesmo caminho que o browser usa |
| Divergência FastAPI ↔ Render | **Nenhuma** — `render.yaml` intocado, prefixo intocado |

## Rotas de health no inventário

| `GET` | `/api/v1/health` | system |
| `GET` | `/health` | system |

As duas rotas são decoradores empilhados no mesmo handler
(`backend/app/main.py`), então o corpo é idêntico e qualquer mudança em um
é uma mudança no outro.

## Render Blueprint (`render.yaml`)

| Serviço | `healthCheckPath` | O que serve | Status medido |
|---|---|---|---|
| `brobond-ai-api` (Docker/FastAPI) | `/api/v1/health` | FastAPI (`GET /api/v1/health`) | 200 |
| `brobond-studio-web` (Node/Next.js) | `/` | Next.js (shell do studio) | 200 |

O `Dockerfile.api` escuta em `${PORT:-8000}` — o Render injeta `PORT` e o
probe chega na mesma porta que a aplicação atende.

## Status que o frontend consome

A casca do studio lê `GET /api/v1/system/gpu` e `GET /api/v1/system/readiness`
(ambas públicas, **200** pelo mesmo proxy que o browser usa). O texto
"API offline" só aparece quando um `fetch` falha de fato (`lib/api.ts`
retorna `'offline'` apenas no `catch`); com o health path reconciliado e o
serviço de pé, o frontend não exibe offline.

## Como reproduzir

```bash
curl -i http://localhost:8000/api/v1/health     # 200
curl -i http://localhost:8000/health            # 200 (alias)
curl -i http://localhost:8000/docs              # 200 (Swagger)
grep -n "healthCheckPath" render.yaml           # / e /api/v1/health
PYTHONPATH=backend pytest backend/tests/test_health_reconciliation.py -q
```

---

## ETAPA 1 — Inventário completo das rotas FastAPI (método, path, tags)

**107 rotas HTTP** (106 sob `/api/v1` + 1 alias `/health`) e **3 WebSockets**.
O inventário detalhado com descrições vive em `docs/API.md` (gerado da
aplicação; guardado por `test_docs_accuracy.py`).

| Método | Path | Tags |
| --- | --- | --- |
| `GET` | `/api/v1/health` | system |
| `GET` | `/health` | system |
| `GET` | `/api/v1/system/gpu` | system |
| `GET` | `/api/v1/system/readiness` | system |
| `GET` | `/api/v1/system/media` | system |
| `POST` | `/api/v1/prompts/enhance` | prompt-engine |
| `GET` | `/api/v1/models/conditioning` | models |
| `GET` | `/api/v1/knowledge` | knowledge |
| `GET` | `/api/v1/models/image` | models |
| `GET` | `/api/v1/models/video` | models |
| `POST` | `/api/v1/auth/register` | auth |
| `POST` | `/api/v1/auth/login` | auth |
| `GET` | `/api/v1/auth/me` | auth |
| `POST` | `/api/v1/generations/images` | generations |
| `POST` | `/api/v1/generations/videos` | generations |
| `GET` | `/api/v1/jobs/{job_id}` | generations |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | queue |
| `POST` | `/api/v1/assets/upload` | assets |
| `GET` | `/api/v1/assets` | assets |
| `GET` | `/api/v1/assets/download/{object_key:path}` | assets |
| `POST` | `/api/v1/assets/{asset_id}/conditioning` | assets |
| `POST` | `/api/v1/assets/{asset_id}/export` | exports |
| `POST` | `/api/v1/personas` | personas |
| `GET` | `/api/v1/personas` | personas |
| `GET` | `/api/v1/personas/{persona_id}` | personas |
| `PATCH` | `/api/v1/personas/{persona_id}` | personas |
| `DELETE` | `/api/v1/personas/{persona_id}` | personas |
| `GET` | `/api/v1/personas/{persona_id}/images` | personas |
| `POST` | `/api/v1/personas/{persona_id}/images` | personas |
| `POST` | `/api/v1/personas/{persona_id}/train` | personas |
| `GET` | `/api/v1/personas/{persona_id}/training/{run_id}` | personas |
| `GET` | `/api/v1/personas/{persona_id}/loras` | personas |
| `POST` | `/api/v1/storyboards/expand` | storyboards |
| `POST` | `/api/v1/core/direct` | core |
| `POST` | `/api/v1/core/director/production-plan` | core |
| `POST` | `/api/v1/core/compile` | core |
| `GET` | `/api/v1/queue` | queue |
| `GET` | `/api/v1/core/personas` | core |
| `GET` | `/api/v1/core/personas/{persona_id}` | core |
| `POST` | `/api/v1/core/personas/{persona_id}/revise` | core |
| `POST` | `/api/v1/core/personas/{persona_id}/approve` | core |
| `POST` | `/api/v1/core/personas/{persona_id}/retire` | core |
| `POST` | `/api/v1/core/personas/{persona_id}/episodes/{episode_id}/snapshot` | core |
| `GET` | `/api/v1/core/personas/{persona_id}/episodes/{episode_id}/memory` | core |
| `GET` | `/api/v1/core/personas/{persona_id}/continuity` | core |
| `GET` | `/api/v1/core/cinematic/lenses` | core |
| `GET` | `/api/v1/core/cinematic/lenses/for` | core |
| `GET` | `/api/v1/core/cinematic/framing` | core |
| `GET` | `/api/v1/core/cinematic/lighting` | core |
| `GET` | `/api/v1/core/cinematic/motivations` | core |
| `GET` | `/api/v1/core/cinematic/motivations/of` | core |
| `GET` | `/api/v1/core/cinematic/audit` | core |
| `GET` | `/api/v1/core/cinematic/explain` | core |
| `GET` | `/api/v1/core/cinematic/consistency` | core |
| `GET` | `/api/v1/core/shots` | core |
| `GET` | `/api/v1/core/shots/families` | core |
| `GET` | `/api/v1/core/shots/audit` | core |
| `GET` | `/api/v1/core/shots/{shot_code}` | core |
| `POST` | `/api/v1/core/storyboard` | core |
| `POST` | `/api/v1/core/storyboard/compile` | core |
| `POST` | `/api/v1/core/timeline` | core |
| `GET` | `/api/v1/core/timeline/formats` | core |
| `POST` | `/api/v1/core/quality/assess` | core |
| `GET` | `/api/v1/core/quality/rules` | core |
| `GET` | `/api/v1/providers` | providers |
| `POST` | `/api/v1/providers/{provider_id}/test` | providers |
| `GET` | `/api/v1/providers/telemetry` | providers |
| `GET` | `/api/v1/core/providers` | core |
| `GET` | `/api/v1/core/providers/health` | core |
| `POST` | `/api/v1/render/batches` | render |
| `GET` | `/api/v1/render/batches` | render |
| `GET` | `/api/v1/render/batches/{batch_id}` | render |
| `POST` | `/api/v1/render/batches/{batch_id}/start` | render |
| `POST` | `/api/v1/render/batches/{batch_id}/cancel` | render |
| `POST` | `/api/v1/render/batches/{batch_id}/retry` | render |
| `POST` | `/api/v1/graph/nodes` | graph |
| `GET` | `/api/v1/graph/nodes` | graph |
| `GET` | `/api/v1/graph/nodes/{node_id}` | graph |
| `PATCH` | `/api/v1/graph/nodes/{node_id}` | graph |
| `DELETE` | `/api/v1/graph/nodes/{node_id}` | graph |
| `POST` | `/api/v1/graph/edges` | graph |
| `GET` | `/api/v1/graph/edges` | graph |
| `DELETE` | `/api/v1/graph/edges/{edge_id}` | graph |
| `GET` | `/api/v1/graph/query` | graph |
| `GET` | `/api/v1/graph/neighbors/{node_id}` | graph |
| `GET` | `/api/v1/graph/characters/{name}/context` | graph |
| `POST` | `/api/v1/graph/seed` | graph |
| `PUT` | `/api/v1/continuity/identity` | continuity |
| `GET` | `/api/v1/continuity/identity/{persona_id}` | continuity |
| `PUT` | `/api/v1/continuity/wardrobe` | continuity |
| `GET` | `/api/v1/continuity/wardrobe` | continuity |
| `PUT` | `/api/v1/continuity/location` | continuity |
| `GET` | `/api/v1/continuity/location` | continuity |
| `PUT` | `/api/v1/continuity/vehicle` | continuity |
| `GET` | `/api/v1/continuity/vehicle` | continuity |
| `PUT` | `/api/v1/continuity/voice` | continuity |
| `GET` | `/api/v1/continuity/voice/{persona_id}` | continuity |
| `GET` | `/api/v1/continuity/resolve` | continuity |
| `POST` | `/api/v1/continuity/episodes` | continuity |
| `GET` | `/api/v1/continuity/episodes` | continuity |
| `POST` | `/api/v1/campaigns/interpret` | campaign |
| `POST` | `/api/v1/campaigns` | campaign |
| `GET` | `/api/v1/campaigns` | campaign |
| `GET` | `/api/v1/campaigns/{campaign_id}` | campaign |
| `POST` | `/api/v1/campaigns/{campaign_id}/duplicate` | campaign |
| `POST` | `/api/v1/campaigns/{campaign_id}/assets/{asset_id}/deliver` | campaign |
| `POST` | `/api/v1/campaigns/{campaign_id}/export` | campaign |
