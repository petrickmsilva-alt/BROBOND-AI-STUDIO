# RELATÓRIO TÉCNICO — ETAPA 5: CINEMATIC LIBRARY

**Repositório:** `petrickmsilva-alt/BROBOND-AI-STUDIO`
**Branch:** `arena/01a0a25e-brobond-ai-studio`
**Data:** 2026-09-14
**Escopo:** apenas a ETAPA 5. Nenhuma etapa posterior foi iniciada.

---

## 1. Objetivo

Transformar a `knowledge_base/CINEMATIC_BIBLE.md` de **prosa** em **gramática estruturada e
regras aplicáveis**: o que cada distância focal significa, o que cada luz faz, quais
motivações justificam um movimento de câmera, e quais regras de grade não são negociáveis.

---

## 2. Auditoria do ponto de partida

| Capacidade | Estado antes da ETAPA 5 |
| --- | --- |
| Estilo → vocabulário técnico | ✅ `StyleResolver` (7 presets, ETAPA 2) |
| Código de shot → preset de direção | ✅ `ShotResolver` (10 shots, ETAPA 2) |
| Intenção em linguagem natural → estilo | ✅ `DirectorAgent` (ETAPA 2) |
| **Linguagem de lentes consultável** | ❌ `lens` era string livre |
| **Gramática de enquadramento/ângulo** | ❌ inexistente |
| **Papéis de luz e o que suportam** | ❌ inexistente |
| **Motivação de movimento de câmera** | ❌ nada registrava nem verificava |
| **Regras de grade verificáveis** | ❌ inexistente |
| **Consistência visual de um episódio** | ❌ nenhum objeto modelava o look de um episódio |

**Conclusão da auditoria:** a CINEMATIC_BIBLE declara regras precisas — *"Volumetric haze is
used to reveal depth, never as decoration"*, *"Every camera movement must have motivation"*,
*"Grain is subtle and consistent across an episode"* — e **nenhuma delas era verificável**,
porque nada no código as representava. Um preset podia violar a Bíblia inteira sem que
qualquer teste ou endpoint percebesse.

### Fronteira adotada (para não duplicar)

A Bíblia é *descritiva e normativa*. Os componentes existentes são *decisórios*. Portanto:

```text
DirectorAgent      linguagem natural -> intenção -> style_hint    (ETAPA 2)
StyleResolver      style_id -> vocabulário técnico                (ETAPA 2)
ShotResolver       código -> preset de direção                    (ETAPA 2)
CinematicLibrary   o que o vocabulário SIGNIFICA e se obedece     (ETAPA 5)
```

Dois testes travam essa fronteira: `test_the_library_never_produces_prompt_text` (não há
`compile`/`build`/`enhance`) e `test_the_library_does_not_recommend_styles` (não há
`recommend`/`style_for`/`direct`). A biblioteca **não** escolhe estilo — isso é do Diretor.

---

## 3. O que foi implementado

| Arquivo | Status | Conteúdo |
| --- | --- | --- |
| `backend/app/core/cinematic_library.py` | **novo, 620 l** | 6 perfis frozen + `CinematicLibrary` + 8 regras |
| `backend/app/core/__init__.py` | alterado | 14 exports; docstring (sete → oito componentes) |
| `backend/app/schemas.py` | alterado | 11 schemas novos |
| `backend/app/main.py` | alterado | 9 rotas somente-leitura |
| `backend/tests/test_core_cinematic_library.py` | **novo, 474 l** | 55 testes |
| `backend/tests/test_core_cinematic_api.py` | **novo, 232 l** | 23 testes |

### Gramática codificada (toda citando a fonte)

| Constante | Itens | Origem na Bíblia |
| --- | --- | --- |
| `LENSES` | 24 / 35 / 50 / 85 / 135 mm | "Lens language" |
| `FRAMES` | establishing, medium, close-up, extreme close-up | "Framing" |
| `ANGLES` | low angle → presence, high angle → vulnerability, centered symmetry → authority | "Framing" |
| `LIGHTS` | key, rim, practical, volumetric haze | "Lighting" |
| `TIME_QUALITIES` | blue hour → reflection, hard noon → discipline, warm side light → legacy | "Lighting" |
| `MOTIVATIONS` | reveal, approach, escape, observation, transformation | "Direction" |

Os testes comparam as tuplas **literalmente** contra o documento, então uma edição futura que
invente vocabulário ou remova uma regra falha no teste em vez de divergir em silêncio.

