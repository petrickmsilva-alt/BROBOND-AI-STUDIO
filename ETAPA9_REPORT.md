# ETAPA 9 — PROMPT COMPILER

**Data:** 2026-09-14
**Branch:** `arena/01a0a25e-brobond-ai-studio`
**Base:** `37087845aa2638f436f38a75c9ac914700d8f94e`
**Escopo:** evoluir o `PromptCompiler` da ETAPA 2 para a estrutura que `SYSTEM_PROMPT.md` declara, sem duplicar nada e sem tocar em `DirectorAgent`.

---

## 1. Resumo

O compilador já existia desde a ETAPA 2, mas emitia **dez** blocos onde o documento do
repositório declara **treze**, e juntava esses blocos sem deduplicar — o que fazia todo prompt
com preset de shot repetir a focal.

| Métrica | Antes | Depois |
|---|---|---|
| Testes | 497 | **548** (+51) |
| Blocos emitidos | 10 | **12** (+ NEGATIVE declarado = 13) |
| Cobertura de `core/` | 98% (29 miss) | **98%** (26 miss) |
| Cobertura de `backend/app` | 83% | **83%** |
| `prompt_compiler.py` | — | **100%** (67 stmts) |
| `style_resolver.py` | — | **100%** (50 stmts) |
| Rotas HTTP `/api/v1` | 51 | **52** |
| Paths com tag `core` | 24 | **25** |
| Arquivos deletados vs. baseline | — | **0** |
| Prompts com focal duplicada | **5 de 5 medidos** | **0 de 5** |

Nenhum arquivo foi removido. `describe()`, `enhance()`, `build()` e
`POST /api/v1/storyboards/expand` mantêm exatamente o comportamento anterior.

---

## 2. Auditoria — o que foi medido antes de escrever código

**2.1 — Dois dos treze blocos não existiam.**
`SYSTEM_PROMPT.md` ("Estrutura de prompt interno") declara SUBJECT, CHARACTER, ENVIRONMENT,
**ACTION**, CAMERA, LENS, LIGHT, **COLOR**, MOTION, STYLE, CONTINUITY, OUTPUT, NEGATIVE.
`PROMPT_BLOCK_ORDER` tinha dez. `ACTION` e `COLOR` não existiam como campos; `NEGATIVE`
existia como `PromptBlocks.negative` e `GenerationSpec.negative_prompt`, fora da ordem.

**2.2 — STYLE estava na posição errada.**
O documento põe STYLE depois de MOTION. A implementação o punha em quarto lugar. O comentário
da ETAPA 2 em `contracts.py` dizia que a ordem era "mandated by ETAPA 9", mas não batia com o
documento — esta etapa alinha ao documento.

**2.3 — Toda prompt compilada repetia a focal. Reproduzido nos 10 presets publicados.**

```text
SH051: 38 cláusulas | repetidas: ['35mm']
SH001: 41 cláusulas | repetidas: ['50mm']
SH014: 36 cláusulas | repetidas: ['85mm']
SH032: 40 cláusulas | repetidas: ['24mm']
SH089: 38 cláusulas | repetidas: ['85mm']
```

Causa raiz medida, não inferida:

```text
camera_phrase(SH051) -> 'orbit 360, full orbit around a locked subject, 35mm'   <- anexa a focal
lens_phrase(SH051)   -> '35mm, subject locked throughout, medium, ...'          <- começa por ela
```

`_dedupe` existia desde a ETAPA 2, mas `inspect.getsource` confirmou que era chamado **uma
única vez**, dentro de `compile_negative()`. Nunca na junção do prompt positivo.

**2.4 — A cor estava fundida no bloco STYLE.**
Inicialmente hipoteizei que os dados de cor do estilo fossem descartados. **Estava errado**:
medi e `describe()` de fato concatena nome + LUT + contraste + grain + paleta, então a cor
chegava ao modelo. O problema real é outro: por estar toda dentro de `style`, `DROP_PRIORITY`
só podia descartar estilo **e** cor juntos — não havia como manter a paleta e perder um
adjetivo.

**2.5 — O orçamento era um 1200 fixo.**
`max_prompt_chars = 1200`, cujo próprio docstring dizia "the provider character budget" sem
que nenhum provider declarasse orçamento algum (`grep` em `providers/` não encontrou
`max_prompt`, `max_chars` nem `budget`).

**2.6 — `as_beats()` não tinha chamador em produção.**
Construído na ETAPA 8 para tornar o storyboard alcançável pelo caminho de prompt; `grep`
mostrou que o único chamador era o próprio teste. O laço storyboard → prompt estava aberto.

---

## 3. O que foi construído

### 3.1 Os treze blocos

```text
SUBJECT · CHARACTER · ENVIRONMENT · ACTION · CAMERA · LENS · LIGHT · COLOR
        · MOTION · STYLE · CONTINUITY · OUTPUT        <- PROMPT_BLOCK_ORDER (12 emitidos)
NEGATIVE                                              <- PROMPT_BLOCKS declara 13
```

