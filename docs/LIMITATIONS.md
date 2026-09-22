# BROBOND AI STUDIO — Limitações conhecidas

Consolidado das 17 etapas. Cada item foi **medido**, não herdado de um relatório anterior:
a coluna "como verificar" dá o comando que reproduz o estado.

A regra do projeto (`SYSTEM_PROMPT.md`) é não inventar arquivos, jobs concluídos, modelos
carregados ou outputs inexistentes. Este documento existe para que "não está pronto" fique tão
visível quanto o que está.

---

## 1. Nada renderizou de verdade nesta máquina

Nenhuma GPU, nenhum peso de modelo. **Nenhum job produziu um arquivo real** durante as 17
etapas.

| Dependência | Estado | Consequência |
| --- | --- | --- |
| `diffusers` | ausente | `_load()` dos providers levanta; nenhum frame foi gerado |
| `torch` | ausente | idem; `cuda_availability()` devolve `(False, "torch is not installed")` |
| `ffmpeg` | ausente | `concat`, `export_h264` e `probe` não rodam de ponta a ponta |
| `PIL` (Pillow) | ausente | `QualityGate.verify_dimensions` devolve `verified: false`; a gate confere a **alegação** do provider, não os pixels |
| `imageio` | ausente | nenhum `.mp4` foi codificado |
| `controlnet_aux` | ausente | OpenPose recusa com `PreprocessingError` |
| Redis | ausente | `EventHub` é **in-process**; falta pub/sub para múltiplos workers |
| MinIO | ausente | S3 testado apenas contra `FakeS3`, nunca contra um bucket real |

**Verificar:**
```bash
PYTHONPATH=backend python -c "import shutil; print('ffmpeg:', shutil.which('ffmpeg'))"
PYTHONPATH=backend python -c "import diffusers" 2>&1 | tail -1
```

Os testes cobrem as **decisões** do código sobre o que tem na frente — qual classe de pipeline
pedir, o que fazer quando falta uma dependência, como nomear o arquivo de saída. Não provam que
uma GPU renderiza.

---

## 2. Estado que ainda vive em memória

PR002 fechou a metade de jobs: a tabela `jobs` é a fonte de verdade — um
processo lê o que o outro escreveu (fixado por `test_job_persistence.py`).
**PR003 fechou a metade de personas**: `Persona` é a fonte de verdade e
`repositories/persona_repository.py` é o repositório que as rotas e o
`MemoryResolver` usam (fixado por `test_persona_engine.py`). **PR004-prep
fechou o acoplamento dos jobs ao banco**: o fluxo vai por `core/job_service.py`
→ interface `JobRepository` → provider injetado
(`PostgresJobRepository` default · `RedisJobRepository` opt-in ·
`MemoryJobRepository` para testes) — fixado por `test_job_repository.py`. O
facade `app/store.py` segue vivo, mas delega (zero import de SQLAlchemy).
O que
restou:

| Onde | O que | Consequência |
| --- | --- | --- |
| `app/store.py` → personas (Legacy) | `dict` em memória, sem call sites desde o PR003 | Mantido pela Regra de Ouro; a leitura/escrita é 100% SQL via repositório |
| `app/store.py` → jobs (facade) | delega a `JobService`/`JobRepository` | Superfície histórica mantida para call sites e testes; sem dependência de banco |
| `app/core/*` seeds | personas, estilos e shots são dados injetáveis via `Protocol` | Sem tabela `Styles`/`Shots` no Postgres; editar pelo produto não persiste |
| `app/core/memory_resolver.py` ledger | snapshots de episódio em memória | O ledger do Core continua in-memory; **a V3.2 fecha a continuidade de produto**: locks e episódios são linhas em `continuity_locks`/`continuity_episodes` (migration `0004`) e sobrevivem a restart — fixado por `test_continuity_*.py` |
| `app/auth.py` `_auth_attempts` | janela do rate limit por IP | In-memory e por processo: com múltiplas instâncias da API o orçamento se multiplica. O próximo passo declarado é um store compartilhado (Redis) — não simulado, apenas declarado |

**Verificar:** `sed -n '1,20p' backend/app/store.py`

---

## 3. Autorização (P0-4, fechado no PR002; ampliado no PR003, no PR008, na V3.1, na V3.2, na V3.3, na V3.4 e na V4.0.1)

**78 de 119 rotas** tocam identidade, e a diferença entre elas importa:

- **75** exigem token — `Depends(current_user)`: `/auth/me`, `/knowledge`, `/queue`,
  `/jobs/{id}`, `/jobs/{id}/cancel`, `/assets/upload`, `/assets`,
  `/assets/download/{object_key:path}`, `/assets/{id}/conditioning`,
  `/assets/{id}/export`, o bloco `/assets/library*` (3 rotas, V4.0.1 — upload
  da biblioteca, listagem filtrada e detalhe com par before/after são dados
  de tenant, como personas: anônimo é recusado e id estrangeiro responde
  404), `POST /personas`, `GET /personas` (listagem, PR003),
  `/personas/{id}` (GET/PATCH/DELETE — perfis persistentes, PR003),
  `/personas/{id}/train`,
  `/personas/{id}/training/{run_id}`, `/personas/{id}/loras`,
  `/personas/{id}/images` (GET/POST — referências, PR003), todo o bloco
  `/api/v1/core/personas/*` (8 rotas, identidade de personagem = PII) e todo o
  bloco `/api/v1/render/*` (6 rotas, PR008 — renders persistem no workspace de
  quem chamou, então anônimo é recusado),
  e todo o bloco `/api/v1/graph/*` (12 rotas, V3.1 — o grafo é dado de tenant,
  como personas: anônimo é recusado e id estrangeiro responde 404),
  e todo o bloco `/api/v1/continuity/*` (13 rotas, V3.2 — locks e episódios
  são dados de tenant, como personas: anônimo é recusado e id estrangeiro
  responde 404),
  e todo o bloco `/api/v1/campaigns/*` (7 rotas, V3.3 — campanhas, briefs,
  entregáveis, timeline e exports são dados de tenant, como personas:
  anônimo é recusado e id estrangeiro responde 404),
  e as 4 rotas de asset em `/api/v1/quality/*` (V3.4 — relatórios de
  qualidade avaliam e marcam assets do workspace, como personas: anônimo é
  recusado e id estrangeiro responde 404).
- **3** aceitam token mas **não exigem** — `Depends(optional_user)`:
  `/generations/images`, `/generations/videos`, `/core/compile`. Uma chamada
  anônima passa — e o job criado anônima não tem tenant, logo nenhuma
  identidade pode lê-lo de volta (consequência documentada, fixada por
  `test_an_anonymous_job_cannot_be_read_back_with_any_token`).
- As outras **38** não verificam identidade por desenho: `GET /health`, o bloco
  `/system/*`, `/models/*`, `/auth/login`, `/auth/register` (com rate limit),
  `/prompts/enhance`, `/storyboards/expand`, `/providers`, `/quality/config`
  (V3.4 — critérios, pesos default e bandas do motor, dados de referência sem
  estado de tenant) e o Core read-only
  (`/core/direct`, `/core/director/production-plan`, `/core/cinematic/*`,
  `/core/shots*`, `/core/storyboard*`, `/core/timeline*`, `/core/quality/*`,
  `/core/providers*`) — dados de referência e decisões, sem estado de tenant.

Regras de tenant: um token nunca enxerga job, asset, run ou LoRA de outro
workspace — as respostas são **404** (não 403), para o id de outro tenant não
ser enumerável. Fixado por `test_security_authorization.py`.

Os **3 WebSockets** autenticam pelo query parameter `token` (o browser não
define header em handshake de WebSocket): sem token, ou com token que não
possui o job/run/batch, o socket é fechado com `1008` **antes** de aceitar.
O terceiro é `/ws/render/{batch_id}` (PR008), com progresso por push e sem
polling.

`POST /auth/login` e `/auth/register` têm rate limit configurável
(`BROBOND_RATE_LIMIT_AUTH_PER_MINUTE`, default 20/min/IP, `0` desliga), e as
ações críticas (auth, criação/cancelamento de job, download de asset,
upload de asset da biblioteca (`asset.uploaded`, V4.0.1), criação
de persona e revisões de identidade) escrevem uma linha append-only em
`audit_log` mais uma linha estruturada no logger `brobond.audit`.

**Verificar:**
```bash
PYTHONPATH=backend python -c "
from fastapi.routing import APIRoute
from app.main import app
import inspect
n = sum(1 for r in app.routes if isinstance(r, APIRoute) and r.path.startswith('/api/v1')
        and 'user' in inspect.signature(r.endpoint).parameters)
print(f'{n} de 119 rotas com identidade')"
```

---

## 4. Achados medidos na ETAPA 16 e seu estado no PR002

### `lora_id` sem `workspace_id` chega cru ao provider

A checagem de posse só roda quando **os dois** parâmetros existem. Sem workspace, a precedência
do `GenerationSpecBuilder` (`request.lora > persona.lora_path`) põe o **id do asset** em
`spec.lora`, onde o loader espera um caminho:

```
spec.lora sem workspace_id = 'LORASINVERIFICADO'
```

**Não é vazamento cross-tenant** — nenhum arquivo é aberto sem a checagem. É um furo de
correção: o loader recebe um valor inutilizável e o job falha no load em vez de ser recusado
antes. Fixado por teste em `test_queue_training_paths.py`.

### `jwt_secret` default tem 23 bytes — **fechado no PR002**

O default era `change-me-in-production` (23 bytes), abaixo dos 32 mínimos do RFC 7518 para
HS256. O PR002:

1. trocou o default por um segredo de desenvolvimento de **70 bytes**;
2. adicionou um `field_validator` que **recusa iniciar** com qualquer `BROBOND_JWT_SECRET`
   menor que 32 bytes (deploy mal configurado falha no boot, em vez de rodar inseguro);
3. `docker-compose.yml` e `.env.example` passam a carregar segredos ≥ 32 bytes.

