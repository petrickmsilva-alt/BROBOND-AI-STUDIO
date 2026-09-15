# ETAPA 17 — DOCUMENTAÇÃO

Relatório técnico. Escopo: fazer a documentação dizer a verdade sobre o código.

**Resultado:** 12 afirmações obsoletas corrigidas, três documentos novos (`docs/API.md`
gerado, `docs/LIMITATIONS.md`, `docs/ETAPAS.md`), um script gerador e **35 testes que impedem
a documentação de ficar obsoleta de novo**. Suíte `1.040 → 1.075`. Zero arquivos deletados.

---

## 1. Auditoria — o que a documentação dizia e o que o código faz

A premissa desta etapa era de que a documentação poderia estar desatualizada. Estava. Cada
item abaixo foi **medido**, não presumido.

| # | Afirmação na doc | Realidade medida | Onde |
| --- | --- | --- | --- |
| D1 | "pytest suite (**176 tests**)" | **1.075** | `README.md:304` |
| D2 | "The generation result is intentionally a **local UI simulation**" | removido na ETAPA 15; a tela mostra `output_url` real | `README.md:29` |
| D3 | "**Motion control** preset browser and keyframe controls" | removido da navegação na ETAPA 15 | `README.md:25` |
| D4 | "held back only by `core/security.py` **at 0%**" | **21%** — a tentativa de import da ETAPA 16 cobre as linhas de topo | `README.md:351` |
| D5 | "Next implementation milestones" com 6 itens | **todos os 6 já entregues** até a ETAPA 12 | `README.md:330-337` |
| D6 | "**seis** componentes independentes" | **doze** desde a ETAPA 14 | `ROADMAP.md` |
| D7 | "nenhum evento de progresso é publicado (`hub.publish` sem chamadores, P0-3)" | **fechado na ETAPA 11** por `publish_sync` | `ROADMAP.md` |
| D8 | "`backend/app/core` at 98%" | **verdadeiro** — conferido, não tocado | `backend/README.md:248` |
| D9 | Nenhum documento lista as rotas | **58** rotas HTTP + 2 WS sem inventário em lugar algum | — |
| D10 | Nenhum índice dos relatórios | 14 relatórios na raiz, sem índice | — |
| D11 | Limitações espalhadas em 14 relatórios | nenhuma visão consolidada | — |
| D12 | "**12** componentes em `INDEPENDENT_MODULES`" | **8** — eu mesmo escrevi isso nesta etapa antes de medir | rascunho de `docs/ETAPAS.md` |

### D12 — o erro que quase publiquei

Escrevi em `docs/ETAPAS.md` que a invariante era "12 componentes em `INDEPENDENT_MODULES`".
Medido:

```
12 componentes | 8 na guarda
fora da guarda: ['cinematic_library', 'generation_spec_builder', 'persona_memory',
                 'shot_library', 'storyboard_engine']
```

Testei se era só omissão: adicionar os cinco fez **4 testes falharem**. O motivo é que a guarda
afirma uma propriedade **mais forte** do que a que importa — importar *sem nenhum irmão do
Core*. Os cinco compõem uns aos outros por desenho (`storyboard_engine` importa
`director_agent` e `shot_library`), então satisfazem "livre de framework" e não "livre de
irmãos".

Os dois fatos são verdadeiros e diferentes: **12** componentes são livres de framework
(verificado por AST, um teste por componente), **8** são também livres de irmãos. A doc agora
diz isso.

### D5 — uma lista de tarefas de trabalho já feito

Os seis "próximos marcos" do README eram:

1. Add FastAPI service — **existe desde antes da ETAPA 1**
2. Add Postgres migrations — `models.py`, `db.py`
3. Add Redis/Celery queue with capability detection — ETAPA 11
4. Add MinIO signed URLs and FFmpeg export — ETAPA 12
5. Replace local UI simulation with WebSocket job updates — ETAPA 15
6. Add unit/API tests — 1.075 deles

Uma lista de marcos inteiramente concluída não é um plano; é uma afirmação falsa sobre o estado
do projeto. Foi substituída por "What is not built yet", apontando para `ROADMAP.md` e
`docs/LIMITATIONS.md`.

