# CHANGELOG

Todas as mudanças relevantes deste repositório. O formato segue
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o versionamento segue as
versões de produto do `ROADMAP.md`.

---

## [Unreleased] — PR011: GPU CLUSTER & FLUX/WAN INTEGRATION

Provider Registry ligado a GPUs externas (RunPod). Cinco arquivos novos em
`backend/app/providers/`, uma linha composta no readiness e **nada mais**:
Director AI, Storyboard Engine, Prompt Compiler e a superfície pública do
Provider Registry ficaram intocados — `docs/API_SNAPSHOT.json` não mudou uma
linha, que é a prova mecânica disso.

- **ETAPA 1** — `providers/gpu_client.py`: transporte e só. HTTP async por
  trás de um `Protocol` (o default importa `httpx` dentro da chamada, então o
  módulo é importável em qualquer máquina), timeout configurável por client e
  por chamada, retry exponencial `0.5s → 1s → 2s` com cap em 8s, poll de jobs,
  cancelamento, upload de referência como data URI base64 e download aceitando
  URL, data URI ou base64 puro. **4xx não é repetido**: um payload malformado
  falha idêntico três vezes, só que gastando o deadline que protegeria uma
  falha real. Um deadline estourado **cancela o job antes de desistir** —
  job de GPU abandonado não é render perdida, é fatura. A chave viaja só no
  header `Authorization`: não aparece em retorno, log, erro ou health, o
  helper `_safe_url` reduz qualquer URL a `scheme://host` antes de entrar numa
  mensagem (que chega ao readiness público, e o path carrega o id do
  endpoint), e o download de uma URL pré-assinada **não** leva o header.
- **ETAPA 2** — `providers/runpod_flux_provider.py` (`runpod-flux`,
  `flux-kontext-pro`, 24GB): `image`, `upscale`, `inpaint`, `outpaint` e
  `control reference`. As cinco operações são declaradas em
  `SUPPORTED_OPERATIONS`/`supports_operation()` e **não** em campos novos de
  `ProviderCapabilities`, porque esse é o contrato público congelado que o PR
  está proibido de mexer; nada fica escondido — o conjunto é testado e está em
  `docs/GPU_CLUSTER.md`. Recebe apenas `GenerationSpec`, verificado por
  assinatura. Modo de referência sem `reference_path` levanta `ValueError`
  **fatal** antes de gastar GPU: o retry engine não repete `ValueError`, e
  repetir não faria a imagem aparecer.
- **ETAPA 3** — `providers/runpod_wan_provider.py` (`runpod-wan`,
  `wan-2.1-t2v-14b`, 48GB): text-to-video, image-to-video, `duration`, `fps`,
  `seed` e camera motion. **Sem tocar o Storyboard**, e sem precisar: a
  intenção de câmera chega como dois campos tipados do spec (`motion`,
  `motion_strength`), e `CAMERA_MOTIONS` é tabela de tradução para o
  vocabulário do worker — um movimento desconhecido passa adiante intacto em
  vez de ser descartado. Duração (1–10s) e fps (8–30) são **limitados e
  registrados** no metadata (`"clamped": true`), não recusados: matar o batch
  porque uma cena pediu 30s seria pior que entregar o clipe mais longo
  possível e dizer que foi cortado.
- **ETAPA 4** — job inteiro no backend:
  `GenerationSpec -> GenerationExecutor -> RunPod -> job_id -> poll -> Asset
  -> Quality Engine`. `backend/app/render/` não mudou uma linha — o Render
  Engine continua chamando só `GenerationExecutor.execute(...)` e não sabe que
  existe um cluster. **Zero polling no frontend**: há teste varrendo `app/`,
  `lib/` e `components/` atrás de `runpod`, `/status/` e `RUNPOD`. Toda falha
  de GPU vira `ProviderUnavailable`, que é exatamente o que a pilha de
  resiliência do PR009 já sabe repetir e contornar; job completo **sem
  artefato** é falha, não sucesso vazio.
- **ETAPA 5** — quatro variáveis, todas opcionais em DEV:
  `BROBOND_RUNPOD_API_KEY`, `BROBOND_RUNPOD_ENDPOINT`, `BROBOND_GPU_TIMEOUT`
  (300s), `BROBOND_GPU_POLL_INTERVAL` (2s). Sem elas o app sobe igual e a
  suíte inteira roda num laptop sem conta na RunPod. No `render.yaml` as duas
  primeiras entram como `sync: false` — pedidas no deploy, fora do arquivo e
  fora do git.
- **ETAPA 6** — `GET /api/v1/system/readiness` ganha o bloco `gpu`
  (`available`, `provider`, `model`, `vram`, `latency_ms`), com as mesmas
  chaves e uma `reason` legível quando indisponível. **Nunca 500** (toda saída
  é dicionário, inclusive a do `except` final) e **nunca gate de deploy** —
  GPU ausente é capacidade ausente; os três gates do 503 continuam sendo
  `database`, `migrations` e `storage`. A sonda usa deadline próprio de 5s e
  **uma** tentativa: três retries virariam 15s num endpoint morto, e quem
  consulta readiness já repete consultando de novo. O bloco `gpu` que
  reportava `nvidia-smi` desde a ETAPA 9 foi **composto, não substituído**:
  `backend`/`message` seguem onde a casca os lê e a sonda do cluster fica em
  `gpu.cluster`.
- **ETAPA 7** — `gpu_fakes.py` (mock integral da API RunPod: `/run`,
  `/status/{id}`, `/cancel/{id}`, `/health`, com um job passando de verdade
  por `IN_QUEUE → IN_PROGRESS → COMPLETED`, senão o polling nunca seria
  exercitado) + 197 testes em `test_gpu_client.py` (64),
  `test_runpod_flux.py` (54), `test_runpod_wan.py` (50) e
  `test_gpu_health.py` (29). Relógio falso: um deadline de 300s é testado em
  microssegundos. **Cobertura dos cinco módulos novos: 100%** (633 statements,
  0 misses), acima do piso de 98% da etapa.
- **ETAPA 8** — `docs/GPU_CLUSTER.md` novo; `ARCHITECTURE.md`, `docs/API.md`,
  `ROADMAP.md` e este arquivo atualizados. `docs/API_SNAPSHOT.json`
  regenerado e **idêntico**: nenhuma rota, modelo ou campo público mudou.

**Dois achados durante a implementação, os dois corrigidos:** a mensagem de
erro do transporte incluía o path do endpoint (e portanto o id do endpoint
serverless) num payload público, e a sonda de health herdava as 3 tentativas
do client, transformando um deadline de 5s em 15s contra um cluster morto.
Ambos foram encontrados por teste, não por leitura.

---

## [Unreleased] — PR010.0: PLATFORM FREEZE

Estabilização antes do AI Core. **Nenhuma feature nova, nenhuma alteração
visual, zero alteração funcional** — apenas contratos e guardas. O diff de
frontend é de zero linhas; o de `backend/app/` é um movimento de arquivos com
corpos byte a byte idênticos.

- **ETAPA 1** — `docs/ARCHITECTURE_MANIFEST.md`: declaração oficial dos dez
  módulos (AI Core *(future)*, Director AI, Storyboard Engine, Render Engine,
  Provider Registry, Campaign Builder, Quality Engine, Persona Engine,
  Database Guard, Network Layer) com **owner**, **responsabilidade**,
  **dependências permitidas** (allow-list completa, não exemplo) e
  **dependências proibidas** com o motivo de cada uma. O mapa de propriedade
  cobre 100% dos arquivos de `backend/app/`: um pacote novo sem dono declarado
  falha na CI, porque allow-list com buraco não é allow-list.
- **ETAPA 2** — `backend/tests/test_architecture_boundaries.py` (51 testes):
  lê o manifesto, constrói o grafo real de imports por AST e compara. As quatro
  proibições do PR — Director ⇏ Providers, Quality ⇏ Render, Providers ⇏
  Director, Campaign ⇏ Quality — são verificadas **direta e transitivamente**,
  então um módulo pass-through não contorna a regra; a mensagem de falha nomeia
  o caminho (`A -> B -> C`). O **AI Core** recebe a assimetria congelada antes
  de existir: pode importar todos, ninguém pode importá-lo. Quatro testes
  plantam violações (direta, transitiva, pacote sem dono, e a suíte inteira
  rodando em subprocesso contra uma cópia adulterada) e exigem vermelho — um
  guard que não sabe falhar não prova nada.
  **Medido: as quatro fronteiras já valiam.** Este PR não corrigiu acoplamento,
  ele travou o que já era verdade.
- **ETAPA 3** — `docs/API_SNAPSHOT.json` + `scripts/gen_api_snapshot.py`
  (16 testes): superfície pública gerada da aplicação — **111** rotas, **3**
  WebSockets, **137** modelos com tipo por campo e obrigatoriedade, e a
  exigência de auth por rota (**70** required / **3** optional / **38**
  public). Cobre o que `docs/API.md` estruturalmente não alcança: um campo que
  muda de tipo, um modelo que perde `output_url` ou uma rota que perde
  `Depends(current_user)` deixavam a prosa intacta. Mudança exige regenerar o
  arquivo, o que põe o diff na PR.
- **ETAPA 4** — `backend/app/contracts/`: o vocabulário compartilhado ganhou
  pacote próprio, dividido por domínio (`generation`, `prompt`, `persona`,
  `cinematic`, `direction`, `graph`). `app/core/contracts.py` permanece como
  **façade** re-exportando os **mesmos objetos** — identidade `is`, não
  igualdade, verificada por teste — porque vinte módulos e boa parte da suíte
  importam esse caminho e a regra permanente é não quebrar import existente
  (Bible §2). Os 26 contratos foram movidos byte a byte, e a assinatura de
  todas as dataclasses (campos, tipos, defaults, `frozen`) tem hash idêntico ao
  de antes do PR. Um teste por AST recusa qualquer redefinição de contrato fora
  do pacote.
- **ETAPA 5** — `docs/EVENT_CATALOG.md` (41 testes): registro dos **11**
  eventos reais (6 de ciclo de job, 5 de render) com payload, transporte e
  estados terminais, mais os **4** nomes reservados ao AI Core
  (`request_received`, `plan_created`, `quality_finished`, `asset_created`) —
  com teste que falha se alguém **emitir** um deles antes de o contrato
  existir. `render_finished` é registrado como nome de domínio de
  `batch_completed`, cujo nome de wire **não** mudou (o frontend já o consome).
  Honestidade medida: o catálogo declara que `queued` está declarado e **não
  tem emissor** hoje, e que o hub é in-process.
- **ETAPA 6** — CI: três jobs obrigatórios e independentes — **Architecture
  Guard**, **Import Boundary Guard** e **API Snapshot Guard** — rodando em
  paralelo ao `backend`. Separados de propósito: uma regressão arquitetural
  precisa aparecer como *"Architecture Guard failed"* na lista de checks, e não
  sumir dentro de uma suíte de 2.215 testes. Cada um escreve no
  `GITHUB_STEP_SUMMARY` o comando exato que conserta a falha.
- **Números** — suíte 2.107 → **2.215** testes (108 novos); cobertura
  `backend/app` mantida em **97%** (gate `--fail-under=95`); rotas, WebSockets
  e modelos inalterados.

---

## [Unreleased] — V3.4: QUALITY AI ENGINE

Um render entra, um veredito honesto 0–100 sai. **Provider Registry e
Director AI intocados** (pré-requisitos do sprint): o motor avalia outputs,
não escolhe providers nem planeja cenas — e **só recomenda**, nunca executa
retry, upscale ou aprovação automaticamente.

- **ETAPA 1** — domínio `backend/app/quality/` em cinco módulos com a mesma
  regra de camadas de `campaign/` e `continuity/`: `quality_score` (critérios,
  pesos, agregação ponderada, puro), `quality_rules` (bandas, findings,
  recomendações, puro), `quality_engine` (heurísticas `measured` + sinais
  `detector`, puro + Pillow), `quality_models` (a tabela) e
  `quality_repository` (única fronteira com o banco).
- **ETAPA 2** — score 0–100 sobre oito critérios (Face, Hands, Eyes,
  Composition, Lighting, Color, Motion, Prompt Fidelity), cada peso
  configurável por chamada ou por injeção; zero números mágicos — toda
  constante é nomeada. Motion é só-vídeo; imagem é julgada em 7 critérios.
  A regra de honestidade do `SYSTEM_PROMPT.md` vale para o score: cada número
  declara a origem (`measured` do arquivo/spec real, `detector` externo) e
  critério não medido é **excluído da média e listado**, nunca zerado.
- **ETAPA 3** — relatório persistente com `overall_score`, `issues[]`,
  `strengths[]`, `suggestions[]`, `retry_recommended`, `upscale_recommended`:
  linha append-only em `quality_reports` (migração `0006`) + documento
  completo junto ao Asset, gravados numa única transação.
- **ETAPA 4** — bandas de decisão: < 70 retry, 70–84 revisão manual, 85+
  aprovado, 95+ masterpiece; upscale recomendado só para render aprovado com
  lado curto < 1024px. Recomendação, nunca execução — a decisão do operador
  (`regenerate`/`upscale`/`approve`) é registrada no relatório com audit.
- **ETAPA 5** — UI `/studio/quality`: score radial SVG, radar chart sobre os
  critérios medidos, problemas/sugestões e os botões Regenerar, Upscale e
  Aprovar (que registram e dizem na tela que nada foi disparado).
- **ETAPA 6** — Asset Library: `assets.quality_score`, `quality_status`,
  `quality_report`, `quality_version` desnormalizados (NULL = nunca avaliado),
  expostos em `GET /api/v1/assets` e no badge da lista.
- **ETAPA 7** — 121 testes novos (score, rules, engine/report, decision,
  persistence, API ponta a ponta) com o pacote `backend/app/quality/` em
  **100% de cobertura** (piso do sprint: 98%). Suíte total: 2.076.
- **ETAPA 8** — `docs/QUALITY_ENGINE.md`, `docs/API.md` regenerado (111
  rotas), `ARCHITECTURE.md`, `ROADMAP.md`, `docs/ETAPAS.md` e
  `docs/LIMITATIONS.md` atualizados e verificados por
  `test_docs_accuracy.py`.

---

## [Unreleased] — V3.2.1: NETWORK RELIABILITY LAYER

A correção proposta no PR009.2, agora implementada. **Nenhuma funcionalidade
nova, nenhum provider alterado** — apenas robustez; Provider Registry, Render
Engine e Director AI intocados.

- **ETAPA 1/2** — `lib/network/request.ts` é a única fronteira de `fetch` do
  frontend: timeout (`AbortSignal.timeout` 10s/30s), merge de abort do
  chamador (`AbortSignal.any`), enum `NetworkErrorType`
  (ONLINE/TIMEOUT/OFFLINE/CORS/UNAUTHORIZED/SERVER_ERROR/UNKNOWN) e
  `NetworkError` tipado — `lib/api.ts` delega (`runRequest`) e não existe mais
  nenhum `catch` retornando o literal `'offline'` (as comparações
  `error === 'offline'` da UI viraram `isUnreachable`/`failureMessage` sobre
  `ApiResult.errorType`).
- **ETAPA 3** — retry policy das sondas de status (`health`, `readiness`,
  `gpuInfo`): somente GET, 3 tentativas, backoff exponencial 300/600/1200ms.
