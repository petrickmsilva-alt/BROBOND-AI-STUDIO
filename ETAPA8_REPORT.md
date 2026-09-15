# ETAPA 8 — STORYBOARD ENGINE

**Data:** 2026-09-14
**Branch:** `arena/01a0a25e-brobond-ai-studio`
**Base:** `37087845aa2638f436f38a75c9ac914700d8f94e`
**Escopo:** transformar beats numa sequência de shots escalados, encadeados e validados.

---

## 1. Resumo

A ETAPA 8 fecha o elo que faltava entre as etapas anteriores: a biblioteca de 300 shots
(ETAPA 6) e a gramática cinematográfica (ETAPA 5) existiam, mas **o storyboard não as
alcançava**. Agora cada cena nomeia um shot real e herda dele lente, luz, movimento e
continuidade.

| Métrica | Antes | Depois |
|---|---|---|
| Testes | 431 | **497** (+66) |
| Cobertura de `core/` | 97% | **98%** |
| Cobertura de `backend/app` | 82% | **83%** |
| Cobertura do módulo novo | — | **100%** (124 statements) |
| Rotas HTTP `/api/v1` | 50 | **51** |
| Paths com tag `core` | 23 | **24** |
| Arquivos deletados vs. baseline | — | **0** |
| `shot_code` populado nas cenas | **0%** | **100%** |

Nenhum arquivo foi removido. `POST /api/v1/storyboards/expand` mantém exatamente o contrato
anterior — verificado por `test_the_legacy_expand_route_still_returns_its_four_fields`.

---

## 2. O problema, medido antes de escrever código

Os três defeitos foram confirmados programaticamente **antes** da implementação, não
inferidos da leitura:

**2.1 — `shot_code` era `None` em todos os beats.**
`SceneBeat` já tinha o campo, mas `DirectorAgent._build_beats` nunca o preenchia. A biblioteca
de 300 presets construída na ETAPA 6 era inacessível pelo caminho do storyboard.

**2.2 — A iluminação era uma string fixa.**
`CONTINUITY_LIGHTING` aplicava `"consistent blue-hour lighting across the sequence"` a todas
as cenas, qualquer que fosse o estilo, o formato ou a cena.

**2.3 — O Diretor reprovava na própria gramática.**
`motion="motivated by the beat"` submetido à ETAPA 5 devolve `attention` com a regra
*"claims motivation without naming one"*, enquanto `"reveal"` devolve `ok`. Ou seja: o
storyboard produzido pelo Diretor não passava na validação que o próprio Diretor usa.

---

## 3. O que foi construído

**`backend/app/core/storyboard_engine.py`** — 418 linhas, único arquivo de código novo.

```text
DirectorAgent        beats: objetivo, emoção, duração             (ETAPA 2)
     |
StoryboardEngine     qual shot entra em cada beat, em que ordem,   (ETAPA 8)
     |               e se a sequência se sustenta
     +-- ShotLibrary         os 300 presets de direção             (ETAPA 6)
     +-- CinematicLibrary    a gramática que valida o movimento    (ETAPA 5)
     |
PromptCompiler       único lugar onde texto de prompt nasce         (ETAPA 2)
```

O engine **sequencia**. Não inventa direção, não guarda shots, não é dono da gramática e não
escreve prompt. Cada uma dessas quatro negativas tem teste estático próprio (seção 6).

### Arco narrativo

`ARC_BY_FORMAT` define o arco canônico de cinco beats por formato detectado
(commercial, fashion, film, reels, story, documentary) mais um `DEFAULT_ARC`. O arco é
elástico: sequências mais longas repetem o beat de desenvolvimento, mais curtas cortam do
meio para fora. Invariante testada sobre 6 formatos × 11 comprimentos: **a abertura é sempre
geografia e o fechamento é sempre resolução**.

### Saída real

