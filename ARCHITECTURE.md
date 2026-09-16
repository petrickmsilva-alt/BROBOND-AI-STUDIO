# BROBOND AI STUDIO — ARCHITECTURE

## Camadas

```text
Frontend/       Next.js, TypeScript, design system, workspace UX
Backend/        FastAPI, auth, REST, WebSocket, orchestration
Core/           memory, prompt engine, director, policy, roadmap
AI Engine/      provider adapters for FLUX, Wan, Hunyuan, ControlNet, IP Adapter
Render Engine/  Celery, Redis, GPU workers, FFmpeg, queue lifecycle
Database/       PostgreSQL, SQLAlchemy, Alembic, workspace metadata
Assets/         MinIO, signed URLs, local development adapter
Knowledge Base/ Cinematic Bible, style, characters, shots, prompts, presets
```

## BROBOND CORE

O Core é a camada de decisão. Ele consulta a Knowledge Base, resolve memória de persona, combina preset cinematográfico, expande o prompt e entrega um `GenerationSpec` versionado ao Render Engine.

```text
User Intent
  -> Director Agent
  -> Memory Resolver
  -> Prompt Composer
  -> GenerationSpec
  -> Provider Adapter
  -> Queue / GPU Worker
  -> Asset + Event Stream
```

### Componentes implementados (ETAPA 2)

Os componentes independentes originais vivem em `backend/app/core/` e importam **apenas**
`core/contracts.py`. Nenhum importa um par; a composição acontece por injeção no boundary da
aplicação (`app.main`), nunca entre componentes. PR005 acrescenta um pacote de orquestração de
planejamento em `backend/app/core/director/`; PR006 adiciona nele `StoryboardState` e
`StoryboardHistory` para edição visual do plano. Esse pacote continua livre de providers e
frameworks.

| Arquivo | Componente | Responsabilidade única |
|---|---|---|
| `contracts.py` | — | Vocabulário puro: dataclasses congeladas, enums e protocols. Zero comportamento. |
| `memory_resolver.py` | `MemoryResolver` | Identidade permanente de personagem, frase de identidade e versionamento. |
| `style_resolver.py` | `StyleResolver` | Estilo escolhido → vocabulário técnico completo (lens, lut, lighting, contrast, grain, motion, particles, fps). |
| `shot_resolver.py` | `ShotResolver` | Código estável `SH###` → preset de direção (camera path, speed, lens, focus, shake, depth). |
| `prompt_compiler.py` | `PromptCompiler` | **Único lugar onde texto de prompt é produzido.** Blocos ordenados + negative prompt. |
| `director_agent.py` | `DirectorAgent` | Intenção em linguagem natural → conceito, roteiro, cenas, câmeras, música, duração. |
| `generation_spec_builder.py` | `GenerationSpecBuilder` | Raiz de composição: combina os quatro anteriores e produz o `GenerationSpec`. |
| `director/storyboard_state.py` | `StoryboardState` | PR006: estado versionado de edição do plano, timeline, drag/reorder, presets de câmera/mood e undo/redo. |

`test_core_independence.py` prova a independência de forma estrutural: cada módulo é
importado num interpretador fresco, com `app.core.__init__` stubbed, e o teste falha se
qualquer par for puxado junto.

### Regra de precedência do builder

Explícito vence inferido; inferido vence padrão. Toda decisão fica registrada num
`ResolutionTrace`, para que um frame gerado possa responder "por que ficou assim?".

```text
style     request.style > persona.default_style > library default
lens      request.lens  > shot.lens            > style.lens
camera    request.camera > shot.camera_phrase  > style.camera_motion
lighting  request.lighting                     > style.lighting
motion    request.motion > shot.motion_phrase  > style.motion_phrase
fps       request.fps                          > style.fps
lora      request.lora                         > persona.lora_path
```

Estilo **ausente** cai no padrão BROBOND; estilo **desconhecido** cai em neutro — nunca
empresta a aparência de outro estilo, porque isso deturparia o pedido em silêncio.
Shot desconhecido retorna `None`: inventar linguagem de câmera é pior que omitir.

## Diretor IA (ETAPA 7)

`DirectorAgent` transforma intenção em direção. O usuário nunca escreve prompt técnico.
Continua **determinístico**: nenhum LLM é carregado e nenhum é fingido; `_enrich` é um gancho
opcional que degrada em silêncio.

### Escolha de formato por especificidade

```python
detect_formats("reels para vender meu produto na loja")
# [("commercial", 3), ("reels", 1)]
```

Ranqueia por **quantidade de palavras-chave** casadas. Antes valia a ordem de declaração do
dicionário: `reels` ganhava com uma palavra contra três comerciais, porque estava declarado
primeiro. Empate mantém a ordem de declaração — regra documentada, não acidente.

Quando há empate real (`"fashion story"` → `fashion` 1, `story` 1) o diretor **não escolhe em
silêncio**: `detect_format_conflict` devolve os empatados e a `clarification` nomeia os dois.
Uma intenção clara continua sem pergunta.

### Os seis formatos

`reels` · `fashion` · `story` · `commercial` · `documentary` · `film`

`documentary` foi restaurado na ETAPA 7: estava dobrado em `film` (pt) ou ausente (en), o que
tornava `ARC_BY_FORMAT["documentary"]` e os 24 presets da família código morto. Declarado
antes de `film` de propósito — "documentário de cinema" carrega os dois vocabulários e a
leitura documental é a mais específica.

### Ritmo declarado = ritmo entregue

`pacing` carrega `{shot}`, preenchido com a duração que os beats de fato carregam. A linha de
reels prometia `"1.5s por plano"` enquanto todo beat saía a 5.0s.

### Oito beats distintos

`objectives` e `emotions` têm oito entradas por idioma, casando com `MAX_BEATS`. Com quatro,
os beats 5-8 repetiam os 1-4 palavra por palavra.

**`CAMERA_LADDER` continua com quatro** e ciclando: estabelecer → conduzir → intensificar →
isolar é gramática visual, fixada por teste, não repetição acidental.

## Director AI Engine (PR005)

`backend/app/core/director/` é o pacote de planejamento cinematográfico completo. Ele não
substitui o `DirectorAgent` histórico de `/core/direct`; ele acrescenta uma saída de produção:
`ProductionPlan`.

```text
Human Intent
  -> MoodEngine
  -> CameraDirector (ShotLibrary existente)
  -> Storyboard de 4 a 8 ShotPlan
  -> PromptCompiler (planejamento textual)
  -> ProductionPlan imutável
```

Contratos:

- `ProductionPlan`: `id`, `title`, `concept`, `mood`, `audience`, `platform`, `duration`,
  `style`, `music`, `voice`, `persona_id`, `shots`, `created_at`.
- `ShotPlan`: `scene_number`, `title`, `objective`, `emotion`, `camera`, `lens`, `lighting`,
  `motion`, `duration`, `prompt`, `negative_prompt`, `environment`.
- `MoodEngine`: presets internos `Luxury`, `Epic`, `Dark`, `Minimal`, `Sport`, `Neo` com LUT,
  contraste, iluminação, temperatura, ritmo e partículas declarados em `mood_config.py`.
- `CameraDirector`: escolhe automaticamente `Dolly`, `Orbit`, `Crane`, `Tracking`, `Static` ou
  `Drone` a partir da `ShotLibrary`; a UI pode editar depois.

Boundary:

- `POST /api/v1/core/director/production-plan` retorna somente planejamento.
- Nenhum provider FLUX/Wan foi alterado, importado pelo pacote ou executado.
- Nenhum job de geração é criado por essa rota.

---

## Storyboard Cinematic Engine (PR006)

PR006 fica depois do `ProductionPlan`: ele transforma o storyboard em um editor visual
versionado, mas continua sem renderização.

