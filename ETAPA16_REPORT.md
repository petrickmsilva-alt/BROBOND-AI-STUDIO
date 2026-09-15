# ETAPA 16 — TESTES 90%

Relatório técnico. Meta: 90% de cobertura.

**Resultado: `89% → 95%`** sobre `backend/app`, com gate `--fail-under=90` no CI.
Suíte **`881 → 1040`** testes. **28 módulos em 100%** (eram 20). Zero arquivos deletados.
Nenhuma rota alterada: **58 / 31 core / 2 WS**, os mesmos números da ETAPA 15.

---

## 1. Auditoria — a cobertura medida antes de escrever

| Módulo | Stmts | Descobertas | Cobertura |
| --- | --- | --- | --- |
| `api/routes.py` | 51 | 51 | **0%** |
| `api/dependencies.py` | 12 | 12 | **0%** |
| `core/security.py` | 14 | 14 | **0%** |
| `services/generation.py` | 23 | 23 | **0%** |
| `preprocessing.py` | 35 | 27 | 23% |
| `training.py` | 47 | 34 | 28% |
| `system.py` | 14 | 9 | 36% |
| `queue.py` | 164 | 66 | 60% |
| `providers/image.py` | 73 | 22 | 70% |
| `providers/video.py` | 89 | 23 | 74% |
| `main.py` | 495 | 106 | 79% |
| **TOTAL** | **3833** | **434** | **89%** |

### O achado que muda como a meta deve ser lida

Antes de escrever um teste, verifiquei se os quatro módulos em 0% eram testáveis:

```
app.api.routes          -> ImportError: cannot import name 'get_settings' from 'app.core.config'
app.api.dependencies    -> ImportError: cannot import name 'get_settings' from 'app.core.config'
app.core.security       -> ImportError: cannot import name 'get_settings' from 'app.core.config'
app.services.generation -> ModuleNotFoundError: 'app.schemas' is not a package
```

**Nenhum dos quatro importa.** São o **P0-1** que `AUDIT.md` §5.1 já registrava como "dois
backends paralelos; seis módulos mortos **e quebrados**". `main.py` nunca os monta (não há
`include_router` em lugar algum) e eles só importam uns aos outros.

Ou seja: **100 statements estão permanentemente fora de alcance**, e qualquer percentual sobre
a árvore inteira é medido com eles no denominador.

Decisão: **não apagar** (instrução permanente) e **não consertar** — consertar significaria
acrescentar `get_settings` ao `core.config` e transformar `schemas.py` num pacote, o que
ressuscitaria um segundo backend que duplica `main.py`. Isso é o oposto de "preservar 100% da
arquitetura". Em vez disso, a fronteira virou teste (seção 4).

---

## 2. O que foi coberto, e com que substituição

As dependências ausentes (GPU, `diffusers`, Pillow, FFmpeg, Redis, MinIO, `controlnet-aux`,
`imageio`) são **exatamente a condição que o código foi escrito para detectar**. Então a maior
parte dos testes afirma a recusa; onde a lógica atrás da recusa é pura, a dependência é
substituída e o ramo é alcançado.

| Módulo | 60–89% → | O que os testes alcançam |
| --- | --- | --- |
| `queue.py` | **100%** | LoRA e imagem de referência resolvidos com checagem de posse; recusa cross-tenant; persistência em workspace com `Asset` criado; `train_lora` com e sem workspace e com run inexistente; `enqueue` com broker fora |
| `training.py` | **100%** | contagem de referências; asset ausente/não-imagem; recusa com MinIO ligado; manifest captionado com nomes zero-padded; stderr do trainer; run que termina sem `safetensors` |
| `preprocessing.py` | **100%** | dispatch por modo; recusa sem Pillow/`controlnet-aux`; ramos `depth`/`edges`/`tile` com PIL substituído; detector OpenPose |
| `system.py` | **100%** | parsing do CSV do `nvidia-smi` (2 GPUs, campos numéricos); timeout de 3 s; saída vazia; linha malformada; OSError/SubprocessError/ValueError |
| `providers/image.py` | **100%** | `_load` com e sem diffusers, cache do pipeline, `enable_model_cpu_offload`; recusa do ControlNet nomeando `FluxControlPipeline`; IP-Adapter na escala do spec; `generate` nomeando por `spec_id` e filtrando kwargs |
| `providers/video.py` | **100%** | recusa sem diffusers; diffusers velho demais para a classe de pipeline; `.to("cuda")`; encode com fps/codec; recusa sem `imageio` |
| `providers/common.py` | **100%** | `generator_for(None)` → `None`; device `cuda`; `health_report`; `cuda_availability` nos três estados; `apply_lora` |
| `lora.py` | **100%** | limites 20–50; captions; `train()` recusa em vez de fingir |
| `auth.py` | **99%** | hash malformado em 5 formas; token forjado/expirado/sem `sub`/de usuário apagado; `login` e `register`; **indistinguibilidade** das falhas |
| `main.py` | **87%** | download local (storage ligado, escape de caminho, ausente, sucesso); conditioning (pose→501, sem Pillow→503, cross-tenant→404); export (sem FFmpeg→503, não-vídeo→422); socket de treinamento |

