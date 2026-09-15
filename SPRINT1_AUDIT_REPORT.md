# SPRINT 1 — RELATÓRIO TÉCNICO DE AUDITORIA (PR #001)

**Projeto:** BROBOND AI STUDIO V2 · `petrickmsilva-alt/BROBOND-AI-STUDIO`
**Commit auditado:** `65721fb` · branch `arena/01a0a607-brobond-ai-studio` · data 2026-09-15
**Autoridade:** `docs/DEVELOPER_BIBLE.md` v2.0 · **Escopo:** auditoria, validação e relatório — **zero código escrito** (§17 da Bíblia)
**Método:** todo item foi medido por comando executado neste checkout (Anexo A). Nada presumido.

---

## 1. Resumo executivo

**Nota geral: 8,0 / 10.**

O BROBOND AI STUDIO é um projeto com **excelente fundação de engenharia** e **gaps críticos de
produção e segurança**. A espinha do produto — o fluxo `User → Director AI → Memory Resolver →
Prompt Compiler → GenerationSpec → Provider → Queue → Asset → Timeline` — está **implementada,
testada e honesta**: 1.077 testes passando, cobertura 95% (gate CI 90%), 58 rotas + 2 WebSockets,
12 componentes de Core isolados por framework e guardados por teste estrutural, documentação que
declara as próprias limitações (`docs/LIMITATIONS.md`) e uma suíte que impede a documentação de
ficar obsoleta (35 guardas anti-drift).

O que impede nota mais alta:

1. **Segurança (Bíblia §16):** 48 de 58 rotas sem verificação de identidade, sem rate limit, sem
   audit trail, segredo JWT padrão de 23 bytes, token em `localStorage`.
2. **Produção (Bíblia §15):** o blueprint do Render roda com storage desligado — mídia vive no
   filesystem **efêmero** do container.
3. **Jobs (Bíblia §14/§6):** estado em memória; um worker Celery em processo separado nunca
   enxerga o job; em produção (fila desligada) o job **nunca executa**.
4. **Conformidade de contrato:** estados de job do código ≠ estados da Bíblia (e há um conflito
   interno entre a Regra de Ouro e o §14); 3 dos 8 objetos centrais do §6 (Job, Persona,
   Storyboard) sem persistência.

Nenhuma feature foi implementada neste Sprint (§17). O código auditado é exatamente o commit
`65721fb`; `git diff` vazio.

---

## 2. Arquitetura encontrada