```text
ProductionPlan
  -> StoryboardState(project_id, production_plan_id, scenes, version, updated_at)
  -> operações de edição granular
  -> timeline recalculada
  -> histórico undo/redo
```

Contratos:

- `StoryboardState`: estado imutável/versionado do editor. Toda alteração real incrementa
  `version` e atualiza `updated_at`.
- `StoryboardScene`: cena editável com `id`, `scene_number`, título, objetivo, emoção,
  câmera, lente, iluminação, movimento, duração, ambiente, mood, LUT, prompt e negative prompt.
- `StoryboardHistory`: histórico com `past`, `present`, `future` e limite de 50 estados.
- `lib/storyboard/storyboard_state.ts`: espelho de frontend usado pelos componentes visuais.

Operações suportadas:

- editar campo da cena sem recriar a cena inteira;
- reordenar por drag/drop, recalculando `scene_number`, timeline e duração total;
- aplicar presets de câmera `Hero Walk`, `Orbit`, `Tracking`, `Crane`, `Drone`, `Static` só no
  bloco CameraDirector (`camera`, `lens`, `lighting`, `motion`);
- aplicar mood por cena (`Luxury`, `Epic`, `Dark`, `Minimal`, `Sport`, `Neo`) alterando apenas
  `mood` e `lut`;
- duplicar cena com novo UUID mantendo câmera e mood;
- remover cena mantendo o storyboard válido;
- undo/redo das operações editar, reordenar, duplicar e remover.

Frontend:

```text
app/studio/director/
├── StoryboardCanvas.tsx
├── Timeline.tsx
├── SceneInspector.tsx
├── CameraPanel.tsx
├── MoodPanel.tsx
└── page.tsx
```

A API não ganhou rota de render. O editor consome o plano de
`/api/v1/core/director/production-plan` e mantém as edições em `StoryboardState`.

---

## Testes e cobertura (ETAPA 16)

O piso é imposto no CI, não apenas medido:

```
coverage run --source=backend/app -m pytest backend/tests -q
coverage report --include='backend/app/*' --skip-empty --fail-under=95
```

### O denominador tem 100 statements que nunca rodam

Quatro módulos formam um cluster fechado que nada importa **e que não importa com sucesso**:

| Módulo | Statements | Por que não importa |
| --- | --- | --- |
| `app/api/routes.py` | 51 | depende de `core.security` |
| `app/core/security.py` | 14 | `get_settings` nunca existiu em `core.config` |
| `app/services/generation.py` | 23 | `app.schemas` é módulo, não pacote |
| `app/api/dependencies.py` | 12 | depende de `core.security` |

É o P0-1 do `AUDIT.md`. Não apagado (instrução permanente) e não consertado — consertar
significaria ressuscitar um segundo backend que duplica `main.py`, que é exatamente o que
"preservar 100% da arquitetura" quer evitar. `test_dead_module_boundary.py` fixa a fronteira:
se algum deles passar a importar, um teste falha e o evento é notado em vez de virar uma
melhora silenciosa de cobertura.

### O que os testes substituem e o que não substituem

As dependências ausentes (GPU, `diffusers`, Pillow, FFmpeg, Redis, MinIO) são **a condição que
o código foi escrito para detectar**, então a maior parte dos testes afirma a recusa. Onde a
lógica atrás da recusa é pura, a dependência é substituída e o ramo é alcançado — parsing do
CSV do `nvidia-smi`, dispatch do preprocessing, escolha da classe de pipeline, nomeação do
arquivo de saída por `spec_id`, filtragem de kwargs contra a assinatura do pipeline.

Nada disso prova que um modelo real roda. Prova que o código toma a decisão certa sobre o que
tem na frente.

---

## Interface (ETAPA 15)

O frontend é Next.js (App Router) na raiz: `app/page.tsx`, `lib/api.ts`, `app/globals.css`.

### O browser não recebe origem fixa

`lib/api.ts` usa base vazia e `next.config.mjs` faz rewrite de `/api/v1/:path*` para o
backend. O alvo é `BROBOND_API_PROXY_TARGET`, não um literal. Antes, `API_URL` default era
`http://localhost:8000` — só funciona com o browser na máquina da API.

`wsUrl(path)` deriva o WebSocket de `window.location.origin`, então o socket passa pelo mesmo
proxy (verificado com handshake: `101 Switching Protocols`).

### Contrato de resultado

```ts
type ApiResult<T> = { data: T; remote: boolean; status?: number; error?: string }
```

`remote` continua significando "chegou dado utilizável". `status` e `error` separam os dois
casos que antes eram um só: **sem resposta** (`error: 'offline'`) e **o servidor respondeu com
erro** (401, 422, 500 — com o `detail` do FastAPI extraído). Cada painel tem um `Notice`.

### A porta de entrada é o Diretor

`DirectorStudio` é o módulo padrão. Ele consome `/api/v1/core/direct` e mostra conceito,
logline, roteiro, beats, música, ritmo e duração — nunca um prompt. Quando
`brief.clarification` vem preenchida, a pergunta do diretor aparece em destaque.

### Nada é inventado

| Antes | Agora |
| --- | --- |
| `RTX 4090 · 18.4 / 24 GB VRAM` | `/api/v1/system/gpu` — ou "No GPU" com a mensagem real |
| `Good evening, Petrick` | saudação pela hora do dia + nome de quem está logado |
| `128 / 84 / 24 / 2 / 18` assets | contados do array real |
| `72 / 2,000` | `{prompt.length} / 2,000` |
| `LoRA v1.2` | "no LoRA trained" até existir run |
| figura CSS "FLUX / 2K" | `<img src={job.output_url}>`, ou "The render failed — no image was produced" |

A última linha é a que importa: a tela mostrava a mesma imagem para `complete` e para
`failed`.

---

## Gate de qualidade (ETAPA 14)

`QualityGate` é o 12º componente independente do Core e roda **entre** a geração e a
persistência:

```
provider.generate(spec) -> quality_gate.assess(spec, output) -> storage.save_path -> complete
                                    |
                                    +-- violação -> job failed, output_url fica None
```

### O que confere

| Regra | Bloqueia | O que verifica |
| --- | --- | --- |
| `file-present` | sim | um arquivo foi de fato escrito no caminho relatado |
| `file-not-empty` | sim | tem ao menos um byte |
| `dimensions-reported` | imagem sim / vídeo não | o produtor relatou largura e altura |
| `resolution-floor` | sim | o lado curto tem ao menos 64px |
| `aspect-ratio` | sim | a razão está a até 3% da pedida |
| `duration` | sim | vídeo: o runtime bate com o spec |
| `frame-rate` | não | vídeo: o fps bate com o spec |
| `container` | não | a extensão casa com o tipo renderizado |

### Por que `dimensions-reported` difere por tipo

Os dois contratos de saída não são iguais, e a gate os segue em vez de exigir o mesmo de
ambos: `GenerationOutput` carrega `width` e `height` como campos obrigatórios, enquanto
`VideoGenerationOutput` carrega duração e fps e **nenhuma geometria**. Exigir dimensões de um
vídeo reprovaria todo job de vídeo do sistema. Na imagem a ausência é contrato quebrado; no
vídeo é "não reportado", as verificações de geometria são puladas e um aviso é emitido.

### Veredito

`pass` (sem achado) · `warn` (só avisos — **não bloqueia**) · `fail` (há violação). Reencodar
para 30fps é recuperável; um arquivo ausente não é.

### O que não é avaliado, e por quê

Nenhum modelo é carregado. `capabilities()` devolve `model_loaded: false` e lista
`does_not_assess`: composição, aderência ao prompt, detecção de artefatos, qualidade
estética, semelhança de persona. Nada neste processo vê a imagem, e inventar um número que
parecesse uma nota estética é exatamente o que `SYSTEM_PROMPT.md` proíbe.

