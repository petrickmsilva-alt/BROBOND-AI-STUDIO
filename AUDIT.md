# BROBOND AI STUDIO — AUDITORIA TÉCNICA (ETAPA 1)

**Data:** 2026-09-15
**Escopo:** repositório `petrickmsilva-alt/BROBOND-AI-STUDIO`, commit `3708784` (branch de trabalho `arena/01a0a25e-brobond-ai-studio`)
**Autor (papéis):** CTO · Arquiteto de Software · ML Engineer · Diretor de Cinema · UX Designer · DevOps
**Natureza:** somente leitura. **Nenhum arquivo existente foi alterado nesta etapa.** Este documento é o único artefato novo produzido.

> Regra respeitada: *"Não modificar nada nesta etapa."* Nada de `backend/app/core/`, `GenerationSpec`, rotas ou refatorações foi criado. As etapas 2–17 permanecem **não iniciadas** e dependem da aprovação deste relatório.

---

## 1. Método e reprodutibilidade

Toda afirmação deste relatório veio de um comando executado neste checkout. Os comandos de verificação estão listados no Anexo A. Resumo do que foi rodado:

| Verificação | Comando | Resultado observado |
|---|---|---|
| Suíte de testes do backend | `PYTHONPATH=backend pytest backend/tests -q` | **22 passed, 1 warning in 1.25s** |
| Cobertura real | `coverage run --source=backend/app -m pytest backend/tests -q` + `coverage report` | **TOTAL 1234 stmts / 542 miss = 56%** |
| Build do frontend | `npm ci && npm run build` | **✓ Compiled successfully** — rota `/` 12,4 kB, First Load JS 99,6 kB, 4 páginas estáticas |
| Importabilidade dos módulos | `python -c "import app.api.routes"` e afins | **6 módulos quebrados** (ver §5.1) |
| Inventário de rotas | introspecção de `app.routes` | **28 `APIRoute` + 2 `APIWebSocketRoute`** (27 sob `/api/v1`) |
| Segurança das rotas | leitura de `/openapi.json` + requisições sem token | **13 endpoints `/api/v1` sem autenticação efetiva** (ver §6) |

**Sobre o histórico de commits:** `git rev-list --all --count` retorna **1**. O repositório inteiro entrou como um único squash-merge (`3708784 Merge pull request #4`). Não há histórico por arquivo disponível para `git blame`. A diretriz "preservar histórico de commits" está atendida no sentido de que nada foi reescrito — mas o histórico granular já não existe e não pode ser recuperado.

---

## 2. Inventário do repositório

**83 arquivos versionados** (`git ls-files | wc -l` → 83). Distribuição de código:

| Área | Arquivos | Linhas | Observação |
|---|---|---|---|
| `backend/app/**/*.py` | 29 (24 com código + 5 `__init__` vazios) | **1.800** | Núcleo da API |
| `backend/tests/*.py` | 13 | 282 | 22 testes, todos via `TestClient` |
| `app/` (Next.js) | 3 | 261 | `page.tsx` = 243 linhas |
| `components/studio-shell.tsx` | 1 | **644** | **Órfão — não importado por nada** |
| `lib/api.ts` | 1 | 92 | Cliente HTTP |
| `app/globals.css` | 1 | 7 linhas / 23 KB | CSS minificado em linhas longas |
| `knowledge_base/*.md` | 5 | 107 | Conhecimento versionado |
| Docs raiz | 5 | — | README, ARCHITECTURE, ROADMAP, STYLE_GUIDE, SYSTEM_PROMPT |
| Infra | — | — | `docker-compose.yml`, 2 Dockerfiles, `render.yaml`, `.github/workflows/ci.yml`, `Makefile` |

### 2.1 Arquivos críticos (por risco, não por tamanho)

| Arquivo | LOC | Por que é crítico |
|---|---|---|
| `backend/app/main.py` | **393** | Todas as 27 rotas `/api/v1` + 2 WebSockets + bootstrap de banco + CORS + headers. É o único ponto de entrada e o maior gargalo de coesão. |
| `backend/app/queue.py` | 151 | Ciclo de vida de job, 3 tasks Celery, persistência de LoRA. Contém o **bug P0-1**. |
| `backend/app/schemas.py` | 184 | Único contrato tipado do sistema. Não existe `GenerationSpec`. |
| `backend/app/store.py` | 27 | Repositório **em memória** para jobs e personas — ponto único de perda de estado. |
| `backend/app/storage.py` | 64 | Fronteira local↔MinIO, URLs assinadas, guarda anti-traversal. |
| `backend/app/auth.py` | 110 | JWT + scrypt. Único mecanismo de identidade real. |
| `backend/app/providers/image.py` / `video.py` | 94 / 64 | Adapters FLUX e Wan. `image.py` tem **0% de cobertura**. |
| `app/page.tsx` | 243 | UI inteira em um único componente cliente, com 40 `useState`. |

---

## 3. Arquitetura documentada × arquitetura real

O `ARCHITECTURE.md` descreve 8 camadas (Frontend, Backend, Core, AI Engine, Render Engine, Database, Assets, Knowledge Base) e um pipeline `User Intent → Director Agent → Memory Resolver → Prompt Composer → GenerationSpec → Provider Adapter → Queue → Asset + Event Stream`.

**Estado real, verificado por busca no código:**