```text
┌────────────────────────────────────────────────────────────────────────────────────┐
│ FRONTEND  app/ (Next.js 14 App Router, TypeScript, CSS autoral)                    │
│   page.tsx (460 L, 7 módulos: Director, Overview, Image, Video, Persona,           │
│   Storyboard, Assets) · lib/api.ts (cliente tipado, URL relativa) ·                │
│   next.config.mjs (proxy /api/v1 → FastAPI) · globals.css (design system)          │
│   components/studio-shell.tsx (644 L) ◄── LEGACY/ÓRFÃO (não montado)               │
└──────────────────────────────┬─────────────────────────────────────────────────────┘
                               │ HTTP + WebSocket (proxy)
┌──────────────────────────────▼─────────────────────────────────────────────────────┐
│ BACKEND  backend/app/ (FastAPI, Python 3.12 no CI/prod, SQLAlchemy 2)              │
│   main.py (1.363 L: 58 rotas + 2 WS + bootstrap + CORS + composição do Core)       │
│   auth.py (JWT pyjwt + scrypt) · schemas.py (contratos, 19 campos do spec)         │
│   models.py (7 tabelas) · db.py · store.py (MemoryStore ◄── jobs/personas em RAM)  │
│   queue.py (Celery, transition() = única mutação) · events.py (hub in-process)     │
│   storage.py (local | S3/MinIO, boto3) · media.py (FFmpeg) · system.py (nvidia-smi)│
│   knowledge.py (12 seeds) · lora.py · training.py · conditioning.py ·              │
│   preprocessing.py · prompt_engine.py (fachada) · spec_adapter.py (Job→Spec)       │
│                                                                                   │
│   ┌─ CORE (camada de decisão; importam só contracts) ──────────────────────────┐  │
│   │ contracts.py (GenerationSpec 19 campos, 13 blocos)                          │  │
│   │ director_agent · memory_resolver · style_resolver (7 presets)               │  │
│   │ shot_resolver (10 publicados) · shot_library (300) · cinematic_library      │  │
│   │ persona_memory (ledger versionado em RAM) · storyboard_engine               │  │
│   │ prompt_compiler (único produtor de texto) · timeline (plano, não render)    │  │
│   │ quality (gate estrutural) · generation_spec_builder (raiz de composição)    │  │
│   │ config.py (settings) · security.py ◄── QUEBRADO/LEGACY (não importa)        │  │
│   └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                   │
│   PROVIDERS  providers/ registry (4 entradas) + common + conditioning             │
│     flux-dev (local) · flux-1.1-pro-ultra (remote) · wan-2.1-t2v (local) ·        │
│     hunyuan-video (local) · generate(spec, output_dir) · recusa, nunca troca      │
│                                                                                   │
│   ┌─ LÉNYA/MORTOS (P0-1 histórico; mantidos pela Regra de Ouro) ──────────────┐  │
│   │ api/routes.py · api/dependencies.py · services/generation.py (não importam) │  │
│   │ backend/requirements.txt · backend/Dockerfile (manifestos não usados)       │  │
│   └─────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬─────────────────────────────────────────────────────┘
                               │
┌──────────────┬───────────────┴──────────────┬───────────────────────────────────────┐
│ DATABASE     │ ASSETS                       │ INFRA                                 │
│ PostgreSQL   │ MinIO/S3 (boto3) ou local    │ render.yaml (web + api + PG 16)       │
│ (SQLite dev) │ media/ (filesystem local)    │ Dockerfile.api (python:3.12-slim)     │
│ 7 tabelas    │ URLs assinadas 1 h           │ docker-compose (PG/Redis/MinIO)       │
│ SEM Alembic  │                              │ .github/workflows/ci.yml (PY+JS)      │
└──────────────┴──────────────────────────────┴───────────────────────────────────────┘
```

**Pastas ativas × Legacy (S1-B):**

| Pasta/área | Estado | Justificativa medida |
|---|---|---|
| `app/` (página, layout, css) | **Ativa** | montada pelo Next; build verde |
| `lib/` | **Ativa** | importada por `page.tsx` |
| `backend/app/` (raiz do pacote) | **Ativa** | importada por `main.py`; 95% cobertura |
| `backend/app/core/` | **Ativa** — exceto `security.py` | 12 componentes vivos; `security.py` **Legacy/quebrado** (não importa: `jose` ausente, `get_settings` inexistente) |
| `backend/app/providers/` | **Ativa** | registry + 3 adapters; 100% cobertura |
| `backend/app/api/` | **Legacy (morta e quebrada)** | nada a importa; `import` falha |
| `backend/app/services/` | **Legacy (morta e quebrada)** | nada a importa; `import` falha |
| `backend/tests/` | **Ativa** | 48 suítes, 1.077 testes |
| `backend/requirements.txt`, `backend/Dockerfile` | **Legacy (manifestos mortos)** | CI/compose/render usam os da raiz |
| `components/studio-shell.tsx` | **Legacy (órfão)** | 644 L, zero imports |
| `knowledge_base/` | **Ativa (seeds/versionada)** | fontes de verdade dos seeds |
| `docs/`, `scripts/`, `.github/`, raiz infra | **Ativos** | CI verde, gerador de docs, blueprint |

---

## 3. Componentes funcionando

**Backend (medido: import + teste + introspecção):**