- **ETAPA 4** — cold start detection: timeout com duração entre 8s e 60s vira
  "Servidor iniciando — o primeiro acesso pode demorar alguns segundos.",
  nunca "API Offline" (free tier do Render).
- **ETAPA 5** — `StatusCenter` (`app/components/StatusCenter.tsx`) montado no
  shell: um estado honesto com cor e ação — Online, Inicializando (sonda a
  cada 3s enquanto o servidor acorda), Sem internet (retry), Sessão expirada,
  Erro interno.
- **ETAPA 6** — trace id `x-brobond-trace` em toda requisição (mesmo id em
  todas as tentativas de retry), log `[brobond:network]` com URL sem query
  string (sem PII), método, latência e desfecho; `ApiResult.traceId`.
- **ETAPA 7** — todos os `app/studio/*/page.tsx` e `app/page.tsx` ramificam
  por `errorType`; `describeError` dos painéis recebe o resultado tipado.
- **ETAPA 8** — `lib/network/request.test.ts` + `lib/network/status.test.ts`
  (DNS, CORS, Timeout, cold start, 500 com retry, 401 sem retry, agenda de
  backoff exata, trace id, log, `readError`); `lib/api.network.test.ts`
  reescrito para o contrato tipado (19 testes); cobertura de `lib/network/**`
  com piso **98%** no `vitest.config.ts` (hoje ~99.5/99/100/99.5, suíte
  inteira: 124 testes).
- **Guardas** — `test_fetch_lives_only_in_the_network_layer` (honesty):
  `fetch(` só em `lib/network/request.ts`; contagens de teste sincronizadas
  (1.955 backend / 124 frontend).
- **Docs** — `docs/NETWORK_LAYER.md` novo; ARCHITECTURE.md, docs/API.md
  (contagem de rotas inalterada: 106 + 3 WS) e este CHANGELOG atualizados.

---

## [Unreleased] — PR009.2: FRONTEND NETWORK RECONCILIATION

Diagnóstico reproduzível do "API Offline" com a API respondendo 200.
**Nenhuma feature, nenhum provider, nenhuma arquitetura alterados** — a
correção fica proposta no relatório, não aplicada.

- **Auditoria** — o literal `'offline'` nasce em exatamente dois `catch` de
  `lib/api.ts` (linhas 84 e 179) e engole três classes distintas: rede real
  (`TypeError`), CORS bloqueado (`TypeError: Failed to fetch` — a API
  respondeu 200 e o browser esconde) e timeout (`TimeoutError`/`AbortError`
  do `AbortSignal.timeout(10000)` — API viva, cold start do free tier).
  Base de URL: `API_URL = NEXT_PUBLIC_API_URL ?? ''` verbatim, sem
  transformação — **MATCH** absoluto com o `render.yaml`
  (`https://brobond-ai-api.onrender.com`).
- **Trace real** — `scripts/network_trace.mjs` mede as chamadas da UI contra
  o proxy same-origin (health/readiness/gpu **200**), a API direta
  (preflight CORS **400** para origem fora da allow-list local = o mecanismo
  do falso offline, **200 + echo** para origem permitida) e as URLs de
  produção (egress do sandbox bloqueado — registrado como inconclusivo).
  Resultado em `docs/NETWORK_TRACE.md`.
- **Testes e2e** — `lib/api.network.test.ts` (17 testes, vitest): API online,
  500, 401, 502, 204, DNS inválido, conexão recusada, CORS e timeout, mais a
  construção exata da URL base e as rotas de status da Home — "offline" só
  em rede real, mais as duas conflações documentadas.
- **Relatório** — `docs/NETWORK_RECONCILIATION_REPORT.md` com o bloco
  MATCH/MISMATCH, primeira chamada da Home, rota que falha, stack real dos
  erros e a correção proposta (distinguir timeout, orçamento maior para as
  rotas de status, proxy same-origin no Render).

---

## [Unreleased] — PR009.1: HEALTH CHECK RECONCILIATION

Hotfix de reconciliação entre as rotas de health do FastAPI e o
`healthCheckPath` do Render Blueprint. **Nenhuma funcionalidade nova**;
`render.yaml` e o prefixo global `/api/v1` permanecem intactos — a medição
encontrou as duas partes já reconciliadas, e o estado passou a ser fixado
por testes para não divergirem de novo.

- **Verificação** — `GET /api/v1/health` e `GET /health` (mesmo handler,
  decoradores empilhados) respondem **200** sem exigir token; o probe do
  Render passa sem credenciais. `healthCheckPath` do blueprint
  (`brobond-ai-api` → `/api/v1/health`, `brobond-studio-web` → `/`) casa
  com rotas reais que retornam 200; Swagger (`/docs`), ReDoc (`/redoc`) e
  `/openapi.json` em 200.
- **Teste novo** — `backend/tests/test_health_reconciliation.py` (8
  testes): 200 nas duas rotas, corpo documentado, sem dependência de
  identidade, prefixo `/api/v1` preservado e **cada `healthCheckPath` do
  `render.yaml` resolvido contra as rotas servidas pela aplicação** —
  qualquer divergência futura falha no CI.
- **Relatório** — `docs/API_HEALTH_REPORT.md` gerado da aplicação em
  execução, com o inventário completo (método, path, tags), status codes
  medidos e o caminho do Swagger.

---

## [Unreleased] — V3.3: CAMPAIGN BUILDER

V3.3 transforma um único briefing em uma campanha completa: sete entregáveis,
timeline de cinco dias, deck de CTAs que nunca repete e ZIP de exportação.
O Director AI, o Provider Registry e o Render Engine não foram alterados — o
builder planeja, agenda e empacota; um ativo só vira `delivered` quando um
arquivo real é anexado a ele.

### O que mudou

- **Pacote `backend/app/campaign/`** — `brief_interpreter.py` (leitura
  determinística PT/EN do briefing: produto, público, plataforma, duração,
  objetivo — com lista honesta de `missing` para todo default), `cta_engine.py`
  (deck de 28 templates embaralhado por seed de campanha; sortear nunca repete,
  por construção), `timeline_builder.py` (catálogo dos 7 entregáveis + plano
  Dia 1..Dia 5 com foco/ativos diferentes por dia + composição de prompt por
  formato), `export_center.py` (manifesto + prompt + metadata + binários
  entregues em um ZIP determinístico com sha256) e `campaign_service.py`
  (orquestra tudo e expande os prompts pelo `PromptEnhancer` existente).
- **Migração Alembic `0005`** — tabelas `campaigns`, `campaign_briefs`,
  `campaign_episodes`, `campaign_assets` e `campaign_exports`, idempotente.
- **Rotas** — sete endpoints `/api/v1/campaigns/*` com identidade
  (interpret, create, list, detail, duplicate, deliver, export), 404 para id
  estrangeiro, 422 para briefing vazio e entrega inválida, audit em cada
  mutação; o ZIP é servido pela rota autenticada `/assets/download/{key}`.
- **UI `/studio/campaigns`** — BriefPanel (interpretar + criar),
  CampaignCalendar (Dia 1..Dia 5 com ativos e CTAs), CampaignAssets (sete
  entregáveis com prompt, CTA e anexar entrega real), ExportPanel (exportar
  ZIP, baixar, duplicar campanha); erros distinguem offline, anônimo e
  rejeição.
- **Testes** — 138 testes novos (`test_campaign_*.py`, 7 arquivos); pacote
  `backend/app/campaign/` em **100%** de cobertura.

### Invariantes

- Nunca repetir CTA dentro da campanha (o deck valida unicidade; duplicar
  cunha seed nova e re-armar o deck).
- Cada dia da timeline roda um conjunto **diferente** de ativos.
- Nada é inventado: export sem arquivo entregue sai só com texto; entrega
  exige chave do próprio workspace existente no storage.

---

## [V3.2] — CHARACTER CONTINUITY ENGINE

V3.2 congela o que cada personagem é, veste, onde está, o que dirige e como
soa — por campanha, com override por episódio, fingerprint visual e
histórico imutável de episódios. O Director, o Provider Registry e o Render
Engine não foram alterados — o resolver devolve um `ContinuityContext` e
nunca reescreve o `GenerationSpec`.

### O que mudou

- **Pacote `backend/app/continuity/`** — `identity_lock.py` (6 campos
  congelados + kernel do pacote: erro único, fingerprint canônico,
  normalização de chaves), `wardrobe_lock.py` (roupa + acessórios/cores/
  sapatos/relógio, troca por episódio), `location_lock.py` (showroom/
  estúdio/rua + cidade/iluminação base), `vehicle_lock.py` (veículo/cor +
  placa opcional/rodas/acabamento), `voice_lock.py` (perfil/emoção/
  velocidade/intensidade) e `continuity_resolver.py`
  (`resolve(persona_id, campaign_id, episode)` → `ContinuityContext` com
  snapshots, frases, fingerprints, missing, drift e consistent).
- **Migração Alembic `0004`** — tabelas `continuity_locks` (upsert com
  `version`, episódio 0 = padrão da campanha) e `continuity_episodes`
  (snapshot congelado do resolver), idempotente.
- **Rotas** — treze endpoints `/api/v1/continuity/*` com identidade (PUT+GET
  por lock com `source_episode`, `GET /resolve`, `POST`/`GET /episodes` com
  auto-numeração), 404 para id estrangeiro ou lock ausente, 409 em episódio
  duplicado, audit em cada mutação.
- **UI `/studio/continuity`** — escopo persona/campanha/episódio, cinco cards
  de lock (ver/editar/fingerprint/versão/origem), painel do contexto
  resolvido e histórico com **Criar novo episódio**; erros distinguem
  offline, anônimo e rejeição.
- **Testes** — 200 testes novos (`test_continuity_*.py`, 4 arquivos); pacote
  `backend/app/continuity/` em 100% de cobertura.

Documentação nova: `docs/CHARACTER_CONTINUITY.md`.

---

## [Unreleased] — V3.1: CINEMATIC KNOWLEDGE GRAPH

V3.1 conecta personagens, marcas, campanhas, lugares, veículos, figurino e
objetos num grafo persistente por workspace, com busca semântica PT/EN e
contexto de personagem para o Director AI. O Director, o Provider Registry e
o Render Engine não foram alterados — o grafo enriquece, nunca reescreve, o
`GenerationSpec`.

### O que mudou

- **Pacote `backend/app/graph/`** — `graph_models.py` (2 tabelas, 7 tipos de
  entidade), `relationship_engine.py` (16 relações canônicas + aliases PT,
  travessia BFS bidirecional, frases em voz ativa), `semantic_query.py`
  (8 tiers determinísticos 100–30, sem embeddings) e `graph_repository.py`
  (CRUD com escopo de workspace, seed idempotente).
- **Migração Alembic `0003`** — tabelas `graph_nodes`/`graph_edges`, idempotente.
- **Contratos** — `GraphContext`/`GraphContextSource` em `core/contracts.py`;
  `MemoryResolver.context_phrases()` (injeção opcional; sem source, vazio).
- **Rotas** — doze endpoints `/api/v1/graph/*` com identidade (CRUD de
  nós/arestas, busca, vizinhança 1–3 saltos, contexto de personagem, seed),
  404 para id estrangeiro, audit em cada mutação.
- **UI `/studio/knowledge`** — canvas SVG radial determinístico, busca, filtros
  por tipo, detalhe com vizinhança e contexto do Director AI.
- **Testes** — 201 testes novos (`test_graph_*.py`, 5 arquivos); pacote
  `backend/app/graph/` em 100% executável; frontend `lib/graph/layout.ts`
  em 100% (vitest, gate de 95%).

Documentação nova: `docs/KNOWLEDGE_GRAPH.md`.

---

## [Unreleased] — PR009: REAL AI CONNECTORS

PR009 liga os adapters de provider a motores reais (Flux para imagem, Wan 2.1 para
vídeo) e envolve o `GenerationExecutor` com retry, timeout, fallback e telemetria.
O Registry, o Director, o Storyboard e o Render Engine não foram alterados — a
resiliência vive inteira em `backend/app/providers/`.

### O que mudou

- **Conector Flux real** — `providers/flux_provider.py`: text-to-image e
  image-to-image (exige `spec.reference_path`), seed, negative, steps, LoRA e
  aspect-ratio; pipeline por modo com cache e CPU offload; recebe apenas
  `GenerationSpec`.
- **Conector Wan real** — `providers/wan_provider.py`: text-to-video e
  image-to-video, duration, fps, motion_strength e seed; frames em `4n+1`; encode
  `imageio/libx264`; capabilities declaram o que é consumido e o que é ignorado.
- **Retry** — `providers/retry_policy.py`: estados `RETRYABLE`/`TIMEOUT`/`FATAL`,
  backoff exponencial com cap, **máximo de 3 tentativas** e hook de decisão.
- **Timeout** — `providers/timeout_manager.py`: deadline por provider (Flux 90s,
  Wan/Hunyuan 300s, default 120s), configurável por ENV
  (`PROVIDER_TIMEOUT_*_SECONDS`); estouro vira `ProviderTimeoutError` retryável.
- **Fallback** — provider indisponível ou kind errado cai para o próximo provider
  do Registry (Mock incluído) com motivo registrado no Job
  (`fallback`/`fallback_from`/`fallback_reason`); erro fatal propaga sem fallback;
  o Batch nunca se perde (teste força 6 falhas e o batch fecha `completed`).
- **Telemetria** — `providers/telemetry.py`: `provider_id`, `latency_ms`,
  `queue_time_ms`, `render_time_ms`, `success`, `error_code` (+ attempts/fallback),
  store thread-safe de 500 registros com sink JSONL opcional.
- **Rotas** — `POST /api/v1/providers/{provider_id}/test` (teste real determinístico)
  e `GET /api/v1/providers/telemetry` (histórico mais-novo-primeiro).
- **UI `/studio/providers`** — Disponibilidade, Último Health e botão **Teste Real**
  com resultado honesto (sucesso / fallback com motivo / falha).
- **Testes** — `backend/tests/test_pr009_ai_connectors.py` (81 testes); pacote
  `backend/app/providers/` a 100% de cobertura.

Documentação nova: `docs/AI_CONNECTORS.md`.

---

## [Unreleased] — PR008: CINEMATIC RENDER ENGINE

PR008 conecta o Director AI ao Generation Executor e ativa a renderização: storyboards
produzem imagens e vídeos reais. O pacote `backend/app/render/` orquestra
`ProductionPlan → Scene → GenerationSpec → Executor → Assets → Jobs` sem chamar nenhum
Provider diretamente — a única dependência voltada a providers é o `GenerationExecutor`.

### O que mudou

- **Render Orchestrator** — `render_orchestrator.py` cria lotes de `ProductionPlan`
  (PR005) ou `StoryboardState` (PR006) e executa cena a cena, com cancelamento
  cooperativo e retry só das falhas; seeds determinísticas (`base + índice`).
- **Scene Renderer** — `scene_renderer.py` compila cada cena em um `GenerationSpec`
  pelo `PromptCompiler` existente, com persona, style, mood, camera, lens, lighting,
  motion, seed, aspect_ratio e duration obrigatórios.
- **Batch Rendering** — `RenderBatch` com estados `queued/running/rendering/completed/
  failed/cancelled` e progresso independente por cena.