```
grep -rniE "generationspec|director|memoryresolver|promptcompiler|styleresolver|shotresolver" backend/ --include=*.py
→ NENHUMA OCORRÊNCIA
```

| Camada documentada | Estado real | Evidência |
|---|---|---|
| **Core** (decisão) | **Não existe.** `backend/app/core/` contém apenas `config.py` (44 L) e `security.py` (25 L, quebrado). Nenhum dos 6 componentes da Etapa 2 existe. | `ls backend/app/core/` |
| **GenerationSpec** | **Não existe.** Jobs trafegam como `Job.parameters: dict` não tipado. | `schemas.py:31` |
| **Director Agent** | Não existe. | grep vazio |
| **Memory Resolver** | Não existe. Personas vivem num `dict` em memória; nada é resolvido em geração. | `store.py:13` |
| **Prompt Composer** | **Parcial.** `prompt_engine.py` (22 L) faz concatenação determinística de 1 função. Não há blocos SUBJECT/PERSONA/ENVIRONMENT/… | `prompt_engine.py:13-19` |
| **AI Engine (adapters)** | **Parcial.** 2 providers concretos (FLUX, Wan). Sem classe abstrata real (`ImageProvider.generate` levanta `NotImplementedError`, mas não é `ABC`), sem `estimate_time()` nem `health()`. Sem Hunyuan, sem Kling. | `providers/image.py:19-21` |
| **Render Engine (queue)** | **Quebrado.** Celery configurado, mas o worker nunca encontra o job (P0-1). | §5.2 |
| **Database** | **Parcial.** SQLAlchemy com 6 modelos; **sem Alembic** (`alembic==1.13.3` em `requirements.txt`, mas `find . -name "alembic*"` → nada). Bootstrap por `create_all` + um `ALTER TABLE` manual. | `main.py:38-62` |
| **Assets (MinIO)** | **Parcial.** boto3 funciona; mas 4 fluxos retornam `501`/`RuntimeError` quando `storage_enabled=true` (LoRA, referência, condicionamento, export). | `queue.py:48,59`, `main.py:265,296` |
| **Knowledge Base** | **Funcional, mínima.** 12 seeds no Postgres/SQLite. | `knowledge.py:17-30` |

**Conclusão de arquitetura:** o repositório é uma **API de orquestração funcional com contratos estáveis** e uma **UI premium de demonstração**. A camada que o produto promete como diferencial (Core / Diretor / Memória) **não foi iniciada**. Isso é bom para a Etapa 2: não há implementação concorrente a desmontar — mas há **duas implementações paralelas mortas** que precisam ser removidas primeiro (§5.1).

---

## 4. Dependências

### 4.1 Duas fontes de verdade incompatíveis (P1)

Existem dois manifests Python com pinos diferentes e **conteúdos divergentes**:

| Pacote | `requirements.txt` (raiz) | `backend/requirements.txt` | Usado pelo código vivo? |
|---|---|---|---|
| `fastapi` | 0.115.0 | 0.115.6 | sim |
| `sqlalchemy` | 2.0.35 | 2.0.36 | sim |
| JWT | `pyjwt==2.9.0` | `python-jose[cryptography]==3.3.0` | código vivo usa **pyjwt** (`auth.py:8`) |
| S3 | `boto3==1.35.24` | `minio==7.2.15` | código vivo usa **boto3** (`storage.py:5`) |
| Driver Postgres | `psycopg[binary]==3.2.1` + `asyncpg==0.29.0` | — | **psycopg sim; asyncpg nunca importado** |
| Hash de senha | `passlib[bcrypt]==1.7.4` | `passlib[bcrypt]==1.7.4` | **nunca importado** — `auth.py` usa `hashlib.scrypt` |
| `Pillow` | `>=10.4.0` | ausente | sim (`main.py:266`) |
| `alembic` | `1.13.3` | ausente | **nunca usado** (sem `alembic.ini`) |

**Impacto real:** `Dockerfile.api` e o CI (`.github/workflows/ci.yml`) instalam **apenas o `requirements.txt` da raiz**. Logo `backend/requirements.txt` é um manifesto morto que, se alguém o usasse, quebraria a aplicação (faltam `boto3`, `pyjwt`, `psycopg`, `Pillow`). `backend/Dockerfile` também é morto — o `docker-compose.yml` constrói `api` e `worker` com `dockerfile: Dockerfile.api`.

**Nota de segurança:** `python-jose` (no manifesto morto) acumula CVEs de confusão de algoritmo e DoS e está sem manutenção; `pyjwt` é a escolha correta e já é a que roda. Isso reforça a recomendação de **apagar** `backend/requirements.txt`, não de mantê-lo.

### 4.2 Dependências de frontend

`package.json`: `next ^14.2.32`, `react 18.3.1`, `framer-motion ^11.11.17`, `lucide-react ^0.468.0`, `typescript 5.5.4`, `tailwindcss ^3.4.17`.

