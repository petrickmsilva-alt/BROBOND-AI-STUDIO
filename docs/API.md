# BROBOND AI STUDIO — API

Inventário gerado a partir da aplicação em execução, não escrito à mão.

```bash
PYTHONPATH=backend python scripts/gen_api_doc.py > docs/API.md
```

`backend/tests/test_docs_accuracy.py` compara este arquivo com a aplicação; se uma rota
mudar e o documento não for regenerado, a suíte falha.

---

## Resumo

- **99** rotas HTTP sob `/api/v1`
- **32** delas são `/api/v1/core/*` — a camada de decisão
- **3** WebSockets
- **16** tags

OpenAPI interativo em `/docs` (Swagger) e `/redoc` quando o serviço está no ar.

PR006 Storyboard Cinematic Engine não adiciona rotas de render: a UI edita um `StoryboardState` versionado sobre o `ProductionPlan` retornado por `/api/v1/core/director/production-plan`. PR007 adiciona `/api/v1/providers` para health/capabilities do registry universal, sem expor segredos. PR008 adiciona seis rotas `/api/v1/render/*` (lotes de render com identidade) e o WebSocket `/ws/render/{batch_id}` com progresso por push, sem polling. V3.1 adiciona doze rotas `/api/v1/graph/*` (Cinematic Knowledge Graph com identidade: CRUD de nós/arestas, busca semântica, vizinhança e contexto de personagem para o Director AI). V3.2 adiciona treze rotas `/api/v1/continuity/*` (Character Continuity Engine com identidade: cinco locks com fingerprint, resolver persona+campanha+episódio e histórico imutável de episódios).

## `assets` — 4

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/assets` | list_assets |
| `GET` | `/api/v1/assets/download/{object_key:path}` | Serve a stored file (PR002: identity and tenant required). |
| `POST` | `/api/v1/assets/upload` | Upload an asset to MinIO or the local media adapter. |
| `POST` | `/api/v1/assets/{asset_id}/conditioning` | create_conditioning_asset |

## `auth` — 3

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Sign in (PR002: rate-limited, and every attempt — success or failure — audited). |
| `GET` | `/api/v1/auth/me` | get_current_user |
| `POST` | `/api/v1/auth/register` | Create an account (PR002: rate-limited and audited). |

## `continuity` — 13

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/continuity/episodes` | List frozen episode snapshots, optionally filtered (V3.2). |
| `POST` | `/api/v1/continuity/episodes` | Freeze a new episode with the currently resolved continuity (V3.2: identity required). |
| `PUT` | `/api/v1/continuity/identity` | Freeze a character's visual identity and fingerprint it (V3.2: identity required). |
| `GET` | `/api/v1/continuity/identity/{persona_id}` | Read a character's frozen visual identity, or 404 when unlocked (V3.2). |
| `GET` | `/api/v1/continuity/location` | Read the resolved set: episode override or campaign default (V3.2). |
| `PUT` | `/api/v1/continuity/location` | Freeze the set for a campaign, optionally for one episode only (V3.2: identity required). |
| `GET` | `/api/v1/continuity/resolve` | Resolve one ContinuityContext: persona + campaign + episode (V3.2). |
| `GET` | `/api/v1/continuity/vehicle` | Read the resolved hero vehicle: episode override or campaign default (V3.2). |
| `PUT` | `/api/v1/continuity/vehicle` | Freeze the hero vehicle for a campaign, optionally for one episode (V3.2: identity required). |
| `PUT` | `/api/v1/continuity/voice` | Freeze a character's voice profile, emotion, speed and intensity (V3.2: identity required). |
| `GET` | `/api/v1/continuity/voice/{persona_id}` | Read a character's frozen voice, or 404 when unlocked (V3.2). |
| `GET` | `/api/v1/continuity/wardrobe` | Read the resolved costume: episode override or campaign default (V3.2). |
| `PUT` | `/api/v1/continuity/wardrobe` | Freeze a costume for a campaign, optionally for one episode only (V3.2: identity required). |