- **Progress Engine** — WebSocket `/ws/render/{batch_id}` com os cinco eventos
  (`batch_started`, `scene_started`, `scene_progress`, `scene_completed`,
  `batch_completed`) por push thread-safe, sem polling.
- **Asset Pipeline** — `asset_pipeline.py` salva PNG/MP4, thumbnail e metadados JSON
  (prompt, seed, provider) pelo `StorageService`, com linhas `Asset` na biblioteca.
- **API e UI** — seis rotas `/api/v1/render/*` com identidade e a tela `/studio/render`
  com storyboard, progresso, cena atual, ETA, preview, download e Fila com Cancelar
  e Repetir.
- **Testes** — `backend/tests/test_pr008_render_engine.py` cobre batch, renderer,
  executor, WebSocket, assets e frontend; pacote `backend/app/render` em 100%.

Documentação nova: `docs/RENDER_ENGINE.md`.

---

## [Unreleased] — PR007: GPU PROVIDER ORCHESTRATOR

PR007 cria a camada universal de Providers. O Core agora trata `provider` como identificador
opaco e não conhece Flux, Wan, Hunyuan, Kling ou Runway; ele apenas produz `GenerationSpec`.
A comunicação com GPU/providers passa por `BaseProvider`, `ProviderRegistry` e
`GenerationExecutor`.

### O que mudou

- **Contrato universal** — `backend/app/providers/base_provider.py` define
  `ProviderCapabilities`, `ProviderEstimate`, `ProviderHealth`, `ProviderAsset` e os métodos
  abstratos `generate_image`, `generate_video`, `upscale`, `health` e `estimate`.
- **Registry sem branches por modelo** — `provider_registry.py` registra Flux, Wan, Mock e
  Hunyuan por factories/aliases e implementa `register()`, `get()`, `list()` e
  `health_all()`.
- **Executor provider-agnóstico** — `generation_executor.py` executa
  `GenerationSpec -> Registry -> Provider -> Asset -> Job` sem conhecer IDs de provider.
- **Adapters universais** — `flux_provider.py` e `wan_provider.py` recebem somente
  `GenerationSpec`; Wan/Hunyuan compartilham wrapper de vídeo para evitar lógica duplicada.
- **Mock obrigatório** — `mock_provider.py` retorna imagem, vídeo e upscale falsos para testes
  e desenvolvimento sem GPU.
- **Capabilities na borda** — budgets e capacidades (`max_resolution`, vídeo, imagem, LoRA,
  upscale, seed e negative prompt) vivem nos providers; o Core aceita apenas budget numérico
  já resolvido.
- **API e UI** — `GET /api/v1/providers` retorna status, latência, versão e capabilities sem
  segredos; `/studio/providers` mostra Flux, Wan e Mock com botão **Testar**.
- **Testes** — `backend/tests/test_pr007_provider_orchestrator.py` cobre contract, registry,
  Mock, Flux, Wan, executor, health endpoint, Core decoupling e UI/client.

Documentação nova: `docs/PROVIDERS.md`.

---

## [Unreleased] — PR006: STORYBOARD CINEMATIC ENGINE

O storyboard do Director AI agora é um editor cinematográfico visual e versionado.
O PR é estritamente de edição do plano: nenhum provider FLUX/Wan foi alterado, nenhum job de
geração é criado e nenhuma imagem é renderizada.

### O que mudou

- **Entidade versionada** — `StoryboardState` com `project_id`, `production_plan_id`,
  `scenes[]`, `version` e `updated_at`; toda alteração real incrementa versão e recalcula a
  timeline.
- **Cena editável** — `StoryboardScene` permite patch granular de título, objetivo, emoção,
  câmera, lente, iluminação, movimento, duração e ambiente sem recriar a cena inteira.
- **Drag & Drop** — `StoryboardCanvas` permite mover cenas; o estado recalcula `scene_number`,
  `timeline_start`, `timeline_end` e duração total.
- **Camera Panel** — presets `Hero Walk`, `Orbit`, `Tracking`, `Crane`, `Drone`, `Static`
  atualizam apenas o bloco CameraDirector (`camera`, `lens`, `lighting`, `motion`).
- **Mood Panel** — cada cena pode usar `Luxury`, `Epic`, `Dark`, `Minimal`, `Sport` ou `Neo`;
  a operação altera somente `mood` e `lut` no plano editável.
- **Timeline** — faixa horizontal com `C1`, `C2`, `C3`, `C4` proporcionais à duração; sliders
  permitem arrastar duração e recalcular o total.
- **Undo/Redo** — `StoryboardHistory` guarda até 50 estados para editar, reordenar, duplicar e
  remover.
- **Duplicate Scene** — botão duplica a cena com novo UUID, mantendo câmera e mood.
- **Frontend desacoplado** — `/studio/director` foi dividido em `StoryboardCanvas`, `Timeline`,
  `SceneInspector`, `CameraPanel` e `MoodPanel`.
- **Testes** — `backend/tests/test_pr006_storyboard_engine.py` cobre a entidade/histórico e
  `lib/storyboard/storyboard_state.test.ts` cobre timeline, drag, undo, redo, duplicate,
  version e scene update. O build e o gate de cobertura de 95% permanecem verdes.

Documentação nova: `docs/STORYBOARD_ENGINE.md`.

---

## [Unreleased] — PR005: DIRECTOR AI ENGINE

O Director AI agora produz um `ProductionPlan` cinematográfico completo a partir de
linguagem humana. O PR é estritamente de planejamento: nenhum provider FLUX/Wan foi
alterado, nenhum job de geração é criado e nenhuma imagem é renderizada.

### O que mudou

- **Core novo** — pacote `backend/app/core/director/` com `director_agent.py`,
  `production_plan.py`, `shot_plan.py`, `mood_engine.py`, `camera_director.py`,
  `mood_config.py` e `__init__.py`.
- **Contratos imutáveis** — `ProductionPlan` e `ShotPlan` são dataclasses congeladas;
  `ShotPlan` exige objetivo, emoção, câmera, lente, iluminação, movimento, duração,
  prompt, negative prompt e ambiente.
- **Mood Engine** — presets internos `Luxury`, `Epic`, `Dark`, `Minimal`, `Sport`,
  `Neo`, configurados fora da lógica com LUT, contraste, iluminação, temperatura,
  ritmo e partículas.
- **Camera Director** — consome a `ShotLibrary` existente para selecionar Dolly, Orbit,
  Crane, Tracking, Static ou Drone como primeira proposta editável.
- **Director Agent** — `create_production_plan(user_intent, persona_id, platform,
  duration, *, mood=None)` executa o fluxo Intent → Mood → Style → Shot Sequence →
  Storyboard → Prompt Compiler → ProductionPlan, gerando 4–8 cenas narrativas sem
  dividir texto igualmente.
- **API** — `POST /api/v1/core/director/production-plan` retorna o plano, sem `job_id`
  e sem `output_url`.
- **Frontend** — página `/studio/director` com campo grande “O que você quer criar
  hoje?”, Persona, Plataforma, Duração, Mood e botão “Criar Produção”; os cards do
  storyboard mostram e permitem editar Cena, Objetivo, Câmera, Lente, Duração e Emoção.
- **Testes** — `backend/tests/test_pr005_director_ai.py` cobre `DirectorAgent`,
  `MoodEngine`, `CameraDirector`, `ProductionPlan`, `ShotPlan`, storyboard, rota e UI.
  O gate backend do CI foi elevado para `coverage report --fail-under=95` e a execução local
  mede 96% em `backend/app`.

---

## [Unreleased] — PR004.1: PROJECT MEMORY CONTRACT

Micro PR de padronização: o contrato de Project Memory foi congelado e toda
a persistência de memória de projeto agora passa por **um único Memory
Adapter**. Nenhuma alteração visual.

### O que mudou

- **Contrato oficial** — `ProjectMemoryState` em `lib/memory/project_memory.ts`:
  `projectId` (único obrigatório), `workspaceId`, `personaId`, `wardrobeId`,
  `styleId`, `loraId`, `cameraPreset`, `aspectRatio`, `lastPrompt`,
  `lastPlatform`, `duration`, `updatedAt`. O formato é idêntico no
  `localStorage` de hoje e no PostgreSQL de amanhã; **só muda com
  migration** (envelope versionado `v`; versão desconhecida → recusa a
  leitura, sem perda silenciosa; shape v0 do PR004 migra automaticamente,
  write-through).
- **Memory Adapter** — `lib/memory/project_memory.ts`:
  `loadProjectMemory(projectId)` / `saveProjectMemory(state)` /
  `clearProjectMemory(projectId)`. Sem acoplamento a React. Uma única
  chave oficial (`PROJECT_MEMORY_KEY`); desserialização sanitizada (campos
  desconhecidos descartados, tipos errados ignorados); SSR/bloqueio de
  storage degradam para `null`, nunca lançam.
- **Hook** — `useProjectMemory(projectId)` (`lib/memory/use_project_memory.ts`)
  retorna `{ memory, save, clear }` e somente consome o adapter; `save` é
  atualização parcial (merge + `updatedAt`).
- **Frontend** — nenhum componente conhece a chave de armazenamento nem toca
  `localStorage`: `app/page.tsx` consome o hook; o token de auth (PR002) e a
  chave legacy `brobond_persona_id` (Persona Lab) passam pelo adapter como
  seams nominais (`getAuthToken`/`setAuthToken`/`clearAuthToken`,
  `setLegacyPersonaId`) — contratos separados, fora do
  `ProjectMemoryState`. `cameraPreset`/`aspectRatio`/`duration` agora são
  owned pelo Home (mesmos controles, mesmos defaults — zero mudança visual)
  para que o contrato possa persisti-los.
- **Legacy** — `lib/projectMemory.ts` (v0) marcado Legacy (Bible §2): sem
  call sites live, delega ao adapter, não toca storage.
- **Testes** — suíte comportamental nova (vitest, escopado a `lib/memory/`):
  persistência, serialização, desserialização, atualização parcial, clear,
  compatibilidade de versão, seams SSR/bloqueadas e hook — com **gate de
  cobertura 95%** no CI. Guards estruturais em
  `backend/tests/test_project_memory_contract.py` (nenhum componente toca
  `localStorage`; um único arquivo referencia `window.localStorage`; uma
  chave oficial; contrato = exatamente os campos da spec; hook consome
  apenas o adapter; CI roda a suíte).
- **Docs** — `docs/PROJECT_MEMORY.md` (contrato, adapter, hook, migração
  PostgreSQL); seções novas em `ARCHITECTURE.md`.

### Decisões

- O repo não tinha runner de JS; o vitest foi adicionado **escopado ao
  contrato** (devDeps + step no CI) — o restante do frontend continua
  coberto por guards estruturais no backend.
- `wardrobeId`/`styleId` carregam hoje nomes/join (o produto ainda não tem
  id por item de wardrobe nem catálogo de estilos versionado); quando o
  backend introduzir ids reais, a migration é de *valor*, não de *shape*.

---

## [Unreleased] — PR004: STUDIO PERSONA PIPELINE

O Persona Engine (PR003) agora atravessa o produto: o usuário escolhe a
Persona no Image Studio e no Video Studio, o compiler resolve identidade,
estilo, LoRA, wardrobe e referência automaticamente, e o projeto restaura
tudo ao reabrir. **Nenhuma alteração estrutural no banco** — apenas
entidades existentes; o contrato `GenerationSpec` ficou intacto e nenhuma
API mudou de comportamento.

### Novos componentes (frontend)

- **`app/components/studio/PersonaSelector.tsx`** (ETAPA 1): seletor
  reutilizável dos dois estúdios — lista as personas do workspace, busca por
  nome, avatar (face primeiro), default style, indicador de LoRA treinado e
  seleção. Componente puro: os dados chegam por prop (degradado honesto
  quando o workspace ainda não tem personas).
- **`app/components/studio/PersonaPreview.tsx`** (ETAPA 2): cartão de
  identidade em tempo real — imagem principal, nome, barba, cabelo, voz,
  estilo padrão, LoRA e roupas cadastradas; o wardrobe é selecionável (os
  nomes viajam no request `wardrobe` e no Project Memory).
- **`lib/projectMemory.ts`** (ETAPA 6): persistência do projeto —
  `persona_id`, `default_style`, `last_lora`, `selected_wardrobe` — em
  `localStorage` (o banco não tem coluna de estado de projeto e o PR proíbe
  alterar o schema; o formato espelha os nomes dos campos do backend, então
  uma entidade server-side futura adota o payload 1:1).

### Studio (ETAPAS 4/5/7)

- **Image Studio**: painel Identity (PersonaSelector + preview), campo
  Style com o atalho **“Usar estilo da Persona”**, e o payload do job ganha
  `persona_id` + `style` + `wardrobe` (os controles explícitos continuam
  vencendo — precedência inalterada).
- **Video Studio**: o mesmo painel + **câmera** (`camera_motion`:
  static/pan/tilt/zoom/tracking/crane) e duração (já existia, 5/10/15s) —
  o usuário escolhe a Persona; o resto o compiler decide.
- **Topbar**: a persona ativa vira a **identidade no topo da tela**
  (avatar + nome + estilo), visível em qualquer módulo.
- **Sidebar**: novo grupo **STUDIO** (Personas / Image / Video / Projects)
  com estado selecionado; WORKSPACE e LIBRARY preservados.
- A busca legacy `brobond_persona_id` nos estúdios foi **superada** pela
  fonte nova (Project Memory); o campo continua sendo escrito pelo Persona
  Lab, que não mudou.

### Backend (ETAPA 3 — compiler resolve tudo)

- `POST /core/compile` (e o worker, pelo `spec_adapter`) aceitam
  `persona_id` + `wardrobe` **opcional**: o compiler resolve identidade,
  `default_style`, LoRA, wardrobe e referências do perfil persistente.
  `wardrobe` só **estreita** o bloco (itens selecionados pelo projeto);
  `GenerationSpec` não ganhou nenhum campo.
- `memory_resolver.identity_phrase(persona, wardrobe=None)`: o bloco PERSONA
  do prompt agora inclui `wardrobe: …` quando a persona tem roupas.
- `persona_repo.to_memory` passa a mapear o wardrobe (antes fixo em `""`).
- **Referência automática**: sem referência explícita, o worker resolve a
  imagem da própria persona (`_persona_reference_object_key`): face primeiro,
  depois ordem de exibição; asset precisa ser `image` **do workspace do
  job** (mesma regra de posse das referências explícitas); sem nada
  adequado o job segue sem referência — falha de identidade nunca derruba
  a geração.
- `PersonaRepository.wardrobe` agora ordena por **nome** (a ordenação por
  `id`/uuid4 era não-determinística entre backends e restarts).

### Testes (ETAPA 8)

- **23 testes novos** em `backend/tests/test_studio_persona_pipeline.py`:
  unidade do bloco de identidade + filtro de wardrobe; compile end-to-end
  com persona/wardrobe/estilo via `/core/compile`; schemas aceitando os
  campos do pipeline; worker auto-referência (face primeiro, fallback por
  ordem, posse de workspace, não-imagem) e guarda estrutural do wiring;
  guards estruturais do frontend (seletor reutilizável, preview, payloads
  com `persona_id`, câmera/duração no vídeo, Project Memory com os 4
  campos, grupo STUDIO na sidebar e identidade na topbar).
- Guarda `test_storage` atualizada para os **três** call sites de
  `storage.download` (LoRA, referência explícita e referência da persona).