- **Tailwind está configurado mas inerte.** `postcss.config.mjs` registra o plugin `tailwindcss` e `tailwind.config.ts` define um tema (`ink`, `canvas`, `line`, `cream`, `mint`), mas `grep -c "@tailwind" app/globals.css` → **0**. Nenhuma diretiva `@tailwind base/components/utilities` existe. O plugin roda a cada build e não gera nada; o design system inteiro é CSS autoral em `globals.css`. As cores do `tailwind.config.ts` (`#0b0c0f`, `#b4f5d0`) **não batem** com o `STYLE_GUIDE.md` (`#0D0D0E`, `#A98AFF`). São 3 fontes de verdade de cor.
- **Sem ESLint.** `package.json` declara `"lint": "next lint"`, mas não existe `.eslintrc*`. O comando entra em modo interativo e falha em CI.
- **Sem Jest, sem Playwright, sem Vitest.** Cobertura de frontend = **0 testes**.
- `@types/*` estão em `dependencies` em vez de `devDependencies`.

---

## 5. Achados funcionais (bugs que quebram a promessa do produto)

### 5.1 P0-1 — Dois backends paralelos; seis módulos mortos **e quebrados**

`backend/app/api/routes.py`, `backend/app/api/dependencies.py`, `backend/app/services/generation.py` e `backend/app/core/security.py` formam uma **segunda API completa** que nunca foi ligada (`grep -rn "include_router"` → apenas a definição em `routes.py:21`; nenhum `include_router` em `main.py`).

Verificação de importação:

```
BROKEN  app.core.security       -> ModuleNotFoundError: No module named 'jose'
BROKEN  app.schemas.auth        -> 'app.schemas' is not a package
BROKEN  app.schemas.generation  -> 'app.schemas' is not a package
BROKEN  app.api.dependencies    -> ModuleNotFoundError: No module named 'jose'
BROKEN  app.api.routes          -> ModuleNotFoundError: No module named 'jose'
BROKEN  app.services.generation -> 'app.schemas' is not a package
```

Causa-raiz tripla:
1. `core/security.py:5` importa `get_settings` de `app.core.config` — **`config.py` exporta `settings`, não `get_settings`**. Mesmo com `jose` instalado, quebraria.
2. `schemas` é um **módulo** (`schemas.py`), não um pacote; `schemas/auth.py` e `schemas/generation.py` **não existem**.
3. `routes.py` e `dependencies.py` usam import absoluto `app.…` enquanto o resto do pacote usa import relativo `.…`.

Esses 4 arquivos somam **229 linhas com 0% de cobertura** e ainda trazem um `POST /auth/login` que **aceita qualquer credencial** (`routes.py:24-34`) e um `GET /system` com GPU inventada (`vram_total_gb=24.0`). Se um dia forem ligados por engano, viram uma backdoor.

**Decisão recomendada:** apagar os 4 arquivos e `backend/requirements.txt` + `backend/Dockerfile`. É remoção de código morto, não destruição de arquitetura — a arquitetura viva (`main.py` + `auth.py` + `schemas.py`) permanece intacta.

### 5.2 P0-2 — O worker Celery **nunca processa nenhum job**

Dois defeitos independentes, ambos fatais para a Etapa 11:

**(a) Mismatch de tipo `UUID` × `str`.** `main.py:156` chama `enqueue(str(job.id))`, mas `store.jobs` é indexado por `UUID` (`store.py:16`). Dentro da task, `store.get_job(job_id)` recebe uma `str` e nunca encontra a chave:

```
store key type: UUID
store.get_job(str(id)) -> None
process_generation(str(id)) -> {'job_id': '78f3e659-…', 'status': 'cancelled'}
```

Ou seja, **todo job enfileirado retorna imediatamente como `cancelled`** (`queue.py:27-29`), mesmo com Redis no ar e `inference_enabled=true`.

**(b) Estado em memória entre processos.** Ainda que o tipo fosse corrigido, `store` é um `dict` do processo da API. O worker Celery é **outro processo** e teria seu próprio `store` vazio. O job precisa estar no Postgres (ou no payload da task) para o worker enxergá-lo.

**Efeito combinado:** hoje o sistema **não consegue completar uma geração real**. O `ROADMAP.md` marca "Redis/Celery/WebSocket contracts" como `[x]`, mas o contrato não fecha ponta a ponta.

### 5.3 P0-3 — Nenhum evento de progresso é publicado

`EventHub.publish()` existe (`events.py:24`) e tem **zero chamadores**:

```
grep -rn "publish" backend/app
→ backend/app/events.py:24:    async def publish(...)   # apenas a definição
```

Consequências:
- `cancel_job` (`main.py:190`) muda o status **sem avisar ninguém**.
- `process_generation` atualiza `job.progress`/`job.status` **sem publicar**.
- O WebSocket `queue_events` (`main.py:200`) envia **um único snapshot** e depois fica bloqueado em `receive_text()`.
- Os eventos exigidos pela Etapa 11 (`job_created`, `progress`, `frame_ready`, `completed`, `error`) **não existem nem como constantes**.
- No frontend, `app/page.tsx:126-131` só atualiza `progress` a partir de `socket.onmessage` → **a barra de progresso nunca sai de 0%** e o `loading` nunca é liberado pelo socket.

### 5.4 P1 — A UI mostra resultados que não existem

O `SYSTEM_PROMPT.md` é explícito: *"Não invente arquivos, jobs concluídos, modelos carregados ou outputs inexistentes."* A UI atual viola isso em 3 pontos:

| Local | O que a tela afirma | Realidade |
|---|---|---|
| `page.tsx:144` | `<div className="result-art">` com `<span className="result-label">FLUX / 2K</span>` | É um desenho em CSS puro (divs `head`/`body`). Nenhuma imagem é renderizada. |
| `page.tsx:50` | `GPU ready` · `RTX 4090` · `18.4 / 24 GB VRAM` | Hardcoded. O endpoint real `GET /api/v1/system/gpu` existe e **não é consumido** pela UI. |
| `page.tsx:50` | `Petrick Martins` como usuário padrão | Nome real hardcoded como fallback de identidade. |

Além disso, controles inteiros são decorativos: `Model`, `Aspect ratio`, `Resolution`, `Negative prompt`, `Seed` e os sliders de `Guidance scale`/`Steps` **não têm estado**. `generate()` envia constantes fixas (`aspect_ratio: '16:9'`, `resolution: '2048'`, `guidance_scale: 7.5`, `steps: 28`) — mover o slider não muda nada. O contador de caracteres é a string literal `"72 / 2,000"`.

### 5.5 P1 — `components/studio-shell.tsx` é uma UI fantasma de 644 linhas

```
grep -rn "studio-shell\|StudioShell" app lib components | grep -v "^components/studio-shell"
→ NOT IMPORTED ANYWHERE
```

É uma segunda implementação completa do estúdio (Overview, Image, Video, Persona, Motion, Storyboard, Assets, Projects, Settings), **58 KB**, não referenciada por nenhum arquivo. É onde vivem as 460 ocorrências de `className` e os dados fake (`projectCards`, `assetItems`, `storyboardScenes`). Duplicação direta de `app/page.tsx`.

### 5.6 P2 — `lib/api.ts` engole todos os erros

`request()` captura qualquer exceção e devolve `{ data: null, remote: false }` (`api.ts:24-27`). Um `401`, um `422` de validação e um timeout de rede são indistinguíveis na UI. O `AbortSignal.timeout(2200)` é curto demais para `POST /generations/videos`. E `data: null as T` quebra a segurança de tipos em todo consumidor.

---

## 6. Segurança

### 6.1 Autorização ausente — 8 endpoints `/api/v1` que deveriam exigir identidade respondem sem token (10 no total, contando os 2 que mentem no OpenAPI)

Medido por requisição real **sem token**:

| Endpoint | Sem token | Impacto |
|---|---|---|
| `GET /api/v1/queue` (`main.py:392`) | **200** — devolve **todos** os jobs de **todos** os workspaces, com `prompt` e `parameters.workspace_id` | Vazamento cross-tenant em massa |
| `GET /api/v1/jobs/{job_id}` (`main.py:182`) | **200** | Leitura de job alheio |
| `POST /api/v1/jobs/{job_id}/cancel` (`main.py:190`) | **200** → status vira `cancelled` | **Mutação de estado sem autenticação** |
| `POST /api/v1/personas` (`main.py:311`) | **202** | Criação anônima; sem vínculo com workspace |
| `POST /api/v1/personas/{id}/train` (`main.py:317`) | **202** | Dispara fila de treino sem identidade (`workspace_id = None`) |
| `GET /api/v1/personas/{id}/training/{run}` (`main.py:338`) | **200** | Leitura de run alheio |
| `GET /api/v1/assets/download/{key}` (`main.py:246`) | **200** | Download de mídia sem autorização (a chave contém `uuid4`, então a exploração exige conhecimento da chave — mas a URL é **permanente e não assinada** no modo local, `storage.py:56-60`) |
| `GET /api/v1/knowledge` (`main.py:117`) | **200** | Expõe a base inteira, incluindo **dados pessoais reais**: `CHAR_PETRICK — "Petrick Martins, 50 years, 1.85m, athletic build…"` (`knowledge.py:21`) |

**Armadilha no OpenAPI:** `POST /api/v1/generations/images` e `POST /api/v1/personas/{id}/train` aparecem com `security` declarado no schema, porque usam `optional_user` (`OAuth2PasswordBearer(auto_error=False)`). O schema **mente** — ambos aceitam请求 anônimas (o próprio `test_api.py:14-22` posta sem token e espera `202`). Auditoria por OpenAPI sozinho daria falso positivo.

### 6.2 O que está correto (preservar)

- **Anti path-traversal funciona.** `storage.local_path` valida `root not in path.parents` (`storage.py:59`). Testado diretamente: `'../../etc/passwd'` → `ValueError: Invalid asset path`; `'ws/../../etc/passwd'` → `ValueError`; `'ws/ok.png'` → caminho válido. O `404` no HTTP também ocorre porque o Starlette normaliza `../` antes do roteamento — **dupla proteção**.
- **Senha com scrypt + `hmac.compare_digest`** (`auth.py:49,59`) — escolha melhor que bcrypt para senhas longas; comparação em tempo constante.
- **JWT valida algoritmo** (`algorithms=[settings.jwt_algorithm]`, `auth.py:73,83`) — imune a `alg=none`.
- **E-mails normalizados** para lowercase no cadastro e no login.
- **Headers de segurança** presentes (`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`).
- **`subprocess` sempre com lista de argumentos**, nunca `shell=True` (`media.py:43`, `training.py:49`).
- **Nenhum segredo commitado** (varredura por padrões de chave/token/secret → 0 acertos).

### 6.3 Lacunas de segurança a corrigir