`structural_score` é a fração das verificações estruturais aplicáveis que passaram. Com
nenhuma verificação aplicável devolve **0.0** — "não aprendemos nada" não pode ler como
"está bom".

### A origem da geometria é visível

`facts.dimensions_source` vale `"provider-report"`: a gate compara a **alegação** do produtor
contra o spec. Conferir contra os pixels exige Pillow ou ffprobe; `verify_dimensions` faz isso
quando há leitor disponível e devolve `verified: false` com o motivo quando não há — nunca
relata uma verificação que não fez.

---

## Linha de tempo de vídeo (ETAPA 13)

`VideoTimeline` é o 11º componente independente do Core: importa `contracts` e nada mais, e
está em `INDEPENDENT_MODULES`.

### O que é, e o que não é

Uma `Timeline` é um **plano de montagem**: ordem dos clipes, pontos de entrada e saída,
transições, cama de áudio e geometria de entrega. **Não é um arquivo.** Clipes sem mídia
renderizada voltam marcados como tal e `complete` permanece `false` até que todos tenham uma
origem real — `SYSTEM_PROMPT.md` proíbe inventar outputs.

### Transição

| Situação | Transição |
| --- | --- |
| primeiro clipe | `cut` (não há de onde vir) |
| mesma família do anterior | `dissolve` (continuação de uma ideia) |
| família diferente | `cut` (mudança de ideia) |
| família vazia | `cut` (dois clipes sem família não são "a mesma ideia") |

`StoryboardEngine.TRANSITION_FAMILIES` parece o gatilho óbvio e **não funciona**: nenhum arco
de `ARC_BY_FORMAT` escala `transition` ou `atmosphere`, então a interseção é vazia. Cinco dos
sete arcos repetem uma família e dissolvem ali; `film` e o arco padrão mudam de ideia a cada
beat e ficam todos em corte — as duas metades da mesma regra.

### Geometria de entrega

`ASPECT_BY_FORMAT` manda `reels` e `story` em `9:16` e os demais em `16:9`. A caixa vertical
é a tabela trocada, não uma resolução separada, e `RESOLUTIONS` confere com `media.QUALITY` —
um teste garante que "1080p" significa o mesmo nos dois lugares.

### Duração derivada, não somada

`duration_seconds` vem do fim do último clipe. Somar durações esconderia um buraco no meio do
corte; assim o número mostra o problema.

### Validação

Mesmo contrato do `StoryboardEngine.validate`: um relatório, nunca uma exceção. `runtime` usa
o **mesmo teto** (`MAX_RUNTIME_SECONDS`), para que uma sequência não passe num e falhe no
outro. Clipes não renderizados são aviso, não violação — e nunca passam em silêncio.

### Onde o FFmpeg entra

`VideoTimeline` nunca chama `subprocess` nem conhece o binário; renderizar é da camada de
aplicação. `media.concat` executa o plano e `media.probe` inspeciona um arquivo. A construção
dos argumentos vive em `concat_command` e `probe_fields`, funções puras testáveis sem o
binário instalado.

---

## Storage (ETAPA 12)

Uma única classe, dois backends. Tudo aqui é API S3 — que é o que o MinIO fala —, então uma
implementação cobre os dois. O pacote `minio` fixado em `requirements.txt` **não** é usado.

| Operação | Modo local | Modo S3/MinIO |
| --- | --- | --- |
| `save` / `save_path` | grava em `media/` | `upload_fileobj` / `upload_file` |
| `upload_path` | cópia só se a chave diferir | upload para chave **do chamador** |
| `download` | devolve o arquivo já local | `download_file` |
| `exists` | `Path.is_file()` | `head_object` |
| `delete` | `unlink` guardado por `local_path` | `delete_object` |
| `signed_url` | `/api/v1/assets/download/{key}` | presigned, `PRESIGNED_TTL_SECONDS` |
| `ensure_bucket` | garante o diretório | `head_bucket` → `create_bucket` |

### Por que `download` importava

Sem um primitivo de leitura, três funcionalidades respondiam 501 assim que
`storage_enabled` era verdadeiro — condicionamento, export e o carregamento de
LoRA/referência no worker. O 501 não era uma decisão de produto; era a ausência de uma
função. Com `download` os quatro pontos passaram a funcionar nos dois backends.

### `upload_path` versus `save_path`

`save_path` **gera** uma chave (`{workspace}/{uuid}-{nome}`), que é o certo para um arquivo
novo. Export e condicionamento derivam a chave do asset de origem
(`{workspace}/exports/{asset}-{qualidade}.mp4`) e ela precisa permanecer estável, porque é a
que já foi escrita na linha `Asset`. `upload_path` existe para esse caso.

### O guard de caminho

```python
root = self.local_root.resolve()
path = (root / key).resolve()
if root not in path.parents:
    raise ValueError("Invalid asset path")
```

`download_local_asset` converte o `ValueError` em 400. Verificado contra `../etc/passwd`,
`/etc/passwd`, `ws/../../etc/passwd`, `""` e `"."` — todos recusados. Até a ETAPA 12 essas
linhas nunca tinham sido executadas por teste algum.

### Cliente sob demanda

O cliente boto3 é uma propriedade com cache, não um atributo de `__init__`. Importar
`app.storage` não resolve credenciais nem região, e `storage.client = FakeS3()` funciona em
teste.

---

## Fila de jobs e eventos (ETAPA 11, persistência no PR002, Repository Pattern no PR004-prep)

O fluxo de um job é: `POST /api/v1/generations/*` cria o job no **repositório** →
`process_generation(job_id)` (Celery) executa a partir do id — lê o job num processo
diferente → o cliente acompanha por `/api/v1/queue/events/{job_id}` autenticado.

PR002 mudou a base do fluxo: jobs deixaram o `dict` em memória (`MemoryStore`; o `dict` de
personas do mesmo store ficou **Legacy** no PR003 — personas agora vivem em
`repositories/persona_repository.py`) e viram `JobRow`. `transition()` persiste **e** emite no
mesmo passo, e o estado terminal `complete` interno é respondido como `completed` na borda
(`events.external_status()` / `schemas.JobResponse`) sem renomear o enum — contrato interno
e clientes existentes intactos.

**PR004-prep (Repository Pattern):** o fluxo de jobs não depende mais diretamente do
PostgreSQL. A separação é em três camadas, com dependência apontando para dentro:

```text
JobService (core/job_service.py)     regra de negócio: máquina de estados, validação
        |  conhece SOMENTE a interface — injetada no construtor
        v
JobRepository (protocol)             repositories/job_repository.py — 6 operações
        +-- PostgresJobRepository    (default) tabela jobs — o único job módulo com SQLAlchemy
        +-- RedisJobRepository       (opt-in)  JSON em hashes + set por workspace
        +-- MemoryJobRepository      (testes)  dict isolado, sem I/O
```

A troca de backend é uma linha no composition root (`app/job_service.py`); o Core, as
rotas e o worker não mudam. O Core troca o `Job` do Pydantic por um value object próprio
(`core.job_service.Job`) — o mapeamento vive na borda (`app/jobs.py`). O facade
`app/store.py` (superfície histórica `store.add_job` etc.) permanece, agora **delegando**
ao `JobService` e sem nenhum import de SQLAlchemy. `queue.store` segue acessível por
compatibilidade com call sites e testes existentes.

### `transition()` é o único ponto de mutação

```python
transition(job, JobStatus.RUNNING, PROGRESS_RENDERING, event=EVENT_PROGRESS)
```

Escreve `job.status` e `job.progress`, **persiste** via `JobService.transition()` (que
valida a máquina de estados e delega ao `JobRepository` injetado — default: a tabela
`jobs`) **e** emite o evento, no mesmo passo. Antes cada call site atribuía os dois campos
diretamente e nada era emitido — por isso `EventHub.publish` não tinha chamador algum: não
existia um instante que significasse "o job andou".