| Componente | Arquivo | Evidência |
|---|---|---|
| API composition root (58 rotas + 2 WS) | `main.py` | 1.077 testes; introspecção das rotas |
| Autenticação JWT + scrypt | `auth.py` | 100% cobertura; `test_auth*.py` |
| Contratos da API | `schemas.py` | 100% cobertura |
| Modelos SQLAlchemy (7 tabelas) | `models.py` | `test_e2e.py` |
| Fila Celery + ciclo de vida de job | `queue.py` | 100%; `transition()` única mutação (guarda AST) |
| Hub de eventos (in-process, replay) | `events.py` | 100%; WS de queue medido |
| Storage local + S3/MinIO | `storage.py` | 100%; `FakeS3` em teste; traversal em 2 camadas |
| FFmpeg (export/probe/concat) | `media.py` | comandos puros testados; binário ausente neste host (declara) |
| Detecção GPU + readiness | `system.py`, `readiness.py` | 100% |
| Knowledge base (12 seeds) | `knowledge.py` | 96% |
| LoRA (plano + hook de treino) | `lora.py`, `training.py` | 100%; recusa honesta sem GPU |
| Conditioning + preprocessing | `conditioning.py`, `preprocessing.py` | 100% |
| Fachada de prompt | `prompt_engine.py` | delega ao Core |
| Adapter Job→GenerationSpec | `spec_adapter.py` | 100%; único módulo que conhece Job e Core |
| **Core (12)** | `core/*.py` | 100–97% cada; independência por subprocesso; `test_core_api.py` |
| Providers (FLUX/Wan/Hunyuan) | `providers/*.py` | 100%; recusa sem CUDA; `test_provider_runtime.py` |
| Frontend — Director, Image, Video, Storyboard, Assets, Auth, GPU/Readiness | `page.tsx`, `lib/api.ts` | rotas reais consumidas; build verde; `test_frontend_honesty.py` (31 guardas) |

## 4. Componentes Mock

**Backend**

| Item | Onde | Natureza |
|---|---|---|
| Jobs e personas | `store.py` (`MemoryStore`) | **Incompleto, não mock**: estado real que não sobrevive a restart/worker separado |
| Treino LoRA | `lora.py:train()`, `training.py` | **Hook declarado** (recusa com erro sem GPU) — honesto, sem simulação de saída |
| Providers | `providers/image.py`, `video.py` | Código real; **nenhum render real ocorreu** (sem torch/diffusers/ffmpeg neste host) — health `available: false` |
| `GET /api/v1/models/*` | `main.py` | **Lista estática** que diverge do registry (hunyuan "planned" vs "local") |

**Frontend (componentes simulados — S1-D)**

| Item | Onde | Evidência |
|---|---|---|
| Persona hardcoded | `PersonaStudio` (`page.tsx`) | `createPersona({ name: 'Petrick Martins', age: 50, ... })` — nome/atributos fixos; cartão sempre "Petrick Martins" |
| Sessão local falsa | `AuthModal` | com API offline, "Sign in" cria `{ id: 'local', email: '…@brobond.ai' }` e a UI passa a exibir usuário logado sem autenticação |
| Aba "Image to video" | `VideoStudio` | botão decorativo — o payload é sempre `mode: 'text-to-video'` |
| Controle de Seed | `ImageStudio` | input `readOnly` "Random" + botão inerte; seed nunca sai do cliente |
| Filtros da Asset Library | `Assets` | abas Images/Videos/LoRA/Audio sem `onClick`; grid sempre lista tudo |
| Search / Help / Bell / Projects / Settings | topbar + sidebar | sem estado/ação (Projects e Settings só navegam para Assets) |
| Timeline do vídeo | `VideoStudio` | barra decorativa (`00:00 ─ 00:0X`); a track reflete o progress do job, não clipes reais |
| `components/studio-shell.tsx` | inteiro | **UI completa alternativa em modo LÉNYA** — não montada, com dados fake (`projectCards`, `assetItems`) |

**O que NÃO é mock (confirmado):** canvas de imagem/vídeo mostra `output_url` real ou
declara falha; GPU/readiness lidos da API; storyboard mostra shots reais + findings; contagem
de assets real; erros distinguem `offline` de rejeição (contrato `ApiResult`).

---

## 5. Bugs encontrados

### P0 — bloqueiam a promessa do produto ou são falhas ativas de segurança

| ID | Bug | Evidência |
|---|---|---|
| P0-1 | **Jobs não persistem e não executam em produção.** `MemoryStore.jobs` é um dict do processo da API. (a) Worker Celery em outro processo → `store.get_job` vazio → `cancelled` sem rodar. (b) Em produção (`BROBOND_QUEUE_ENABLED=false`) `enqueue()` devolve `False` e o job **fica `queued` para sempre**. | `store.py`, `queue.py:enqueue`, `render.yaml` |
| P0-2 | **Autorização ausente em 48 de 58 rotas + 1 WS.** `GET /queue` devolve jobs de todos os workspaces; `POST /jobs/{id}/cancel` muta sem token; `GET /knowledge` expõe PII real (`CHAR_PETRICK` — nome, idade, altura); `GET /assets/download/{key}` abre download com URL permanente e não assinada; `POST /personas/{id}/train` (opcional) dispara treino sem identidade. | introspecção: 6 exigem, 4 opcionais, 48 abertas; `knowledge.py:21` |
| P0-3 | **Cluster morto com backdoor embutida.** `app.api.routes` contém `POST /auth/login` que **aceita qualquer credencial** e `GET /system` com GPU inventada (`vram_total_gb=24.0`). Nada o importa hoje — mas está no pacote enviado pelo Dockerfile (`COPY backend ./backend`) e a um `include_router` de virar backdoor. 4 módulos, 4/4 não importam. | `api/routes.py:24-34`; `import` falha nos 4 |

