# BROBOND AI STUDIO ROADMAP

Este documento é a fonte estratégica do produto. Toda nova feature deve ser classificada aqui antes de ser implementada.

## Status atual

A fundação visual, API, autenticação, jobs, storage, providers, storyboard, personas, LoRA contracts, conditioning e readiness operacional já estão estruturados. A execução de modelos reais depende de hardware GPU, pesos e providers instalados.

**Atualização da ETAPA 2 (BROBOND CORE):** a camada de decisão agora existe em
`backend/app/core/`. Começou com seis componentes (`DirectorAgent`, `MemoryResolver`,
`PromptCompiler`, `StyleResolver`, `ShotResolver`, `GenerationSpecBuilder`) e chegou a **treze**
componentes vivos na PR004-prep, com `PersonaMemory`, `CinematicLibrary`, `ShotLibrary`,
`StoryboardEngine`, `VideoTimeline`, `QualityGate` e `JobService`. PR005 acrescenta o pacote
`core/director/` para `ProductionPlan`/`ShotPlan`, `MoodEngine` e `CameraDirector`; PR006
acrescenta `StoryboardState`/`StoryboardHistory` e o editor visual desacoplado — mais o contrato
`GenerationSpec` e seus 19 campos obrigatórios. PR007 acrescenta o GPU Provider Orchestrator:
`BaseProvider`, `ProviderRegistry`, `GenerationExecutor`, `MockProvider` obrigatório e
`/studio/providers`, mantendo nomes/modelos de provider fora do Core. Nenhuma rota FastAPI contém
lógica de geração. Ver `AUDIT.md` para o ponto de partida, `CHANGELOG.md` para o que mudou e
`docs/ETAPAS.md` para o índice das 17 etapas.

**Atualização da ETAPA 3 (GENERATION SPEC):** `GenerationSpec` é agora a única entrada de
todo provider — `generate(spec, output_dir)`, com `ImageProvider`/`VideoProvider` como ABC.
Nenhum call site passa prompt solto ou `dict` de parâmetros. O bug de chave que fazia o
worker devolver `cancelled` sem executar nada (P0-2a) foi corrigido.

**Atualização PR002/PR003 (segurança e persistência):** os P0s pendentes foram
fechados. **P0-2b** (jobs em memória): `JobRow` + repositório SQL — API e
worker compartilham a tabela `jobs` (Alembic `0001`). **P0-4** (endpoints
sem token): 34 de 72 rotas exigem identidade, 3 a aceitam sem exigir e 35 são
públicas por desenho; os 3 WebSockets autenticam por `?token=`. **P0-3** foi
fechado na ETAPA 11 com `publish_sync`. **P0-1** permanece por decisão:
quatro módulos mortos e quebrados, não apagados nem ressuscitados. E as
**personas** deixaram a memória no PR003 (Persona Memory Engine): tabelas
`personas` / `persona_images` / `persona_wardrobe` / `persona_identity_revision`
(Alembic `0002`), `repositories/persona_repository.py` como única fronteira
com o SQLAlchemy e `MemoryResolver.resolve_persona` injetado no Core por
adapters — ver `docs/PERSONA_ENGINE.md`. **PR004-prep (Repository Pattern):**
o fluxo de jobs foi desacoplado do PostgreSQL — `core/job_service.py`
(13º componente, máquina de estados) conhece apenas a interface
`JobRepository`; providers `PostgresJobRepository` (default),
`RedisJobRepository` (opt-in) e `MemoryJobRepository` (testes) trocáveis por
injeção sem tocar Core, rotas ou worker. O que ainda impede geração real
ponta a ponta: GPU, pesos e providers instalados. Ver `docs/LIMITATIONS.md`.

**Atualização V3.1 (Cinematic Knowledge Graph):** a memória de personagem
virou conhecimento relacional. O pacote `backend/app/graph/` (GraphRepository,
Relationship Engine, Semantic Query) persiste Character, Brand, Campaign,
Location, Vehicle, Wardrobe e Prop — todas relacionáveis — com catálogo
canônico no workspace `global` (somente leitura) e nós do workspace por cima;
o `MemoryResolver` ganhou `knowledge_context(persona_id)` por injeção de
`KnowledgeContextSource` (vocabulário puro em `core/contracts.py`), sem
alterar o `GenerationSpec`; UI `/studio/knowledge` com grafo, busca semântica
("RAM branca" → o Vehicle completo) e filtros. Director AI, Provider Registry
e Render Engine intactos. Ver `docs/KNOWLEDGE_GRAPH.md`.

## v1.0 — Workspace local

- [x] Interface premium
- [x] Image Generation contract
- [x] Video Generation contract
- [x] Projects, Assets e upload
- [x] Auth JWT e workspace
- [x] Redis/Celery/WebSocket contracts
- [ ] Primeiro render GPU validado ponta a ponta

## v1.5 — Direção visual