- Suíte: **1.188 testes** (1.187 passed + 1 skipped); cobertura total
  **95%** (gate CI: 90%).

### Honestidade (o que não há neste PR)

- Sem browser no ambiente de build: **sem screenshots/GIFs** do Studio
  gerados aqui (documentado em `docs/LIMITATIONS.md`); a regressão visual é
  garantida pelo build + pelos guards estruturais.
- Project Memory em `localStorage` por decisão de escopo (sem coluna de
  estado de projeto no schema — ver `docs/PERSONA_ENGINE.md`).

---

## [Unreleased] — PR004-prep: ARQUITETURA DE JOBS — REPOSITORY PATTERN

O fluxo de jobs foi desacoplado do PostgreSQL por injeção de dependência,
sem alterar nenhuma API, nenhum comportamento externo e sem apagar
nenhum arquivo (Bible §2/§3). O Core ganha o 13º componente.

### Arquitetura (camadas em dependência)

- **`backend/app/core/job_service.py`** (novo, 13º componente): `JobService`
  — máquina de estados do job (`queued → running → complete/failed/cancelled`;
  terminais imutáveis; tick de progresso sempre permitido), validação de
  status e o value object `Job` puro (zero framework, zero SQLAlchemy; a
  interface é conhecida só por hint de tipo, sem import em runtime).
- **`backend/app/repositories/job_repository.py`** (novo): a interface
  `JobRepository` — exatamente as seis operações: `create`, `get`, `update`,
  `transition`, `list_by_workspace`, `delete`.
- **`backend/app/repositories/postgres_job_repository.py`** (novo,
  **default**): `JobRow`/tabela `jobs` (Alembic `0001`, inalterada). Único
  módulo de job com SQLAlchemy (guarda AST).
- **`backend/app/repositories/redis_job_repository.py`** (novo, opt-in):
  JSON em hashes `brobond:job:{id}` + set por workspace; conexão lazy.
- **`backend/app/repositories/memory_job_repository.py`** (novo, testes):
  dict isolado, thread-safe, sem I/O.
- **`backend/app/models/`** (agora pacote): `JobRow` vive em `models/job.py`
  (git registra como rename; `app.models` re-exporta — nenhum call site
  mudou).
- **`backend/app/jobs.py`** (novo): mapeamento `Job` (API/Pydantic) ↔ `Job`
  (Core) — único ponto onde os dois vocabulários se encontram.
- **`backend/app/job_service.py`** (novo): composition root do serviço —
  `job_service = JobService(PostgresJobRepository())`; trocar de backend é
  uma linha aqui.

### Compatibilidade (comportamento externo idêntico)

- Rotas, worker e eventos inalterados; `transition()` continua sendo o único
  ponto onde o job anda (persiste via `JobService` **e** emite).
- `app/store.py`: `JobStore`/`Store` permanecem, agora **delegando** ao
  `JobService` — zero import de SQLAlchemy no módulo (guarda AST); `queue.store`
  segue acessível para call sites e testes históricos.
- `queue.list_jobs` sem workspace: antes caía numa query sem escopo; agora
  lista vazio (a edge case de usuário sem workspace era vetor de enumeração
  cross-tenant — endurecimento intencional, documentado).
- Novos testes: `test_job_repository.py` (20) — interface nos 3 providers,
  mesmo ciclo de vida em Postgres/Redis/memória, máquina de estados idêntica,
  guards de pureza DI (Core não importa provider; store sem SQLAlchemy;
  Postgres é o único job módulo com SQLAlchemy) e facade legado funcional.

---

## [Unreleased] — PR003: PERSONA MEMORY ENGINE

As personas deixam a memória do processo e ganham persistência em PostgreSQL
(Bible §2: nada recriado, nada deletado, Core sem SQL). A arquitetura é
preservada: o `Core` continua dependendo só de protocolos, e a nova camada de
persistência fica entre as rotas e o banco.

### Persistência (Alembic `0002`)

- **4 novas tabelas** na migration idempotente `0002_persona_engine`
  (`downgrade` é no-op documentado — a Bible proíbe drop de tabelas
  históricas): `personas` (perfil + `uq_personas_workspace_slug`),
  `persona_images` (referências a assets existentes), `persona_wardrobe`
  (metadata JSON) e `persona_identity_revision` (histórico append-only).
- **`backend/app/repositories/persona_repository.py`** (pacote novo, camada
  app): `create` / `update` / `delete` / `find_by_id` / `find_by_slug` /
  `list_workspace` + helpers de imagens/wardrobe/revisões. É o único lugar
  que fala com os models SQLAlchemy; as rotas e o `MemoryResolver` dependem
  dele. Sessões curtas por chamada, mesma convenção do `JobStore` (PR002).
- **`knowledge_entries`** já existia na baseline `0001` (guard
  idempotente), então o 0002 só cria as tabelas de persona.

### Core evoluído (12 → continua 12 componentes, novos contratos)

- `contracts.py`: `WardrobeItem`, `ReferenceImage`, `PersonaProfile` e o
  protocolo opcional `PersonaProfileSource` — o `PersonaSource` original
  (`fetch`/`search`) **não mudou**, todos os implementadores existentes
  seguem válidos.
- `MemoryResolver.resolve_persona(persona_id)`: devolve o perfil completo
  (identidade + wardrobe + LoRA + imagens de referência), preferindo a fonte
  persistente e derivando o perfil da identidade quando só existe o ledger
  (personagens seed).
- `main.py` (composition root): `_CompositePersonaSource` (persona
  persistente → fallback ledger; o `search` global permanece apenas com
  personagens — persona de um tenant nunca vaza para o catálogo) e
  `_PersistentPersonaProfileSource`, injetados no resolver.
- **Gerações herdaram a persona**: `ImageGenerationRequest`/
  `VideoGenerationRequest` ganham `persona_id` opcional; a identidade e o
  estilo padrão da persona persistida passam a chegar no `GenerationSpec`
  via `MemoryResolver`, e o `lora_id` treinado da persona é herdado nos
  parâmetros (LoRA explícito no request sempre vence).

### API (6 rotas novas, todas `Depends(current_user)`)

- `GET /api/v1/personas` — lista os perfis do workspace.
- `GET /api/v1/personas/{id}` — perfil completo (wardrobe, imagens,
  revisões).
- `PATCH /api/v1/personas/{id}` — atualização parcial; mudança de
  identidade incrementa `revision` e appende linha imutável em
  `persona_identity_revision`; `wardrobe` (quando enviado) substitui o
  guarda-roupa inteiro.
- `DELETE /api/v1/personas/{id}` — remove perfil e filhas; assets
  referenciados e histórico de treino permanecem.
- `GET /api/v1/personas/{id}/images` — referências de imagem com
  name/url do asset quando ele ainda existe.
- `POST /api/v1/personas/{id}/images` — anexa asset **existente** do
  workspace (só `kind=image`; 404 externo/ausente, 422 não-imagem, 409
  duplicado). Upload continua apenas no fluxo de assets.
- `POST /api/v1/personas` (existente) agora **persiste** o perfil no banco;
  o contrato de request/response é inalterado (PersonaStudio e o fluxo de
  treino funcionam sem mudança). Slug duplicado no workspace → 409.
- `/personas/{id}/train` agora lê a persona do banco (sobrevive a restart)
  e mantém o contrato legado de atualizar o conjunto de referências.

### Frontend

- Nova tela **`/studio/personas`** (Dark Premium): listar, criar, editar
  identidade/wardrobe/estilo/LoRA, anexar imagens do acervo e excluir —
  com histórico de revisões visível. `lib/api.ts` ganha as funções de
  perfil; a página inicial ganha o atalho.

### Testes e docs

- `backend/tests/test_persona_engine.py` (19 testes): CRUD, isolamento de
  workspace, slug único, revisões append-only, imagens, `resolve_persona`,
  `/core/compile` consumindo persona persistida, herança de LoRA, catálogo
  privado e as duas migrations (upgrade + downgrade sem drop).
- `docs/PERSONA_ENGINE.md` novo; `ARCHITECTURE.md`, `docs/ETAPAS.md`,
  `docs/LIMITATIONS.md`, `ROADMAP.md` e `docs/API.md` atualizados.

---

## [2026-09-15] — PR002: SEGURANÇA E PERSISTÊNCIA (entregue no PR #6)

O backend passa a ser um ambiente de produção sem alterar a arquitetura
(Bible §2/§18): a auditoria `SPRINT1_AUDIT_REPORT.md` (P0-2 e P0-4) foi
executada e os dois achados de segurança mais graves foram fechados.

### Segurança

- **JWT ≥ 32 bytes**: default de desenvolvimento agora tem 70 bytes e um
  `field_validator` **recusa iniciar** a aplicação com `BROBOND_JWT_SECRET`
  menor que 32 bytes (mínimo do RFC 7518 para HS256). `docker-compose.yml` e
  `.env.example` atualizados para segredos válidos.
- **Autorização em todas as rotas protegidas**: 22 de 58 rotas exigem token
  (`/queue`, `/jobs/*`, `/assets/download/*`, `/knowledge`, as 4 rotas de
  `/personas/*` e as 8 de `/core/personas/*`); 3 aceitam sem exigir
  (`/generations/*`, `/core/compile` — mantido o contrato original); 33
  permanecem públicas por desenho (dados de referência e Core read-only).
- **Proteção de download/cancel/jobs por tenant**: `/jobs/{id}`,
  `/jobs/{id}/cancel`, `/queue` e `/assets/download/{key}` checam posse pelo
  workspace do caller — resposta **404** (não 403), para o id de outro tenant
  não ser enumerável.
- **PII removida do acesso público**: `GET /api/v1/knowledge` (perfis de
  personagens, ex. CHAR_PETRICK) agora exige identidade.
- **Rate limit configurável**: `BROBOND_RATE_LIMIT_AUTH_PER_MINUTE`
  (default 20/min/IP, `0` desliga) em `/auth/login` e `/auth/register`, com
  `Retry-After` no 429. In-memory por processo; o passo seguinte declarado é
  store compartilhado (Redis), documentado em `docs/LIMITATIONS.md` §2.
- **Audit log**: `app/audit.py` + tabela `audit_log` append-only. Ações
  críticas (login bem-sucedido/falhado, registro, criação/cancelamento de
  job, download de asset, criação de persona, treino, revisões/aprovações de
  identidade) escrevem a linha + uma linha estruturada no logger
  `brobond.audit`.
- **WebSockets autenticados**: os 2 sockets aceitam o token pelo query
  parameter `token` (browsers não definem header em handshake) e verificam
  posse do job/run — fecham com `1008` **antes** de aceitar. O cliente
  (`lib/api.ts → wsUrl`) agora anexa o token do `localStorage`.

### Persistência

- **Alembic instalado e usado** (`alembic==1.13.3`, já pinado): `alembic.ini`
  + `alembic/env.py` (URL lida das settings da aplicação) +
  `alembic/versions/0001_initial_schema.py` — migration inicial com as 7
  tabelas existentes + `jobs` + `audit_log`.
- **Jobs fora da RAM**: `JobRow` (tabela `jobs`) + `JobStore` em
  `app/store.py` — a API e o worker Celery leem/escrevem a mesma linha;
  `process_generation(job_id)` é agora o contrato real de outro processo.
  O cancelamento passa por `transition()` (persiste **e** emite o evento —
  antes o cancel não emitia nada).
- **Bootstrap por migration**: `app.main._bootstrap_database` roda
  `alembic upgrade head` (com retry para o Postgres do Render) em vez de
  `create_all` + `ALTER TABLE` manual. A migration é idempotente: um banco
  legado do bootstrap antigo atualiza no lugar (coluna
  `training_runs.workspace_id` adicionada quando ausente).
- **`Dockerfile.api`** agora copia `alembic/` e `alembic.ini` para o
  `upgrade head` funcionar no container.

### Compatibilidade (nada quebrado)

- `complete` continua sendo o estado **interno** (`JobStatus`, eventos,
  worker); a borda responde **`completed`** via `events.external_status()` /
  `schemas.JobResponse` — uma única função, um único lugar. `TERMINAL_STATUSES`
  e os nomes de evento são inalterados.
- `/generations/*` continua aceitando anônimo (202); consequência documentada:
  job anônimo não tem tenant e não pode ser lido de volta (fixado por teste;
  a UI avisa "sign in to track it").
- Zero arquivos deletados; `MemoryStore` segue existindo para personas
  (persistência delas é o PR004); `docs/API.md` regenerado pelo script.

### Testes e validação

- **1.125 testes** (era 1.077): 4 arquivos novos —
  `test_security_authorization.py` (matriz 401, isolamento de tenant, rate
  limit, validador de JWT, WS), `test_job_persistence.py` (job visível para
  outro processo, worker por id, cancel persistido, fila por tenant),
  `test_audit_log.py` (ações com linha e logger estruturado, append-only por
  AST) e `test_migrations.py` (upgrade em banco novo, idempotência, upgrade
  de banco legado, downgrade).
- Testes existentes atualizados apenas onde o PR muda o contrato:
  `test_knowledge.py` e `test_core_api.py` (`/knowledge` com token),
  `test_queue_events.py` (WS com `?token=`, snapshot `completed`),
  `test_core_persona_api.py` (rotas protegidas), `test_lora.py`,
  `test_asset_export_routes.py` (socket de training agora exige token),
  `test_queue_training_paths.py` (leitura de volta via store),
  `test_docs_accuracy.py` (contagem 22/3 e docs).
- Cobertura `backend/app`: **95%** (gate CI: 90%). `npm run build` OK.

---

## [Unreleased] — ETAPA 17: DOCUMENTAÇÃO

Relatório técnico completo em `ETAPA17_REPORT.md`.

### Corrigido

Doze afirmações que eram verdadeiras quando escritas e ficaram falsas sem ninguém notar:

- `README.md` dizia **"pytest suite (176 tests)"** — a suíte tem **1.075**.
- `README.md` dizia que o resultado da geração é **"a local UI simulation"** — removido na
  ETAPA 15; a tela mostra o `output_url` real.
- `README.md` listava **"Motion control preset browser"** — removido da navegação na ETAPA 15.
- `README.md` atribuía a lacuna de cobertura a **"`core/security.py` at 0%"** — está em 21%.
- `README.md` tinha seis **"Next implementation milestones"** — os seis já estavam entregues
  até a ETAPA 12. Substituídos por "What is not built yet".
- `ROADMAP.md` dizia **"seis componentes independentes"** — são **doze** desde a ETAPA 14.
- `ROADMAP.md` descrevia o **P0-3** como aberto — foi fechado na ETAPA 11 por `publish_sync`.

### Adicionado

- **`docs/API.md`** — inventário das 58 rotas + 2 WebSockets, **gerado** da aplicação por
  `scripts/gen_api_doc.py`, com a primeira linha do docstring de cada endpoint.
- **`docs/LIMITATIONS.md`** — o que não está pronto num lugar só, com o comando que reproduz
  cada estado: dependências ausentes, estado em memória, 10 de 58 rotas tocam identidade (6 exigem token, 4 não), os dois
  achados da ETAPA 16, o cluster morto, o frontend, as dependências mortas.
- **`docs/ETAPAS.md`** — índice das 17 etapas, estado dos cinco P0, invariantes e números.
- **`backend/tests/test_docs_accuracy.py`** — 35 guardas anti-drift, incluindo um teste por
  componente do Core provando que nenhum importa framework.