### Regras normativas

| Regra | Severidade | Origem |
| --- | --- | --- |
| `grain-subtle` | attention | "Grain is subtle" |
| `grain-consistent-across-episode` | **violation** | "…and consistent across an episode" |
| `protect-highlights` | attention | "Protect highlights" |
| `teal-amber-sparingly` | attention | "Use teal and amber sparingly" |
| `skin-natural` | ok/attention | "Keep skin natural" |
| `motion-motivated` | violation / attention | "Every camera movement must have motivation" |
| `haze-reveals-depth` | attention | "never as decoration" |
| `lens-declared` | attention | "Lens language" |

Cada achado carrega `source="knowledge_base/CINEMATIC_BIBLE.md"`.

### Superfície HTTP (9 rotas novas, todas `GET`)

```
GET /api/v1/core/cinematic/lenses            GET /api/v1/core/cinematic/lenses/for
GET /api/v1/core/cinematic/framing           GET /api/v1/core/cinematic/lighting
GET /api/v1/core/cinematic/motivations       GET /api/v1/core/cinematic/motivations/of
GET /api/v1/core/cinematic/audit             GET /api/v1/core/cinematic/explain
GET /api/v1/core/cinematic/consistency
```

`test_the_cinematic_routes_are_read_only` afirma que nenhuma expõe verbo além de `GET`: uma
biblioteca de referência não é mutável por HTTP.

---

## 4. Resultado da auditoria sobre a biblioteca real

Rodei as regras contra os **7 estilos e 10 shots publicados**. 12 conformes, 5 sinalizados,
**todos em `attention`, nenhuma `violation`**:

| Item | Regra | Achado |
| --- | --- | --- |
| `cinematic-realism` | motion-motivated | `"motivated, steady"` alega motivação sem nomeá-la |
| `imax-hero` | lens-declared | `"40mm large format"` não está na linguagem de lentes |
| `john-wick` | protect-highlights | `crushed, specular` — proteger realces |
| `neo-tokyo` | grain-subtle | `"medium digital grain"` não está no conjunto sutil |
| `neo-tokyo` | protect-highlights | `glowing` — proteger realces |
| `marvel-trailer` | teal-amber-sparingly | `teal / orange, warm` — usar com parcimônia |
| `marvel-trailer` | lens-declared | `"28mm dynamic wide"` não está na linguagem de lentes |

Reportar as exceções da própria biblioteca é o objetivo: uma regra que nunca é conferida
contra as seeds é uma regra que ninguém segue. `test_the_audit_finds_no_false_violations_in_the_seeds`
fixa que nenhuma seed é condenada — assim apertar um conjunto de palavras-chave não pode
começar a reprovar a biblioteca publicada em silêncio.

---

## 5. Defeitos encontrados e corrigidos

### 5.1 `focal_of("135mm")` devolvia **35**

Bug real, com impacto em dado publicado. A busca era por substring e `"35mm"` ocorre dentro de
`"135mm"`; como 35 vem antes na lista, vencia. Verificado nos dados reais antes de corrigir:

```
SH122 lens='135mm' -> focal_of=35      (errado)
```

Corrigido com fronteira de dígito (`(?<!\d)(\d+)\s*mm`). Depois da correção, os 10 shots e os
7 estilos são lidos sem divergência. Coberto por `test_a_135mm_lens_is_not_read_as_35mm`.

### 5.2 O motor de regras condenava o que a Bíblia não condena

A primeira versão da auditoria produziu **falsos positivos** que expuseram defeitos meus, não
da biblioteca:

| Falso positivo | Causa | Correção |
| --- | --- | --- |
| `"static"` marcado como **violation** | A Bíblia restringe *movimento*; câmera parada não tem o que justificar | `STILL_MOTIONS` → regra não se aplica |
| `"elegant slow dolly"` sem motivação | só `"dolly-in"` estava no vocabulário | `dolly` isolado → approach |
| `"slow drift, backlit"` (SH089) sem motivação | só `"handheld drift"` | `drift`/`handheld` → observation |
| `"motivated, steady"` como **violation** | alega motivação sem nomear | terceiro estado: `attention` |
| `"teal and amber restraint"` sinalizado | a palette já declara parcimônia | `RESTRAINT_WORDS` satisfaz a regra |

`_check_motion` passou de 2 para 3 estados (ok / attention / violation). Depois disso, a
auditoria só produz achados defensáveis.

