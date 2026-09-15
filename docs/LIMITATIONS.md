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

| Onde | O que | Consequência |
| --- | --- | --- |
| `app/store.py` → `MemoryStore` | jobs e personas em `dict` | **P0-2b, aberto desde a ETAPA 1.** Um worker Celery **em outro processo** não enxerga o job criado pela API. O worker síncrono dos testes funciona; o distribuído, não |
| `app/core/*` seeds | personas, estilos e shots são dados injetáveis via `Protocol` | Sem tabela `Styles`/`Shots` no Postgres; editar pelo produto não persiste |
| `app/core/memory_resolver.py` ledger | episódios de continuidade em memória | Continuidade entre episódios não sobrevive a restart |

**Verificar:** `sed -n '10,14p' backend/app/store.py`

---

## 3. Autorização incompleta (P0-4, aberto)

**10 de 58 rotas** tocam identidade, e a diferença entre elas importa:

- **6** exigem token — `Depends(current_user)`: `/auth/me`, `/assets/upload`, `/assets`,
  `/assets/{id}/conditioning`, `/assets/{id}/export`, `/personas/{id}/loras`.
- **4** aceitam token mas **não exigem** — `Depends(optional_user)`: `/generations/images`,
  `/generations/videos`, `/personas/{id}/train`, `/core/compile`. Uma chamada anônima passa.
- As outras **48** não verificam identidade — incluindo `POST /api/v1/core/direct`, todo o
  bloco `/api/v1/core/personas/*` e `GET /api/v1/assets/download/{object_key:path}`.

`/personas/{id}/train` com identidade opcional é o ponto mais sensível dos quatro: dispara um
treinamento que pode consumir GPU sem exigir quem pediu.

O vazamento cross-tenant de `GET /api/v1/queue` apontado na auditoria original foi corrigido,
mas a superfície continua majoritariamente aberta.

Também registrado na ETAPA 16: `WS /api/v1/personas/{id}/training/events/{run_id}` aceita
conexão sem token, ao contrário da rota HTTP equivalente. O `run_id` é um UUID aleatório, então
não é enumerável — mas o endpoint não verifica identidade.

**Verificar:**
```bash
PYTHONPATH=backend python -c "
from fastapi.routing import APIRoute
from app.main import app
import inspect
n = sum(1 for r in app.routes if isinstance(r, APIRoute) and r.path.startswith('/api/v1')
        and 'user' in inspect.signature(r.endpoint).parameters)
print(f'{n} de 58 rotas autenticadas')"
```

---

## 4. Dois achados medidos na ETAPA 16, ainda abertos

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

### `jwt_secret` default tem 23 bytes

`change-me-in-production` — abaixo dos 32 mínimos do RFC 7518 para HS256. O PyJWT emite
`InsecureKeyLengthWarning` em cada chamada. O filtro em `pytest.ini` documenta o motivo em vez
de escondê-lo.

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
**95%**; sem eles, 97%. O gate do CI impõe 90% sobre o número conservador.

---

## 6. Frontend

| Item | Estado |
| --- | --- |
| 4 rotas Core no cliente sem painel | `timeline`, `quality/assess`, `quality/rules` e `providers` estão tipadas em `lib/api.ts` mas nenhuma tela as mostra |
| `components/studio-shell.tsx` (644 l) | não está montado em `app/layout.tsx`; a página renderiza `app/page.tsx`. Mantido intacto |
| Nenhum teste JavaScript | o repositório não tem runner de front. As 31 guardas de `test_frontend_honesty.py` leem o fonte — cobrem presença e ausência, não comportamento em runtime |
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