---

## 2. O que foi criado

### 2.1 `docs/API.md` — gerado, não escrito

```bash
PYTHONPATH=backend python scripts/gen_api_doc.py > docs/API.md
```

58 rotas HTTP + 2 WebSockets, agrupadas por tag, com a **primeira linha do docstring** de cada
endpoint como descrição. O documento abre dizendo como foi produzido e que um teste o confere.

O gerador é um arquivo real e executável — verificado por teste (`returncode == 0`, saída
começando com o cabeçalho certo). Um documento que manda o leitor rodar um script inexistente
seria a mesma categoria de mentira que esta etapa existe para remover.

### 2.2 `docs/LIMITATIONS.md` — o que não está pronto, num lugar só

Oito seções, cada uma com o comando que reproduz o estado:

1. Nada renderizou de verdade — `diffusers`, `torch`, `ffmpeg`, `PIL`, `imageio`,
   `controlnet_aux`, Redis e MinIO **ausentes** (verificados um a um)
2. Estado em memória — `MemoryStore` (**P0-2b**), seeds injetáveis, ledger de episódios
3. Autorização incompleta — **10 de 58** rotas verificam identidade (**P0-4**)
4. Os dois achados da ETAPA 16 — `lora_id` cru sem workspace; `jwt_secret` de 23 bytes
5. O cluster morto (**P0-1**) — 4 módulos, 100 statements
6. Frontend — 4 rotas Core sem painel, `studio-shell.tsx` não montado, sem testes JS, CVE do
   `next@14.2.32`
7. Dependências — `minio==7.2.15` não é importado por `backend/app`
8. Itens do ROADMAP explicitamente futuros

### 2.3 `docs/ETAPAS.md` — índice das 17 etapas

Tabela com a entrega principal e o relatório de cada etapa, o estado dos cinco P0 da auditoria
original, as seis invariantes que atravessaram o trabalho e os números atuais.

As etapas 2 e 3 não têm relatório próprio — foram executadas antes de o formato existir, na
ETAPA 4. O documento diz isso em vez de fingir que os arquivos existem.

---

## 3. `test_docs_accuracy.py` — 35 testes contra o drift

Este é o ponto da etapa. Corrigir 12 afirmações obsoletas resolve hoje; impedir que voltem a
ficar obsoletas resolve o problema.

| Guarda | O que impede |
| --- | --- |
| `test_the_api_doc_matches_the_application` | regenera `docs/API.md` em memória e compara byte a byte |
| `test_every_documented_route_is_real` / `test_every_route_is_documented` | nos dois sentidos: rota fantasma e rota não documentada |
| `test_the_generator_script_exists_and_is_runnable` | o doc mandar rodar um script quebrado |
| `test_the_readme_states_the_real_test_count` | conta os testes por `--collect-only` e compara com o README |
| `test_the_backend_readme_states_the_real_test_count` | idem para `backend/README.md` |
| `test_the_readme_tree_comment_is_not_stale` | o "176 tests" da árvore de diretórios |
| `test_the_etapas_index_states_the_real_counts` | rotas, core e testes no índice |
| `test_the_readme_does_not_repeat_a_stale_claim` (4 casos) | `176 tests`, `local UI simulation`, `Motion control preset browser`, `security.py at 0%` |
| `test_the_readme_milestones_are_not_a_todo_list_of_finished_work` | a lista de marcos concluídos voltar |
| `test_the_roadmap_no_longer_claims_publish_has_no_callers` | P0-3 ser descrito como aberto |
| `test_the_roadmap_says_twelve_components_not_six` | "seis componentes" voltar |
| `test_every_core_component_is_framework_free` (12 casos) | um componente importar framework — **um teste por componente** |
| `test_every_report_named_in_the_index_exists` / `test_every_existing_report_is_in_the_index` | índice e relatórios divergirem, nos dois sentidos |
| `test_the_authorisation_count_is_the_real_one` | o "10 de 58" ser contado, não lembrado |
| `test_the_dead_cluster_still_does_not_import` | o cluster morto voltar a importar e a doc ficar errada |
| `test_the_limitations_doc_names_the_absent_dependencies` | as dependências ausentes saírem do documento |