`status` e `progress` são ambos opcionais, para que um tick de progresso não precise
reafirmar o status. Um teste estrutural varre o AST de `queue.py` e falha se qualquer
função que não seja `transition` escrever `job.status` ou `job.progress`.

| Constante | Valor | Significado |
| --- | --- | --- |
| `PROGRESS_STARTED` | 10 | o worker pegou o job |
| `PROGRESS_SPEC_COMPILED` | 25 | `GenerationSpec` compilado |
| `PROGRESS_INPUTS_RESOLVED` | 40 | referências e condicionamento resolvidos |
| `PROGRESS_RENDERING` | 55 | inferência em andamento |
| `PROGRESS_PERSISTED` | 90 | output persistido no storage |
| `PROGRESS_DONE` | 100 | concluído |

### Contrato de evento

Todo evento tem exatamente `{job_id, event, status, progress, at}`. `output_url` e `error`
aparecem só quando significam algo. Os nomes vêm de `JOB_EVENTS`
(`queued, started, progress, complete, failed, cancelled`); `TERMINAL_STATUSES` é
`{complete, failed, cancelled}` e é o que encerra o stream.

PR002: o campo `status` do payload é o nome **externo** — `external_status()` mapeia
`complete` → `completed` num único lugar (dentro de `job_event`), enquanto o nome do
**evento** continua `complete` (é um identificador de contrato, não um valor de estado).
Toda a superfície que cruza a borda (eventos, snapshot do WS, `JobResponse`) passa por essa
mesma função; o banco e o worker seguem falando `complete`.

### Por que `publish_sync` e não `publish`

O worker é tarefa Celery **síncrona**; o `EventHub` é asyncio-only (`asyncio.Lock`,
`await send_text`). `await hub.publish(...)` não é chamável de dentro do worker.
`publish_sync` **grava o evento incondicionalmente** e só despacha se houver loop rodando —
gravar é o que torna a transição visível a um cliente neste processo.

### Buffer de replay

`EVENT_BUFFER_SIZE` é 64 por job. A rota envia um snapshot do estado atual, drena
`hub.history(job_id, cursor)` e empurra, fechando o socket em status terminal e liberando o
buffer no `finally`. Um cliente que conecta depois do fim recebe o histórico em vez de ficar
preso sem resposta.

### Dois WebSockets, dois mecanismos

| Rota | Mecanismo |
| --- | --- |
| `/api/v1/queue/events/{job_id}` | push via `EventHub` (esta etapa) |
| `/api/v1/personas/{persona_id}/training/events/{run_id}` | polling com `asyncio.sleep(2)` |

O de treinamento nunca foi migrado — fora do escopo desta etapa, registrado como pendência.

PR002: os dois autenticam pelo query parameter `token` (`auth.ws_identity` — browsers não
definem header em handshake de WebSocket) e checam a posse do job/run pelo workspace do
caller. Sem token, ou com token alheio, o socket é fechado com `1008` **antes** do
`accept`. O cliente (`lib/api.ts → wsUrl`) anexa o token do `localStorage` quando existe.

### Limitação conhecida: o hub é in-process

`EventHub` vive no processo da API. Num deploy real, com o worker Celery em outro processo,
os eventos gerados lá não alcançam os sockets abertos na API. Resolver isso exige Redis
pub/sub (o `redis_url` já está em `core/config.py`). **Não foi simulado.**

---

## Provider adapters (ETAPA 10)

`SYSTEM_PROMPT.md` declara FLUX, Wan, Hunyuan, ControlNet e IP Adapter como **adapters
substituíveis**. Até a ETAPA 10 o worker escolhia assim:

```python
if job.type == GenerationType.IMAGE:
    provider = FluxDiffusersProvider(...)   # qualquer que fosse spec.provider
else:
    provider = WanVideoProvider(...)        # qualquer que fosse spec.provider
```

Pedir Hunyuan devolvia Wan sem erro, e a API já anunciava `hunyuan-video` como
`planned-provider` sem nada atrás.

```text
job.parameters["model"]  ->  registry.resolve(id, kind)  ->  registry.check(entry, kind)
                                     |                              |
                            ProviderEntry                     recusa ANTES de carregar
                            (kind, status,                    planned / remote / kind errado
                             module, attribute,
                             model_id, conditioning)
                                     |
                            registry.adapter_class(entry)   <- getattr em tempo de chamada
```

A classe é resolvida por `getattr` **no momento da chamada**, não no import. Isso não é
detalhe: os testes do worker fazem `monkeypatch.setattr(image_module, "FluxDiffusersProvider", Fake)`,
e uma referência capturada cedo venceria o patch.

Um provider **recusado** é diferente de um provider **substituído**. `check()` falha alto
para planejado, remoto ou kind errado — rodar outro modelo em silêncio é como um usuário
recebe saída do pipeline errado sem explicação.

### Uma definição para o que era quatro

Medido antes da mudança:

| Helper | Estado |
|---|---|
| `_generator` | byte-idêntico nos dois arquivos (151 chars) |
| `_apply_lora` | byte-idêntico nos dois arquivos |
| `health()` | idêntico salvo o nome do provider |
| `_supported_kwargs` | idêntico salvo o docstring |

Agora vivem em `providers/common.py` e os módulos os reexportam — são o **mesmo objeto**, não
cópias. Duas cópias de um gerador de seed não é questão de estilo: uma correção aplicada a
uma não se aplica à outra.

### Conditioning como objeto

ControlNet e IP-Adapter eram um `if` dentro do provider FLUX. Dois problemas reais: os pesos
de IP-Adapter eram **SDXL** sobre um pipeline FLUX, e ControlNet não é uma flag — FLUX
ControlNet exige `FluxControlPipeline`, outra classe. Agora `Conditioning` declara o que
precisa e o registry recusa a combinação antes de carregar nada.

Wan e Hunyuan compartilham `_DiffusersVideoProvider` e diferem só onde os modelos diferem:

| | Wan 2.1 | Hunyuan |
|---|---|---|
| pipeline | `WanPipeline` | `HunyuanVideoPipeline` |
| frames (fps 24 × 5s) | **121** (4n+1) | **120** (sem restrição) |
| 16:9 padrão | 832×480 | 1280×720 |
| `num_inference_steps` | não enviado | enviado (`spec.steps`) |

## GPU Provider Orchestrator (PR007)

PR007 adiciona uma segunda camada acima do catálogo da ETAPA 10: o contrato universal de
execução em `backend/app/providers/base_provider.py`. O Core continua responsável por decidir
e compilar `GenerationSpec`; nomes como Flux, Wan, Hunyuan, Kling ou Runway ficam fora de
`backend/app/core/`.

```text
GenerationSpec
  -> ProviderRegistry.get(spec.provider)
  -> BaseProvider.generate_image/generate_video/upscale(spec, ...)
  -> ProviderAsset
  -> Job.asset_url / metadata
```

Componentes:

| Arquivo | Responsabilidade |
|---|---|
| `providers/base_provider.py` | `BaseProvider`, `ProviderCapabilities`, `ProviderEstimate`, `ProviderHealth`, `ProviderAsset`. |
| `providers/provider_registry.py` | `register()`, `get()`, `list()`, `health_all()` por registro/alias, sem `if/else` por modelo. |
| `providers/flux_provider.py` | Conector real de imagem (PR009): text-to-image e image-to-image; recebe apenas `GenerationSpec`. |
| `providers/wan_provider.py` | Conector real de vídeo (PR009): text-to-video e image-to-video; loader de vídeo compartilhado com Hunyuan. |
| `providers/mock_provider.py` | Provider fake obrigatório para testes e desenvolvimento sem GPU; destino padrão do fallback. |
| `providers/generation_executor.py` | Orquestra `GenerationSpec -> Registry -> Provider -> Asset -> Job` com retry, timeout, fallback e telemetria (PR009), sem conhecer IDs de provider. |

