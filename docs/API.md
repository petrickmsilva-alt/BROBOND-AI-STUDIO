# BROBOND AI STUDIO — API

Inventário gerado a partir da aplicação em execução, não escrito à mão.

```bash
PYTHONPATH=backend python scripts/gen_api_doc.py > docs/API.md
```

`backend/tests/test_docs_accuracy.py` compara este arquivo com a aplicação; se uma rota
mudar e o documento não for regenerado, a suíte falha.

---

## Resumo

- **58** rotas HTTP sob `/api/v1`
- **31** delas são `/api/v1/core/*` — a camada de decisão
- **2** WebSockets
- **12** tags

OpenAPI interativo em `/docs` (Swagger) e `/redoc` quando o serviço está no ar.

## `assets` — 4

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/assets` | list_assets |
| `GET` | `/api/v1/assets/download/{object_key:path}` | download_local_asset |
| `POST` | `/api/v1/assets/upload` | Upload an asset to MinIO or the local media adapter. |
| `POST` | `/api/v1/assets/{asset_id}/conditioning` | create_conditioning_asset |

## `auth` — 3

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/auth/login` | login_user |
| `GET` | `/api/v1/auth/me` | get_current_user |
| `POST` | `/api/v1/auth/register` | register_user |

## `core` — 31

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
| `GET` | `/api/v1/core/personas` | Current identities in the character library, with their version. |
| `GET` | `/api/v1/core/personas/{persona_id}` | A character's full history: every revision, who made it and why. |
| `POST` | `/api/v1/core/personas/{persona_id}/approve` | Promote a planned character to approved. |
| `GET` | `/api/v1/core/personas/{persona_id}/continuity` | Whether a character stayed consistent across the given episodes. |
| `GET` | `/api/v1/core/personas/{persona_id}/episodes/{episode_id}/memory` | The identity an episode was actually made with, not the current one. |
| `POST` | `/api/v1/core/personas/{persona_id}/episodes/{episode_id}/snapshot` | Bind the current identity to an episode. |
| `POST` | `/api/v1/core/personas/{persona_id}/retire` | Retire a character. Episodes already made keep their memory snapshots. |
| `POST` | `/api/v1/core/personas/{persona_id}/revise` | Apply an attributed edit. |
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
| `GET` | `/api/v1/jobs/{job_id}` | get_job |

## `knowledge` — 1

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/knowledge` | knowledge |

## `models` — 3

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/models/conditioning` | conditioning_models |
| `GET` | `/api/v1/models/image` | image_models |
| `GET` | `/api/v1/models/video` | video_models |

## `personas` — 4

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/personas` | Register a persona and reserve a future LoRA training job. |
| `GET` | `/api/v1/personas/{persona_id}/loras` | list_persona_loras |
| `POST` | `/api/v1/personas/{persona_id}/train` | train_persona |
| `GET` | `/api/v1/personas/{persona_id}/training/{run_id}` | training_status |

## `prompt-engine` — 1

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/prompts/enhance` | enhance_prompt |

## `queue` — 2

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | cancel_job |
| `GET` | `/api/v1/queue` | list_queue |

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