Fixado por `test_the_jwt_secret_validator_refuses_a_short_key` e
`test_a_short_configured_secret_refuses_to_boot`. O filtro em `pytest.ini` permanece como
guarda de regressão (documentado lá).

---

## 5. O cluster morto (P0-1)

Quatro módulos, **100 statements**, que nada importa **e que não importam com sucesso**:

| Módulo | Stmts | Por que não importa |
| --- | --- | --- |
| `app/api/routes.py` | 51 | depende de `core.security` |
| `app/core/security.py` | 14 | `get_settings` nunca existiu em `core.config` |
| `app/services/generation.py` | 23 | `app.schemas` é módulo, não pacote |
| `app/api/dependencies.py` | 12 | depende de `core.security` |

Não apagados (instrução permanente de nunca deletar código) e não consertados — consertar
ressuscitaria um segundo backend que duplica `main.py`. `test_dead_module_boundary.py` fixa a
fronteira: se algum passar a importar, um teste falha.

**Consequência prática:** eles pesam no denominador da cobertura. Com eles, `backend/app` lê
**96%**; sem eles, a margem é maior. O gate do CI agora impõe **95%** sobre o número
conservador.

---

## 6. Frontend

| Item | Estado |
| --- | --- |
| Jobs anônimos não são rastreáveis na UI | PR002: a criação anônima continua valida (`optional_user`), mas o acompanhamento (WS e `/jobs/{id}`) é autenticado. O cliente avisa "Job created — sign in to track it" em vez de sugerir que o job vai atualizar. Rastreamento de job anônimo é decisão de UX futura, não bug |
| 4 rotas Core no cliente sem painel | `timeline`, `quality/assess`, `quality/rules` e `providers` estão tipadas em `lib/api.ts` mas nenhuma tela as mostra |
| `components/studio-shell.tsx` (644 l) | não está montado em `app/layout.tsx`; a página renderiza `app/page.tsx`. Mantido intacto |
| Testes JS escopados (PR004.1) | há runner (vitest) **somente para o contrato de Project Memory** (`lib/memory/`, gate de cobertura 95%). O restante do frontend segue sem testes comportamentais: as guardas de `test_frontend_honesty.py`, `test_studio_persona_pipeline.py` e `test_project_memory_contract.py` leem o fonte — cobrem presença e ausência, não comportamento em runtime |
| Project Memory em `localStorage` (PR004/PR004.1) | o `ProjectMemoryState` persiste por browser, não por conta: o schema não tem coluna de estado de projeto e o PR proíbe alterá-lo. O contrato está congelado em `docs/PROJECT_MEMORY.md` — a futura tabela `project_memory(state JSONB)` serve o **mesmo objeto**, e o adapter troca de transporte sem mudar a assinatura |
| Nenhum componente toca `localStorage` (PR004.1) | a única fronteira de storage do front é o Memory Adapter (`lib/memory/project_memory.ts`); token de auth e chave legacy passam por seams nominais no mesmo módulo. Guardado por teste estrutural |
| Sem screenshots/GIFs do Studio (PR004) | o ambiente de build não tem browser (nenhum Chromium/Playwright): as telas do pipeline de persona são verificadas por build + guards estruturais, não por captura de tela. Nada foi inventado para substituir isso |
| `next@14.2.32` | vulnerabilidade conhecida sinalizada pelo npm durante a instalação |
| Render real nunca visto | o caminho `<img src={job.output_url}>` foi verificado por guarda estrutural e pelo contrato do WebSocket, não por uma imagem na tela |

---

## 7. Dependências e manifesto

- **`minio==7.2.15` em `backend/requirements.txt` não é importado** por `backend/app` — o
  storage usa o SDK da AWS (`boto3`). Dependência morta, mantida por não deletar.
- **`backend/requirements.txt` não é o manifesto que o CI instala.** O CI usa o
  `requirements.txt` da raiz (ver `AUDIT.md` §sobre manifestos). `coverage` foi adicionado à
  raiz na ETAPA 16 justamente por isso.
- **`diffusers`/`torch` não estão em manifesto algum** — pertencem ao perfil GPU, que não está
  versionado.

**Verificar:** `grep -rn "import minio\|from minio" backend/app/ || echo "não importado"`

---

## 8. Itens do ROADMAP explicitamente não implementados

Estão em `ROADMAP.md` como `- [ ]` e continuam futuros: primeiro render GPU validado ponta a
ponta, Shot Library com volume persistido, presets cinematográficos editáveis, persistência de
Personas/Styles/Shots no Postgres, Character Library, Prompt Library classificada, continuidade
entre episódios, roteirista automático, diretor de câmera IA, voice clone, lip sync,
colaboração multi-agente, multi-tenancy SaaS, cloud rendering, billing, app mobile e painel
administrativo.

---

## Como este documento é mantido

Os números daqui são verificados por `backend/tests/test_docs_accuracy.py` contra a aplicação
em execução. Se uma contagem mudar e o documento não for atualizado, a suíte falha — a mesma
disciplina que `scripts/gen_api_doc.py` aplica a `docs/API.md`.