`GET /api/v1/providers` expõe health, latência, versão e capabilities (`max_resolution`,
`supports_video`, `supports_image`, `supports_lora`, `supports_upscale`, `supports_seed`,
`supports_negative_prompt`, `prompt_budget`) sem secrets. A página `/studio/providers` usa
essa resposta diretamente para mostrar Flux, Wan e Mock e recarregar status pelo botão
**Testar**.

Prompt budget agora é capability do provider. O compilador aceita um número já resolvido
pela borda; sem isso, usa o budget conservador global e trata o nome do provider como opaco.

## Cinematic Render Engine (PR008)

PR008 conecta o Director AI ao Generation Executor: o storyboard vira imagens e vídeos
reais. O pacote `backend/app/render/` orquestra o fluxo sem conhecer nenhum provider —
a única dependência voltada a providers é o `GenerationExecutor` (PR007).

```text
ProductionPlan / StoryboardState
  -> SceneRenderer (+ PromptCompiler) -> GenerationSpec (uma por cena)
  -> GenerationExecutor -> Registry -> Provider -> ProviderAsset + ProviderJob
  -> RenderAssetPipeline -> PNG/MP4 + thumbnail + metadata (AssetStore)
```

Componentes:

| Arquivo | Responsabilidade |
|---|---|
| `render/render_batch.py` | `RenderBatch`/`RenderScene` com estados `queued/running/rendering/completed/failed/cancelled`, progresso independente por cena e `RenderBatchStore` em memória. |
| `render/scene_renderer.py` | `SceneRenderer`: cena → `GenerationSpec` via `PromptCompiler`, com os campos obrigatórios persona, style, mood, camera, lens, lighting, motion, seed, aspect_ratio e duration. |
| `render/render_orchestrator.py` | `RenderOrchestrator`: cria lotes do plano, executa cena a cena pelo executor, publica progresso e trata cancel/retry. |
| `render/progress.py` | `RenderProgressHub`: push thread-safe dos cinco eventos (`batch_started`, `scene_started`, `scene_progress`, `scene_completed`, `batch_completed`), sem polling. |
| `render/asset_pipeline.py` | `RenderAssetPipeline`: persiste principal + thumbnail + metadados (prompt, seed, provider) pelo `StorageService`, com linhas `Asset` quando há sessão. |

Seis rotas `/api/v1/render/*` (todas com identidade) e o WebSocket `/ws/render/{batch_id}`
alimentam a tela `/studio/render`: storyboard, progresso, cena atual, ETA, preview,
download e Fila com Cancelar/Repetir. Detalhes em `docs/RENDER_ENGINE.md`.

## Real AI Connectors (PR009)

PR009 liga os adapters de PR007 a motores reais (Flux para imagem, Wan 2.1 para vídeo) e
envolve o `GenerationExecutor` com resiliência — tudo dentro de `backend/app/providers/`,
sem tocar Core, Director, Storyboard ou Render Engine.

```text
GenerationSpec
  -> ProviderRegistry.get(spec.provider)   (falha? -> fallback com motivo)
  -> RetryEngine (max 3 tentativas, backoff com cap)
     -> TimeoutManager (Flux 90s / Wan+Hunyuan 300s / default 120s, ENV-override)
        -> BaseProvider.generate_image/generate_video
  -> ProviderAsset + ProviderJob (attempts, fallback, fallback_from, fallback_reason)
  -> TelemetryStore (provider, latency_ms, queue_time, render_time, success, error_code)
```

Componentes novos:

| Arquivo | Responsabilidade |
|---|---|
| `providers/retry_policy.py` | `RetryPolicy`/`RetryEngine`: classificação `RETRYABLE`/`TIMEOUT`/`FATAL`, backoff exponencial, cap de 3 tentativas, hook de decisão. |
| `providers/timeout_manager.py` | Deadline por provider, configurável por ENV (`PROVIDER_TIMEOUT_*_SECONDS`); estouro vira `ProviderTimeoutError` retryável. |
| `providers/telemetry.py` | `ProviderTelemetryRecord` + store thread-safe (500, sink JSONL opcional) + `default_telemetry_store()`. |

Decisões de desenho: erro **fatal** propaga sem fallback (spec inválido não é falha de
provider); o fallback registra o motivo no Job e o Batch nunca se perde; telemetria é
registrada em todo desfecho, inclusive na falha. Rotas públicas novas:
`POST /api/v1/providers/{id}/test` e `GET /api/v1/providers/telemetry`. Detalhes em
`docs/AI_CONNECTORS.md`.

## Cinematic Knowledge Graph (V3.1)

V3.1 persiste o universo BROBOND — personagens, marcas, campanhas, lugares,
veículos, figurino, objetos — em duas tabelas (`graph_nodes`, `graph_edges`,
migração `0003`), com travessia e busca sem framework em
`backend/app/graph/`:

```text
Director AI -> CharacterGraph.context(nome) -> frases ("Petrick dirige RAM")
MemoryResolver(persona) + GraphContextSource -> context_phrases()  (ETAPA 5)
GraphNode/GraphEdge --workspace--> GraphRepository --adapter--> RelationshipEngine
                                                        \---> SemanticQuery
```

O motor (`relationship_engine.py`) é stdlib-only sobre o protocolo
`GraphStore`: 16 relações canônicas, aliases PT (`dirige`/`veste`/`pertence`/
`localizado`), inversas únicas e BFS bidirecional cycle-safe. A busca
(`semantic_query.py`) ranqueia em 8 tiers (100–30) com fold de acentos, sem
embeddings. O repositório vincula os dois a um workspace; id estrangeiro
responde 404, nunca 403. `GraphContext`/`GraphContextSource` estendem
`core/contracts.py` sem tocar `GenerationSpec`; o resolver global continua sem
source de grafo — o enriquecimento é explícito por rota. Doze rotas
`/api/v1/graph/*` (tag `graph`), todas com identidade, e a UI
`/studio/knowledge`. Detalhes em `docs/KNOWLEDGE_GRAPH.md`.

## Prompt compiler (ETAPA 9)

`SYSTEM_PROMPT.md` declara treze blocos. Até a ETAPA 9 só dez eram emitidos e a junção não
deduplicava, então **todo** prompt que carregava um preset de shot repetia a focal
(`"... 35mm, 35mm ..."`): `camera_phrase()` já anexa a focal e `lens_phrase()` começa por
ela, e `_dedupe` existia desde a ETAPA 2 aplicado apenas ao negative prompt.

```text
SUBJECT · CHARACTER · ENVIRONMENT · ACTION · CAMERA · LENS · LIGHT · COLOR
        · MOTION · STYLE · CONTINUITY · OUTPUT        <- PROMPT_BLOCK_ORDER (12 emitidos)
NEGATIVE                                              <- declarado, nunca concatenado
```

`NEGATIVE` fica **fora** da ordem de emissão de propósito: providers de difusão o recebem
como argumento separado, e anexá-lo ao prompt positivo inverteria seu sentido.

Cor e estilo são blocos distintos. `describe()` empacotava nome + LUT + contraste + grain +
paleta numa cláusula só, o que impedia descartar um adjetivo sem perder a paleta. Agora
`style_phrase()` devolve o nome e `color_phrase()` a grade, e `DROP_PRIORITY` coloca
`color` **abaixo** de `style`: sob aperto de orçamento, a grade — que é o que mantém uma
sequência reconhecível entre cortes — sobrevive ao adjetivo.

O orçamento é do provider, não do compilador. PR007 removeu o mapa
`PROVIDER_PROMPT_BUDGET` do Core: `budget_for()` trata o provider como opaco e aceita apenas
um `budget` numérico já resolvido pela camada de provider. O teto `max_prompt_chars` continua
sendo limite duro: um orçamento de provider só pode apertá-lo, nunca afrouxá-lo.