- [x] Motion Control presets
- [x] Storyboard continuity
- [x] Prompt Engine
- [x] ControlNet/IP Adapter contracts
- [ ] Shot Library completa com 300+ presets *(resolver pronto com os 10 códigos publicados e `catalog(query)` para o browser visual; falta o volume e a persistência)*
- [ ] Cinematic presets persistidos e editáveis *(7 estilos no `StyleResolver` com fonte injetável; falta a tabela Styles)*

## v2.0 — BROBOND CORE

- [x] Persona LoRA contracts
- [x] Character memory foundation
- [x] **Persona Memory Engine** (ETAPA 4: histórico versionado, governança atribuída, snapshots de episódio, relatório de drift)
- [x] **Cinematic Library** (ETAPA 5: CINEMATIC_BIBLE como gramática consultável + 8 regras verificáveis + auditoria da própria biblioteca)
- [x] **Shot Library 300 presets** (ETAPA 6: 290 novos em 12 famílias, todos validados contra a Bíblia, navegador visual na API)
- [x] **Storyboard Engine** (ETAPA 8: beats escalados em shots reais, arco por formato, encadeamento de continuidade e validação da sequência contra a Bíblia)
- [x] Versioned LoRA assets
- [x] Knowledge Base persistente no PostgreSQL
- [x] Memory Resolver API inicial
- [x] **BROBOND CORE implementado** (`core/`: componentes independentes + `GenerationSpec`; PR005 adiciona pacote de ProductionPlan; PR006 adiciona StoryboardState versionado)
- [x] **Memory Resolver em cada GenerationSpec** (`persona_id` → frase de identidade no prompt)
- [x] **Testes 95%** (ETAPA 16: cobertura 89% → 95%; PR005: cobertura atual 96% e gate `--fail-under=95` no CI, fronteira do cluster morto fixada por teste, 3 achados registrados)
- [x] **UX Premium** (ETAPA 15 + PR005 + PR006: Diretor como porta de entrada consumindo `/core/direct` e `/core/director/production-plan`, editor `/studio/director` com drag/drop, timeline, câmera/mood por cena e undo/redo, as 32 rotas Core alcançáveis, casca sem fatos inventados, resultado real em vez de desenho, erros distinguindo offline de rejeição, proxy relativo)
- [x] **Quality AI** (ETAPA 14: `QualityGate` como 12º componente independente, output conferido contra o spec antes de persistir, job que não produziu arquivo deixa de ser `complete`, limites da avaliação declarados em vez de fingidos)
- [x] **Video Timeline** (ETAPA 13: `VideoTimeline` como 11º componente independente, `media.concat` para montagem, `probe` finalmente parseado, dissolve por continuação de família, plano nunca fingindo arquivo renderizado)
- [x] **Director AI** (ETAPA 7: arco `documentary` restaurado, escolha de formato por especificidade em vez de ordem de dicionário, empate declarado em vez de decidido em silêncio, ritmo declarado igual ao entregue, oito beats distintos)
- [x] **Storage MinIO/S3** (ETAPA 12: `download`/`exists`/`delete`/`upload_path`/`ensure_bucket`, os quatro 501 religados, ramo S3 e guard de traversal cobertos, `storage.py` a 100%)
- [x] **Queue & WebSocket** (ETAPA 11: `transition()` como único ponto de mutação, `EventHub.publish` finalmente com chamador, seis marcos de progresso, buffer de replay, socket push em vez de loop de leitura)
- [x] **Provider Adapters** (ETAPA 10: registry como fonte única, Hunyuan adicionado, ControlNet/IP-Adapter como objetos, quatro duplicações removidas, provider indisponível recusado em vez de substituído)
- [x] **GPU Provider Orchestrator** (PR007: `BaseProvider` universal, `ProviderRegistry`, `GenerationExecutor`, Mock obrigatório, Flux/Wan adapters e `/api/v1/providers` + `/studio/providers`)
- [x] **Prompt Compiler estruturado** (ETAPA 9 + PR007: os 13 blocos de `SYSTEM_PROMPT.md`, dedupe entre blocos, cor separada de estilo, orçamento numérico vindo das capabilities do provider, storyboard compilado cena a cena)
- [x] **Director Agent determinístico** (intenção → conceito, roteiro, cenas, câmeras, música, duração)
- [x] **Style Resolver** com 5 estilos nomeados + padrão + neutro
- [x] **Shot Resolver** com os 10 códigos publicados
- [ ] Personas, Styles e Shots persistidos no PostgreSQL (hoje são seeds injetáveis via `Protocol`)
- [ ] Character Library completa
- [ ] Prompt Library classificada
- [ ] Continuidade entre episódios
- [x] **Providers recebendo apenas `GenerationSpec`** (ETAPA 3: `generate(spec, output_dir)`, ABC, zero strings soltas)

## v3.0 — AI Director