## `core` — 32

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/core/cinematic/audit` | Audit the library against the Bible and report what does not comply. |
| `GET` | `/api/v1/core/cinematic/consistency` | "Grain is subtle and consistent across an episode." |
| `GET` | `/api/v1/core/cinematic/explain` | Director-facing prose for a style: what it is and why it looks that way. |
| `GET` | `/api/v1/core/cinematic/framing` | Shot sizes and angles. Angle is meaning: low angle creates presence. |
| `GET` | `/api/v1/core/cinematic/lenses` | The lens language: what each focal length is for. |
| `GET` | `/api/v1/core/cinematic/lenses/for` | Which focal lengths serve a purpose. `purpose=isolation` -> 135mm. |
| `GET` | `/api/v1/core/cinematic/lighting` | Light roles and the tone each light quality supports. |
| `GET` | `/api/v1/core/cinematic/motivations` | The five legitimate reasons to move the camera. |
| `GET` | `/api/v1/core/cinematic/motivations/of` | Which motivations a camera move can claim, and whether it is still. |
| `POST` | `/api/v1/core/compile` | Compile a GenerationSpec without executing it (dry run). |
| `POST` | `/api/v1/core/direct` | Turn a plain-language intention into direction. |
| `POST` | `/api/v1/core/director/production-plan` | Create a Director AI production plan. Planning only; no image generation. |
| `GET` | `/api/v1/core/personas` | Current identities in the character library, with their version (PR002: identity required). |
| `GET` | `/api/v1/core/personas/{persona_id}` | A character's full history: every revision, who made it and why (PR002: identity required). |
| `POST` | `/api/v1/core/personas/{persona_id}/approve` | Promote a planned character to approved (PR002: identity required, audited). |
| `GET` | `/api/v1/core/personas/{persona_id}/continuity` | Whether a character stayed consistent across the given episodes (PR002: identity required). |
| `GET` | `/api/v1/core/personas/{persona_id}/episodes/{episode_id}/memory` | The identity an episode was actually made with, not the current one (PR002: identity required). |
| `POST` | `/api/v1/core/personas/{persona_id}/episodes/{episode_id}/snapshot` | Bind the current identity to an episode (PR002: identity required, audited). |
| `POST` | `/api/v1/core/personas/{persona_id}/retire` | Retire a character (PR002: identity required, audited). Episodes already made keep their memory snapshots. |
| `POST` | `/api/v1/core/personas/{persona_id}/revise` | Apply an attributed edit (PR002: identity required, audited). |
| `GET` | `/api/v1/core/providers` | Every registered adapter, with its kind, status and checkpoint. |
| `GET` | `/api/v1/core/providers/health` | Whether each local adapter could run on this machine, right now. |
| `POST` | `/api/v1/core/quality/assess` | Check a rendered artifact against the spec it was supposed to satisfy. |
| `GET` | `/api/v1/core/quality/rules` | What the gate checks, what it explicitly does not, and why. |
| `GET` | `/api/v1/core/shots` | Browse the 300-shot library by function, lens, frame or motivation. |
| `GET` | `/api/v1/core/shots/audit` | Library-wide compliance report against the CINEMATIC_BIBLE. |
| `GET` | `/api/v1/core/shots/families` | The narrative families and how many shots each holds. |
| `GET` | `/api/v1/core/shots/{shot_code}` | One shot, with the grammar read off it. 404 rather than a silent fallback. |
| `POST` | `/api/v1/core/storyboard` | Cast a brief into an ordered shot sequence and validate it. |
| `POST` | `/api/v1/core/storyboard/compile` | Cast a brief into shots, then compile one prompt per scene. |
| `POST` | `/api/v1/core/timeline` | Assemble a brief into an ordered cut and report whether it holds. |
| `GET` | `/api/v1/core/timeline/formats` | Which frame each narrative format ships in, and what the cut can be. |

## `exports` — 1

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/assets/{asset_id}/export` | export_video |