### Medido, não presumido

O rascunho de `docs/ETAPAS.md` afirmava "12 componentes em `INDEPENDENT_MODULES`". Medido:
são **8**. Adicionar os cinco restantes fez **4 testes falharem**, porque a guarda afirma uma
propriedade mais forte — importar *sem nenhum irmão do Core* — e esses cinco compõem uns aos
outros por desenho. Os dois fatos são verdadeiros e diferentes: 12 são livres de framework, 8
são também livres de irmãos. A doc diz isso.

### Nenhuma limitação foi consertada

Esta etapa **documenta**. `MemoryStore`, as 48 rotas sem autenticação, o `lora_id` cru sem
workspace e o `jwt_secret` de 23 bytes continuam abertos, cada um com seção em
`docs/LIMITATIONS.md`. Nenhum arquivo foi deletado: `minio==7.2.15` segue sem ser importado e
os quatro módulos do P0-1 seguem no repositório, ambos documentados em vez de removidos.

---

## [Unreleased] — ETAPA 16: TESTES 90%

Relatório técnico completo em `ETAPA16_REPORT.md`.

### Cobertura

`89% → 95%` sobre `backend/app`. **28 módulos em 100%** (eram 20). Suíte `881 → 1040` testes.

| Módulo | Antes | **Depois** |
| --- | --- | --- |
| `queue.py` | 60% | **100%** |
| `training.py` | 28% | **100%** |
| `preprocessing.py` | 23% | **100%** |
| `system.py` | 36% | **100%** |
| `providers/image.py` | 70% | **100%** |
| `providers/video.py` | 74% | **100%** |
| `providers/common.py` | 87% | **100%** |
| `lora.py` | 89% | **100%** |
| `auth.py` | 89% | **99%** |
| `main.py` | 79% | **87%** |

### Adicionado

- **`pytest.ini`** e um **gate de cobertura no CI** (`coverage report --fail-under=90`). O
  piso agora é imposto, não apenas relatado; `coverage==7.6.1` entrou em `requirements.txt`.
- **`test_runtime_capabilities.py`** (48), **`test_queue_training_paths.py`** (28),
  **`test_provider_runtime.py`** (23), **`test_auth_paths.py`** (28),
  **`test_asset_export_routes.py`** (21), **`test_dead_module_boundary.py`** (11).

### Achados (medidos, não corrigidos nesta etapa)

- **`lora_id` sem `workspace_id` chega cru ao provider.** A checagem de posse só roda quando os
  dois existem; sem workspace, `GenerationSpecBuilder` (precedência `request.lora >
  persona.lora_path`) põe o **id do asset** em `spec.lora` onde o loader espera um caminho. Não
  é vazamento cross-tenant — nenhum arquivo é aberto — mas o job falha no load em vez de ser
  recusado antes. Fixado por teste para que seja visível.
- **`jwt_secret` default tem 23 bytes**, abaixo dos 32 mínimos do RFC 7518 para HS256. O PyJWT
  avisa a cada chamada.
- **O socket de treinamento não tem guarda de autenticação**, ao contrário da rota HTTP
  equivalente. O `run_id` é um UUID aleatório, então não é enumerável, mas o endpoint não
  verifica identidade. Fixado por teste.

### O cluster morto, contabilizado

`app.api.routes`, `app.api.dependencies`, `app.core.security` e `app.services.generation`
(**100 statements**) seguem sem importar — é o P0-1 do `AUDIT.md` §5.1. Não foram apagados
(instrução permanente) nem consertados (consertar ressuscitaria um segundo backend que duplica
`main.py`). `test_dead_module_boundary.py` transforma isso em decisão: se um dia passarem a
importar, um teste falha.

---

## [Unreleased] — ETAPA 15: UX PREMIUM

Relatório técnico completo em `ETAPA15_REPORT.md`.

### Corrigido