### O teste que se provou antes de eu confiar nele

`test_docs_accuracy.py` foi executado **antes** de qualquer correção de prosa e falhou em
**12 pontos** — exatamente os 12 achados da auditoria. Isso é a prova de não-vacuidade: a
guarda não estava aprovando um estado que eu já tinha arrumado; ela encontrou os defeitos.

---

## 4. Verificações literais

| Verificação | Antes | **Depois** |
| --- | --- | --- |
| `pytest backend/tests -q` | 1.040 | **1.075 passed** |
| 22 testes originais | 22 | **22** |
| `test_core_independence.py` | 23 | **23** |
| `test_docs_accuracy.py` | — | **35** |
| Cobertura `backend/app` · `backend/app/core` | 95% · 98% | **95% · 98%** (inalterada) |
| Rotas `/api/v1` · core · WS | 58 · 31 · 2 | **58 · 31 · 2** |
| Componentes do Core livres de framework | 12 (não verificado) | **12, um teste por componente** |
| Afirmações obsoletas corrigidas | 12 | **0** |
| `npm run build` | ✓ | **✓** |
| Arquivos deletados desde `3708784` | 0 | **0** |

A cobertura **não mudou** de propósito: esta etapa não toca `backend/app/`. Os números de rota,
Core e componentes são os mesmos da ETAPA 16.

---

## 5. Um problema de ambiente, resolvido em vez de contornado

`.venv` **e** `node_modules` não persistiram entre sessões. Ambos foram recriados:

```
python3 -m venv .venv && pip install -r backend/requirements.txt && pip install coverage
npm ci
```

O `npm run build` da primeira tentativa falhou com `sh: 1: next: not found`. Foi reinstalado e
o build passou — não foi relatado como "não verificável".

---

## 6. O que **não** foi feito, dito explicitamente

- **Nenhum código de `backend/app/` foi alterado.** A única mudança fora de `docs/` e dos
  relatórios é `backend/tests/test_docs_accuracy.py` (novo) e `scripts/gen_api_doc.py` (novo).
- **Nada foi apagado.** `minio==7.2.15` segue em `backend/requirements.txt` sem ser importado,
  e os quatro módulos do P0-1 seguem no repositório — ambos documentados em
  `docs/LIMITATIONS.md` em vez de removidos.
- **As limitações não foram consertadas.** Esta etapa as **documenta**. `MemoryStore`, as 48
  rotas sem autenticação, o `lora_id` cru e o `jwt_secret` curto continuam abertos; cada um tem
  a seção correspondente.
- **Nenhum teste JavaScript foi adicionado.** O repositório continua sem runner de front.
- **`docs/API.md` é gerado, o que significa que ele não explica.** Ele inventaria as rotas e
  diz o que cada uma faz na primeira linha do docstring. O *porquê* de cada camada continua em
  `ARCHITECTURE.md`, que tem uma seção por etapa (3 a 16).
- **`ARCHITECTURE.md` não ganhou seção da ETAPA 17.** Esta etapa não adiciona uma camada ao
  sistema; ela descreve as que existem. As seções novas estão em `docs/`.

---

## 7. Arquivos

| Arquivo | Mudança |
| --- | --- |
| `docs/API.md` | **novo** — gerado, 146 l |
| `docs/LIMITATIONS.md` | **novo** — limitações consolidadas |
| `docs/ETAPAS.md` | **novo** — índice das 17 etapas |
| `scripts/gen_api_doc.py` | **novo** — gerador do inventário |
| `backend/tests/test_docs_accuracy.py` | **novo** — 35 guardas anti-drift |
| `README.md` | "Current slice" reescrito; milestones concluídos substituídos; `176 tests` e `security.py at 0%` corrigidos |
| `ROADMAP.md` | doze componentes; P0-3 fechado; P0-1 e P0-4 com estado real |
| `CHANGELOG.md`, `backend/README.md` | atualizados |
| `ETAPA17_REPORT.md` | **este relatório** |

Nenhum arquivo deletado.