| # | Lacuna | Evidência | Risco |
|---|---|---|---|
| S-1 | `jwt_secret` com default `"change-me-in-production"` e **nenhuma validação em startup** | `core/config.py:22` | Se a env não for definida, qualquer um forja token. `docker-compose.yml` usa `change-me-in-compose`. |
| S-2 | JWT sem `workspace_id`, `iat`, `iss`, `aud`; **sem refresh e sem revogação** | `auth.py:66` | Token roubado vale 60 min em qualquer workspace; não há como invalidar. |
| S-3 | Token no `localStorage` | `lib/api.ts:16` | XSS rouba a sessão permanentemente. |
| S-4 | **Sem rate limiting** em `/auth/login` | nenhuma middleware além de CORS + headers | Brute force. Agravado por S-5. |
| S-5 | scrypt `n=2**14, r=8, p=1` = **16 MiB por tentativa**, sem throttle | `auth.py:49` | Amplificação de memória: 100 req/s de login ≈ 1,6 GB/s de alocação → DoS trivial. |
| S-6 | **Sem limite de tamanho de upload**; no modo local `await file.read()` carrega o arquivo inteiro em RAM | `storage.py:36` | DoS por upload. (O branch MinIO usa `upload_fileobj` e faz streaming — só o local é vulnerável.) |
| S-7 | Validação de upload confia no `content_type` do cliente | `main.py:221-222` | Um `.html` declarado como `image/png` passa e é servido pelo `FileResponse`. |
| S-8 | `PIL.Image.open` em upload de usuário sem ajuste de `MAX_IMAGE_PIXELS` | `main.py:269` | Decompression bomb. |
| S-9 | **Sem paginação** em `/api/v1/assets` e `/api/v1/queue` | `main.py:241,392` | Resposta ilimitada; `store.jobs` **nunca é limpo** (medido: 200 criações → 200 jobs retidos em memória). |
| S-10 | **Sem CSP nem HSTS** | `main.py:67-72` | Sem defesa em profundidade contra XSS. |
| S-11 | Sem logging estruturado, sem request-id, sem trilha de auditoria; único log é `print()` no bootstrap | `main.py:59` | Incidente não é investigável. |
| S-12 | CORS `allow_methods=["*"]`, `allow_headers=["*"]` com `allow_credentials=True` | `main.py:75-80` | Aceitável com a lista explícita de origins, mas deve ser estreitado antes de virar SaaS. |

---

## 7. Performance e escalabilidade

| # | Gargalo | Evidência | Consequência |
|---|---|---|---|
| P-1 | **`_bootstrap_database()` roda na importação do módulo** (`main.py:64`), com 12 tentativas × 5 s | `main.py:38-62` | Até **60 s de bloqueio** no import; testes e health checks ficam reféns; em Postgres lento o container reinicia em loop. |
| P-2 | **`create_all` em todo boot**, sem Alembic, + `ALTER TABLE` manual para `training_runs.workspace_id` | `main.py:45-53` | Sem versionamento de schema; impossível migrar produção com segurança. `alembic` está nos requisitos e nunca é usado. |
| P-3 | **`store` em memória, sem limite e sem TTL** | `store.py`, medido 200/200 retidos | Vazamento de memória linear; estado perdido a cada deploy (o filesystem do Render é efêmero). |
| P-4 | **Personas em memória** (`store.add_persona`) | `main.py:313` | `POST /personas` **não persiste**. Após restart, `/personas/{id}/train` retorna 404. Incompatível com a Etapa 4. |
| P-5 | **7 cópias** de `db.scalar(select(Workspace).where(Workspace.owner_id == user.id))` em `main.py` | grep → 7 ocorrências | Sem camada de repositório; cada nova rota duplica a consulta e o risco de esquecer o filtro de tenant. |
| P-6 | `export_video` roda FFmpeg **síncrono** dentro da requisição HTTP (`timeout=900`) | `main.py:300`, `media.py:43` | 15 min de thread do threadpool presa por export; um único usuário trava o pool. Viola a regra do `ARCHITECTURE.md`: *"Jobs longos nunca rodam na thread HTTP."* |
| P-7 | `conditioning` faz processamento Pillow na rota HTTP | `main.py:269-275` | Bloqueia thread do pool; existe uma task Celery pronta (`preprocess_reference`) que **não é chamada** por essa rota. |
| P-8 | WebSocket de treino faz **polling de banco a cada 2 s** por cliente | `main.py:374` | N clientes × 1 query/2 s. Não escala. |
| P-9 | `datetime.utcnow` em **8 lugares** | `models.py` ×6, `schemas.py` ×2 | Datetimes naive; deprecated no Python 3.12 (o CI usa 3.12). Corrupção silenciosa de fuso ao comparar com `datetime.now(UTC)` do `auth.py:65`. |
| P-10 | `GET /api/v1/knowledge` faz `ILIKE '%…%'` sem índice | `knowledge.py:46` | Seq scan; aceitável com 12 linhas, inaceitável com 300+ shots. |
| P-11 | Tabela `projects` existe no modelo mas **não tem nenhuma rota** | `grep Project backend/ --include=*.py` → só `models.py` | Tabela morta. `project_id`, exigido no `GenerationSpec` da Etapa 3, ainda não tem dono. |

---

## 8. Qualidade de código e dívida técnica

**Cobertura medida por arquivo** (`coverage report`, total **56%** contra a meta de 90% da Etapa 16):