### P1 — graves, sem vazamento ativo contínuo

| ID | Bug | Evidência |
|---|---|---|
| P1-1 | **Produção viola a Bíblia §15:** `render.yaml` fixa `BROBOND_STORAGE_ENABLED=false`, sem MinIO no blueprint → mídia no filesystem efêmero do Render (some a cada deploy). | `render.yaml` envVars |
| P1-2 | **Segredos e rate limit (Bíblia §16):** `jwt_secret` default `change-me-in-production` (23 bytes < 32 do RFC 7518; warning suprimido em `pytest.ini`); `docker-compose.yml` usa `change-me-in-compose`; nenhuma validação em startup; **sem rate limit** em `/auth/login` (scrypt n=2^14 ≈ 16 MiB/tentativa → DoS de memória). | `core/config.py:22`, `main.py` |
| P1-3 | **Schema sem versionamento:** `alembic` nos requisitos e nunca usado; `create_all` + `ALTER TABLE` manual **na importação do módulo**, com retry 12×5 s — até 60 s antes de o servidor responder; em Postgres novo do Render o container reinicia em loop até o banco subir. | `main.py:38-62`; `find . -name alembic*` vazio |
| P1-4 | **Estados de Job ≠ Bíblia §14:** código tem `queued, running, complete, failed, cancelled`; a Bíblia permite 8 (`+loading_model, rendering, upscaling`, e `completed` — não `complete`). Renomear quebra API (Regra de Ouro §2) — **conflito interno da Bíblia**, decisão de produto. | `schemas.py:10-15` × §14 |
| P1-5 | **Personas não persistem** (Bíblia §7 "identidade permanente"): `POST /personas` → dict em RAM (some no deploy); o `PersonaMemoryEngine`/`PersonaLedger` do Core também vivem em memória (seeds injetáveis). `TrainingRun.persona_id` é string solta sem FK. | `main.py:311`, `core/persona_memory.py` |
| P1-6 | **Drift de catálogo de modelos:** `GET /api/v1/models/video` anuncia `hunyuan-video` como `planned-provider`; o registry (fonte única, `/core/providers`) o lista como **local com adapter**. A UI exibe o status errado. | `main.py:video_models` × `registry.py:125-130` |
| P1-7 | **Eventos não cruzam processos:** `EventHub` é in-process; num deploy com worker separado, o cliente WebSocket não recebe as transições do worker (precisa de Redis pub/sub). Declarado no código, mas quebra a UX de progresso em escala. | `events.py` docstring |
| P1-8 | **`datetime.utcnow` em 8 lugares** (naive; deprecado no 3.12 do CI) misturado com `datetime.now(timezone.utc)` no JWT — comparação de tempo pode corromper silenciosamente. | `grep -rn utcnow backend/app` → 8 |

### P2 — qualidade/robustez