**Dois testes de indistinguibilidade** merecem destaque porque não são óbvios: senha errada e
e-mail inexistente devolvem a mesma mensagem (senão o endpoint vira oráculo de enumeração de
contas), e token forjado, expirado, sem sujeito e de usuário apagado devolvem o mesmo `detail`.

---

## 3. Erros meus, todos pegos por medição

| Erro | Como apareceu |
| --- | --- |
| Escrevi `build_seed_generator`; a função é **`generator_for`** | `AttributeError` — escrevi contra uma API que não reli |
| Afirmei que o modo `tile` não faz `convert` algum | falso: todo modo faz `convert("RGB")` ao abrir; o que tile não faz é `convert("L")`/`filter` |
| Afirmei `_dimensions("16:9", 1024) == (1280, 720)` | medido: `resolution` é o **lado maior**, então `(1024, 576)` |
| Patcheei `local_root` no **módulo** `app.storage` | é atributo da **instância** — o mesmo erro que já me pegou com `media` |
| Assumi que `Asset.id` existe após `db.add` | é `default=lambda: str(uuid4())`, um *column default* aplicado no flush; o fake precisou se comportar igual |
| Patcheei `media._available` / `media._checked` | não existem; `available` é `shutil.which("ffmpeg") is not None` — o certo é patchear `shutil.which` |
| Assumi que upload de `.mp4` dá `kind == "video"` | `kind` vem de `content_type.split("/")[0]`, então o teste precisa controlar o content type |
| Parametrizei `../etc/passwd` na rota de download | o cliente HTTP normaliza; nunca chega à rota |
| Proibi `/api/v1/system/gpu` em `page.tsx` na etapa anterior | aparece como **rótulo** para o usuário, que é o comportamento honesto |

### Uma suposição minha que a medição derrubou por completo

Parametrizei `GET /api/v1/assets/download/..` esperando 400. Voltou **200**.

Investigado em vez de ajustado: `storage.local_path("..")` **levanta `ValueError`
corretamente**. O 200 vem de outro lugar — o cliente HTTP normaliza
`/api/v1/assets/download/..` para `/api/v1/assets/`, que casa com a **rota de listagem**. O
corpo é `[]`. Não é traversal; é normalização de URL batendo noutra rota. O teste agora diz
isso explicitamente, e os cinco escapes relativos são verificados onde são reais, em
`storage.local_path`.

---

## 4. Três achados medidos, registrados e não corrigidos

Esta etapa é de testes. Mudar comportamento aqui misturaria um ajuste de segurança com uma
etapa de cobertura, então cada achado foi **fixado por teste** para ficar visível, e o
conserto pertence a outra etapa.

### 4.1 `lora_id` sem `workspace_id` chega cru ao provider

A checagem de posse roda apenas quando **os dois** existem. Sem workspace:

```
spec.lora sem workspace_id = 'LORASINVERIFICADO'
```

`GenerationSpecBuilder` tem precedência `request.lora > persona.lora_path`, então o **id do
asset** entra em `spec.lora` onde o loader espera um caminho.

**Não é vazamento cross-tenant** — nenhum arquivo é aberto sem a checagem, então o adaptador de
outro workspace não vaza. É um furo de correção: o loader recebe um valor inutilizável e o job
falha no load em vez de ser recusado antes. Há um teste que afirma exatamente isso, com o
contraste (com workspace, vira caminho real e `is_file()` é verdadeiro).

### 4.2 `jwt_secret` default tem 23 bytes

```
jwt_secret: 'change-me-in-production' | bytes: 23
RFC 7518 minimum for HS256: 32 bytes
```

O PyJWT emite `InsecureKeyLengthWarning` **em cada chamada**. O filtro em `pytest.ini` documenta
o motivo em vez de escondê-lo.

### 4.3 O socket de treinamento não tem guarda de autenticação

`WS /api/v1/personas/{id}/training/events/{run_id}` aceita conexão sem token, ao contrário da
rota HTTP equivalente (`GET .../training/{run_id}`, que usa `current_user`). O `run_id` é um
UUID aleatório, então não é enumerável — mas o endpoint não verifica identidade. Fixado por
teste, com o comentário dizendo que é registrado, não endossado.

---

## 5. O piso agora é imposto