`compile_beats()` consome a projeção `StoryboardEngine.as_beats()` e devolve um prompt por
cena. Assina sobre `SceneBeat` — tipo de `contracts` — e não sobre `Storyboard`: o
compilador importa `contracts` e nada mais, porque está em `INDEPENDENT_MODULES` e
`test_core_independence.py` falha se ele puxar um irmão.

```text
StoryboardEngine.as_beats()  ->  tuple[SceneBeat, ...]  ->  PromptCompiler.compile_beats()
        (ETAPA 8)                  tipo de contrato              (ETAPA 9)
```

## Storyboard engine (ETAPA 8)

Um storyboard não é uma lista de frases de câmera: é uma **escalação**. Cada beat recebe um
shot real da biblioteca de 300 e herda dele lente, luz, movimento e continuidade.

```text
DirectorAgent        beats: objetivo, emoção, duração            (ETAPA 2)
     |
StoryboardEngine     qual shot entra em cada beat, em que ordem,  (ETAPA 8)
     |               e se a sequência se sustenta
     +-- ShotLibrary         os 300 presets de direção            (ETAPA 6)
     +-- CinematicLibrary    a gramática que valida o movimento   (ETAPA 5)
     |
PromptCompiler       único lugar onde texto de prompt nasce        (ETAPA 2)
```

O engine **sequencia**. Não inventa direção, não guarda shots, não é dono da gramática e não
escreve prompt. `validate()` devolve um relatório com `violations` e `attention` em vez de
lançar exceção: um diretor precisa ver *o que* está errado num corte, não apenas saber que
falhou.

```text
arco canonical (commercial, 5 beats)
  establishing -> introduction -> product -> product -> resolution
  24mm      ->  50mm       ->  85mm   ->  135mm  ->  24mm
  ^ abre na geografia                                  ^ fecha na resolução
```

Sequências mais longas repetem o beat de desenvolvimento; mais curtas cortam do meio para
fora, então **abertura e resolução sempre sobrevivem** (`test_opening_and_closing_always_anchor_the_arc`).

`_pick_shot` evita repetição **em todo o storyboard**, não só no corte anterior. Evitar só a
cena anterior satisfaz `no-repeat-cut` e ainda assim produz uma sequência de 12 que alterna
entre dois shots — o que lê como o mesmo plano duas vezes. Esgotada a família, reutiliza-se o
shot visto há mais tempo.

`as_beats()` projeta o storyboard de volta em `SceneBeat` com `shot_code` preenchido, então o
caminho de prompt existente passa a enxergar a biblioteca sem nenhuma mudança no
`PromptCompiler`.

## Biblioteca de shots (ETAPA 6)

300 presets de direção, no alvo que `knowledge_base/SHOT_LIBRARY.md` declara. Um preset é
**direção reutilizável, não um blob de prompt**.

```text
ShotResolver    código -> preset (nunca inventa: desconhecido -> None)
ShotLibrary     os 300, navegáveis + validados contra a Bíblia
CinematicLibrary  a gramática usada na validação            (ETAPA 5)
```

Cada linha autorada carrega só os campos criativos que o documento pede
(`code, name, lens_mm, frame, movement, lighting, intention, continuity`). `speed`, `focus`,
`shake` e `depth` são **derivados** de enquadramento, lente e movimento — um close-up de 85 mm
tem sempre profundidade rasa e um tripé travado nunca treme, então derivar impede que 300
entradas se contradigam.

`violations()` confere os 300 contra a gramática: lente dentro das 5 distâncias declaradas,
movimento com motivação, enquadramento conhecido, intenção presente e — em shots novos —
`frame`/`lighting`/`continuity` preenchidos. **Tamanho não vale nada se as entradas
contradizem o documento que dizem implementar.**

Os 10 códigos publicados são identificadores estáveis e permanecem intactos; os 290 novos
ocupam os códigos livres de `SH001–SH300`. A composição fica em `main.py`, então
`shot_resolver.py` não importa `shot_library.py`.

## Biblioteca cinematográfica (ETAPA 5)

A `knowledge_base/CINEMATIC_BIBLE.md` deixa de ser prosa e vira **gramática consultável +
regras verificáveis**. Fronteira estrita com os componentes existentes:

```text
DirectorAgent      linguagem natural -> intenção -> style_hint    (ETAPA 2)
StyleResolver      style_id -> vocabulário técnico                (ETAPA 2)
ShotResolver       código -> preset de direção                    (ETAPA 2)
CinematicLibrary   o que o vocabulário SIGNIFICA e se obedece     (ETAPA 5)
```

A biblioteca é **descritiva e normativa, nunca decisória**: não produz prompt (o
`PromptCompiler` é o único lugar que produz texto) e não recomenda estilo (isso é do Diretor).
Dois testes travam essa fronteira negando `compile`/`build`/`enhance` e
`recommend`/`style_for`/`direct`.

Seis perfis frozen codificam o documento — `LENSES` (24/35/50/85/135 mm), `FRAMES`, `ANGLES`,
`LIGHTS`, `TIME_QUALITIES`, `MOTIVATIONS` — e os testes comparam as tuplas literalmente contra
a Bíblia, então vocabulário inventado falha no teste em vez de divergir em silêncio.