| ID | Bug |
|---|---|
| P2-1 | Upload sem limite de tamanho (modo local lê o arquivo inteiro em RAM); validação confia no `content_type` do cliente; `PIL.Image.open` sem `MAX_IMAGE_PIXELS` (decompression bomb); sem paginação em `GET /assets` e `/queue`; `store.jobs` nunca é esvaziado (memória cresce sem limite) |
| P2-2 | Token JWT em `localStorage` (XSS rouba sessão); CORS `allow_methods/headers=["*"]` com `allow_credentials=True` |
| P2-3 | Mocks de UI (seção 4): persona hardcoded, sessão local falsa, 6 controles decorativos |
| P2-4 | Sem logging estruturado, request-id ou audit trail (Bíblia §16) — único log é `print()` no bootstrap |
| P2-5 | Tailwind configurado mas inerte (0 diretivas `@tailwind`); 3 fontes de cor (STYLE_GUIDE × tailwind.config × globals.css); `npm run lint` entra em modo interativo (sem `.eslintrc`); `@types/*` em `dependencies` |
| P2-6 | Tabela `projects` existe sem nenhuma rota — o objeto `Project` (Bíblia §6) não tem dono |
| P2-7 | Quality Gate é estrutural (arquivo/dimensões/duração/fps); os 8 critérios estéticos da Bíblia §13 (Face, Hands, Overall Score, regeneração < 85) não existem — gap de feature, não de bug |
| P2-8 | `GET /knowledge` faz `ILIKE '%…%'` sem índice (seq scan); WS de treino faz polling de banco a cada 2 s por cliente; export FFmpeg roda **síncrono na thread HTTP** (até 15 min — viola a regra "jobs longos nunca rodam na thread HTTP"); conditioning roda Pillow na rota com task Celery pronta (`preprocess_reference`) nunca chamada |

---

## 6. Dívida técnica

1. **`main.py` god module (1.363 L).** 58 rotas, 2 WS, bootstrap, CORS, headers e a composição
   inteira do Core num único módulo. É o ponto de maior risco de coesão e o gargalo de qualquer
   refatoração futura. Caminho: `APIRouter` por domínio (auth, generations, assets, personas,
   knowledge, core), sem mudar contrato.
2. **`MemoryStore` como fonte de verdade.** Jobs e personas em `dict` tornam "funciona em dev"
   falso em produção (P0-1, P1-5, P2-1). Enquanto existir, qualquer componente que leia estado
   (ex.: memória de episódios) parece funcionar e falha em escala.
3. **Ausência de migrations.** `create_all` + `ALTER TABLE` manual impede evoluir schema de
   produção com segurança; a dependência `alembic` já está paga e não é usada.
4. **Cluster morto + 2 manifestos + 1 UI fantasma (370 L + 264 L + 644 L).** A Regra de Ouro os
   torna permanentes (marcador Legacy, nunca remoção). Custos reais: 100 statements no
   denominador de cobertura, risco de backdoor acidental (P0-3), IDE sugerindo imports que
   quebram, `studio-shell.tsx` duplicando a UI viva.
5. **Consultas duplicadas de workspace (×8) sem repositório** — cada rota refaz
   `select(Workspace).where(owner_id == user.id)` e pode esquecer o filtro de tenant (é
   exatamente o esquecimento que causou o vazamento histórico de `/queue`).
6. **Bootstrap na importação** acopla disponibilidade do banco a todo import do módulo (testes,
   health checks, workers) — 60 s de bloqueio potencial.
7. **Três fontes de verdade de UI** (`page.tsx` viva, `studio-shell.tsx` morta, e a lista
   estática de modelos em `main.py` vs registry) — a mesma informação em lugares concorrentes é
   o que produziu os drifts medidos (P1-6, P2-3).
8. **Frontend sem runner de testes** (as 31 guardas de `test_frontend_honesty.py` leem o fonte;
   não há Jest/Playwright) e sem contexto/router — tudo em 1 componente cliente com 40+ estados
   `useState`.
9. **Sem observabilidade** (P2-4): incidente não é investigável; o único log é o `print` do
   bootstrap.
10. **`datetime.utcnow` ×8** — dívida de 1 linha cada, risco de 1 bug cada (P1-8).

---

## 7. Arquivos críticos (top 20, por risco × centralidade)