`coverage` não estava em `requirements.txt` e o CI só rodava `pytest`. Agora:

```yaml
- name: Coverage gate (90%)
  run: |
    PYTHONPATH=backend coverage run --source=backend/app -m pytest backend/tests -q
    coverage report --include='backend/app/*' --skip-empty --fail-under=90
```

Verificado nos dois sentidos:

| Comando | Exit |
| --- | --- |
| `--fail-under=90` | **0** (passa) |
| `--fail-under=99` | **2** (falha) |

`test_dead_module_boundary.py` fixa a fronteira do cluster morto:

- cada um dos quatro **continua não importando** (se um dia importar, um teste falha — é um
  evento arquitetural, não uma melhora de cobertura)
- **nada vivo os importa** (varredura em `backend/app/**/*.py`, ignorando os próprios membros)
- `main.py` não tem `include_router`
- a contagem de **100 statements** está fixada, para que uma mudança no denominador seja visível

---

## 6. Não-vacuidade

| Defeito reintroduzido | Resultado |
| --- | --- |
| Checagem de workspace removida do LoRA | **1 failed** — `test_a_lora_from_another_workspace_is_refused` |
| `_verify_password` sempre aprovando | **7 failed** — login, senha vazia e indistinguibilidade |

Restaurado: **1040 passed**.

---

## 7. Verificações literais

| Verificação | Antes | **Depois** |
| --- | --- | --- |
| `pytest backend/tests -q` | 881 | **1040 passed** |
| Sem cache / hermético | 881 | **1040 / 1040** |
| 22 testes originais · independência | 22 · 23 | **22 · 23** |
| Cobertura `backend/app` | 89% | **95%** |
| Módulos em 100% | 20 | **28** |
| Gate `--fail-under=90` | inexistente | **exit 0** |
| Rotas `/api/v1` · core · WS | 58 · 31 · 2 | **58 · 31 · 2** |
| `npm run build` | ✓ | **✓** |
| Arquivos deletados desde `3708784` | 0 | **0** |

Novos arquivos de teste: `test_runtime_capabilities.py` (48) · `test_queue_training_paths.py`
(28) · `test_provider_runtime.py` (23) · `test_auth_paths.py` (28) ·
`test_asset_export_routes.py` (21) · `test_dead_module_boundary.py` (11) — **159 testes**.

---

## 8. O que **não** foi verificado, dito explicitamente

- **Nenhum modelo real rodou.** `diffusers`, `torch`, Pillow, FFmpeg, Redis e MinIO continuam
  ausentes. Os testes provam que o código toma a decisão certa sobre o que tem na frente — não
  que uma GPU renderiza.
- **Os 100 statements do cluster morto seguem inalcançáveis.** Aparecem como 8–33% no relatório
  porque a tentativa de import executa as linhas de topo antes do `ImportError`; o corpo das
  funções nunca roda.
- **`main.py` ficou em 87%, não 100%.** As 64 linhas restantes são o corpo de rotas que exigem
  FFmpeg ou Pillow de verdade (o sucesso do conditioning e do export), mais ramos de WebSocket
  que precisariam de dois leitores concorrentes — o padrão que já travou a suíte antes.
- **A meta de 90% foi atingida sobre a árvore inteira (95%), com os 100 statements mortos no
  denominador.** Sem eles seria 97%. Os dois números estão aqui de propósito: o primeiro é o
  conservador, e é o que o gate impõe.
- **O gate roda no CI, não aqui.** O GitHub Actions não foi executado nesta sessão; verifiquei
  o comando localmente nos dois sentidos (exit 0 e exit 2).

---

## 9. Arquivos

| Arquivo | Mudança |
| --- | --- |
| `backend/tests/test_runtime_capabilities.py` | **novo** — 48 testes |
| `backend/tests/test_queue_training_paths.py` | **novo** — 28 testes |
| `backend/tests/test_provider_runtime.py` | **novo** — 23 testes |
| `backend/tests/test_auth_paths.py` | **novo** — 28 testes |
| `backend/tests/test_asset_export_routes.py` | **novo** — 21 testes |
| `backend/tests/test_dead_module_boundary.py` | **novo** — 11 testes |
| `pytest.ini` | **novo** — testpaths + filtro de warning documentado |
| `.github/workflows/ci.yml` | gate de cobertura |
| `requirements.txt` | `coverage==7.6.1` |
| `CHANGELOG.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `README.md`, `backend/README.md` | atualizados |

Nenhum arquivo deletado. **Nenhum arquivo de `backend/app/` foi alterado** — a cobertura subiu
porque o código passou a ser exercitado, não porque foi tocado. As 58 rotas, o `QualityGate`, o
`VideoTimeline` e os providers estão exatamente como a ETAPA 15 os deixou.