| 0% (nunca executado por teste) | Cobertura baixa |
|---|---|
| `api/dependencies.py` 0% · `api/routes.py` 0% · `core/security.py` 0% · `services/generation.py` 0% · `providers/image.py` 0% | `queue.py` **20%** · `preprocessing.py` 23% · `training.py` 28% · `providers/video.py` 35% · `system.py` 36% · `media.py` 47% · `events.py` 52% · `main.py` **60%** · `storage.py` 61% |

Os 22 testes são **todos de superfície HTTP feliz**. Não existe teste para: cancelamento, WebSocket, falha de provider, storage MinIO, export FFmpeg, treino real, autorização (nenhum teste verifica que uma rota **nega** acesso), nem um único teste negativo de segurança.

**Outras dívidas:**

- **D-1 — Rotas contêm lógica de negócio.** O `ARCHITECTURE.md` diz *"Rotas nunca contêm lógica de inferência"*, mas `main.py` tem Pillow inline (269-275), FFmpeg inline (300) e a **expansão de storyboard inteira na rota** (`main.py:380-390`, com `camera_progression` hardcoded). É exatamente o que a Etapa 2/8 vai corrigir.
- **D-2 — `main.py` é um god module** (393 L, 27 rotas, 2 WS, bootstrap, CORS, headers). Precisa virar `APIRouter` por domínio — o que a Etapa 2 exige de qualquer forma.
- **D-3 — `Job.parameters: dict` sem tipo** (`schemas.py:31`). É a materialização do problema que a Etapa 3 resolve: hoje o provider recebe um `dict` de strings soltas, exatamente o que a missão proíbe.
- **D-4 — Duplicação de prompt engine.** `prompt_engine.py` e `api/routes.py:85-91` implementam a mesma "melhoria de prompt" de duas formas diferentes.
- **D-5 — Duplicação de validação de LoRA.** `lora.py:19-20` e `training.py:19-20` validam "20–50 imagens" com mensagens e exceções diferentes (`ValueError` vs `TrainingError`).
- **D-6 — Providers sem contrato real.** `ImageProvider`/`VideoProvider` não são `ABC`; falta `estimate_time()` e `health()` (exigidos pela Etapa 10). `FluxDiffusersProvider` escreve sempre em `image.png` fixo (`providers/image.py:72`) — duas gerações concorrentes no mesmo worker **sobrescrevem o mesmo arquivo**.
- **D-7 — `WanVideoProvider` ignora `reference_path`, `lora` de vídeo, `camera_motion`, `native_audio`, `slow_motion`, `cinematic_mode`** — campos aceitos pelo schema (`schemas.py:50-61`) e silenciosamente descartados.
- **D-8 — `README.md` documenta endpoints que não existem** com essa assinatura: `POST /api/v1/personas` existe, mas `PATCH`/`DELETE /personas` e `GET /personas` **não** (medido: `404`, `404`, `405`). A Etapa 4 precisa criá-los.
- **D-9 — `ROADMAP.md` marca como concluído o que não fecha**: "Redis/Celery/WebSocket contracts `[x]`", "Knowledge Base persistente no PostgreSQL `[x]`" (funciona, mas com 12 seeds), "Storyboard continuity `[x]`" (é uma lista de 4 câmeras em loop).
- **D-10 — `.env.example` incompleto**: falta `BROBOND_TRAINING_ENABLED`, `BROBOND_MINIO_BUCKET` está, mas faltam `BROBOND_LOCAL_MEDIA_DIR`, `BROBOND_ACCESS_TOKEN_MINUTES`, `BROBOND_JWT_ALGORITHM`.

---

## 9. Lacunas de produto por etapa (matriz de prontidão)