- **A interface não consumia nenhuma rota Core.** `grep -rn "api/v1/core" app components lib`
  → zero. Quatorze etapas de camada de decisão e 31 rotas `/api/v1/core/*` inalcançáveis do
  produto. O usuário continuava diante de um campo de prompt com um botão "Enhance" —
  exatamente o que `SYSTEM_PROMPT.md` proíbe ("o usuário conversa com um diretor de cinema,
  não com um campo de prompt").
- **A casca inventava fatos.** `RTX 4090 · 18.4 / 24 GB VRAM` num host sem GPU (a rota real
  responde `{"available": false, "backend": "cpu"}`), `Good evening, Petrick` fixo em um nome
  e uma hora, `12 renders`/`4 renders`/`2 personas`, abas de biblioteca em `128/84/24/2/18`,
  `LoRA v1.2` sem nenhum treino, e um contador de prompt `72 / 2,000` que não acompanhava o
  campo.
- **O resultado mostrado não era o render.** `output_url` aparecia no tipo `Job` mas nunca era
  lido: a tela desenhava uma figura CSS (`result-person`) rotulada **"FLUX / 2K"** haja o que
  houvesse. Um job `failed` mostrava a mesma imagem de um `complete`.
- **Todo erro virava "offline".** `request()` engolia 401, 422 e 500 no mesmo
  `{ data: null, remote: false }`. Senha errada e servidor desligado eram indistinguíveis —
  inclusive no login.
- **Os controles não comandavam nada.** Model, aspect ratio e resolution eram `<select>`
  renderizados enquanto o payload levava literais: escolher `9:16 · Portrait` produzia 16:9.
- **O browser recebia uma origem fixa.** `API_URL` default `http://localhost:8000`, que só
  funciona quando o browser está na mesma máquina da API.

### Adicionado

- **Painel do Diretor como porta de entrada** — `POST /api/v1/core/direct`. Intenção em
  linguagem natural, resposta com conceito, logline, roteiro, beats, música, ritmo, duração e
  a pergunta de esclarecimento quando o diretor precisa dela.
- **Proxy `/api/v1` no `next.config.mjs`** — URL relativa, sem origem fixa no browser.
  WebSocket incluído (verificado: `101 Switching Protocols` através do proxy).
- **Storyboard via Core** (`/api/v1/core/storyboard`) mostrando os shots escalados **e** as
  violações/atenções que o motor reporta.
- **Cartão de GPU e painel de readiness reais**, lidos de `/api/v1/system/gpu` e
  `/api/v1/system/readiness`.
- **Contrato de erro honesto** em `lib/api.ts`: `{ data, remote, status?, error? }`, com o
  `detail` do FastAPI extraído e um componente `Notice` em cada painel.
- **`backend/tests/test_frontend_honesty.py`** — 31 guardas estruturais.

### Removido

O módulo "Motion control" saiu da navegação: era inteiramente estático, sem uma única chamada,
e mantê-lo ao lado de painéis que funcionam ensinava o usuário a desconfiar dos que funcionam.

---

## [Unreleased] — ETAPA 14: QUALITY AI

Relatório técnico completo em `ETAPA14_REPORT.md`.

### Corrigido

- **Nada examinava o que foi gerado.** Reproduzido de ponta a ponta antes de escrever uma
  linha: um provider devolveu um caminho que **não existia** e dimensões (512×512) que
  contradiziam os 16:9 pedidos. O worker persistiu, gravou `output_url` e marcou o job
  `complete`. Violação direta de `SYSTEM_PROMPT.md` — "Não invente arquivos, jobs concluídos,
  modelos carregados ou outputs inexistentes".
- **`GenerationOutput.width` e `.height` não eram lidos por código algum** do repositório. O
  provider auto-relatava a geometria e ninguém conferia.
- **`from app.core import *` estava quebrado** com `AttributeError: BRIDGING_FAMILIES`.
  Defeito introduzido na ETAPA 13: a constante foi removida e a entrada em `__all__` ficou.
  Nenhum teste pegou porque nada fazia star-import. Corrigido e agora vigiado por dois testes.

### Adicionado

- **`backend/app/core/quality.py`** — o 12º componente independente do Core. `QualityGate`
  confere o artefato contra o spec que o produziu: existência, tamanho, geometria relatada
  contra o aspect ratio pedido, piso de resolução e — para vídeo — duração e frame rate.
- **A gate roda no worker antes de persistir.** Uma violação marca o job `failed` com o
  motivo, em vez de entregar um `output_url` quebrado.
- **`POST /api/v1/core/quality/assess`** e **`GET /api/v1/core/quality/rules`** (56 → 58 rotas).
- **`backend/tests/test_core_quality.py`** — 69 testes.
- **`app.core.quality` em `INDEPENDENT_MODULES`** (21 → 23 testes de independência).

### O que a gate **não** faz, declarado

Nenhum modelo é carregado e nenhum é fingido. `GET /api/v1/core/quality/rules` devolve
`model_loaded: false` e uma lista `does_not_assess` com composição, aderência ao prompt,
detecção de artefatos anatômicos, qualidade estética e semelhança de persona — porque nada
neste processo vê a imagem. `structural_score` é a fração das verificações estruturais
aplicáveis que passaram, e a nota diz isso.

### Fixture de teste corrigida

Seis fakes de provider em três arquivos devolviam caminhos que nunca eram escritos. Antes da
ETAPA 14 nada conferia, então passavam. Agora escrevem o arquivo — a asserção de cada teste
sobre entrega de spec permanece intocada.

---

## [Unreleased] — ETAPA 13: VIDEO TIMELINE

Relatório técnico completo em `ETAPA13_REPORT.md`.

### Corrigido

- **Nada montava um filme.** O estúdio dirigia um storyboard de várias cenas (ETAPA 8) e
  gerava cada cena como um job próprio, mas não havia como juntá-las: `export_h264` recebe
  **uma** origem e não existia concatenação em lugar nenhum do repositório. Um storyboard de
  cinco cenas produzia cinco arquivos órfãos. `SYSTEM_PROMPT.md` pede que o Diretor ajuste
  "ritmo, lente, movimento, iluminação, **montagem**, som e duração" — montagem era a única
  palavra sem código atrás.
- **`media.probe` devolvia o JSON do ffprobe sem parsear** (`{"raw": stdout}`) e tinha **zero
  chamadores**. Nenhum código conseguia ler duração, fps ou tamanho de um clipe — exatamente
  o que uma linha de tempo precisa saber.

### Adicionado

- **`backend/app/core/timeline.py`** — o 11º componente independente do Core. `VideoTimeline`
  monta uma sequência escalada num corte ordenado: ordem dos clipes, pontos de entrada e
  saída, transições, cama de áudio e geometria de entrega, com o runtime checado contra o
  **mesmo teto** do `StoryboardEngine`.
- **`media.concat`** — o passo de montagem que faltava, com a cama de música como segunda
  entrada mapeada explicitamente e `-shortest` para a trilha não segurar o arquivo aberto.
- **`probe_fields` e `concat_command`** — construção de argumentos em funções puras,
  testáveis **sem** o binário do FFmpeg. Este sandbox não tem `ffmpeg` no PATH.
- **`POST /api/v1/core/timeline`** e **`GET /api/v1/core/timeline/formats`** (54 → 56 rotas).
- **`backend/tests/test_core_timeline.py`** — 84 testes.
- **`app.core.timeline` entrou em `INDEPENDENT_MODULES`** (17 → 19 testes de independência).

### Regra de transição

Dissolve **dentro de uma ideia**, corte **entre duas**: dois clipes consecutivos da mesma
família são continuação, e um corte seco ali leria como salto. O primeiro clipe sempre corta.

A primeira versão usava `StoryboardEngine.TRANSITION_FAMILIES` (`transition`, `atmosphere`)
como gatilho. **Era código morto**: nenhum arco de `ARC_BY_FORMAT` escala essas famílias, a
interseção é vazia e um dissolve nunca poderia ter sido emitido. Medido antes de trocar.

### Honestidade preservada

Um `Timeline` **não é um arquivo renderizado**. Clipes cuja mídia ainda não foi produzida
voltam como não renderizados, `complete` fica `false`, e `validate` reporta cada um como
aviso — nunca passa em silêncio. `SYSTEM_PROMPT.md`: não inventar outputs inexistentes.

---

## [Unreleased] — ETAPA 12: STORAGE (MinIO/S3)

Relatório técnico completo em `ETAPA12_REPORT.md`.

### Corrigido

- **`StorageService` era write-only** — havia `save`, `save_path`, `signed_url` e
  `local_path`, mas nenhuma forma de **ler** um objeto de volta. Por isso três caminhos
  recusavam trabalhar com storage ligado, respondendo 501: condicionamento
  (`"MinIO preprocessing adapter is not enabled"`), export
  (`"MinIO source download adapter is not enabled for exports yet"`) e o carregamento de
  LoRA/referência no worker (`RuntimeError`). Nenhum dos três era difícil — faltava o
  primitivo.
- **O ramo S3 nunca tinha sido executado por teste algum.** `storage.py` estava em 61%: as
  linhas de upload, presigned URL e o guard de *path traversal* de `local_path` (l.57-61)
  jamais rodaram. Um controle de segurança sem cobertura é uma intenção, não uma garantia.
  Agora em **100%**.

### Adicionado

- **`download(key, destination)`** — traz um objeto para um arquivo de trabalho local. Em
  modo local devolve o próprio arquivo, sem cópia.
- **`exists(key)`** — responde se o objeto está lá, em vez de deixar a falha aparecer só no
  download, longe da causa.
- **`delete(key)`** — apagar a linha `Asset` nunca removia os bytes; um workspace que se
  limpava continuava enchendo o bucket.
- **`upload_path(source, key, content_type)`** — envia para uma chave **escolhida pelo
  chamador**, diferente de `save_path` que gera uma. Export e condicionamento derivam a
  chave do asset de origem e ela precisa permanecer estável.
- **`ensure_bucket()`** — um MinIO novo não tem o bucket `brobond-assets`, e sem isso o
  primeiro upload falhava com um `NoSuchBucket` cru do botocore que chegava ao usuário como
  500. Idempotente.
- **`PRESIGNED_TTL_SECONDS`** — o TTL de 3600 estava hardcoded em três lugares.
- **`StorageUnavailable`** — exceção nomeada para "storage foi exigido mas está desligado".
- **`backend/tests/test_storage.py`** — 37 testes com um cliente S3 falso em memória,
  cobrindo os dois backends.

### Mudado

- **O cliente boto3 é construído sob demanda**, não no `__init__`. Importar o módulo não
  resolve mais credenciais nem região, e o cliente passa a ser injetável em teste.
- Os quatro pontos que recusavam 501/RuntimeError passaram a usar `storage.download`.

---

## [Unreleased] — ETAPA 7: DIRECTOR AI

Relatório técnico completo em `ETAPA7_REPORT.md`.

### Corrigido

- **O arco `documentary` era inalcançável.** `FORMAT_KEYWORDS` dobrava
  `"documentário"`/`"documentario"` em `film` e não conhecia `"documentary"`: um brief em
  inglês caía em `commercial` **com pergunta de esclarecimento**, e em português virava
  `film`. O engine já tinha `ARC_BY_FORMAT["documentary"]` e 24 presets da família — código
  morto dos dois lados. Havia um teste (`test_the_documentary_arc_is_currently_unreachable`)
  fixando o defeito de propósito, com o aviso "this test fails the day that lands".
- **A escolha de formato seguia a ordem do dicionário, não o brief.** `"um fashion film
  editorial"` casa `fashion` (2 palavras) e `film` (1); vencia `fashion` por estar declarado
  antes — acidente, não regra. `"reels para vender meu produto na loja"` dava `reels` com uma
  única palavra contra três comerciais.
- **O diretor descrevia um ritmo que não entregava.** `pacing` de reels prometia
  `"cortes rápidos, 1.5s por plano"` enquanto todos os beats saíam a 5.0s.
- **Oito beats eram quatro beats duas vezes.** Com só 4 objetivos e 4 emoções, os beats 5-8
  repetiam os 1-4 palavra por palavra: o diretor dava a mesma instrução duas vezes.

### Adicionado

- **`detect_formats(intent)`** — todos os formatos casados, ranqueados por contagem de
  palavras-chave. `detect_format` passa a devolver o mais específico; empate mantém a ordem
  de declaração, que é uma regra documentada em vez de um acidente.
- **`detect_format_conflict(intent)`** — os formatos empatados em primeiro. Quando há empate
  real o diretor **diz** em vez de escolher em silêncio, e a pergunta nomeia os dois
  candidatos.
- **Formato `documentary` completo** nos dois idiomas: `concept`, `music` e `pacing`.
- **Oito objetivos e oito emoções** por idioma, casando com `MAX_BEATS`.
- **`backend/tests/test_core_director_agent.py`** — de 20 para 41 testes.

### Não alterado (de propósito)

- **`CAMERA_LADDER` continua ciclando em 4.** É gramática visual fixada por teste
  (`beats[4].camera == beats[0].camera`), não repetição acidental.
- **`expand()` continua sem teto próprio** — a validação é da camada de API
  (`scene_count: ge=2, le=12`) e do `StoryboardEngine` (teto de runtime de 180s). Camadas,
  não bug.
- **`DirectorAgent` continua sem LLM carregado.** `_enrich` segue opcional e degradando em
  silêncio; nada foi fingido.

---

## [Unreleased] — ETAPA 11: QUEUE & WEBSOCKET

Relatório técnico completo em `ETAPA11_REPORT.md`.

### Corrigido

- **`EventHub.publish` tinha zero chamadores** (P0-3, aberto desde `AUDIT.md`). O socket
  `/api/v1/queue/events/{job_id}` enviava um snapshot na conexão e depois bloqueava em
  `await websocket.receive_text()` — era um loop de *leitura*, não de envio. Um cliente
  conectado nunca via o job andar. Verificado de ponta a ponta antes e depois.
- **O progresso saltava de 10 para 100.** Não havia marco intermediário, então nenhuma
  barra de progresso podia ser desenhada com honestidade.
- **Dois eventos `complete` eram enviados** quando um cliente conectava no fim do job: a
  rota drenava o buffer e ainda emitia um evento terminal sintético. Agora o sintético só
  sai se o buffer não trouxe o terminal.

### Adicionado

- **`transition()` em `backend/app/queue.py`** — o único ponto que escreve `job.status` e
  `job.progress`, e que emite o evento no mesmo passo. Antes, cada call site atribuía os
  dois campos diretamente e nada era emitido: não existia um instante que significasse "o
  job andou". Guardado por um teste estrutural que varre o AST.
- **Seis marcos de progresso** declarados como constantes: `PROGRESS_STARTED` 10,
  `PROGRESS_SPEC_COMPILED` 25, `PROGRESS_INPUTS_RESOLVED` 40, `PROGRESS_RENDERING` 55,
  `PROGRESS_PERSISTED` 90, `PROGRESS_DONE` 100.
- **`publish_sync()`** — o worker é tarefa Celery síncrona e o hub é asyncio-only, então
  `await hub.publish(...)` nunca seria chamável dali. `publish_sync` grava o evento
  incondicionalmente e só despacha se houver loop rodando.
- **Buffer de replay com cursor** (`EVENT_BUFFER_SIZE` 64). Um cliente que conecta depois
  do job terminar recebe o histórico e o socket fecha; antes ficava preso sem resposta.
- **Contrato de evento único**: `{job_id, event, status, progress, at}` + `output_url` /
  `error` só quando significam algo. Nomes declarados em `JOB_EVENTS`.
- **`backend/tests/test_queue_events.py`** — 28 testes. O comportamento dos WebSockets
  nunca tinha sido testado: a única guarda existente era `len(websockets) == 2`.

### Documentado (não fingido)

- **O hub é in-process.** Com o worker em outro processo (deploy real com Celery), os
  eventos não alcançam os sockets da API — isso exige Redis pub/sub. Registrado como
  pendência em vez de simulado.

---

## [Unreleased] — ETAPA 10: PROVIDER ADAPTERS

Relatório técnico completo em `ETAPA10_REPORT.md`.

### Adicionado

- **`backend/app/providers/registry.py`** — fonte única de verdade para a escolha do
  adapter. `SYSTEM_PROMPT.md` diz que os providers são "adapters substituíveis"; até aqui
  isso não era verdade: o worker escolhia por `job.type`, então toda imagem rodava FLUX e
  todo vídeo rodava Wan, qualquer que fosse o pedido.
- **`HunyuanVideoProvider`** — `GET /api/v1/models/video` já anunciava `hunyuan-video`
  como `planned-provider` sem nada atrás. Agora existe adapter, e pedir Hunyuan devolve
  Hunyuan em vez de Wan silenciosamente.
- **`backend/app/providers/common.py`** — uma única definição para o que os dois providers
  duplicavam: `supported_kwargs`, `generator_for`, `apply_lora`, `health_report`,
  `cuda_availability`, `require_cuda`.
- **`backend/app/providers/conditioning.py`** — ControlNet e IP-Adapter como objetos com
  requisito declarado (`IpAdapterWeights`, `Conditioning`), em vez de um `if` dentro do
  provider FLUX.
- **`_DiffusersVideoProvider`** — base dos dois adapters de vídeo. Wan e Hunyuan diferem só
  onde os modelos de fato diferem: classe de pipeline, regra de contagem de frames e
  resolução padrão.
- **`GET /api/v1/core/providers`** e **`GET /api/v1/core/providers/health`** + 3 schemas.
- **57 testes novos** (`test_provider_adapters.py`). `registry.py` e `conditioning.py` a
  **100%**; o que resta descoberto é caminho de inferência GPU.

### Corrigido

- **O IP-Adapter carregava pesos SDXL num pipeline FLUX.**
  `pipeline.load_ip_adapter("h94/IP-Adapter", weight_name="ip-adapter-plus_sdxl_vit-h.safetensors")`
  sobre `FluxPipeline`. A documentação do diffusers para `FluxPipeline` especifica
  `XLabs-AI/flux-ip-adapter` + `weight_name="ip_adapter.safetensors"` +
  `image_encoder_pretrained_model_name_or_path`. Numa máquina com GPU a chamada antiga
  falharia no load.
- **`FluxDiffusersProvider.CONSUMED_SPEC_FIELDS` mentia.** Declarava 9 campos mas
  `pipeline_arguments` consome `negative_prompt`, que não estava declarado. O teste
  existente só verificava que os declarados existem no spec — nunca se batiam com o código.
  Agora `test_the_declared_fields_match_the_code` compara por análise estática, e foi
  verificado que **falha** quando a omissão é reintroduzida.
- **Defeito meu da ETAPA 9:** `PROVIDER_PROMPT_BUDGET` tinha a chave `"wan-video"`, que não
  é id do catálogo (o real é `"wan-2.1-t2v"`), então um job de vídeo real caía no orçamento
  conservador de 1000 em vez de 1200. Chaves realinhadas aos ids do catálogo +
  `PROVIDER_BUDGET_ALIASES` para tolerar a grafia antiga.
- **Bug meu introduzido e corrigido nesta etapa:** `HunyuanVideoProvider.arguments` consome
  `spec.steps` mas a primeira versão copiava a declaração do Wan, que não inclui `steps` —
  exatamente a classe de erro que a etapa remove. Corrigido com
  `VIDEO_CONSUMED_SPEC_FIELDS | {"steps"}`.

### Mudado

- **Quatro implementações duplicadas viraram uma.** Medido antes: `_generator` e
  `_apply_lora` eram byte-idênticos nos dois arquivos; `health()` idêntico salvo o nome do
  provider; `_supported_kwargs` idêntico salvo o docstring. Agora são o **mesmo objeto**.
- O worker escolhe o adapter pelo provider pedido, via registry, e **recusa** combinações
  impossíveis antes de carregar qualquer coisa (provider planejado, remoto, ou de kind
  errado) em vez de rodar outro modelo silenciosamente.
- Guardas de contagem: **54 rotas HTTP** (eram 52) e **27 paths** com tag `core` (eram 25).
  Nada removido.

### Achados (documentados, não remendados)

- **`spec.provider` mistura dois namespaces**: id de repositório para imagem
  (`"black-forest-labs/FLUX.1-dev"`) e id de catálogo para vídeo (`"wan-2.1-t2v"`). É
  comportamento deliberado da ETAPA 3, fixado por
  `test_the_worker_needs_no_fallback_because_the_adapter_already_resolved_it`. Não alterado;
  o registry despacha pelo id lógico vindo de `job.parameters["model"]`.
- **`resolve_model_id` devolve o fallback FLUX para todo id desconhecido** — 6 de 7 entradas
  medidas caem em `"black-forest-labs/FLUX.1-dev"`. Preservado por
  `test_resolve_model_id_never_invents_a_repository`; o registry agora cobre o caso por cima.
- **`describe()` de `StyleResolver` e `pipeline_arguments` de módulo** permanecem como
  superfície pública mesmo com chamadores internos reduzidos.

---

## [Unreleased] — ETAPA 9: PROMPT COMPILER

Relatório técnico completo em `ETAPA9_REPORT.md`.

### Adicionado

- **Os 13 blocos que `SYSTEM_PROMPT.md` declara.** Faltavam `ACTION` e `COLOR`;
  `NEGATIVE` existia como campo lateral, fora da ordem de emissão. `PROMPT_BLOCK_ORDER`
  passa a ter 12 blocos emitidos e `PROMPT_BLOCKS` declara os 13, com `NEGATIVE_BLOCK`
  mantido **fora** da ordem de propósito: providers de difusão recebem o negative como
  argumento separado, e anexá-lo ao prompt positivo inverteria seu sentido.
- **`STYLE` movido para a posição declarada no documento** — depois de `MOTION`, como
  modificador global de look, e não como a quarta coisa que o modelo lê.
- **`StyleResolver.style_phrase()` e `color_phrase()`.** `describe()` é preservado
  integralmente (é superfície pública, fixada por teste próprio); os dois métodos novos
  separam o nome do estilo da sua grade de cor.
- **`PromptCompiler.compile_beats()`** — consome a projeção `StoryboardEngine.as_beats()`
  e devolve um prompt por cena, com ACTION, CAMERA, LENS, LIGHT e CONTINUITY vindos do
  preset escalado. Assina sobre `SceneBeat` (tipo de contrato), não sobre `Storyboard`:
  o compilador importa `contracts` e nada mais, e essa independência é guarda testada.
- **`PROVIDER_PROMPT_BUDGET` + `budget_for()`.** `flux-dev` 1000, `wan-video` 1200,
  `hunyuan-video` 1200, desconhecido 1000. O teto `max_prompt_chars` continua sendo o
  limite duro: um orçamento de provider só pode apertá-lo, nunca afrouxá-lo.
- **`POST /api/v1/core/storyboard/compile`** + 3 schemas (`CoreStoryboardCompileRequest`,
  `CompiledSceneResponse`, `CoreStoryboardCompileResponse`).
- **`SceneBeat.lens` e `SceneBeat.continuity`** (opcionais, default `""`), para que a
  projeção `as_beats()` não perca a focal nem a nota de continuidade do shot escalado.
- **50 testes novos** (`test_core_prompt_blocks.py` 26, `test_core_storyboard_compile_api.py` 24).
  `prompt_compiler.py` e `style_resolver.py` a **100%**.

### Corrigido

- **Toda prompt compilada repetia a focal.** `ShotResolver.camera_phrase()` já anexa a
  focal do preset e `lens_phrase()` começa por ela, então cada prompt com shot emitia
  `"... 35mm, 35mm ..."`. Reproduzido nos 10 presets publicados. `_dedupe` existia desde a
  ETAPA 2 mas só era aplicado ao negative prompt; agora é aplicado na junção dos blocos.
  Verificado: 0 cláusulas repetidas nos 5 presets medidos.
- **A grade de cor estava no bloco errado.** `describe()` empacota nome + LUT + contraste +
  grain + paleta numa cláusula só, o que impedia descartar um adjetivo sem perder a
  paleta. `DROP_PRIORITY` agora tem `color` abaixo de `style`: sob aperto de orçamento, a
  grade — que é o que mantém uma sequência reconhecível entre cortes — sobrevive ao
  adjetivo.
- **O orçamento era um 1200 fixo** cujo próprio docstring chamava de "provider character
  budget" sem que nenhum provider declarasse um.

### Mudado

- Guardas de contagem: **52 rotas HTTP** (eram 51) e **25 paths** com tag `core` (eram 24).
  Nada removido.
- Duas guardas que fixavam a ordem antiga de 10 blocos foram atualizadas para os 13 do
  documento. O comentário da ETAPA 2 dizia que a ordem era "mandated by ETAPA 9", mas não
  batia com `SYSTEM_PROMPT.md` — esta etapa alinha ao documento.

### Achados (documentados, não remendados)

- **Adjetivos soltos vindos de campos verbatim.** `ShotPreset.depth = "medium, strong
  parallax"` vira `"medium, strong parallax depth of field"`, e `contrast = "high, glowing
  highlights"` vira a cláusula solta `"high"`. É o dado publicado sendo emitido como está;
  reescrevê-lo seria editar presets que as guardas da ETAPA 6 protegem.
- **O SUBJECT continua no idioma do usuário** enquanto o resto do prompt é inglês. Não é
  defeito: `SYSTEM_PROMPT.md` determina que o texto cru vire o bloco SUBJECT.

---

## [Unreleased] — ETAPA 8: STORYBOARD ENGINE

Relatório técnico completo em `ETAPA8_REPORT.md`.

### Adicionado

- **`backend/app/core/storyboard_engine.py`** (415 linhas) — transforma beats numa
  **sequência de shots escalados, encadeados e validados**. Cada cena passa a nomear um
  código real da biblioteca de 300 (`SH002 City Wakes`), e lente, luz, movimento e
  continuidade passam a vir do preset em vez de um texto fixo.
- **`ARC_BY_FORMAT`** — arco narrativo canônico de cinco beats por formato detectado
  (commercial, fashion, film, reels, story, documentary) + `DEFAULT_ARC`. Sequências mais
  longas repetem o beat de desenvolvimento; mais curtas cortam do meio para fora, de modo
  que **abertura e resolução sempre sobrevivem**.
- **`StoryboardEngine.build/cast_beats/arc_for/validate/beat_sheet/as_beats`** — escala os
  beats, monta o arco, valida a sequência e devolve um relatório (não uma exceção), porque
  um diretor precisa ver **o que** está errado num corte.
- **`as_beats()`** — projeta o storyboard de volta em `SceneBeat` **com `shot_code`
  preenchido**, o que torna a biblioteca de 300 alcançável pelo caminho de prompt existente
  sem tocar no `PromptCompiler`.
- **`POST /api/v1/core/storyboard`** + 4 schemas (`CoreStoryboardRequest`,
  `CoreStoryboardShotResponse`, `CoreStoryboardFindingResponse`, `CoreStoryboardResponse`).
  Nomes com prefixo `Core` para não colidir com o `StoryboardResponse` legado.
- **66 testes novos** (`test_core_storyboard_engine.py` 47, `test_core_storyboard_api.py` 19),
  cobertura **100%** do módulo (124 statements).

### Corrigido

- **`shot_code` nunca era preenchido** — a biblioteca de 300 da ETAPA 6 era inalcançável do
  storyboard. Agora toda cena nomeia um shot real.
- **Iluminação idêntica em todas as cenas** (`"consistent blue-hour lighting across the
  sequence"`) — agora vem do preset escalado e varia cena a cena.
- **O Diretor reprovava na própria gramática**: `motion="motivated by the beat"` é exatamente
  o que a ETAPA 5 marca como *afirmar motivação sem nomeá-la* (`attention`). O movimento
  agora carrega uma motivação real da Bíblia (`reveal`, `approach`, `observation`).

### Mudado

- **`_pick_shot` evita repetição em todo o storyboard, não só no corte anterior.** A primeira
  versão só comparava com a cena anterior: passava na regra `no-repeat-cut` e ainda assim
  alternava entre dois shots numa sequência de 12 (`SH079` aparecia 5×). Agora prefere shots
  nunca usados e, esgotada a família, reutiliza o visto há mais tempo. Verificado: 12 cenas
  → 12 shots distintos.
- Guardas de contagem atualizadas para o novo total: **51 rotas HTTP** (era 50) e
  **24 paths** com tag `core` (eram 23). Nada foi removido.

### Achados (documentados, não remendados)

- **O arco `documentary` é inalcançável.** `DirectorAgent.FORMAT_KEYWORDS` agrupa
  "documentário"/"documentario" sob `film`, então `detect_format` nunca devolve
  `"documentary"`. Corrigir mudaria o comportamento da ETAPA 2 — território da **ETAPA 7**
  (Diretor), que está em aberto. Fixado por `test_the_documentary_arc_is_currently_unreachable`.
- **O casting não é sensível à emoção, de propósito.** O Diretor emite 4 emoções em português
  (`curiosidade`, `desejo`, `convicção`, `tensão`) e as intenções da biblioteca são em inglês:
  medido, **zero casamentos**. Um branch de pareamento por token seria código morto vestido de
  recurso; o mapeamento entre os dois vocabulários pertence ao Diretor. Fixado por
  `test_casting_is_not_emotion_aware`.

---

## [Unreleased] — ETAPA 6: SHOT LIBRARY (300 PRESETS)

Relatório técnico completo em `ETAPA6_REPORT.md`.

### Adicionado

- **`backend/app/core/shot_library.py`** (667 linhas) — **290 novos presets de direção**,
  levando a biblioteca ao alvo que `SHOT_LIBRARY.md` declara ("300+ shots"). Organizados em
  12 famílias narrativas (establishing, introduction, dialogue, action, tension, intimacy,
  product, fashion, transition, atmosphere, resolution, documentary), nenhuma com menos de 24
  shots.
- **`ShotLibrary`** — navegação por família, lente, enquadramento e motivação, mais
  `violations()`/`duplicates()`/`audit()` que verificam **todos os 300** contra a gramática da
  ETAPA 5.
- **`ShotPreset` recebeu `frame`, `lighting`, `continuity` e `family`** (com defaults), os
  campos que a política de expansão do documento exige: *"New shots require code, name, lens,
  frame, movement, lighting, emotional intention and continuity notes."*
- **4 rotas somente-leitura** — `/api/v1/core/shots` (com filtros combináveis), `/families`,
  `/audit` e `/{shot_code}`. É o navegador visual que `ShotResolver.catalog()` previa desde a
  ETAPA 2.
- **3 schemas** e **71 testes** novos (360 → **431**).

### Alterado

- **`shot_resolver` agora serve os 300.** A composição acontece em `main.py`, no composition
  root, então `shot_resolver.py` não importa `shot_library.py` — sem ciclo de import e sem
  alteração no módulo existente.
- **`"descent"` entrou no vocabulário de `reveal`** da ETAPA 5. A primeira validação dos 300
  apontou 1 violação em `SH087` ("crane **descent**"); a lacuna era na gramática, que conhecia
  só `descend`/`descending`. A correção foi **na gramática, não no shot** — reformular o texto
  para passar no verificador seria enganar o verificador.

### Corrigido

- **`duplicates()` não detectava código repetido.** A implementação comparava o código já visto
  com o atual (`seen[key] != shot.code`), o que é sempre falso justamente quando o código se
  repete. Pior: `_by_code` é um dict, então a duplicata seria descartada em silêncio.
  Reescrito contando códigos e nomes independentemente.
- **`violations()` não exigia os campos da política de expansão.** Só checava `intention`,
  então um shot novo podia omitir `frame`, `lighting` e `continuity` e passar. Corrigido, com
  isenção explícita para os 10 publicados.
- **Código morto removido:** `replace_family()` foi escrito "para composição futura" e nunca
  usado. Cobertura de `shot_library.py` foi de 97% a **100%** depois disso e de dois testes
  que faltavam (frame desconhecido, intenção ausente).

### Preservação

- **`SEED_SHOTS` não foi tocado** — os 10 publicados continuam byte a byte iguais
  (`SHOT_LIBRARY.md`: *"Shot codes are stable identifiers"*). Nada foi renumerado.
- Os 290 novos ocupam os códigos livres de `SH001–SH300` (290 livres + 10 publicados = **300
  exatos**).
- Os 10 publicados mantêm `frame=""`, `lighting=""` e `continuity=""` **de propósito**: o
  documento não declara tamanho de plano para todos, e preencher seria fabricar.

### Resultado da validação

```
total 300 | target 300 | meets_target True
published 10 | expanded 290
violations {} | duplicates []
```

Distribuição por lente: 24mm 57 · 35mm 69 · 50mm 60 · 85mm 62 · 135mm 52.
Por enquadramento: establishing 65 · medium 101 · close-up 70 · extreme close-up 54.

**Achado honesto:** a cobertura por motivação é enviesada — observation 161, approach 125,
reveal 21, escape 16, **transformation 2**. É realista, mas um diretor procurando um movimento
de transformação encontrará pouquíssimo. O número é exposto por `audit()` e fixado por teste,
não escondido.

### Verificado

| Verificação | Antes | Depois |
| --- | --- | --- |
| `pytest backend/tests -q` | 360 passed | **431 passed** |
| Os 22 testes originais, isolados | 22 passed | 22 passed |
| Independência do Core (subprocesso) | 17 passed | 17 passed |
| `core/shot_library.py` | — | **100%** (112 stmts, 0 miss) |
| Cobertura total do backend | 81% | **82%** |
| `npm run build` | ✓ | ✓ Compiled successfully |
| Shots na biblioteca | 10 | **300** |
| Rotas `/api/v1` (HTTP) | 46 | **50** |
| **Rotas removidas** | — | **nenhuma** |

Diff de inventário contra o commit base `3708784` (por AST, HTTP + WebSocket):
**baseline 30 → agora 53, 0 removidas, 23 adicionadas**.

### Explicitamente NÃO feito nesta etapa

- **Nenhum preset publicado foi alterado** e **nenhum valor foi inventado** para eles.
- **A `SHOT_LIBRARY.md` não foi reescrita** — o código passou a cumprir o alvo que ela declara.
- Biblioteca segue **em memória**; a costura `ShotSource` para PostgreSQL existe desde a ETAPA
  2 e continua sem implementação.
- Rotas sem autenticação (P0-4 aberto). UI ainda não consome (ETAPA 15).
- **Cobertura de `transformation` permanece em 2/300** — relatado, não corrigido.

---

Relatório técnico completo em `ETAPA5_REPORT.md`.

### Adicionado

- **`backend/app/core/cinematic_library.py`** (620 linhas) — a
  `knowledge_base/CINEMATIC_BIBLE.md` como gramática estruturada e regras aplicáveis:
  `LENSES` (24/35/50/85/135), `FRAMES`, `ANGLES`, `LIGHTS`, `TIME_QUALITIES`, `MOTIVATIONS`,
  e `CinematicLibrary` com 8 verificações normativas. Cada constante cita a frase de origem;
  nada foi inventado.
- **Auditoria da própria biblioteca.** `audit_library()` roda as regras contra os presets
  publicados e reporta as exceções em vez de escondê-las.
- **Consistência de episódio.** `episode_consistency()` aplica *"Grain is subtle and
  consistent across an episode"*: divergência de grão é `violation`; de grade e paleta é
  `attention`.
- **9 rotas somente-leitura** sob `/api/v1/core/cinematic/*`: lentes (e busca por propósito),
  enquadramento, iluminação, motivações (e análise de um movimento), auditoria, explicação de
  um estilo e consistência de episódio.
- **11 schemas** e **78 testes** novos (282 → **360**).

### Corrigido

- **`focal_of("135mm")` devolvia 35.** A busca era por substring e `"35mm"` ocorre dentro de
  `"135mm"`. Impacto real: **SH122, shot publicado, tinha a lente lida errada**. Corrigido com
  fronteira de dígito; os 10 shots e 7 estilos agora são lidos sem divergência.
- **O motor de regras condenava o que a Bíblia não condena.** `"static"` era marcado como
  violação, mas a Bíblia restringe *movimento* — câmera parada não tem o que justificar.
  `"elegant slow dolly"` e `"slow drift"` passavam sem motivação porque só `"dolly-in"` e
  `"handheld drift"` estavam no vocabulário. `"teal and amber restraint"` era sinalizado
  apesar de declarar parcimônia. `_check_motion` passou de 2 para 3 estados
  (ok / attention / violation).
- **Dois schemas colapsavam formas distintas** — `TimeQuality` tem `supports`, não `role`;
  `AngleProfile` tem `creates`, não `carries`. Falhava com `ValidationError` em runtime.
  Criados `TimeQualityResponse` e `AngleProfileResponse`.
- **Dependências declaradas não batiam com os imports vivos.** Uma instalação limpa não rodava
  o app: `backend/app/auth.py` importa `jwt`/`jwt.PyJWTError` (PyJWT) mas só `python-jose`
  estava declarado, e `backend/app/storage.py` importa `boto3` mas só `minio` estava declarado.
  Adicionados `PyJWT==2.14.0` e `boto3==1.43.94`. Fora do escopo da etapa; registrado por
  transparência.

### Resultado da auditoria sobre os presets publicados

7 estilos + 10 shots: **12 conformes, 5 sinalizados, nenhuma violação**.

| Item | Regra | Achado |
| --- | --- | --- |
| `cinematic-realism` | motion-motivated | `"motivated, steady"` alega motivação sem nomeá-la |
| `imax-hero` | lens-declared | `"40mm large format"` fora da linguagem de lentes |
| `john-wick` | protect-highlights | `crushed, specular` |
| `neo-tokyo` | grain-subtle | `"medium digital grain"` não é sutil |
| `neo-tokyo` | protect-highlights | `glowing` |
| `marvel-trailer` | teal-amber-sparingly | `teal / orange, warm` |
| `marvel-trailer` | lens-declared | `"28mm dynamic wide"` fora da linguagem de lentes |

### Verificado

| Verificação | Antes | Depois |
| --- | --- | --- |
| `pytest backend/tests -q` | 282 passed | **360 passed** |
| Os 22 testes originais, isolados | 22 passed | 22 passed |
| Independência do Core (subprocesso) | 17 passed | 17 passed |
| `core/cinematic_library.py` | — | **100%** (242 stmts, 0 miss) |
| `backend/app/core/` | 96% | **97%** |
| Cobertura total do backend | 78% | **81%** |
| `npm run build` | ✓ | ✓ Compiled successfully |
| Rotas `/api/v1` (HTTP) | 37 | **46** |
| **Rotas removidas** | — | **nenhuma** |

Diff de inventário contra o commit base `3708784` (extraído por AST, HTTP + WebSocket):
**baseline 30 → agora 49, 0 removidas, 19 adicionadas**.

### Explicitamente NÃO feito nesta etapa

- **Nenhum preset foi alterado.** Os 7 estilos e 10 shots continuam iguais; a auditoria
  *reporta* exceções, não as corrige em silêncio.
- **A Bíblia não foi reescrita** — o código passou a obedecê-la.
- Biblioteca segue **em memória**; a costura `StyleSource`/`ShotSource` para PostgreSQL existe
  desde a ETAPA 2 e continua sem implementação.
- Rotas sem autenticação (P0-4 aberto). UI ainda não consome (ETAPA 15).
- **ETAPA 6 (300 shots) não foi iniciada.**

---

Relatório técnico completo em `ETAPA4_REPORT.md`.

### Adicionado

- **`backend/app/core/persona_memory.py`** (405 linhas) — `PersonaLedger` (histórico
  append-only, implementa o `PersonaSource` que a ETAPA 2 reservou) e
  `PersonaMemoryEngine` (governança, snapshots de episódio, drift). Compõe o
  `MemoryResolver` da ETAPA 2: não há segunda definição de vocabulário nem da regra de
  autorização.
- **`PersonaNotFound`**, subclasse de `MemoryError_`, para que a camada HTTP responda 404 em
  vez de 409 sem quebrar handlers existentes.
- **8 rotas** sob `/api/v1/core/personas*`: catálogo, histórico completo, `revise`,
  `approve`, `retire`, snapshot por episódio, recall por episódio e `continuity`. Todas
  apenas delegam; nenhuma decide regra de identidade.
- **5 schemas** com validação (`PersonaRevisionRequest`, `PersonaTransitionRequest`,
  `PersonaVersionResponse`, `PersonaMemoryResponse`, `PersonaHistoryResponse`).
- **Testes:** 2 arquivos novos, **60 testes** (222 → **282**).

### Alterado

- **`PersonaLedger` é a fonte única de identidade.** `PersonaMemoryEngine` escreve o
  histórico nele e `MemoryResolver` lê dele, então engine e `GenerationSpecBuilder` enxergam
  o mesmo estado: um personagem aprovado pela API fica imediatamente utilizável pelo
  compilador, sem fiação extra.
- `revision` (sequência do ledger, sobe em toda escrita) foi separada de `version` (versão de
  identidade, sobe só em mudança de rosto/corpo/cabelo/roupa/voz). A semântica de `version`
  da ETAPA 2 foi preservada porque testes antigos dependem dela.

### Regras novas, todas cobertas por teste

| Regra | Comportamento |
| --- | --- |
| Mudança de identidade sem autorização | 409, e **nada** é gravado no histórico |
| Todo write exige `actor` e `reason` | 422 sem eles |
| Personagem novo | nasce `planned`, não gera |
| Aprovação de identidade indefinida | 409 — aprovação certifica identidade, nunca a inventa |
| Edição administrativa (LoRA, estilo) | registrada, mas não sobe `version` |
| Revisão que não muda nada | 409 `changes nothing` |
| Episódio já publicado | mantém o snapshot original, imune a revisões posteriores |
| Episódio sem snapshot | reportado como ausente, nunca inferido como consistente |

### Corrigido

- **`drift()` contradizia o próprio docstring**: dizia "identity fields" mas incluía
  `lora_path`, misturando churn administrativo com deriva de identidade. Agora filtra por
  `PERSONA_IDENTITY_FIELDS`; o histórico continua registrando tudo.
- **`_episodes` declarado com `field(default_factory=dict)` em classe comum** — produziria um
  objeto `Field` compartilhado entre instâncias. Movido para o `__init__`.

### Verificado

| Verificação | Antes | Depois |
| --- | --- | --- |
| `pytest backend/tests -q` | 222 passed | **282 passed** |
| Ordem inversa dos arquivos de teste | — | **282 passed** |
| Os 22 testes originais, isolados | 22 passed | 22 passed |
| `core/persona_memory.py` | — | **100%** (151 stmts, 0 miss) |
| `backend/app/core/` | 95% | **96%** |
| Cobertura total do backend | 75% | **78%** |
| `npm run build` | ✓ | ✓ Compiled successfully |
| Rotas `/api/v1` | 29 | **37** |
| **Rotas removidas** | — | **nenhuma** |

Diff de inventário contra o baseline pré-Core (HTTP + WebSocket, 30 entradas): **0 removidas,
10 adicionadas** (2 da ETAPA 2 + 8 desta).

### Explicitamente NÃO feito nesta etapa

- **Ledger em memória.** Um processo reiniciado perde o histórico; episódios idem. A costura
  `PersonaSource` está pronta e testada, mas a migração para PostgreSQL não foi feita.
- **As rotas novas não têm autenticação**, seguindo o padrão das `/core/*` existentes — o
  P0-4 da auditoria permanece aberto.
- **Nenhum personagem novo foi inventado.** `CHAR_JEFFERSON` continua `planned`, sem
  atributos, e `approve()` recusa promovê-lo.
- A UI ainda não consome essas rotas (ETAPA 15). `hub.publish` segue sem chamadores (P0-3).

---

### Adicionado

- **`backend/app/spec_adapter.py`** — tradução de um `Job` persistido em
  `GenerationSpec`, passando pelo `GenerationSpecBuilder`. É o único módulo que conhece
  `app.schemas.Job` **e** o Core ao mesmo tempo, então o Core continua sem saber que a
  camada de API existe. `resolve_model_id()` mapeia id de catálogo para id carregável e
  **nunca inventa um repositório**: id desconhecido cai no fallback.
- **`GenerationSpec` recebeu extras tipados** além dos 19 obrigatórios (que permanecem
  intactos em `GENERATION_SPEC_FIELDS`): `resolution`, `guidance_scale`, `steps`,
  `ip_adapter_scale`, `mode`, `cinematic_mode`, `slow_motion`, `native_audio`,
  `reference_path`. Eles existem porque um provider não pode receber mais nada além do
  spec — então os parâmetros de sampling viajam **dentro** dele, tipados, em vez de
  chegarem num `dict` solto ao lado.
- **`health()` em cada provider** — reporta `available`, `reason`, `model_id` e `loaded`.
  Retorna `available: false` honestamente onde não há CUDA.
- **`CONSUMED_SPEC_FIELDS` / `UNSUPPORTED_SPEC_FIELDS`** declarados em cada provider. O
  que o Wan local não honra (`native_audio`, `slow_motion`, `controlnet`, …) fica
  declarado em vez de ser descartado em silêncio.
- **Testes:** 2 arquivos novos, **46 testes** (total do backend: 176 → **222**).

### Alterado — a mudança central da etapa

**Todo provider recebe apenas `GenerationSpec`.** Antes:

```python
FluxDiffusersProvider(...).generate(job.prompt, parameters, settings.weights_dir)   # str + dict
```

Depois:

```python
provider.generate(spec, settings.weights_dir)                                       # spec apenas
```

- `ImageProvider` e `VideoProvider` viraram **ABC** com `generate(spec, output_dir)`
  abstrato. A assinatura é o ponto de aplicação da regra: um provider *não consegue*
  receber um prompt solto, porque não aceita um.
- `queue.py` monta o spec via `compile_job(job)` e injeta `lora` / `reference_path` já
  resolvidos para caminhos locais, **depois** de validar a posse pelo workspace.
- Os dois call sites de `.generate()` no repositório passam exatamente `(spec, output_dir)`.
- `POST /api/v1/core/compile` passou a expor **todos** os campos do spec e a aceitar os
  extras de sampling com validação.

### Corrigido

- **`MemoryStore.get_job` aceitava só `UUID`.** Como o Celery serializa o argumento como
  string, `store.get_job("…")` errava **todo** job e o worker devolvia `cancelled` sem
  nunca executar nada (P0-2a da auditoria). Agora aceita `UUID` ou `str`. Verificado:
  `process_generation(str(id))` passou de `{'status': 'cancelled'}` para
  `{'status': 'complete', 'mode': 'orchestration-only'}`.
- **`frame_count` estava com a lógica invertida.** A docstring dizia "4n+1" mas o código
  retornava múltiplos de 4 (`if frames % 4` é falso justamente quando é múltiplo de 4).
  Para 24 fps × 5 s produzia 120 frames, que o pipeline Wan rejeitaria. Agora
  `frames - (frames % 4) + 1`, sempre 4n+1.
- **Kwargs não suportados eram passados ao pipeline.** O FLUX é *guidance-distilled* e não
  aceita `negative_prompt`; a chamada anterior estouraria num diffusers real. Agora
  `_supported_kwargs()` filtra contra a assinatura do pipeline instalado, em vez de
  hardcodar a assinatura de uma versão.
- **Saídas de provider colidiam.** Ambos escreviam em `image.png` / `video.mp4` fixos,
  então duas gerações concorrentes se sobrescreviam (D-6 da auditoria). Agora o arquivo é
  nomeado pelo `spec_id`.
- **`resolve_model_id`**: o worker passava o id de catálogo (`"flux-1.1-pro-ultra"`) como
  se fosse um repositório HuggingFace. Agora há mapeamento explícito e fallback.

### Verificado

| Verificação | Antes | Depois |
| --- | --- | --- |
| `pytest backend/tests -q` | 176 passed | **222 passed** |
| Os 22 testes originais, isolados | 22 passed | 22 passed |
| Cobertura total do backend | 71% | **75%** |
| `providers/image.py` | 0% | **59%** |
| `providers/video.py` | 35% | **59%** |
| `queue.py` | 20% | **45%** |
| `spec_adapter.py` | — | **100%** |
| `npm run build` | ✓ | ✓ Compiled successfully |
| Call sites de `.generate()` com string solta | 2 | **0** |

O teste `test_the_worker_hands_the_image_provider_only_a_spec` faz a prova ponta a ponta:
patcheia o provider, roda o `process_generation` real com `inference_enabled=True` e afirma
que o provider recebeu uma instância de `GenerationSpec` e mais nada.

### Explicitamente NÃO feito nesta etapa

- **Persistência de `Job` no PostgreSQL (P0-2b) continua aberta.** O bug de chave foi
  corrigido, mas o `store` segue em memória: um worker Celery em **outro processo** ainda
  não enxerga o job da API. Corrigir isso exige migrar `Job` para o banco, o que é uma
  etapa própria.
- Os campos `style`, `persona_id` e `shot` **não fazem parte** dos schemas de requisição de
  geração. O adaptador os encaminha quando existem, mas a UI ainda não os envia — isso é
  trabalho da ETAPA 15.
- A saída continua sendo escrita em `settings.weights_dir` (comportamento pré-existente,
  preservado de propósito). Mover para storage é ETAPA 12.
- Nenhum provider novo: ETAPA 10 continua devendo `HunyuanProvider` e
  `KlingCompatibleProvider`, além de `generate_image()`/`generate_video()`/`estimate_time()`.
- `hub.publish` segue sem chamadores e os endpoints sem autorização seguem abertos
  (P0-3 e P0-4 da auditoria).

---

### Adicionado

**`backend/app/core/` — a camada de decisão.** Sete arquivos novos, 559 statements, **97% de
cobertura** (medido só sobre os arquivos novos; o diretório inteiro, incluindo `config.py`
e o `security.py` morto pré-existente, fica em 95%):

- **`contracts.py`** — vocabulário puro: `GenerationSpec`, `PersonaMemory`, `StylePreset`,
  `ShotPreset`, `SceneBeat`, `DirectorIntent`, `PromptBlocks`, `CompiledPrompt`,
  `GenerationKind`, `PersonaStatus` e os protocols `PersonaSource`, `StyleSource`,
  `ShotSource`, `LanguageModel`. `GENERATION_SPEC_FIELDS` declara os **19 campos
  obrigatórios** uma única vez; `SPEC_SCHEMA_VERSION = "1.0"`.
- **`memory_resolver.py`** — `MemoryResolver` com seeds canônicos
  (`CHAR_PETRICK` aprovado, `CHAR_JEFFERSON` planejado sem identidade inventada),
  frase de identidade, `is_generable()` e `revise()`, que **recusa mudança de identidade
  sem autorização explícita** e abre nova versão quando autorizada.
- **`style_resolver.py`** — `StyleResolver` com os 5 estilos nomeados na missão
  (IMAX HERO, JOHN WICK, LUXURY FASHION, NEO TOKYO, MARVEL TRAILER) mais o padrão
  `cinematic-realism` e o neutro. Cada um carrega lens, lut, lighting, contrast, grain,
  camera_motion, particles e fps.
- **`shot_resolver.py`** — `ShotResolver` com os **10 códigos já publicados** em
  `knowledge_base/SHOT_LIBRARY.md` e `knowledge.py`, cada um com camera path, speed, lens,
  focus, shake, depth e intenção. Códigos são identificadores estáveis: nada foi renumerado.
- **`prompt_compiler.py`** — `PromptCompiler`, o único lugar onde texto de prompt é
  produzido. Blocos na ordem SUBJECT → PERSONA → ENVIRONMENT → STYLE → CAMERA → LENS →
  LIGHT → MOTION → CONTINUITY → OUTPUT, negative prompt com o guarda do `STYLE_GUIDE.md`,
  orçamento de caracteres com corte **relatado** (`CompiledPrompt.dropped`) e compilação
  determinística.
- **`director_agent.py`** — `DirectorAgent` determinístico: `"Quero vender uma camiseta"`
  → conceito, formato, logline, roteiro, 4–8 beats (objetivo, emoção, câmera, luz,
  movimento, duração), música, ritmo e duração total. Detecta formato
  (reels/fashion/story/commercial/film) e paleta (luxo/futuro/legado/disciplina) em
  português e inglês, e devolve **uma pergunta curta de direção** quando a intenção é
  ambígua. Nenhum prompt técnico é produzido aqui.
- **`generation_spec_builder.py`** — `GenerationSpecBuilder`, a raiz de composição, com
  `ResolutionTrace` registrando a origem de cada campo contestado.

**API (2 rotas novas, aditivas):**

- `POST /api/v1/core/direct` → `DirectorBriefResponse`
- `POST /api/v1/core/compile` → `GenerationSpecResponse` (dry run, não gera mídia nem cria job)

**Testes:** 9 arquivos novos, **154 testes** (total do backend: 22 → **176**). Inclui
`test_core_independence.py`, que prova a independência importando cada módulo num
interpretador fresco com `app.core.__init__` stubbed.

**Documentação:** `CHANGELOG.md` (este arquivo); seções novas em `ARCHITECTURE.md`,
`README.md`, `backend/README.md` e `ROADMAP.md`.

### Alterado

- **`backend/app/main.py`** — a raiz de composição do Core foi adicionada no boundary da
  aplicação. A lógica de direção que vivia dentro de `POST /api/v1/storyboards/expand`
  (a `camera_progression` inline e o laço de cenas) **saiu da rota** e foi para o
  `DirectorAgent`. Nenhuma rota foi removida: 28 → 30 rotas HTTP, 2 WebSockets mantidos.
- **`backend/app/prompt_engine.py`** — virou **fachada** do `PromptCompiler`. `PromptEnhancer`,
  `default_style` e `enhance(prompt, style, persona, camera, lighting)` mantêm exatamente a
  mesma assinatura; a composição passou a acontecer no Core. Ganhou `compile()` e
  `compose_scene_prompt()`.
- **`backend/app/schemas.py`** — modelos novos e aditivos: `DirectorRequest`,
  `DirectorBriefResponse`, `SceneBeatResponse`, `GenerationSpecRequest`,
  `GenerationSpecResponse`. Nenhum modelo existente foi alterado.
- **`backend/app/core/__init__.py`** — docstring original preservado e expandido; exporta a
  superfície pública do Core.

### Comportamento

- O prompt compilado mudou de formato: de uma única frase
  `"Ultra-realistic {style} scene of {subject}..."` para blocos ordenados separados por
  vírgula. A assinatura de qualidade (`cinematic composition, high dynamic range, film
  grain, IMAX quality`) e os padrões (`cinematic realism`, `medium shot, 85mm lens`,
  `soft volumetric light`) são **preservados literalmente**, e todo texto do usuário passa a
  ser o bloco SUBJECT — nunca o prompt inteiro.
- Todo prompt passa a carregar um negative prompt com o guarda do `STYLE_GUIDE.md`
  (pele plástica, oversharpening, estética genérica de IA).
- Storyboard: os campos `number`, `title`, `duration_seconds` e a câmera da cena 1
  (`"wide establishing shot, ..."`) são idênticos aos anteriores. A marcação de
  continuidade passou de sufixo `"... Continuity beat 1 of 4."` para o bloco CONTINUITY.

### Verificado

| Verificação | Antes | Depois |
| --- | --- | --- |
| `pytest backend/tests -q` | 22 passed | **176 passed** |
| Cobertura total do backend | 56% | **71%** |
| Cobertura de `backend/app/core/` | — | **95%** |
| `npm run build` | ✓ Compiled successfully | ✓ Compiled successfully |
| Rotas `/api/v1` | 27 | 29 (0 removidas) |
| Testes nas 3 formas de invocação | — | 176 passed em todas |

### Explicitamente NÃO feito nesta etapa

- **ETAPA 3** — providers continuam recebendo `dict` de parâmetros; o `GenerationSpec` ainda
  não é a entrada de `FluxDiffusersProvider`/`WanVideoProvider`.
- **Persistência** — personas, estilos e shots são seeds em memória com fonte injetável.
  Não há tabelas `Personas`, `Styles` nem `Shots`, e não há Alembic.
- **Os 4 P0 da auditoria continuam abertos**: jobs em memória, worker Celery que não
  encontra o job (chave `UUID` × `str`), `hub.publish` sem chamadores e endpoints sem
  autorização. O Core não resolve nenhum deles.
- **300 shots** (ETAPA 6) e **Qualidade IA** (ETAPA 14) não foram iniciados.
- Nenhum código existente foi removido. Os 229 linhas mortas apontadas em `AUDIT.md`
  (`backend/app/api/`, `backend/app/services/`, `core/security.py`) permanecem intactas:
  a regra da etapa foi preservar 100% da arquitetura existente.

---

## [0.1.0] — Fundação

Fatia vertical inicial: dashboard Next.js, API FastAPI com auth JWT e workspaces, upload
de assets (local e MinIO), contratos de geração de imagem e vídeo, prompt engine,
storyboard, personas com contrato de treino de LoRA, conditioning, readiness de GPU,
export FFmpeg e blueprint de deploy no Render. 22 testes, 56% de cobertura.

Auditoria completa em [`AUDIT.md`](AUDIT.md).