Oito regras normativas, cada achado citando a frase de origem. Severidade importa:
divergência de grão num episódio é `violation` (a Bíblia diz *"consistent across an
episode"*); quase todo o resto é `attention`.

`audit_library()` roda as regras contra os próprios presets publicados e **reporta as
exceções da biblioteca** — uma regra nunca conferida contra as seeds é uma regra que ninguém
segue. Um teste fixa que nenhuma seed é condenada, para que apertar palavras-chave não passe a
reprovar a biblioteca publicada em silêncio.

## Memória de persona (ETAPA 4)

Identidade de personagem é **permanente, versionada e atribuída**. Três objetos, uma regra
cada:

```text
PersonaLedger          histórico append-only (implementa PersonaSource)
PersonaMemoryEngine    governança: create / revise / approve / retire + episódios
MemoryResolver         vocabulário e a regra de mudança de identidade  (ETAPA 2, intocada)
```

O engine **compõe** o resolver em vez de reimplementá-lo — existe exatamente uma definição de
`identity_phrase` e da exigência de autorização.

`revision` (sequência do ledger, sobe em toda escrita) é distinta de `version` (identidade,
sobe só em mudança de rosto/corpo/cabelo/roupa/voz). `fetch_version(id, n)` devolve a última
revisão daquela versão de identidade: o estado que o personagem efetivamente apresentava.

O ledger é a **fonte única**: `PersonaMemoryEngine` escreve nele e `MemoryResolver` lê dele,
de modo que engine e `GenerationSpecBuilder` enxergam o mesmo estado. É a costura
`PersonaSource` prometida na ETAPA 2 — trocar o seed por PostgreSQL não toca `memory_resolver.py`.

Duas regras de produto valem mais que o mecanismo:

- **Aprovação exige definição, nunca a fornece.** Um personagem sem atributos não pode ser
  aprovado; a identidade precisa existir antes da certificação.
- **Episódio publicado mantém seu snapshot.** `remember()` grava a identidade sob
  `(episode_id, persona_id)`; revisões posteriores não a alcançam. `continuity()` distingue
  "consistente" de "sem registro" — ausência de dado nunca é lida como consistência.

### Persona Memory Engine (PR003)

As personas do produto (perfis persistentes) deixaram a memória do processo
sem tocar o desenho acima: o `Core` continua dependendo de protocolos, e a
persistência entrou por injeção no composition root (`main.py`).

```text
POST /api/v1/personas/*  ──►  repositories/persona_repository.py  ──►  PostgreSQL (migration 0002)
                                                        │
        Persona (tabela)  ◄─────────────────────────────┤   o único módulo que fala com o SQLAlchemy
        │ to_memory() / to_profile()                    │
        ▼                                                ▼
_CompositePersonaSource (fetch)      _PersistentPersonaProfileSource (get_profile)
        └────────────► MemoryResolver ◄────────────────────┘
                          │ resolve()           → identidade (prompt, estilo, versionamento)
                          │ resolve_persona()   → perfil completo (wardrobe, LoRA, referências)
                          ▼
                 GenerationSpecBuilder  (persona_id do request / do core/compile)
```

Regras fixadas por teste (`test_persona_engine.py`):

- **O Core não toca SQL.** Os adapters vivem em `main.py`; `memory_resolver.py`
  só conhece `PersonaMemory`/`PersonaProfile`.
- **Composite em `fetch`, privado em `search`.** Uma persona persistida resolve
  no builder por id; mas o catálogo global `/core/personas` segue listando
  apenas personagens do ledger — o perfil de um tenant não vaza para outro.
- **`PersonaSource` não mudou.** O protocolo original (`fetch`/`search`) e os
  seus implementadores continuam válidos; o perfil completo entra pelo
  protocolo opcional `PersonaProfileSource` (injeção, não acoplamento).
- **Revisão append-only.** Toda mudança de identidade no `PATCH` incrementa
  `revision` e appende uma linha em `persona_identity_revision` (nunca
  reescrita); metadados (estilo, LoRA) não contam como identidade.
- **Slug único por workspace** (`uq_personas_workspace_slug`), 409 na API.
- **Persona referencia asset, não armazena.** `persona_images` aponta para
  assets existentes (upload segue no fluxo de assets); o treino legado pode
  referenciar id ainda não criado, por isso a coluna não é FK — a validação
  de existência vive na rota `/images`.
- **LoRA da persona via parâmetro.** O `lora_id` da persona entra em
  `job.parameters` (o worker já resolve asset → path com checagem de
  workspace); o `spec.lora` não carrega id cru, mantendo a regra da ETAPA 16.

Detalhes de schema, contratos e decisões: `docs/PERSONA_ENGINE.md`.

## Project Memory (PR004.1)

A memória de projeto do estúdio (persona ativa, estilo, wardrobe, LoRA,
câmera, proporção, duração e último prompt) segue um **contrato congelado**
independente do backend: hoje `localStorage`, amanhã PostgreSQL. O objeto
(`ProjectMemoryState`) é exatamente o mesmo nos dois mundos; só o
transporte troca.

- **Contrato** — `ProjectMemoryState` em `lib/memory/project_memory.ts`:
  `projectId` é o único campo obrigatório, os demais opcionais. O formato
  só muda com migration (envelope versionado `v`).
- **Adapter (única fronteira de storage)** — `lib/memory/project_memory.ts`
  expõe `loadProjectMemory(projectId)`, `saveProjectMemory(state)` e
  `clearProjectMemory(projectId)`. É o **único arquivo do repositório** que
  referencia `window.localStorage` (guarda estrutural). Uma única chave
  oficial (`PROJECT_MEMORY_KEY`); nenhum componente conhece a string.
- **Hook** — `useProjectMemory(projectId)` (`lib/memory/use_project_memory.ts`)
  retorna `{ memory, save, clear }` e **somente consome o adapter**: não
  toca storage, não conhece a chave, não serializa. `save` é atualização
  parcial (merge).
- **Regra arquitetural** — nenhum componente (ou `lib`) acessa
  `localStorage` diretamente; o token de auth (PR002) e a chave legacy do
  Persona Lab também passam pelo adapter como seams nominais, mas **não**
  fazem parte do `ProjectMemoryState`.
- **Migração futura** — uma tabela `project_memory(project_id, workspace_id,
  state JSONB, version, updated_at)` + endpoint autenticado; o adapter troca
  o corpo das três funções mantendo a assinatura, o hook não muda.

Contrato, adapter, hook, regras e migração: `docs/PROJECT_MEMORY.md`.

## Contrato de provider (ETAPA 3; universalizado no PR007)

**Todo provider recebe apenas `GenerationSpec`.** A assinatura é o mecanismo de aplicação
da regra — não existe caminho por onde uma string solta entre. A ETAPA 3 introduziu o
contrato mínimo de imagem; PR007 o substitui na execução por `BaseProvider`, que cobre
imagem, vídeo, upscale, health e estimate:

```python
class BaseProvider(ABC):
    @abstractmethod
    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset: ...
    @abstractmethod
    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset: ...
    @abstractmethod
    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset: ...
    @abstractmethod
    def health(self) -> ProviderHealth: ...
    @abstractmethod
    def estimate(self, spec: GenerationSpec) -> ProviderEstimate: ...
```

Fluxo de um job:

```text
Job (persistido)
  -> spec_adapter.compile_job(job)        # transporte, não decisão
  -> GenerationSpecBuilder.build_traced() # o Core decide tudo
  -> GenerationSpec                       # lora/reference_path já resolvidos
  -> provider.generate(spec, output_dir)  # única entrada
```

`app/spec_adapter.py` é o **único** módulo que conhece `app.schemas.Job` e o Core ao mesmo
tempo. É por isso que o Core continua sem importar a camada de API: a tradução fica no
boundary, a decisão fica no Core.

Os 19 campos de `GENERATION_SPEC_FIELDS` são o contrato. Além deles o spec carrega extras
**tipados** (`resolution`, `guidance_scale`, `steps`, `ip_adapter_scale`, `mode`,
`cinematic_mode`, `slow_motion`, `native_audio`, `reference_path`) — porque um provider não
pode receber nada além do spec, os parâmetros de sampling viajam dentro dele em vez de
chegarem num `dict` ao lado.

Cada provider declara `CONSUMED_SPEC_FIELDS` e `UNSUPPORTED_SPEC_FIELDS`. O que um provider
não honra fica declarado, nunca descartado em silêncio.

## Agentes

- **CEO Agent:** prioridade, escopo, impacto no roadmap.
- **CTO Agent:** arquitetura, segurança, contratos e qualidade.
- **Director Agent:** roteiro, linguagem cinematográfica, ritmo e câmera.
- **ML Agent:** provider, VRAM, LoRA, ControlNet e inferência.
- **UX Agent:** fluxo, clareza, feedback e acessibilidade.

Agentes são responsabilidades lógicas e podem começar como serviços determinísticos. A evolução para modelos separados não deve alterar os contratos do Core.

## Contratos importantes

- `GenerationSpec`: prompt estruturado, memória, preset, condicionadores e output.
  Definido em `core/contracts.py` com `schema_version` e **19 campos obrigatórios**
  declarados uma única vez em `GENERATION_SPEC_FIELDS`:

  ```text
  project_id · user_id · persona_id · style_id · prompt_original · prompt_compiled
  negative_prompt · camera · lens · lighting · motion · weather · aspect_ratio
  fps · duration · provider · seed · lora · controlnet
  ```

  `prompt_original` guarda o texto do usuário; `prompt_compiled` é o que o modelo
  recebe. Os dois vivem juntos para que qualquer frame seja reproduzível e auditável.
- `Job`: estado, progresso, logs, cancelamento e output.
- `Asset`: arquivo, tipo, workspace, versão e origem.
- `PersonaMemory`: identidade fixa, LoRAs, roupas, voz e autorização.
- `ShotPreset`: código, câmera, lente, movimento, luz e ritmo.
- `StylePreset`: lens, lut, lighting, contrast, grain, camera_motion, particles, fps.
- `DirectorIntent`: conceito, formato, logline, roteiro, beats, música, ritmo e duração.

## Regras de isolamento

Providers nunca acessam diretamente componentes React. Rotas nunca contêm lógica de inferência. A Knowledge Base é somente leitura durante geração e versionada durante edição. Jobs longos nunca rodam na thread HTTP.

Regras adicionais aplicadas desde a ETAPA 2, cada uma com teste que falha se for violada:

| Regra | Como é garantida |
|---|---|
| Rotas não contêm lógica de geração | `test_core_api.py::test_no_route_contains_prompt_or_direction_logic` procura vocabulário de prompt/câmera no trecho de rotas de `main.py`. |
| Nenhum componente do Core importa um par | `test_core_independence.py` (probe em subprocesso + guarda estática). |
| O Core não importa FastAPI, SQLAlchemy, Celery ou boto3 | `test_module_does_not_depend_on_the_application_layer`. |
| O Core não conhece o banco | `MemoryResolver`/`StyleResolver`/`ShotResolver` recebem um `Protocol` (`PersonaSource`, `StyleSource`, `ShotSource`); `JobService` recebe `JobRepository` por injeção (PR004-prep). O provider (Postgres/Redis/memória) entra na borda, nunca no Core. |
| Prompt bruto nunca vai ao modelo | `test_raw_prompt_is_never_emitted_alone`. |
| Identidade não muda em silêncio | `test_unauthorized_identity_change_is_refused` + versionamento. |
| O storyboard não produz prompt | `test_the_engine_never_produces_prompt_text` + `test_the_new_endpoint_does_not_produce_prompt_text`. |
| Os treze blocos do documento são emitidos na ordem declarada | `test_blocks_follow_the_documented_order` (igualdade exata) + `test_every_block_system_prompt_declares_is_emitted`. |
| NEGATIVE nunca é concatenado ao prompt positivo | `test_negative_is_declared_but_never_joined_to_the_prompt`. |
| Nenhuma cláusula é emitida duas vezes | `test_a_repeated_clause_is_emitted_once` + `test_no_published_shot_produces_a_duplicated_clause`. |
| O compilador não conhece o storyboard | `test_compile_beats_takes_only_contract_types` (AST) + `test_core_independence.py`. |
| O orçamento de provider não afrouxa o teto | `test_a_provider_budget_can_never_loosen_the_compiler_ceiling`. |
| O Core trata nomes de provider como opacos | `test_core_treats_provider_names_as_opaque_for_budgeting` + `test_core_does_not_name_provider_brands_or_catalogue_ids`. |
| O adapter é escolhido pelo provider pedido, não pelo tipo do job | `test_asking_for_hunyuan_gets_hunyuan_not_wan` + `test_the_worker_routes_a_video_request_to_the_requested_adapter`. |
| Um provider indisponível é recusado, nunca substituído | `test_a_planned_or_remote_provider_is_refused_not_substituted` + `test_the_worker_refuses_a_remote_only_provider`. |
| Campos declarados batem com o código | `test_the_declared_fields_match_the_code` (análise estática; verificado que falha ao reintroduzir o bug). |
| Os pesos de IP-Adapter combinam com o modelo base | `test_the_flux_ip_adapter_weights_are_flux_weights_not_sdxl`. |
| Nenhum helper compartilhado volta a ser copiado | `test_the_shared_helpers_are_the_same_object_not_copies` + `test_the_video_adapters_inherit_rather_than_reimplement`. |
| Todo provider universal declara orçamento em capabilities | `test_prompt_budgets_live_in_provider_capabilities_not_the_core` + `test_provider_capability_helpers_keep_main_thin_and_core_opaque`. |
| O engine não guarda shots nem reimplementa a biblioteca | `test_the_engine_holds_no_shots_of_its_own` (AST) + `test_the_engine_does_not_reimplement_the_library_rules`. |
| O engine não reimplementa o Diretor | `test_the_engine_does_not_reimplement_the_director` (sem `FORMAT_KEYWORDS`, `_build_beats` nem `detect_format` locais). |
| Toda cena nomeia um shot real | `test_every_scene_names_a_real_shot_from_the_library` + `test_the_cast_comes_from_the_expanded_library_not_the_brief`. |
| Abertura e resolução sempre sobrevivem ao corte | `test_opening_and_closing_always_anchor_the_arc` (6 formatos × 11 comprimentos). |
| A sequência não colapsa em dois shots | `test_a_long_sequence_does_not_alternate_between_two_shots` + `test_no_two_neighbouring_scenes_use_the_same_shot`. |
| `GenerationSpec` mantém os 19 campos | `test_generation_spec_declares_every_mandatory_field`. |
| Provider não recebe string solta nem `dict` | `test_generate_accepts_a_spec_and_nothing_else` + `test_no_provider_accepts_a_prompt_string_or_a_parameters_dict` (inspeção de assinatura). |
| O worker entrega de fato só o spec | `test_the_worker_hands_the_image_provider_only_a_spec` roda o `process_generation` real com provider patcheado. |
| A resposta da API não esconde campo do spec | `test_compile_exposes_every_field_the_spec_carries` (Pydantic descarta extras em silêncio por padrão). |
| Identidade não muda sem autorização | `test_identity_change_without_authorization_is_rejected` (e nada é gravado). |
| Aprovação nunca inventa identidade | `test_approval_refuses_an_undefined_identity`. |
| Episódio mantém o snapshot original | `test_an_episode_keeps_its_original_snapshot`. |
| Rotas de persona não decidem regra | `test_the_persona_routes_contain_no_identity_logic`. |
| Seeds de personagem não são duplicados | `test_seeds_are_not_duplicated_by_the_ledger`. |
| Vocabulário não diverge da Bíblia | `test_the_lens_language_is_the_five_focal_lengths_the_bible_names` e irmãos (tuplas literais). |
| A biblioteca não decide nem produz texto | `test_the_library_never_produces_prompt_text`, `test_the_library_does_not_recommend_styles`. |
| A biblioteca publicada não é condenada | `test_the_audit_finds_no_false_violations_in_the_seeds`. |
| Rotas cinematográficas são somente-leitura | `test_the_cinematic_routes_are_read_only`. |
| Os 300 obedecem à Bíblia | `test_every_shot_obeys_the_cinematic_bible` (`violations() == {}`). |
| Códigos publicados nunca são renumerados | `test_published_codes_are_reserved`, `test_the_published_presets_come_first_and_unchanged`. |
| Nenhum valor inventado nos publicados | `test_the_published_shots_are_not_given_invented_expansion_fields`. |
| Código desconhecido não cai em fallback | `test_an_unknown_shot_does_not_silently_fall_back`. |

### Fronteira de API do Core

| Rota | Contrato |
|---|---|
| `POST /api/v1/core/direct` | Intenção → `DirectorBriefResponse`. Nunca devolve prompt técnico. |
| `POST /api/v1/core/compile` | Dry-run → `GenerationSpecResponse` com `trace`. Não gera mídia nem cria job. |
| `POST /api/v1/core/storyboard` | Brief → `CoreStoryboardResponse`: sequência escalada, validada, com `beat_sheet`. Não produz prompt nem gera mídia. |
| `POST /api/v1/core/storyboard/compile` | Brief → `CoreStoryboardCompileResponse`: um prompt compilado por cena, com orçamento aplicado e `dropped` explícito. Não gera mídia. |
| `GET /api/v1/core/providers` | Catálogo de adapters do registry legado: kind, status, checkpoint, conditioning. Filtrável por `kind`. |
| `GET /api/v1/core/providers/health` | Se cada adapter local pode rodar **nesta máquina agora**. Nunca lança. |
| `GET /api/v1/providers` | Registry universal PR007: status, latência, versão e capabilities por provider, sem segredos. |

`POST /api/v1/storyboards/expand` e `POST /api/v1/prompts/enhance` mantêm exatamente o
contrato anterior; apenas a composição saiu da rota e foi para o Core. `prompt_engine.py`
permanece como fachada (`PromptEnhancer`, `default_style`, `enhance`) delegando ao
`PromptCompiler`, então nenhum chamador precisou mudar.