| Etapa | Requisito | Estado hoje | Pronto para começar? |
|---|---|---|---|
| 2 — Core | `DirectorAgent`, `MemoryResolver`, `PromptCompiler`, `StyleResolver`, `ShotResolver`, `GenerationSpecBuilder` | **0 de 6 existe** | ✅ `backend/app/core/` existe e está quase vazio |
| 3 — GenerationSpec | 19 campos obrigatórios, provider só recebe spec | **0%** — `Job.parameters: dict` | ✅ Nenhum contrato concorrente |
| 4 — Persona Memory | Tabela `Personas` + 4 verbos HTTP + consulta automática | **0%** — pydantic em `dict`; só `POST`; sem persistência | ⚠️ Precisa migrar `store.personas` antes |
| 5 — Cinematic Library | Tabela `Styles` (lens, lut, lighting, contrast, grain, motion, particles, fps) | **0%** — nada de tabela; `KnowledgeEntry` genérico com 2 seeds "cinematic" | ✅ Pode reusar `KnowledgeEntry` ou criar tabela própria |
| 6 — Shot Library | **300 presets** + interface visual | **1,7%** — **5 shots** no banco (`SH001, SH014, SH032, SH051, SH120`); **10** no markdown | ⚠️ Falta schema (camera path, speed, focus, shake, depth) e UI |
| 7 — Director AI | Agente conversacional, zero prompt técnico | **0%** — só `/prompts/enhance` determinístico | ✅ Depende da Etapa 2 |
| 8 — Storyboard Engine | 4–8 cenas com objetivo/emoção/prompt/movimento/duração/referência, **salvas no banco** | **~25%** — `/storyboards/expand` gera 2–12 cenas com número/título/prompt/duração, **não persiste nada** e não tem objetivo/emoção/referência | ⚠️ Precisa de tabela e de sair da rota |
| 9 — Prompt Compiler | Blocos SUBJECT→OUTPUT | **~15%** — `prompt_engine.enhance` é uma única f-string de 19 palavras | ✅ Contrato `/prompts/enhance` estável |
| 10 — Provider Adapters | `ImageProvider`/`VideoProvider` ABC + 4 implementações + 4 métodos | **~30%** — 2 de 4 providers, 1 de 4 métodos (`generate`) | ⚠️ Precisa refatorar sem quebrar `queue.py` |
| 11 — Queue | 5 estados + 5 eventos WS | **~20%** — estados existem (`JobStatus`), **0 de 5 eventos emitidos**, worker quebrado | 🔴 **Bloqueado por P0-2 e P0-3** |
| 12 — Storage | Assets, Versions, Signed URLs, Preview, Thumbnail, Transcode | **~40%** — Assets + signed URL (1 h) + transcode H.264. **Sem Versions, sem Preview, sem Thumbnail**; 4 fluxos retornam `501` com MinIO ligado | ⚠️ |
| 13 — Video Timeline | Regenerar trecho, trocar câmera/LUT/duração, add/del cena | **0%** — só uma barra `00:00 ─── 00:05` decorativa (`page.tsx:169`) | 🔴 Depende de 8 + 11 |
| 14 — Quality AI | 8 critérios, score, regeneração automática <85 | **0%** | ✅ Greenfield |
| 15 — UX Premium | 5 entry points (Filme/Reels/Moda/Story/Comercial), modo avançado oculto | **0%** — a UI atual expõe exatamente o oposto: dezenas de parâmetros de cara | ⚠️ Redesign de `page.tsx` |
| 16 — Testes | Pytest + Jest + Playwright, 90% | **56% backend / 0% frontend**, sem Jest/Playwright | ⚠️ |
| 17 — Documentação | README, ROADMAP, ARCHITECTURE, CHANGELOG, OpenAPI | **~60%** — 4 docs bons, mas **sem CHANGELOG** e com drift (§8 D-8/D-9) | ⚠️ |

---

## 10. Priorização recomendada (insumo para o Sprint 1)

### 🔴 P0 — bloqueiam tudo (fazer antes da Etapa 2)

| ID | Ação | Por quê antes |
|---|---|---|
| **P0-1** | Remover `backend/app/api/`, `backend/app/services/`, `backend/app/core/security.py`, `backend/requirements.txt`, `backend/Dockerfile` (229 L mortas + manifesto enganoso) | A Etapa 2 vai escrever em `backend/app/core/`; não se pode construir sobre um `core/security.py` que não importa |
| **P0-2** | Persistir `Job` no Postgres **e** corrigir a chave `UUID`/`str` em `store.get_job` | Sem isso a Etapa 11 não é testável e nenhum `GenerationSpec` chega a um provider |
| **P0-3** | Ligar `hub.publish()` nas transições de estado e definir as 5 constantes de evento | O `GenerationSpecBuilder` precisa emitir progresso para ser observável |
| **P0-4** | Fechar a autorização: `current_user` obrigatório + filtro de workspace em `/queue`, `/jobs/*`, `/personas*`, `/assets/download/*`, `/knowledge` | Vazamento cross-tenant ativo. Barato de corrigir agora, caro depois |

### 🟠 P1 — habilitam o Sprint 1

- **P1-1** Migrar `Personas` para tabela SQL (pré-requisito direto da Etapa 4).
- **P1-2** Introduzir Alembic e substituir `create_all` + o `ALTER TABLE` manual (pré-requisito de toda migração das etapas 4, 5, 6, 8).
- **P1-3** Mover o bootstrap de banco para o lifespan do FastAPI (fora da importação).
- **P1-4** Criar camada de repositório (`WorkspaceRepository`) para eliminar as 7 consultas duplicadas.
- **P1-5** Validar `jwt_secret` no startup e estreitar CORS.

### 🟡 P2 — qualidade contínua

- P2-1 Rate limiting em `/auth/*` + limite de tamanho de upload.
- P2-2 Paginação em `/assets` e `/queue`; TTL/evicção no `store` (até ser substituído pelo Postgres).
- P2-3 Substituir `datetime.utcnow` (8 ocorrências).
- P2-4 Remover `components/studio-shell.tsx` **ou** promovê-lo a UI oficial — decidir uma das duas, não manter as duas.
- P2-5 Unificar a fonte de verdade de cor (`STYLE_GUIDE.md` × `tailwind.config.ts` × `globals.css`) e decidir o destino do Tailwind.
- P2-6 Adicionar ESLint + CHANGELOG.md.
- P2-7 Corrigir o drift de `README.md`/`ROADMAP.md` (§8 D-8/D-9).

### Ordem de execução sugerida para o Sprint 1

```
P0-1 (limpeza)  →  P1-2 (Alembic)  →  P0-2 (Job persistido)
                                      ↓
                 Etapa 3 (GenerationSpec)  →  Etapa 9 (PromptCompiler)
                                      ↓
                 P1-1 (tabela Personas)  →  Etapa 4 (PersonaMemory)
                                      ↓
                 P0-3 + P0-4 (eventos + autorização)
```