- [x] **Director AI Engine / PR005**: intenção humana → `ProductionPlan` imutável, moods internos, câmera automática por Shot Library, storyboard de 4–8 cenas e UI `/studio/director`, sem render e sem providers.
- [x] **Storyboard Cinematic Engine / PR006**: `StoryboardState` versionado, editor visual desacoplado, drag/drop, timeline proporcional com duração editável por arraste, CameraPanel, MoodPanel, undo/redo e duplicação de cena sem render.
- [x] **Cinematic Render Engine / PR008**: Director conectado ao `GenerationExecutor` — `RenderBatch` com cenas de progresso independente, `SceneRenderer` (cena → `GenerationSpec` via `PromptCompiler`), pipeline de assets (PNG/MP4 + thumbnail + metadados com prompt/seed/provider), WebSocket `/ws/render/{batch_id}` por push e UI `/studio/render` com Fila, Cancelar e Repetir.
- [x] **Real AI Connectors / PR009**: conectores reais Flux (imagem) e Wan 2.1 (vídeo) recebendo apenas `GenerationSpec`, retry com cap de 3 tentativas, timeout por provider (Flux 90s / Wan 300s, configurável por ENV), fallback para o próximo provider do Registry com motivo no Job e Batch nunca perdido, telemetria (`provider_id`, `latency_ms`, `queue_time_ms`, `render_time_ms`, `success`, `error_code`), rotas `/providers/{id}/test` + `/providers/telemetry` e UI com Disponibilidade, Último Health e Teste Real. Ver `docs/AI_CONNECTORS.md`.
- [~] Conversa de direção: trailer, luxo, fashion film, documental *(ETAPA 2 entregou o `DirectorAgent` determinístico e `POST /api/v1/core/direct`, PR005 entrega `POST /api/v1/core/director/production-plan`; falta a conversa multi-turno e o enriquecimento por LLM, cujo hook `LanguageModel` já existe)*
- [~] Roteirista automático persistido e versionado *(PR006 versiona o StoryboardState no editor; persistência server-side continua como evolução futura)*
- [x] Diretor de câmera IA inicial (PR005: Dolly, Orbit, Crane, Tracking, Static, Drone escolhidos da Shot Library; PR006: presets Hero Walk, Orbit, Tracking, Crane, Drone e Static editáveis por cena)
- [x] Ritmo, montagem, música e iluminação por intenção no plano (PR005; PR006 permite ajustar duração, iluminação, movimento e mood por cena; ainda sem render)
- [ ] Voice Clone
- [ ] Lip Sync

## v3.1 — Cinematic Knowledge Graph

- [x] **Graph Repository / ETAPA 1**: `backend/app/graph/` com as quatro peças nomeadas (`graph_models.py`, `graph_repository.py`, `relationship_engine.py`, `semantic_query.py`); persistência em PostgreSQL (migration `0003`), catálogo canônico idempotente no workspace `global` e nós por workspace.
- [x] **Entidades / ETAPA 2**: Character, Brand, Campaign, Location, Vehicle, Wardrobe, Prop — **todas relacionáveis** (qualquer par de tipos é legal; o vocabulário só sugere pares típicos).
- [x] **Relationship Engine / ETAPA 3**: relações tipadas com rótulo de reverso (bidirecionalidade: uma linha no banco, duas leituras) — Petrick → `dirige` → RAM, Petrick → `veste` → Legacy Jacket, Legacy → `pertence` → BroBond, Showroom → `localizado` → Goiânia; validação (sem self-loop, extremidades existentes, duplicata 409) e BFS de caminho mínimo.
- [x] **Semantic Query / ETAPA 4**: pontuação determinística sem modelo — "RAM branca" → o Vehicle completo (atributos + relações); "Showroom" → o Location; frase desconhecida → resposta vazia, nunca chute.
- [x] **Memory Resolver / ETAPA 5**: `knowledge_context(persona_id)` por injeção (`KnowledgeContextSource`); **sem alterar o GenerationSpec** — spec compilado com grafo conectado é idêntico ao sem ele (teste fixa a igualdade campo a campo).
- [x] **UI `/studio/knowledge` / ETAPA 6**: grafo com nós, arestas e rótulos, busca semântica com resultados completos, filtros por tipo e por relação, painel do nó com ações (ligar, remover).
- [x] **Testes / ETAPA 7**: 76 novos testes; pacote `graph/` a 100%; suíte a 1.495 testes com gate de 95% (atual: 97%).

## v4.0 — Escala

- [ ] Multi-agent collaboration real
- [ ] Multi-tenancy SaaS
- [ ] Cloud rendering e autoscaling
- [ ] Créditos, quotas e billing
- [ ] Mobile app
- [ ] Painel administrativo

## Regra de evolução

Toda nova solicitação deve informar: versão, módulo, impacto na memória, impacto nos providers, contrato de API, UX, testes e documentação. Features que não se encaixam em uma versão devem primeiro atualizar este arquivo.
