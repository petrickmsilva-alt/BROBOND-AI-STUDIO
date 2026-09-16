# RECONCILIAÇÃO OFICIAL — BROBOND AI STUDIO

**Data:** 2026-09-16
**Tipo:** somente leitura (nenhum código implementado, nenhum merge executado, nenhum PR criado)
**Veredito em uma linha:** a fonte única de verdade é **`main` @ `04438e2`** (merge do GitHub PR #9). Nada existe fora de `main` exceto 3 branches remotas obsoletas e 1 commit avulso já superado.

---

## 1. Estado real

- **Total de commits no repositório:** 67, todos alcançáveis a partir de `main`.
- **GitHub PRs #1–#9:** todos `MERGED`, todos com CI verde (`backend` + `frontend`).
- **PRs abertos:** zero. **Branches com trabalho não mergeado:** zero.
- **Validação local do HEAD (`04438e2`), executada nesta reconciliação (venv em `/tmp`, fora do repo):**
  - `1407 tests collected` → **1406 passed, 1 skipped** em ~23s.
  - Cobertura total `backend/app`: **97%** (gate `--fail-under=95` do CI: **pass**); `backend/app/core/`: **98%**.
- **Último CI em `main` (push do merge #9):** run `35084362426` — `success` (backend ~1m15s).
- **Único commit não contido em `main` em todo o repositório:** `ab09992` (ver §6) — conteúdo já superado, sem valor de merge.

### Branches existentes (locais + remotas)

| Branch | Localização | Tip | Situação vs `main` |
|---|---|---|---|
| `main` | local + `origin/main` | `04438e2` | referência (mais avançada) |
| `arena/01a0a9c6-brobond-ai-studio` | local (esta sessão) | `04438e2` | idêntica a `main` (`git diff` vazio) |
| `origin/arena/01a0a194-brobond-ai-studio` | remota (sobra do GitHub PR #1) | `ab09992` | **26 atrás, 1 à frente** (1 commit avulso superado) |
| `origin/arena/01a0a1fd-brobond-ai-studio` | remota (sobra do GitHub PR #2) | `6a72dd9` | 24 atrás, 0 à frente (100% mergeada) |
| `origin/arena/01a0a215-brobond-ai-studio` | remota (sobra do GitHub PR #3) | `cdbb483` | 22 atrás, 0 à frente (100% mergeada) |

As branches dos GitHub PRs #4–#9 (`arena/01a0a23b`, `01a0a25e`, `01a0a607`, `01a0a748`, `01a0a7d3`, `01a0a7ee`) foram **deletadas após o merge**; restam apenas `refs/pull/N/head`, todos antepassados de `main`.

### Últimos 30 commits de `main` (= `origin/main` = branch da sessão; as três são idênticas)

```
04438e2 Merge pull request #9 from petrickmsilva-alt/arena/01a0a7ee-brobond-ai-studio
507566b PR009: REAL AI CONNECTORS — conectores Flux/Wan reais com retry, timeout, fallback e telemetria
f0874e3 Merge pull request #8 from petrickmsilva-alt/arena/01a0a7d3-brobond-ai-studio
995f1b4 PR008: Cinematic Render Engine — Director connected to GenerationExecutor
7e159c3 Merge pull request #7 from petrickmsilva-alt/arena/01a0a748-brobond-ai-studio
99203cb PR007 GPU Provider Orchestrator
9295e39 Merge pull request #6 from petrickmsilva-alt/arena/01a0a607-brobond-ai-studio
d1c47de CI: harden the queue-events waits and self-report test failures
59a4496 PR004.1: Project Memory Contract — um adapter, uma chave, um formato estável
7435c7b PR004: Studio Persona Pipeline — persona do estúdio ao provider, sem tocar no banco
6efc18d PR004-prep: Arquitetura de jobs — Repository Pattern (Core desacoplado do PostgreSQL)
07f3a85 PR003: Persona Memory Engine — personas persistentes em PostgreSQL
32a46c1 PR002: segurança e persistência — produção sem alterar a arquitetura
749bc36 PR001 (entregável aprovado): relatório de auditoria SPRINT1 + Developer Bible no caminho canônico
65721fb Merge pull request #5 from petrickmsilva-alt/arena/01a0a25e-brobond-ai-studio
27f02e1 Fix: docs/LIMITATIONS.md dizia que 10 rotas exigem token; só 6 exigem
8f509b6 Fix: a suíte falhava no CI por assumir que Pillow está ausente
adc9f91 BROBOND AI STUDIO V2 — 17 etapas: Core de direção, gate de qualidade e cobertura 95%
3708784 Merge pull request #4 from petrickmsilva-alt/arena/01a0a23b-brobond-ai-studio
35ec914 fix(deploy): bind uvicorn to Render's PORT instead of hardcoded 8000
db578df fix(deploy): build the Next.js app before next start
76844d7 Merge pull request #3 from petrickmsilva-alt/arena/01a0a215-brobond-ai-studio
cdbb483 fix(render): align render.yaml with the current Blueprint schema
09277ae Merge pull request #2 from petrickmsilva-alt/arena/01a0a1fd-brobond-ai-studio
6a72dd9 ci(render): add Render blueprint + cloud deploy fixes
26d4ab6 Merge pull request #1 from petrickmsilva-alt/arena/01a0a194-brobond-ai-studio
4c18ffe fix: preserve versioned health endpoint
98dc92c fix: complete frontend build dependencies
2048ce4 fix: reconcile remote scaffold with BROBOND Core schemas
76d423e merge remote workspace foundation
```

Últimos 30 das branches obsoletas: `origin/arena/01a0a1fd` e `origin/arena/01a0a215` são prefixos diretos da história acima (tips `6a72dd9` e `cdbb483`); `origin/arena/01a0a194` = mesma história até `4c18ffe` + o commit avulso `ab09992` no topo. Nenhuma contém trabalho posterior ao GitHub PR #3.

---

## 2. Branch mais avançada

**`main` (e, por identidade, `origin/main` e `arena/01a0a9c6-brobond-ai-studio`), em `04438e2`.**

Evidência (`git rev-list --left-right --count main...<branch>`):

| Comparação | `main` à frente | branch à frente |
|---|---|---|
| `main` vs `arena/01a0a9c6` (sessão) | 0 | 0 (idênticas) |
| `main` vs `origin/arena/01a0a194` | 26 | 1 (`ab09992`, superado) |
| `main` vs `origin/arena/01a0a1fd` | 24 | 0 |
| `main` vs `origin/arena/01a0a215` | 22 | 0 |

O `diff main..origin/arena/01a0a194` mostra ~52 mil deleções: as sobras remotas são anteriores ao V2 (GitHub PR #5) e a todos os PR001–PR009. O único commit "à frente" (`ab09992`, `chore: add Render Blueprint for CI/CD deployment`, só `render.yaml`, +99) foi feito na branch do PR #1 **depois** do merge e foi superado pelos GitHub PRs #2/#3/#4 (blueprint com 2 serviços + Postgres, schema atual, build do Next, `$PORT`). Mergeá-lo hoje seria uma **regressão** do deploy.

---

## 3. Main atual

- **SHA:** `04438e2335e73087e375fccad0c6264361af13b5` — merge do GitHub PR #9 (2026-09-16T10:19:35Z).
- **Conteúdo:** fundação (PR #1) + deploy Render (PRs #2–#4) + V2/ETAPAs 4–17 (PR #5) + PR001–PR004.1 (PR #6) + PR005/PR006/PR007 (PR #7) + PR008 (PR #8) + PR009 (PR #9).
- **Números medidos no HEAD (não lembrados — extraídos da aplicação e da suíte):**
  - 74 rotas HTTP sob `/api/v1` (32 Core, 14 tags), 3 WebSockets — cf. `docs/API.md` (gerado) e `test_docs_accuracy.py`.
  - Identidade: 34 rotas exigem token, 3 aceitam sem exigir, 37 públicas por desenho; os 3 WebSockets autenticam por `?token=` (verificado no código, incl. `/ws/render/{batch_id}`).
  - 1.407 testes coletados; cobertura 97% total / 98% no Core; 4 módulos mortos (100 statements) isolados por teste — tudo confirmado por execução local.
- **`main` está atrasada? NÃO.** É o ponto mais avançado do projeto em código, testes e CI. Qualquer percepção de atraso vem de documentação desatualizada (ver §5), não de código.

---

## 4. PRs encontrados (PR001–PR008 solicitados + PR009 registrado)

> Nota de nomenclatura: "GitHub PR #N" = pull request do GitHub; "PR00X" = rótulo interno dos commits. Os dois esquemas **não** coincidem (ex.: o GitHub PR #6 contém os internos PR001–PR004.1).

| PR interno | Branch de origem (deletada pós-merge) | Commit SHA | GitHub PR | Status | CI do GitHub PR |
|---|---|---|---|---|---|
| PR001 | `arena/01a0a607` | `749bc36b134fd6e2f4b99bc0f7728aaf2da80917` | #6 | **merged** (`9295e39`, 2026-09-15T22:47:04Z) | backend ✅ + frontend ✅ |
| PR002 | `arena/01a0a607` | `32a46c18b5f7d735faec146cff987c8bc8742421` | #6 | **merged** | backend ✅ + frontend ✅ |
| PR003 | `arena/01a0a607` | `07f3a85dff1bfc12cf2e9dcf7a24b8dedbe231e4` | #6 | **merged** | backend ✅ + frontend ✅ |
| PR004-prep | `arena/01a0a607` | `6efc18d2819a2b5ae0b3396268ef33c44392c59b` | #6 | **merged** | backend ✅ + frontend ✅ |
| PR004 | `arena/01a0a607` | `7435c7b02f7ab32be88f96d013cb2b28da78657a` | #6 | **merged** | backend ✅ + frontend ✅ |
| PR004.1 | `arena/01a0a607` | `59a449699a77ee1280ff16a530c8072776a33e7c` | #6 | **merged** | backend ✅ + frontend ✅ (+ `d1c47de` fix de CI) |
| **PR005** | `arena/01a0a748` | **sem commit próprio — dentro de `99203cb`** | #7 | **merged** (`7e159c3`, 2026-09-16T01:25:37Z) | backend ✅ + frontend ✅ |
| **PR006** | `arena/01a0a748` | **sem commit próprio — dentro de `99203cb`** | #7 | **merged** | backend ✅ + frontend ✅ |
| PR007 | `arena/01a0a748` | `99203cb15cb3a218322268f27a0a7c3706259aa9` | #7 | **merged** | backend ✅ + frontend ✅ |
| PR008 | `arena/01a0a7d3` | `995f1b48a189f4668a9d693f6fef1ea38a45983f` | #8 | **merged** (`f0874e3`, 2026-09-16T01:56:38Z) | backend ✅ + frontend ✅ |
| PR009 | `arena/01a0a7ee` | `507566befc3b627186c7565d607198c95d5f755b` | #9 | **merged** (`04438e2`, 2026-09-16T10:19:35Z) | backend ✅ + frontend ✅ |

**Achado importante:** PR005 (Director AI) e PR006 (Storyboard Engine) **não existem como commits ou branches separadas**. O GitHub PR #7 (`PR005-PR007 — Director AI + Storyboard + GPU Provider Orchestrator`) contém um único commit, `99203cb`, que entrega os três juntos. Prova dentro de `99203cb` (57 arquivos, +5.817/−195): `backend/app/core/director/*` + `test_pr005_director_ai.py` + `docs/DIRECTOR_AI.md` (PR005); `storyboard_state.py` + `lib/storyboard/*` + `test_pr006_storyboard_engine.py` + `docs/STORYBOARD_ENGINE.md` (PR006); `providers/*` + `test_pr007_provider_orchestrator.py` + `docs/PROVIDERS.md` (PR007).

### Arquivos alterados e testes por PR

- **PR001** (`749bc36`, docs-only, 2 arquivos +536): `SPRINT1_AUDIT_REPORT.md`, `docs/DEVELOPER_BIBLE.md`. Testes: nenhum.
- **PR002** (`32a46c1`, 39 arquivos +2.212/−269): segurança (JWT ≥32B, rate limit, audit log `app/audit.py`), persistência (`JobRow`, Alembic `0001`, `store.py` SQL), `main.py`, `auth.py`, `schemas.py`, `LIMITATIONS/API/ARCHITECTURE/CHANGELOG`. Testes adicionados: `test_audit_log.py`, `test_job_persistence.py`, `test_migrations.py`, `test_security_authorization.py` (+ ajustes em 8 suítes).
- **PR003** (`07f3a85`, 24 arquivos +2.578/−57): Persona Memory Engine (Alembic `0002`, `repositories/persona_repository.py` 441 linhas, `core/contracts.py`, `memory_resolver` injetável, 6 rotas `/personas`, UI `/studio/personas`, `docs/PERSONA_ENGINE.md`). Testes: `test_persona_engine.py` (465 linhas).
- **PR004-prep** (`6efc18d`, 24 arquivos +1.334/−164): Repository Pattern de jobs (`core/job_service.py` + `job/postgres/redis/memory_job_repository.py`, `models.py` → pacote `models/`). Testes: `test_job_repository.py` (431 linhas).
- **PR004** (`7435c7b`, 21 arquivos +1.055/−41): Studio Persona Pipeline (seletor/preview no Studio, `queue.py` injeta persona no spec, `lib/projectMemory.ts`). Testes: `test_studio_persona_pipeline.py` (434 linhas).
- **PR004.1** (`59a4496`, 21 arquivos +4.783/−248): Project Memory Contract (`lib/memory/project_memory.ts` + hook + `docs/PROJECT_MEMORY.md`, vitest + gate 95% frontend). Testes: `test_project_memory_contract.py` (241 linhas) + `project_memory.test.ts` (399) + `use_project_memory.test.tsx` (102).
- **PR005+PR006+PR007** (`99203cb`, 57 arquivos +5.817/−195): pacote `core/director/` (ProductionPlan/ShotPlan/Mood/CameraDirector/StoryboardState), `BaseProvider`/`ProviderRegistry`/`GenerationExecutor`/`MockProvider`, Flux/Wan adapters, `/api/v1/providers`, `/studio/director`, `/studio/providers`, `docs/{DIRECTOR_AI,STORYBOARD_ENGINE,PROVIDERS}.md`. Testes: `test_pr005_director_ai.py` (294) + `test_pr006_storyboard_engine.py` (336) + `test_pr007_provider_orchestrator.py` (342) + `storyboard_state.test.ts` (243).
- **PR008** (`995f1b4`, 26 arquivos +4.264/−33): `backend/app/render/*` (orquestrador, batch, scene renderer, assets, progresso), 6 rotas `/api/v1/render/*`, WS `/ws/render/{batch_id}`, UI `/studio/render`, `docs/RENDER_ENGINE.md`. Testes: `test_pr008_render_engine.py` (**1.524 linhas**).
- **PR009** (`507566b`, 41 arquivos +3.655/−348): conectores reais Flux/Wan (+Hunyuan via conector de vídeo), `retry_policy.py`, `timeout_manager.py`, `telemetry.py`, fallback no executor, rotas `/providers/{id}/test` + `/providers/telemetry`, `docs/AI_CONNECTORS.md`. Testes: `test_pr009_ai_connectors.py` (**1.304 linhas**).

### Resultado do CI (todos os GitHub PRs + `main`)

| GitHub PR | backend | frontend | Observação |
|---|---|---|---|
| #1–#4, #7, #8, #9 | ✅ pass | ✅ pass | verde direto |
| #5 (V2) | ✅ pass | ✅ pass | 2 runs intermediários `failure`, corrigidos nos commits seguintes |
| #6 (PR001–PR004.1) | ✅ pass | ✅ pass | 1 run intermediário `failure`, corrigido (`d1c47de`) |
| `main` pós-merge #9 | ✅ run `35084362426` success | ✅ | HEAD validado no servidor e localmente |

### Comparação dos 9 subsistemas (estado em `main` vs história)

| Subsistema | Onde vive em `main` | Introduzido / evoluído por | Estado |
|---|---|---|---|
| GenerationSpec | `core/contracts.py` (19 campos, `GENERATION_SPEC_FIELDS`), `core/generation_spec_builder.py`, `app/spec_adapter.py` | ETAPA 3 → PR003 → PR004 → PR007 → PR009 | ✅ único input de providers, imposto por teste |
| Persona Engine | `core/persona_memory.py`, `core/memory_resolver.py`, `repositories/persona_repository.py`, Alembic `0002` | V2 (ETAPA 4, memória) → PR003 (SQL) → PR004 (pipeline) | ✅ persistente, versionada, atribuída |
| Director AI | **duplo por desenho:** legado `core/director_agent.py` (ETAPA 7, serve `/core/direct`) + pacote `core/director/` PR005 (serve `/core/director/production-plan`) — ambos com call sites reais | ETAPA 7 → PR005 | ✅ os dois vivos e roteados |
| Storyboard Engine | `core/storyboard_engine.py` (ETAPA 8) + `core/director/storyboard_state.py` + `lib/storyboard/*.ts` (PR006) | ETAPA 8 → PR006 | ✅ cast + editor versionado |
| Provider Registry | **duplo por desenho:** `providers/registry.py` legado (catálogo Core, incl. `hunyuan-video` planejado) + `providers/provider_registry.py` universal (flux, wan, mock, hunyuan — PR009) | PR #1 → ETAPA 10 → PR007 → PR009 | ✅ Core sem nomes de modelo; executor com fallback |
| Render Engine | `app/render/*` + 6 rotas `/api/v1/render/*` + WS `/ws/render/{batch_id}` + `/studio/render` | PR008 | ✅ Director → Executor, progresso por push |
| WebSocket | `/api/v1/queue/events/{job_id}`, `/api/v1/personas/.../training/events/...`, `/ws/render/{batch_id}` | PR #1 → ETAPA 11 → PR002 (auth) → PR008 | ✅ 3 sockets, todos `?token=`, push (sem polling) |
| Jobs | `core/job_service.py` (máquina de 5 estados) + 3 repositórios (postgres/redis/memory) + `queue.py`/Celery | PR #1 → PR002 (SQL) → PR004-prep (pattern) | ✅ Core desacoplado do PostgreSQL |
| Storage | `app/storage.py` (MinIO/S3 + local, 100% coberto) + `store.py` (shim legado) + `media.py` (FFmpeg) | PR #1 → ETAPA 12 → PR002 | ✅ metadados no banco, bytes no storage |

Não há implementação mais avançada de nenhum subsistema fora de `main`: as branches obsoletas são anteriores a todos os PR001–PR009.

---

## 5. Divergências (código × docs)

Verificado por leitura + execução. O repositório tem um oráculo forte (`test_docs_accuracy.py`: rotas, contagens, API.md gerado, nº de testes, identidade, módulos mortos) — as divergências abaixo são exatamente as que o oráculo **não** cobre.

### Alta relevância

- **D1 — `DEVELOPER_BIBLE.md` (§0 diz ser "autoridade máxima") contradiz a realidade.** §14 lista 8 estados de job (`loading_model`, `rendering`, `upscaling`…) que nunca existiram — o código tem 5 (`queued`, `running`, `complete`, `failed`, `cancelled`, cf. `core/job_service.py:58`). §§17–19 congelam o projeto nos Sprints 1–5 ("proibido implementar features no Sprint 1") enquanto V2 + PR001–PR009 já foram entregues. §15 exige S3/MinIO obrigatório; o código é local-first com storage opcional. **Risco: um agente que obedeça a Bíblia ao pé da letra tentará "corrigir" código correto.**
- **D2 — `README.md` parou no PR007.** "Current slice" diz `/studio/director … editing only, no render` (PR008 entrega render); não há nenhuma seção PR008/PR009 (`/studio/render`, conectores reais, retry/timeout/telemetria). A árvore "Architecture target" lista `app/models.py` (virou pacote `app/models/` no PR004-prep) e omite `app/render/`, `app/repositories/`, `core/director/`.
- **D3 — Contagens de rotas divergem em 3 documentos.** Real (medido): **74 HTTP / 37 com identidade / 37 públicas**. `README.md`: "35 of 66" (era PR007) ❌. `ROADMAP.md`: "34 de 72… 35 públicas" (era PR008) ❌. Corretos: `docs/LIMITATIONS.md`, `docs/ETAPAS.md`, `docs/API.md` ✅ (cobertos pelo oráculo).

### Média relevância

- **D4 — Cobertura 96% vs 97%.** Medido nesta reconciliação: **97% total / 98% no Core** (README ✅). `docs/LIMITATIONS.md` §5 e `ROADMAP.md` dizem 96% ❌ (era pré-PR009).
- **D5 — `CHANGELOG.md` incompleto.** Sem seção PR001; sem seções ETAPA 1–5 (salta de ETAPA 6 para "Fundação"); sem entradas para os GitHub PRs #2–#4 (deploy Render — só uma menção de uma linha em "Fundação").
- **D6 — `ROADMAP.md` v2.0:** checkbox "Personas, Styles e Shots persistidos no PostgreSQL (hoje são seeds injetáveis)" — **personas JÁ são persistidas desde o PR003**; só styles/shots seguem como seeds. O checkbox agrupa os três como pendentes.
- **D7 — Tabela de providers no README lista 3 (flux/wan/mock); o registry universal tem 4** (`hunyuan` registrado em `provider_registry.py:161-166`, conector real em `wan_provider.py:358`).

### Baixa relevância / cosméticas

- **D8 — `docs/API.md`:** contagens corretas (geradas), mas o parágrafo de prosa cita PR006/7/8 e não o PR009 (prosa do `scripts/gen_api_doc.py` desatualizada).
- **D9 — `ARCHITECTURE.md`:** título "Dois WebSockets, dois mecanismos" (seção da ETAPA 11) vs 3 sockets no HEAD — histórico setorial, mas sem apontar o terceiro (PR008).
- **D10 — Faltam `ETAPA1/2/3_REPORT.md`** (existem só 4–17); ROADMAP referencia "Atualização da ETAPA 2/3" sem relatório correspondente.

### Conformidades confirmadas (não-divergências)

`GenerationSpec` 19 campos (README/ROADMAP ✅); 32 rotas Core (ROADMAP ✅); 1.407 testes (README/`backend/README`/árvore ✅, imposto por teste); 13 componentes Core ✅; 4 módulos mortos / 100 statements ✅; 3 WebSockets com `?token=` ✅ (incl. `/ws/render`, verificado no código); dualidade Director legado+novo e Registry legado+universal — intencional, roteada e testada.

---

## 6. Riscos

1. **Merge na direção errada (mais grave).** As 3 branches remotas obsoletas parecem "trabalho existente". Mergeá-las em `main` apagaria ~52 mil linhas (V2 + PR001–PR009) e regrediria o deploy (`ab09992` traz um `render.yaml` primitivo). **Nunca mergear `arena/01a0a194/01a0a1fd/01a0a215` em `main`.**
2. **PR005/PR006 invisíveis na história.** Sem commits próprios, quem procurar "branch do PR005" conclui (errado) que está perdido. Registro canônico: ambos vivem em `99203cb` (GitHub PR #7, merge `7e159c3`).
3. **Bíblia vs realidade (§5-D1).** Autoridade declarada máxima + conteúdo congelado no Sprint 1 = risco de agentes futuros "alinharem" o código à Bíblia e quebrarem o que funciona (ex.: inventar estados `rendering`/`upscaling`).
4. **README desatualizado como porta de entrada.** Novos devs/agentes formam modelo mental pré-PR008 (sem render, sem conectores reais, árvore errada).
5. **Trilha de auditoria com lacunas.** CHANGELOG sem PR001/ETAPAs 1–5; ETAPA 1–3 sem relatórios.
6. **Complexidade dual legítima, mas confusa.** 2 Directors, 2 registries, providers legados + novos — tudo testado e roteado, porém exige leitura cuidadosa; deletar qualquer lado quebra a Regra de Ouro e a suíte.
7. **Contagens conflitantes (66/72/74).** Três números diferentes de rotas em docs distintos minam confiança; o número certo (74) está nos docs cobertos pelo oráculo.

---

## 7. Recomendação de merge

**NENHUM merge deve ser feito.** Não há código fora de `main` que `main` não contenha — exceto `ab09992`, cujo conteúdo foi superado e deve ser descartado, não mergeado.

Limpeza opcional (requer aprovação explícita do dono; **não executada** nesta reconciliação):

```bash
# Somente após aprovação: remover sobras remotas já 100% mergeadas/superadas
git push origin --delete arena/01a0a194-brobond-ai-studio arena/01a0a1fd-brobond-ai-studio arena/01a0a215-brobond-ai-studio
```

Nada mais. Nenhum cherry-pick, nenhum rebase, nenhum PR de reconciliação de código.

---

## 8. Próximo ponto seguro de desenvolvimento

- **Fonte única de verdade:** `main` @ `04438e2335e73087e375fccad0c6264361af13b5` (merge do GitHub PR #9).
- **Base para qualquer nova branch:** `origin/main` neste SHA. Ex.: `git checkout -b arena/<id>-brobond-ai-studio origin/main`.
- **Ordem sugerida (antes de qualquer feature nova):**
  1. **PR docs-only de reconciliação** — zerar §5: atualizar README (PR008/PR009, árvore, "35 of 66"), ROADMAP (74/37, checkbox de personas, 97%), LIMITATIONS (97%), CHANGELOG (PR001 + ETAPAs 1–5 + deploys), prosa do `gen_api_doc.py`, e **versionar a DEVELOPER_BIBLE** (V2.1: estados reais de job, mapa V2/PR001–PR009, autoridade preservada sem contradições). O oráculo `test_docs_accuracy.py` deve continuar verde.
  2. **Deletar as 3 branches remotas obsoletas** (com aprovação) para eliminar o risco §6.1.
  3. **Retomar o ROADMAP** pelos itens `- [ ]` genuínos: primeiro render GPU validado ponta a ponta, Styles/Shots persistidos, Character/Prompt libraries, continuidade entre episódios — cada um como uma branch nova a partir de `04438e2`, um PR, CI verde, merge em `main`.
- **Critério de sucesso desta reconciliação — ATENDIDO:** uma única fonte de verdade foi identificada (`main` @ `04438e2`, validada por CI verde + execução local de 1.406 passed / 97%) antes de qualquer novo PR. Nenhum código foi alterado para produzir este relatório, além da criação deste próprio arquivo.