`NEGATIVE_BLOCK` fica **fora** de `PROMPT_BLOCK_ORDER` de propósito: providers de difusão
recebem o negative como argumento separado, e anexá-lo ao prompt positivo inverteria seu
sentido. A decisão é fixada por `test_negative_is_declared_but_never_joined_to_the_prompt`.

### 3.2 Dedupe na junção dos blocos

`_join` passou de `@staticmethod` para `@classmethod` e aplica `_dedupe`. A correção ficou no
compilador, não nos resolvers: é o compilador que junta blocos, e a defesa pega **qualquer**
duplicação entre blocos, não só este caso. Medido depois: 0 cláusulas repetidas nos 5 presets.

### 3.3 Cor separada de estilo

`StyleResolver` ganhou `style_phrase()` (só o nome) e `color_phrase()` (LUT, contraste,
grain, paleta). `describe()` foi preservado integralmente — é superfície pública e
`test_style_vocabulary_is_described_without_camera_detail` afirma `"cyan" in described`.

`DROP_PRIORITY` agora tem `color` **abaixo** de `style`: sob aperto de orçamento, a grade —
que é o que mantém uma sequência reconhecível entre cortes — sobrevive ao adjetivo.

### 3.4 Orçamento por provider

```text
flux-dev        -> 1000
wan-video       -> 1200
hunyuan-video   -> 1200
desconhecido    -> 1000
com teto 120    -> 120   (provider nunca afrouxa o teto)
```

`max_prompt_chars` continua sendo o limite duro e sobrescrevível — quebrei isso na primeira
tentativa e um teste existente pegou (seção 4).

### 3.5 `compile_beats()` — o laço fechado

```text
StoryboardEngine.as_beats()  ->  tuple[SceneBeat, ...]  ->  PromptCompiler.compile_beats()
        (ETAPA 8)                  tipo de contrato              (ETAPA 9)
```

A assinatura é sobre `SceneBeat`, **não** sobre `Storyboard`. `prompt_compiler` está em
`INDEPENDENT_MODULES`, e `test_core_independence.py` importa cada módulo num interpretador
limpo e falha se ele puxar um irmão. Importar o engine teria quebrado a guarda.

Saída real:

```text
POST /api/v1/core/storyboard/compile
  { "brief": "Quero um comercial de 30 segundos para uma camiseta artesanal.",
    "scene_count": 3, "persona_id": "CHAR_PETRICK", "style": "neo-tokyo" }

scenes[0].shot_code  SH002
scenes[0].prompt     "Quero um comercial de 30 segundos para uma camiseta artesanal,
                      Petrick Martins, 50 years old, ..., rain, steam, floating signage glow,
                      the world before the story, slow crane reveal descending to street level,
                      24mm, blue hour ambience, soft volumetric key, saturated cyan-magenta
                      night grade, ..., slow, deliberate, neo tokyo, establish geography once;
                      later scenes inherit this light, detailed textures, ..."
scenes[0].tokens     34
scenes[0].dropped    []
```

### 3.6 `SceneBeat.lens` e `SceneBeat.continuity`

Adicionados como opcionais (`""`). Sem eles, a projeção `as_beats()` perdia a focal e a nota
de continuidade do shot escalado — verificado: `as_beats` produzia beats com `lens` ausente.
Nenhum teste fixa o conjunto de campos de `SceneBeat`, e os dois únicos pontos de construção
(`director_agent.py:315`, `storyboard_engine.py:406`) continuam válidos pelos defaults.

---

## 4. Erros meus, encontrados por teste

**4.1 — Quebrei um knob público.** Ao introduzir `budget_for()`, passei a ignorar
`max_prompt_chars`, que é público e sobrescrevível. `test_oversized_prompt_is_trimmed_and_the_trim_is_reported`
faz `compiler.max_prompt_chars = 120` e falhou. **Fix:** `budget_for()` devolve
`min(provider_budget, self.max_prompt_chars)` — o provider só aperta, nunca afrouxa.

**4.2 — Uma hipótese errada que eu quase documentei como achado.** Achei que a cor do estilo
fosse descartada. Medi antes de escrever e descobri que `describe()` já a concatena. O
achado real era outro (fusão com STYLE). Registrado aqui porque a diferença muda o projeto:
não era preciso **levar** a cor ao modelo, era preciso **separá-la**.

**4.3 — Um regex corrompeu um import multi-linha.** Ao adicionar nomes a
`from app.core.contracts import (...)`, meu padrão `^from app\.core\.contracts import (.+)$`
casou com a linha de abertura parentetizada e produziu
`from app.core.contracts import (, NEGATIVE_BLOCK, PROMPT_BLOCKS`. Erro de coleção imediato.
**Lição (repetida da ETAPA 6):** regex sobre import multi-linha não é seguro; editar o bloco
inteiro é.

**4.4 — Testes meus com expectativas erradas.** Marcadores de uma letra colidiam
(`index("CO")` casava dentro de `"COLOUR"`); troquei por igualdade exata do prompt, que é
mais forte. `compiled.dropped` é **tupla**, não lista. E um teste de trim usava orçamento 200
para um prompt de 108 caracteres, então nunca aparava.