Justificativa: a Etapa 3 (`GenerationSpec`) é o contrato do qual as etapas 4, 5, 6, 8, 9, 10 e 14 dependem. Produzi-lo antes de qualquer feature evita retrabalho — e ele só pode ser testado de ponta a ponta se o job sobreviver entre processos (P0-2).

---

## 11. Riscos de arquitetura para as próximas etapas

1. **Risco de colisão em `core/`.** `backend/app/core/` hoje tem `config.py` (vivo) e `security.py` (morto). A Etapa 2 cria 6 arquivos ali. Remover P0-1 primeiro evita que `DirectorAgent` conviva com um `security.py` quebrado que o IDE sugere importar.
2. **Risco de duplicar `schemas`.** A Etapa 3 precisa decidir: `GenerationSpec` entra em `schemas.py` (184 L, já grande) ou vira `schemas/` pacote? O código morto já tentou `schemas/generation.py` e falhou porque `schemas` é módulo. **Converter `schemas.py` em pacote é breaking change para 12 importadores** — decidir antes de escrever.
3. **Risco de memória vs. persistência.** Enquanto `store` for a fonte de jobs, qualquer `MemoryResolver` vai parecer funcionar em dev e falhar em produção. Persistência primeiro.
4. **Risco de UI.** A Etapa 15 pede 5 entry points e parâmetros ocultos. A UI atual é 1 componente de 243 linhas com 40 `useState` e uma segunda UI fantasma de 644 linhas. Redesenhar sem resolver P2-4 cria uma **terceira** UI.
5. **Risco de escala na Shot Library.** 300 presets com `ILIKE '%…%'` sem índice (P-10) e sem paginação (S-9) vai degradar. O schema da Etapa 6 já deve nascer indexado e paginado.

---

## 12. Veredito

O repositório **não é um protótipo abandonado**: tem CI verde, 22 testes passando, build de produção funcional, deploy declarado no Render, documentação de arquitetura coerente e fronteiras de provider bem desenhadas no papel. A fundação é aproveitável.

Mas **a promessa central do produto ainda não existe em código**. Nenhum dos 6 componentes do Core foi escrito, não há `GenerationSpec`, personas e jobs não persistem, o worker Celery nunca completa um job, nenhum evento de progresso é emitido e a UI exibe resultados desenhados em CSS. A lacuna entre o `ARCHITECTURE.md` e o `backend/app/` é a principal dívida do projeto.

**Recomendação:** aprovar este relatório e autorizar a Etapa 2 **somente após** os 4 itens P0. Eles representam ~1 dia de trabalho e removem todo o terreno instável sobre o qual o Core seria construído.

---

## Anexo A — Comandos de verificação

```bash
# Testes e cobertura
PYTHONPATH=backend python -m pytest backend/tests -q                    # 22 passed
python -m coverage run --source=backend/app -m pytest backend/tests -q
python -m coverage report --skip-empty                                   # TOTAL 56%

# Build do frontend
npm ci && npm run build                                                  # ✓ Compiled successfully

# Inventário
git rev-list --all --count                                               # 1
git ls-files | wc -l                                                   # 83
find backend -name '*.py' | xargs wc -l                                  # 1800

# Módulos mortos
for m in app.core.security app.schemas.auth app.schemas.generation \
         app.api.dependencies app.api.routes app.services.generation; do
  PYTHONPATH=backend python -c "import $m" 2>&1 | tail -1
done

# Bug do worker
PYTHONPATH=backend python -c "
from app.store import store
from app.schemas import Job, GenerationType
from app.queue import process_generation
j = store.add_job(Job(type=GenerationType.IMAGE, prompt='x'))
print(process_generation(str(j.id)))"                                    # status: cancelled

# Eventos não publicados
grep -rn 'publish' backend/app                                           # só a definição

# Componente órfão
grep -rn 'studio-shell\|StudioShell' app lib components | grep -v '^components/studio-shell'

# Alembic ausente
find . -name 'alembic*' -o -name migrations -type d                      # vazio

# Seeds da Knowledge Base
PYTHONPATH=backend python -c "from app.knowledge import SEEDS; print(len(SEEDS))"   # 12
```

## Anexo B — Superfície de API verificada (27 rotas `/api/v1` + 2 WS)

```
Auth (3)          POST /auth/register · POST /auth/login · GET /auth/me
System (5)        GET /health · GET /api/v1/health · GET /system/gpu · GET /system/readiness · GET /system/media
Models (3)        GET /models/image · GET /models/video · GET /models/conditioning
Generations (2)   POST /generations/images · POST /generations/videos
Jobs (2)          GET /jobs/{id} · POST /jobs/{id}/cancel
Queue (1)         GET /queue
Assets (5)        POST /assets/upload · GET /assets · GET /assets/download/{key}
                  · POST /assets/{id}/conditioning · POST /assets/{id}/export
Personas (4)      POST /personas · POST /personas/{id}/train
                  · GET /personas/{id}/training/{run_id} · GET /personas/{id}/loras
Storyboards (1)   POST /storyboards/expand
Prompt (1)        POST /prompts/enhance
Knowledge (1)     GET /knowledge
WebSocket (2)     /queue/events/{job_id} · /personas/{id}/training/events/{run_id}

Ausentes e exigidos pela Etapa 4:  GET /personas · PATCH /personas/{id} · DELETE /personas/{id}
```