### 5.3 Dois schemas colapsavam formas distintas

Reutilizei `LightingProfileResponse` para `TimeQuality` (que tem `supports`, não `role`) e
`FrameProfileResponse` para `AngleProfile` (que tem `creates`, não `carries`). Falhava com
`ValidationError` em runtime. Criados `TimeQualityResponse` e `AngleProfileResponse`.

### 5.4 Dependências declaradas não batiam com os imports vivos (achado de infraestrutura)

Ao recriar o ambiente, duas instalações limpas **não rodavam o app**:

| Módulo vivo | Importa | `requirements.txt` declarava |
| --- | --- | --- |
| `backend/app/auth.py` | `jwt` + `jwt.PyJWTError` | `python-jose` (usado só pelo `core/security.py`, morto) |
| `backend/app/storage.py` | `boto3` | `minio` (não importado em nenhum caminho vivo) |

Adicionei `PyJWT==2.14.0` e `boto3==1.43.94` com comentário explicando cada um. É aditivo e
não remove nada; sem isso nenhuma verificação era possível. **Fora do escopo da ETAPA 5**,
registrado aqui por transparência.

---

## 6. Verificação

| Verificação | Antes | Depois |
| --- | --- | --- |
| `pytest backend/tests -q` | 282 passed | **360 passed** |
| Os 22 testes originais, isolados | 22 passed | 22 passed |
| Independência do Core (subprocesso) | 17 passed | 17 passed |
| Cobertura de `core/cinematic_library.py` | — | **100%** (242 stmts, 0 miss) |
| Cobertura de `backend/app/core/` | 96% | **97%** |
| Cobertura total `backend/app` | 78% | **81%** |
| `npm run build` | ✓ | ✓ Compiled successfully |
| Rotas `/api/v1` (HTTP) | 37 | **46** (+9) |
| **Rotas removidas** | — | **nenhuma** |

Diff de inventário contra o commit base `3708784` (extraído por AST, HTTP + WebSocket):
**baseline 30 → agora 49, 0 removidas, 19 adicionadas** (2 da ETAPA 2 + 8 da ETAPA 4 + 9 desta).

O ambiente de verificação (`/tmp/audit-venv`, `node_modules`) havia sido apagado e foi
recriado: `python3 -m venv .venv` + `pip install -r backend/requirements.txt coverage` e
`npm ci`. Os 282 testes anteriores foram reconfirmados verdes **antes** de qualquer código
novo da ETAPA 5.

---

## 7. Explicitamente NÃO feito nesta etapa

- **Nenhum preset foi alterado.** Os 7 estilos e 10 shots publicados continuam byte a byte
  iguais; a auditoria *reporta* exceções, não as corrige silenciosamente.
- **A Bíblia não foi reescrita.** O código passa a obedecê-la; o documento continua sendo a
  fonte.
- **Biblioteca segue em memória** (seeds injetáveis via `StyleSource`/`ShotSource`). A
  costura para PostgreSQL existe desde a ETAPA 2 e continua sem implementação.
- **As rotas não têm autenticação**, seguindo o padrão das `/core/*` existentes (P0-4 aberto).
- **A UI ainda não consome** esses endpoints (ETAPA 15).
- **ETAPA 6 (300 shots) não foi iniciada**, conforme instrução.

---

## 8. Riscos e recomendação

| Risco | Mitigação aplicada |
| --- | --- |
| Vocabulário divergir do documento | Testes comparam as tuplas literalmente |
| Regra apertada condenar a biblioteca publicada | `test_the_audit_finds_no_false_violations_in_the_seeds` |
| Biblioteca virar recomendadora e duplicar o Diretor | Testes de fronteira negam `recommend`/`style_for` |
| Rotas implementarem regra inline | `test_the_cinematic_routes_contain_no_rules_of_their_own` |
| Mutação da referência por HTTP | `test_the_cinematic_routes_are_read_only` |

**Dois itens de infraestrutura que valem atenção fora desta etapa:**

1. `npm ci` avisou que **`next@14.2.32` tem vulnerabilidade de segurança** conhecida. Trocar
   a versão do framework é mudança arriscada e não pertence à ETAPA 5, mas não deve ser
   esquecido.
2. `minio` e `python-jose` permanecem em `requirements.txt` sem serem usados por nenhum
   caminho vivo. Removê-los é limpeza, não correção — deixei de propósito para não reduzir
   dependências declaradas dentro de uma etapa aditiva.