---

## 5. Fronteiras preservadas

| Fronteira | Teste |
|---|---|
| O compilador não conhece o storyboard | `test_compile_beats_takes_only_contract_types` (AST: imports ⊆ `contracts`) + `test_core_independence.py` |
| A rota não contém lógica de composição | `test_the_route_contains_no_composition_logic_of_its_own` (AST sobre `main.py`) |
| `describe()` não mudou | `test_describe_is_unchanged_so_its_callers_still_work` |
| NEGATIVE nunca vai ao prompt positivo | `test_negative_is_declared_but_never_joined_to_the_prompt` |
| Persona PLANNED não vaza | `test_a_planned_persona_never_leaks_into_a_prompt` |
| Persona desconhecida não é inventada | `test_an_unknown_persona_is_ignored_rather_than_invented` |
| A rota da ETAPA 8 segue só escalando | `test_the_casting_endpoint_is_untouched` |

`DirectorAgent` **não foi editado** — continua sendo território da ETAPA 7, que está em aberto.

---

## 6. Verificação

Todos os comandos foram executados; os números abaixo são as saídas reais.

```
PYTHONPATH=backend pytest backend/tests -q                    -> 548 passed
pytest backend/tests -q          (hermético, sem PYTHONPATH)  -> 548 passed
pytest <arquivos em ordem inversa>                            -> 548 passed
pytest <13 arquivos do baseline 3708784>                      -> 22 passed
pytest backend/tests/test_core_independence.py                -> 17 passed
coverage report --include=*/prompt_compiler.py                -> 67 stmts, 0 miss, 100%
coverage report --include=*/style_resolver.py                 -> 50 stmts, 0 miss, 100%
coverage report --include=backend/app/core/*                  -> 1288 stmts, 26 miss, 98%
coverage report --include=backend/app/*                       -> 3029 stmts, 500 miss, 83%
npm run build                                                 -> ✓ Compiled successfully
git diff --diff-filter=D --name-only 3708784                  -> vazio (0 removidos)
```

Caminhos de código efetivamente exercitados: `PromptCompiler.compile → budget_for → _join →
_dedupe`, `compile_beats`, `compile_negative`, `StyleResolver.style_phrase/color_phrase`,
`GenerationSpecBuilder.build` (com `provider` propagado) e a rota
`compile_core_storyboard` em `main.py`.

---

## 7. Achados documentados, não remendados

**7.1 — Adjetivos soltos vindos de campos verbatim.** `ShotPreset.depth = "medium, strong
parallax"` vira `"medium, strong parallax depth of field"`, e `StylePreset.contrast = "high,
glowing highlights"` vira a cláusula solta `"high"`. É o dado publicado sendo emitido como
está; reescrevê-lo significaria editar presets que as guardas da ETAPA 6 protegem
(`test_the_published_presets_come_first_and_unchanged`).

**7.2 — O SUBJECT continua no idioma do usuário** enquanto o resto do prompt é inglês
(medido: `"Um herói caminha pela cidade à noite"` seguido de cláusulas em inglês). Não é
defeito: `SYSTEM_PROMPT.md` determina que o texto cru vire o bloco SUBJECT. Não corrigido.

**7.3 — `ACTION` vem de `ShotPreset.intention`.** É o único campo em inglês que descreve o que
a cena faz (`"the world before the story"`, `"desire stated"`, `"confident forward motion"`).
O `objective` do beat serviria semanticamente melhor, mas é português e misturaria idiomas no
prompt. Compromisso explícito, não invenção: nada é sintetizado.

**7.4 — `describe()` ficou sem chamador em produção.** Continua sendo superfície pública e
testada. Mantida de propósito; removê-la quebraria um chamador externo sem ganho.

---

## 8. Documentação atualizada

`CHANGELOG.md` (bloco `[Unreleased] — ETAPA 9`), `ARCHITECTURE.md` (nova seção "Prompt
compiler (ETAPA 9)" + 5 guardas na tabela + rota na fronteira de API), `ROADMAP.md` (item
atualizado), `README.md` (contagens, seção "Prompt compiler", suítes), `backend/README.md`
(contagens, seção "Prompt compiler", módulos a 100%).

---

## 9. Pendências

Herdadas e não resolvidas: **ETAPA 7 (Director AI) inteira** — bloqueada por falha de
infraestrutura no sandbox quando foi pedida; P0-2b persistência de `Job`; ledger de persona em
memória; bibliotecas em memória; P0-3 `hub.publish` sem chamadores; P0-4 endpoints sem
autorização; UI não consome as rotas Core; `next@14.2.32` com CVE conhecida;
`minio`/`python-jose` declarados sem uso em caminho vivo; motivação `transformation` com 2 de
300 presets; arco `documentary` inalcançável e ciclo de objetivos em `_build_beats` (ambos
dependem da ETAPA 7).

Novas desta etapa: os adjetivos soltos de campos verbatim (7.1) e `describe()` sem chamador em
produção (7.4).
