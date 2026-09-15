# RELATÓRIO TÉCNICO — ETAPA 6: SHOT LIBRARY (300 PRESETS)

**Repositório:** `petrickmsilva-alt/BROBOND-AI-STUDIO`
**Branch:** `arena/01a0a25e-brobond-ai-studio`
**Data:** 2026-09-14
**Escopo:** apenas a ETAPA 6. Nenhuma etapa posterior foi iniciada.

---

## 1. Objetivo

Levar a biblioteca de shots ao alvo que o próprio repositório declara em
`knowledge_base/SHOT_LIBRARY.md`:

> "The full library target is 300+ shots. New shots require code, name, lens, frame,
> movement, lighting, emotional intention and continuity notes."

E entregar o navegador visual que `ShotResolver.catalog()` já previa no docstring desde a
ETAPA 2 (*"Feeds the visual shot browser required by ETAPA 6, so a user never has to type a
shot code"*).

---

## 2. Auditoria do ponto de partida

| Item | Estado antes da ETAPA 6 |
| --- | --- |
| Shots publicados | 10 (`SH001, SH014, SH032, SH051, SH089, SH120–SH124`) |
| Alvo declarado no documento | 300+ |
| `ShotPreset` com `frame` / `lighting` / `continuity` | ❌ campos não existiam |
| Navegador por função / lente / enquadramento | ❌ só busca textual |
| Validação de conformidade com a Bíblia | ❌ inexistente |
| `resolve()` para código desconhecido | ✅ `None` (nunca inventa) — preservado |

**Conclusão:** faltavam 290 presets, três campos do contrato e qualquer mecanismo que
garantisse que 300 entradas não contradizem a `CINEMATIC_BIBLE.md`.

### Decisão de preservação

`SHOT_LIBRARY.md` declara: *"Shot codes are stable identifiers."* Portanto:

- **`SEED_SHOTS` não foi tocado** — os 10 publicados permanecem byte a byte iguais.
- Os 290 novos ocupam os códigos livres de `SH001–SH300` (290 livres + 10 publicados = 300
  exatos). Nada foi renumerado.
- A composição acontece em `main.py`, no composition root, então `shot_resolver.py` **não**
  importa `shot_library.py` — sem ciclo de import e sem alteração no módulo existente.

---

## 3. O que foi implementado

| Arquivo | Status | Conteúdo |
| --- | --- | --- |
| `backend/app/core/shot_library.py` | **novo, 667 l** | 290 presets autorados + `ShotLibrary` + derivação técnica |
| `backend/app/core/contracts.py` | alterado | `ShotPreset` += `frame`, `lighting`, `continuity`, `family` (com defaults) |
| `backend/app/core/cinematic_library.py` | alterado | `"descent"` adicionado ao vocabulário de `reveal` |
| `backend/app/core/__init__.py` | alterado | 7 exports; docstring (oito → nove componentes) |
| `backend/app/schemas.py` | alterado | 3 schemas novos |
| `backend/app/main.py` | alterado | 4 rotas somente-leitura + fiação do composition root |
| `backend/tests/test_core_shot_library.py` | **novo, 375 l** | 45 testes |
| `backend/tests/test_core_shot_api.py` | **novo, 193 l** | 26 testes |

### Formato de autoria

Cada linha carrega **apenas os campos criativos** que o documento pede:

```python
(code, name, lens_mm, frame, movement, lighting, intention, continuity)
```

Os campos técnicos — `speed`, `focus`, `shake`, `depth` — são **derivados** de
enquadramento, lente e movimento. Isso é deliberado: um close-up de 85 mm tem sempre
profundidade rasa e um tripé travado nunca treme. Derivar evita digitar 1.160 valores à mão
que poderiam contradizer-se entre si.

### As 12 famílias narrativas

| Família | Shots | Família | Shots |
| --- | --- | --- | --- |
| establishing | 25 | intimacy | 24 |
| introduction | 25 | product | 24 |
| dialogue | 24 | fashion | 24 |
| action | 24 | transition | 24 |
| tension | 24 | atmosphere | 24 |
| *(publicados)* | 10 | resolution | 24 |
| | | documentary | 24 |

Nenhuma família é entrada simbólica: a menor tem 24 shots.

### Superfície HTTP (4 rotas novas, todas `GET`)

```
GET /api/v1/core/shots?q=&family=&lens_mm=&frame=&motivation=&limit=
GET /api/v1/core/shots/families
GET /api/v1/core/shots/audit
GET /api/v1/core/shots/{shot_code}
```

As rotas estáticas são declaradas **antes** de `{shot_code}`, senão `/shots/families` seria
engolida pelo caminho dinâmico — coberto por
`test_the_static_routes_are_declared_before_the_dynamic_one`.

---

## 4. Resultado: a biblioteca inteira obedece à Bíblia

```
total 300 | target 300 | meets_target True
published 10 | expanded 290
violations {} | duplicates []
```

A validação (`ShotLibrary.violations()`) confere, para cada um dos 300:

- lente dentro das 5 distâncias focais que a Bíblia declara;
- movimento nomeando uma motivação (ou declarando ausência de movimento);
- enquadramento entre os 4 tamanhos conhecidos;
- intenção emocional presente;
- **em shots novos:** `frame`, `lighting` e `continuity` preenchidos.

Isso é o que torna uma biblioteca de 300 entradas confiável: tamanho não vale nada se as
entradas contradizem o documento que dizem implementar.

### Distribuição por lente e enquadramento

| Lente | Shots | | Enquadramento | Shots |
| --- | --- | --- | --- | --- |
| 24mm | 57 | | establishing shot | 65 |
| 35mm | 69 | | medium shot | 101 |
| 50mm | 60 | | close-up | 70 |
| 85mm | 62 | | extreme close-up | 54 |
| 135mm | 52 | | | |

### Distribuição por motivação — **achado honesto**

| Motivação | Shots |
| --- | --- |
| observation | 161 |
| approach | 125 |
| reveal | 21 |
| escape | 16 |
| **transformation** | **2** |

A biblioteca é fortemente enviesada para `observation` e `approach`, e **quase não cobre
`transformation` (2/300)**. Isso é realista — a maioria dos planos é observacional ou de
aproximação — mas um diretor procurando um movimento de transformação encontrará pouquíssimo.
O número é **exposto por `audit()` e fixado por teste** (`test_motivation_coverage_is_reported_honestly`)
em vez de escondido. Ampliar essa cobertura é trabalho de uma expansão futura, não algo que
eu deva maquiar agora.

---

## 5. Defeitos encontrados e corrigidos

### 5.1 `duplicates()` não detectava código repetido

Bug real, pego pelo próprio teste. A implementação comparava o código já visto com o código
atual:

```python
if key in seen and seen[key] != shot.code:   # sempre False quando o código se repete
```

Justamente no caso principal — o mesmo código duas vezes — os dois são iguais por definição,
então nada era sinalizado. Pior: `_by_code` é um dict, então uma duplicata seria descartada
em silêncio. Reescrito contando códigos e nomes independentemente.

### 5.2 Lacuna na gramática da ETAPA 5 (`descent`)

A primeira validação dos 300 retornou **1 violação**: `SH087` usa *"crane descent following
the fall"* e o vocabulário de `reveal` conhecia `"descend"`/`"descending"`, mas não o
substantivo `"descent"`.

A correção foi **na gramática, não no shot**. Reformular o texto de SH087 para passar no
verificador seria enganar o verificador. `"descent"` é a mesma noção cinematográfica, então
entrou no conjunto — coberto por `test_the_descent_noun_form_is_recognised`.

### 5.3 `violations()` não exigia os campos da política de expansão

A política do documento exige `frame`, `lighting`, `intention` e `continuity` em shots
**novos**, mas a validação só checava `intention`. Um shot novo poderia omitir os outros três
e passar. Corrigido, com isenção explícita para os 10 publicados.

### 5.4 Código morto que eu mesmo introduzi

Escrevi `replace_family()` "para composição futura" e nunca a usei. Removida, junto com o
import que ela exigia. Cobertura de `shot_library.py` foi de 97% para **100%** depois disso e
de dois testes que faltavam (frame desconhecido, intenção ausente).

---

## 6. Preservação verificada

| Garantia | Teste |
| --- | --- |
| Os 10 publicados vêm primeiro e inalterados | `test_the_published_presets_come_first_and_unchanged` |
| Os 9 campos originais de SH001 intactos | `test_the_published_shots_keep_their_original_nine_fields` |
| SH122 continua `135mm` (o bug da ETAPA 5) | idem |
| Nenhum valor inventado nos 10 publicados | `test_the_published_shots_are_not_given_invented_expansion_fields` |
| Nenhum código publicado reutilizado | `test_published_codes_are_reserved` |
| SH001 ainda compila exatamente como antes | `test_a_published_shot_still_compiles_exactly_as_before` |
| Código desconhecido continua sem fallback | `test_an_unknown_shot_does_not_silently_fall_back` |

Os 10 publicados mantêm `frame=""`, `lighting=""` e `continuity=""` **de propósito**: a
`SHOT_LIBRARY.md` não declara tamanho de plano para todos eles, e preencher seria fabricar.
Eles ficam isentos da regra de campos novos, mas não das regras de lente e motivação.

---

## 7. Verificação

| Verificação | Antes | Depois |
| --- | --- | --- |
| `pytest backend/tests -q` | 360 passed | **431 passed** |
| Modo hermético (sem `PYTHONPATH`) | 360 | **431** |
| Os 22 testes originais, isolados | 22 passed | 22 passed |
| Independência do Core (subprocesso) | 17 passed | 17 passed |
| Cobertura de `core/shot_library.py` | — | **100%** (112 stmts, 0 miss) |
| Cobertura de `backend/app/core/` | 97% | **97%** |
| Cobertura total `backend/app` | 81% | **82%** |
| `npm run build` | ✓ | ✓ Compiled successfully |
| Shots na biblioteca | 10 | **300** |
| Rotas `/api/v1` (HTTP) | 46 | **50** |
| **Rotas removidas** | — | **nenhuma** |

Diff de inventário contra o commit base `3708784` (extraído por AST, HTTP + WebSocket):
**baseline 30 → agora 53, 0 removidas, 23 adicionadas**.

Dois testes existentes foram atualizados porque a contagem cresceu — nada foi removido:
`test_route_inventory_only_grew` (46 → 50) e `test_the_audit_covers_the_whole_library`
(`shots_audited` 10 → 300).

---

## 8. Explicitamente NÃO feito nesta etapa

- **Nenhum dos 10 presets publicados foi alterado.** Continuam byte a byte iguais.
- **Nenhum valor foi inventado para eles.** Os campos novos ficam vazios onde o documento não
  declara.
- **A `SHOT_LIBRARY.md` não foi reescrita.** O código passou a cumprir o alvo que ela declara;
  o documento continua sendo a fonte. (Ele segue listando os 10 em tabela — atualizá-lo com
  300 linhas seria ruído; o catálogo completo está na API.)
- **Biblioteca em memória.** A costura `ShotSource` para PostgreSQL existe desde a ETAPA 2 e
  continua sem implementação.
- **Rotas sem autenticação**, no padrão das `/core/*` existentes (P0-4 aberto).
- **A UI ainda não consome** esses endpoints (ETAPA 15).
- **Cobertura de `transformation` permanece em 2/300** — relatado, não corrigido.

---

## 9. Riscos e recomendação

| Risco | Mitigação aplicada |
| --- | --- |
| 300 entradas contradizerem a Bíblia | `violations()` roda sobre todas; teste exige `{}` |
| Código estável ser renumerado | `PUBLISHED_CODES` reservado + teste de interseção vazia |
| Duplicata descartada em silêncio | `duplicates()` reescrito e testado nos dois sentidos |
| Campos obrigatórios omitidos em shots novos | Regra de completude + teste de isenção |
| Rotas estáticas engolidas por `{shot_code}` | Ordem de declaração fixada por teste |
| Regra implementada dentro da rota | `test_the_shot_routes_contain_no_library_rules` |
| Verificador enganado por reformulação | O caso `descent` foi corrigido na gramática, com teste |

**Recomendação:** a biblioteca agora é o maior ativo de conteúdo do repositório e vive em
memória. Junto com a persistência do `Job` (P0-2b) e do `PersonaLedger` (ETAPA 4), são os
três pontos onde conteúdo valioso se perde a cada reinício de processo. Vale tratar
persistência como etapa própria antes de acumular mais conteúdo sobre memória volátil.