## `generations` — 3

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/generations/images` | Create an image job. Authenticated jobs are persisted to the user's asset library. |
| `POST` | `/api/v1/generations/videos` | Create an H.264 video job for the configured video provider. |
| `GET` | `/api/v1/jobs/{job_id}` | Read one of the caller's jobs (PR002: identity required). |

## `graph` — 12

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/graph/characters/{name}/context` | CharacterGraph: identity, relations and phrases for one character (V3.1). |
| `GET` | `/api/v1/graph/edges` | List the caller's graph edges, filterable by endpoint or relation (V3.1). |
| `POST` | `/api/v1/graph/edges` | Relate two nodes; the verb is normalised onto the engine vocabulary (V3.1). |
| `DELETE` | `/api/v1/graph/edges/{edge_id}` | Delete one graph edge; the endpoint nodes are untouched (V3.1). |
| `GET` | `/api/v1/graph/neighbors/{node_id}` | Walk the graph around one node: depth 1-3, in/out/both directions (V3.1). |
| `GET` | `/api/v1/graph/nodes` | List the caller's graph nodes, optionally filtered by entity type (V3.1). |
| `POST` | `/api/v1/graph/nodes` | Create a knowledge-graph node in the caller's workspace (V3.1: identity required). |
| `DELETE` | `/api/v1/graph/nodes/{node_id}` | Delete a graph node and its incident edges in both directions (V3.1). |
| `GET` | `/api/v1/graph/nodes/{node_id}` | Read one of the caller's graph nodes (V3.1; foreign ids 404). |
| `PATCH` | `/api/v1/graph/nodes/{node_id}` | Partially update a graph node; attributes/aliases replace wholesale (V3.1). |
| `GET` | `/api/v1/graph/query` | Semantic search over the caller's graph: names, aliases, attributes (V3.1). |
| `POST` | `/api/v1/graph/seed` | Load the demonstration graph into the caller's workspace, idempotently (V3.1). |

## `knowledge` — 1

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/knowledge` | Search the knowledge base (PR002: identity required). |

## `models` — 3

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/models/conditioning` | conditioning_models |
| `GET` | `/api/v1/models/image` | image_models |
| `GET` | `/api/v1/models/video` | video_models |

## `personas` — 10

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/personas` | List the caller's persistent persona profiles (PR003). |
| `POST` | `/api/v1/personas` | Register a persona and reserve a future LoRA training job. |
| `DELETE` | `/api/v1/personas/{persona_id}` | Delete a persona profile and its children (PR003). |
| `GET` | `/api/v1/personas/{persona_id}` | Read one of the caller's persona profiles (PR003; foreign ids 404). |
| `PATCH` | `/api/v1/personas/{persona_id}` | Partially update a persona profile (PR003). |
| `GET` | `/api/v1/personas/{persona_id}/images` | List a persona's image references (PR003). |
| `POST` | `/api/v1/personas/{persona_id}/images` | Attach a stored image asset to a persona (PR003). |
| `GET` | `/api/v1/personas/{persona_id}/loras` | list_persona_loras |
| `POST` | `/api/v1/personas/{persona_id}/train` | Queue LoRA training for one of the caller's personas (PR002: identity required). |
| `GET` | `/api/v1/personas/{persona_id}/training/{run_id}` | Read one of the caller's training runs (PR002: identity required). |

## `prompt-engine` — 1

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/prompts/enhance` | enhance_prompt |

## `providers` — 3

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/providers` | Universal provider health, latency, version and capabilities (PR007). |
| `GET` | `/api/v1/providers/telemetry` | Recent provider telemetry records, newest first (PR009). |
| `POST` | `/api/v1/providers/{provider_id}/test` | PR009 real test: run a deterministic test spec through the full path. |

## `queue` — 2

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Cancel one of the caller's jobs (PR002: identity required). |
| `GET` | `/api/v1/queue` | List the caller's generation queue (PR001: real data, no seed; PR002: identity required). |

## `render` — 6

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/render/batches` | List the caller's render batches, newest first (PR008: identity required). |
| `POST` | `/api/v1/render/batches` | Create a render batch from a Director storyboard (PR008: identity required). |
| `GET` | `/api/v1/render/batches/{batch_id}` | Read one of the caller's render batches with per-scene progress (PR008). |
| `POST` | `/api/v1/render/batches/{batch_id}/cancel` | Cancel a render batch (PR008: identity required). |
| `POST` | `/api/v1/render/batches/{batch_id}/retry` | Retry the failed/cancelled scenes of a finished batch (PR008). |
| `POST` | `/api/v1/render/batches/{batch_id}/start` | Start rendering a queued batch in the background (PR008: identity required). |

## `storyboards` — 1

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/storyboards/expand` | Expand a brief into connected, independently renderable scene prompts. |

## `system` — 4

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/health` | health |
| `GET` | `/api/v1/system/gpu` | system_gpu |
| `GET` | `/api/v1/system/media` | system_media |
| `GET` | `/api/v1/system/readiness` | system_readiness |

## WebSockets

| Rota | Descrição |
| --- | --- |
| `/api/v1/personas/{persona_id}/training/events/{run_id}` | training_events |
| `/api/v1/queue/events/{job_id}` | Stream a job's transitions until it reaches a terminal state. |
| `/ws/render/{batch_id}` | Push a batch's render events until the terminal one. No polling. |