```text
POST /api/v1/core/storyboard  { "brief": "Quero um comercial de 30 segundos para
                                uma camiseta artesanal.", "scene_count": 5 }

COMMERCIAL — 5 scenes, 25.0s
01. SH002 City Wakes           [establishing]  24mm establishing shot
02. SH028 First Silhouette     [introduction]  50mm medium shot
03. SH157 Hero Product Reveal  [product]       85mm close-up
04. SH158 Material Macro       [product]      135mm extreme close-up
05. SH253 Walk Into Distance   [resolution]    24mm establishing shot

valid: True | violations: [] | attention: []
```

A progressão de lentes 24 → 50 → 85 → 135 → 24mm emerge da escalação, não é declarada em
lugar nenhum.

### `validate()` devolve relatório, não exceção

Um diretor precisa ver **o que** está errado num corte, não apenas saber que falhou. O
relatório separa `violations` (invalidam o corte) de `attention` (merecem olhar):

| Regra | Status |
|---|---|
| `scene-count` — menos de 2 cenas | violation |
| `no-repeat-cut` — mesma cena em cortes vizinhos | violation |
| `motion-motivated` — movimento sem motivação nomeada | violation |
| `runtime` — acima de 180s | violation |
| `lens-declared` — focal fora da Bíblia | attention |
| `continuity-declared` — cena sem nota de continuidade | attention |
| `arc-opens-establishing` / `arc-closes-resolution` | attention |

### `as_beats()`

Projeta o storyboard de volta em `SceneBeat` **com `shot_code` preenchido**. É o que torna a
biblioteca de 300 alcançável pelo caminho de prompt existente sem nenhuma mudança no
`PromptCompiler`.

---

## 4. Bugs encontrados durante a implementação

Dois defeitos reais no meu próprio código, encontrados por teste e não por leitura.

**4.1 — `_pick_shot` evitava só o corte imediatamente anterior.**
A primeira versão comparava cada escolha com a cena anterior. Isso satisfazia a regra
`no-repeat-cut` e ainda assim produzia uma sequência de 12 cenas alternando entre `SH079` e
`SH080` — `SH079` aparecia 5 vezes. Passava na validação e lia como o mesmo plano duas vezes.
**Fix:** preferir shots nunca usados em todo o storyboard; esgotada a família, reutilizar o
visto há mais tempo (`min(pool, key=used.index)`). Verificado: 12 cenas → 12 shots distintos,
em commercial, fashion e film.

**4.2 — Um branch de casting por emoção que nunca executava.**
`_pick_shot` tentava casar tokens da emoção do beat com a intenção do shot. Medido sobre
5 briefs × 11 comprimentos: o Diretor emite apenas **4 emoções**, todas em português
(`curiosidade`, `desejo`, `convicção`, `tensão`), e as intenções da biblioteca são em inglês —
**zero casamentos**. Era código morto vestido de recurso. **Removido**, no mesmo critério
aplicado ao `replace_family()` na ETAPA 6: código que não executa se remove, não se testa.
A decisão está fixada por `test_casting_is_not_emotion_aware`, que falha se algum dia um
casamento aparecer.

A cobertura do módulo passou de 97% para **100%** depois dessa remoção — as 4 linhas que
faltavam eram exatamente esse branch e uma guarda defensiva, que ganhou teste próprio.

---

## 5. Achados documentados, não remendados

**5.1 — O arco `documentary` é inalcançável.**
`DirectorAgent.FORMAT_KEYWORDS` agrupa `"documentário"`/`"documentario"` sob `"film"`, e
"documentary" em inglês não está em nenhuma lista. Verificado:
`detect_format("documentário sobre artesãos") → "film"`. A chave `"documentary"` de
`ARC_BY_FORMAT` nunca é atingida pela detecção atual. Corrigir mudaria o comportamento da
ETAPA 2 — território da **ETAPA 7** (Diretor), que está em aberto. Fixado por
`test_the_documentary_arc_is_currently_unreachable`, que falha no dia em que isso for
corrigido, servindo de lembrete para remover a nota.