| # | Arquivo | Por que crítico |
|---|---|---|
| 1 | `backend/app/main.py` | god module: 58 rotas + 2 WS + bootstrap na importação + CORS; 8 duplicatas de tenant; o P0-1/P0-2 passam por ele |
| 2 | `backend/app/queue.py` | ciclo de vida do job; P0-1 (worker não enxerga job); ponto único de mutação (`transition`) |
| 3 | `backend/app/store.py` | fonte de verdade em memória de jobs e personas (P0-1, P1-5) |
| 4 | `backend/app/core/contracts.py` | `GenerationSpec` (19 campos) + 13 blocos — o contrato do qual tudo depende |
| 5 | `backend/app/models.py` | 7 tabelas; sem migrations; `projects` morta; sem `jobs`/`personas` |
| 6 | `backend/app/auth.py` | identidade; segredo fraco default; sem workspace no claim; sem revogação |
| 7 | `backend/app/core/config.py` | settings + `jwt_secret` 23 bytes; `cors_origins`; todos os toggles de produção |
| 8 | `backend/app/storage.py` | fronteira local/S3; traversal guard; URLs assinadas; modo local sem limite de upload |
| 9 | `backend/app/schemas.py` | contrato HTTP (Job, Persona, requests) — 540 stmts, 100% |
| 10 | `backend/app/providers/registry.py` | fonte única de provider; recusa vs substituição; P1-6 (drift com a lista estática) |
| 11 | `backend/app/events.py` | hub in-process (P1-7); contrato dos 6 eventos |
| 12 | `backend/app/core/generation_spec_builder.py` | raiz de composição; precedência; trace |
| 13 | `backend/app/core/director_agent.py` | porta de entrada do produto (`/core/direct`) |
| 14 | `backend/app/core/persona_memory.py` | governança de identidade em RAM (P1-5) |
| 15 | `backend/app/core/prompt_compiler.py` | único produtor de texto de prompt (invariante) |
| 16 | `backend/app/media.py` | FFmpeg na thread HTTP (P2-8); export/probe/concat |
| 17 | `render.yaml` | blueprint de produção; P1-1 (storage off) e P0-1 (fila off) moram aqui |
| 18 | `Dockerfile.api` | imagem de produção; envia o cluster morto junto (P0-3) |
| 19 | `app/page.tsx` | a UI inteira; mocks da seção 4; 40+ estados |
| 20 | `lib/api.ts` | contrato browser↔API; token em localStorage (P2-2); base relativa + proxy |

*Infra igualmente crítica (fora do top 20 por ser estável):* `.github/workflows/ci.yml`,
`requirements.txt`, `docker-compose.yml`, `next.config.mjs`.

---

## 8. Plano dos próximos PRs

Ordenado por dependência e pela ordem de sprints da Bíblia (§19). Cada PR começa com a própria
auditoria (regra §20) e termina com a DoD (§18). Nenhum inclui o que a Bíblia proíbe; nenhum
deleta arquivo (Regra de Ouro).

| PR | Título | Fecha | Bíblia |
|---|---|---|---|
| **PR002** | **Segurança:** matriz de permissões por recurso (token obrigatório onde a Bíblia §16 exige + filtro de workspace em `/queue`, `/jobs/*`, `/assets/download/*`, `/knowledge`, `/personas/*`, WS de treino), rate limit em `/auth/*`, segredo JWT validado no startup (≥ 32 B), claims de workspace, CORS explícito, log estruturado/audit trail, token fora de `localStorage` | P0-2, P1-2, P2-2, P2-4 | §16 |
| **PR003** | **Jobs no Postgres:** Alembic (baseline + migrações), tabela `jobs`, repositório, `process_generation` lê/escreve no banco, `MemoryStore` só no perfil de teste, bootstrap no lifespan (redesign do conftest: 25 `TestClient` sem context manager) | P0-1, P1-3 | §4, §6, §14 |
| **PR004** | **Personas no Postgres:** tabela `personas`, adapter `PersonaSource` persistente (o Core já recebe por injeção — `memory_resolver.py` não muda), `POST /personas` persiste, FK `training_runs.persona_id` | P1-5 | §7 |
| **PR005** | **Conformidade de estados de Job:** decisão de produto `complete` → `completed` (alias de resposta para preservar a API — Regra de Ouro) + estados finos `loading_model/rendering/upscaling` como marcos já existentes, se a Bíblia mantiver a lista | P1-4 | §14 × §2 |
| **PR006** | **Storage em produção:** MinIO no blueprint + `BROBOND_STORAGE_ENABLED=true` + bucket versionado + validação do fluxo com bucket real | P1-1 | §15 |
| **PR007** | **Higiene Legacy (só documentos/etiquetas):** rotular cluster morto e `studio-shell.tsx` como Legacy (docstrings + `docs/LIMITATIONS.md`), remover o `login` que aceita qualquer credencial do módulo morto **marcando-o como desabilitado** (não apagando), corrigir a lista estática de modelos para espelhar o registry, `datetime.utcnow` → `datetime.now(UTC)` (8), índice em `knowledge` | P0-3 (mitigado), P1-6, P1-8, P2-8 | §2, §3.8 |
| **PR008** | **Honestidade da UI:** remover a sessão local falsa (offline = mensagem, sem usuário fake), parametrizar a criação de persona (nada de "Petrick Martins" hardcoded), controles decorativos ou ganham função ou saem da tela | P2-3 | §2, §8 |
| **PR009** | **Robustez de recursos:** limite de upload + `MAX_IMAGE_PIXELS`, paginação em `/assets` e `/queue`, TTL/evicção do store, export FFmpeg fora da thread HTTP (task Celery existente), WS de treino por push em vez de polling | P2-1, P2-8 | §3, §14 |
| **PR010+** | Sprints 4/5 da Bíblia: Quality AI estética (8 critérios + score + regeneração < 85), Lip Sync, Timeline regenerativa por cena | P2-7 | §9, §13, §19 |

Sequência: **PR002 → PR003 → PR004** (segurança antes de persistência; persistência antes de
estados) → PR005/PR006 (decisão de produto + infra) → PR007/PR008/PR009 (higiene) → PR010+.

---

## 9. Definition of Done

**Confirmação formal: nenhuma feature foi implementada neste Sprint.**

| Critério (Bíblia §18 + PR #001) | Estado | Evidência |
|---|---|---|
| Build aprovado | ✅ | `npm ci && npm run build` → `✓ Compiled successfully` (15,1 kB, First Load 102 kB) |
| Testes aprovados | ✅ | `pytest backend/tests -q` → **1.077 passed** (Python 3.11 local; CI usa 3.12) |
| Documentação atualizada | ✅ | este relatório + `docs/DEVELOPER_BIBLE.md` versionado; nenhum número de doc divergente (guardas anti-drift verdes) |
| Changelog atualizado | ✅ (N/A por design) | Sprint de auditoria não gera entrada de CHANGELOG — o PR que implementar mudará |
| APIs documentadas | ✅ | `docs/API.md` (58 rotas + 2 WS, gerada por script) continua válida — zero rotas alteradas |
| Sem regressões | ✅ | 1.077 testes antes = 1.077 depois; `git diff --stat` vazio |
| Compatibilidade preservada | ✅ | nenhum arquivo existente tocado; Regra de Ouro íntegra |

**Arquivos do PR #001:** 0 modificados · 0 removidos do projeto · 2 criados (`docs/DEVELOPER_BIBLE.md`
— a constituição, que não existia versionada — e este `SPRINT1_AUDIT_REPORT.md`) · 1 substituído
(`SPRINT1_AUDIT.md`, rascunho untracked do mesmo Sprint, anulado por este relatório).

---

## Anexo A — Comandos de verificação (reprodutíveis)

```bash
# Baseline
python3 -m venv .venv-ci && .venv-ci/bin/pip install -r requirements.txt
.venv-ci/bin/python -m pytest backend/tests -q                  # 1077 passed
.venv-ci/bin/python -m coverage run --source=backend/app -m pytest backend/tests -q
.venv-ci/bin/python -m coverage report --include='backend/app/*' --skip-empty   # TOTAL 95%
npm ci && npm run build                                          # ✓ Compiled successfully

# S1-B árvore
git ls-files                                                     # 108 arquivos versionados

# S1-C módulos mortos
for m in app.api.routes app.api.dependencies app.core.security app.services.generation; do
  PYTHONPATH=backend python -c "import $m"                       # 4/4 falham
done

# S1-C/E rotas e identidade
PYTHONPATH=backend python -c "introspecção de app.routes"        # 58 APIRoute + 2 WS;
                                                                 # 6 obrigatórias, 4 opcionais, 48 abertas
# S1-C jobs
sed -n '10,15p' backend/app/schemas.py                           # 5 estados
# S1-G database
find . -name 'alembic*'                                          # vazio
grep -rn utcnow backend/app --include='*.py' | wc -l             # 8
# S1-F produção
grep -n 'STORAGE_ENABLED' render.yaml                            # "false", sem MinIO no blueprint
grep -n 'healthCheckPath' render.yaml                            # / e /api/v1/health (existem no app)

# DoD
git diff --stat                                                  # vazio
git status --porcelain                                           # só os 2 documentos novos
```