**5.2 — O objetivo da cena 5 repete o da cena 1.**
`DirectorAgent._build_beats` cicla 4 objetivos por módulo, então numa sequência de 5 cenas o
objetivo da última volta a ser o da primeira. Visível no beat sheet acima (cena 05:
*"Estabelecer o mundo..."*). Comportamento pré-existente da ETAPA 2; **não corrigido**, pois
pertence à ETAPA 7.

**5.3 — Nenhuma motivação `transformation` é escalada.**
Dos 300 presets, apenas 2 declaram `transformation` (achado já registrado na ETAPA 6). O
engine escala o que a biblioteca oferece; ele não inventa motivações para preencher o
espaço.

---

## 6. Fronteiras preservadas

| Fronteira | Teste |
|---|---|
| O engine não produz prompt | `test_the_engine_never_produces_prompt_text`, `test_the_new_endpoint_does_not_produce_prompt_text` |
| O engine não guarda shots | `test_the_engine_holds_no_shots_of_its_own` (AST sobre o módulo) |
| O engine não reimplementa a gramática | `test_the_engine_does_not_reimplement_the_library_rules` |
| O engine não reimplementa o Diretor | `test_the_engine_does_not_reimplement_the_director` |
| A rota não contém lógica de direção | `test_the_engine_is_the_only_thing_building_the_storyboard` (AST sobre `main.py`) |
| O beat sheet não é um prompt | `test_the_beat_sheet_is_not_a_prompt` |
| A rota legada não mudou | `test_the_legacy_expand_route_still_returns_its_four_fields`, `..._still_produces_prompt_text` |

`DirectorAgent` **não foi editado** — é território da ETAPA 7, que continua em aberto.

---

## 7. Verificação

Todos os comandos foram executados; os números abaixo são as saídas reais.

```
PYTHONPATH=backend pytest backend/tests -q                    -> 497 passed
pytest backend/tests -q          (hermético, sem PYTHONPATH)  -> 497 passed
pytest <arquivos em ordem inversa>                            -> 497 passed
pytest <13 arquivos do baseline 3708784>                      -> 22 passed
pytest backend/tests/test_core_independence.py                -> 17 passed
coverage report --include=*/storyboard_engine.py              -> 124 stmts, 0 miss, 100%
coverage report --include=backend/app/core/*                  -> 1267 stmts, 29 miss, 98%
coverage report --include=backend/app/*                       -> 2972 stmts, 503 miss, 83%
npm run build                                                 -> OK
git diff --diff-filter=D --name-only 3708784                  -> vazio (0 removidos)
```

Caminhos de código efetivamente exercitados: `StoryboardEngine.build` → `cast_beats` →
`_pick_shot` → `validate` → `beat_sheet` / `as_beats`, e a rota
`build_core_storyboard` em `main.py`.

---

## 8. Documentação atualizada

`CHANGELOG.md` (bloco `[Unreleased] — ETAPA 8`), `ARCHITECTURE.md` (nova seção "Storyboard
engine (ETAPA 8)" + 6 guardas na tabela + rota na fronteira de API), `ROADMAP.md` (item
marcado), `README.md` (contagens, seção "Storyboard engine", suítes), `backend/README.md`
(contagens, seção "Storyboard engine", módulos a 100%).

---

## 9. Pendências

Herdadas e não resolvidas nesta etapa: **ETAPA 7 (Director AI) inteira** — bloqueada por
falha de infraestrutura no sandbox quando foi pedida; P0-2b persistência de `Job`; ledger de
persona em memória; bibliotecas em memória; P0-3 `hub.publish` sem chamadores; P0-4 endpoints
sem autorização; UI não consome as rotas Core; `next@14.2.32` com CVE conhecida;
`minio`/`python-jose` declarados sem uso em caminho vivo; motivação `transformation` com
apenas 2 de 300 presets.

Novas desta etapa: o arco `documentary` inalcançável (5.1) e o ciclo de objetivos em
`_build_beats` (5.2) — ambas dependem da ETAPA 7.
