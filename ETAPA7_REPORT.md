# ETAPA 7 — DIRECTOR AI

Relatório técnico. Escopo: `DirectorAgent`, o diretor de cinema com quem o usuário conversa.

**Resultado:** quatro defeitos de direção corrigidos, todos medidos antes. O arco
`documentary` — morto dos dois lados — foi restaurado. `director_agent.py` em **100%** de
cobertura. `670 → 692` testes. `DirectorAgent` continua determinístico: nenhum LLM carregado,
nenhum fingido.

Esta etapa estava bloqueada por falha do sandbox desde a primeira tentativa. Foi executada
agora, junto com a ETAPA 12, como pedido.

---

## 1. Auditoria — cinco suspeitas, uma refutada

Todas verificadas por execução, não por leitura.

| # | Suspeita | Veredito |
| --- | --- | --- |
| D1 | Arco `documentary` inalcançável | **confirmado** |
| D2 | 8 beats = 4 beats duas vezes | **confirmado** |
| D3 | Formato escolhido por ordem de dicionário | **confirmado** |
| D8 | Ritmo declarado contradiz o entregue | **confirmado** |
| D9 | `expand()` sem teto | **REFUTADO — não é defeito** |

### D9 refutado: medir antes de afirmar

Suspeitei que `expand(scene_count=50)` produzindo 50 beats fosse um bug, porque `direct()`
clampa em `MAX_BEATS=8`. Falso. A validação existe, em duas outras camadas:

- `StoryboardRequest.scene_count: int = Field(default=4, ge=2, le=12)`
- `StoryboardEngine.validate` → `"360.0s exceeds the 180.0s ceiling"`

`test_an_overlong_runtime_is_reported_as_a_finding_not_a_crash` fixa exatamente esse
comportamento. `expand` sem teto é **camada**, não descuido. Não foi alterado.

### D1 — o arco morto

```
'a documentary about a small farm'   -> format='commercial'  clarification=True
'um documentario sobre uma fazenda'  -> format='film'
```

Inglês nem conhecia a palavra e caía em `commercial` **com pergunta de esclarecimento**;
português dobrava em `film`. Enquanto isso o engine já tinha
`ARC_BY_FORMAT["documentary"]` e a biblioteca tinha **24 presets** da família — código morto
dos dois lados.

Havia um teste fixando o defeito de propósito:

```python
def test_the_documentary_arc_is_currently_unreachable(engine):
    """... Restoring it is ETAPA 7 (Director) work; this test fails the
    day that lands, which is the reminder to drop the note."""
```

Ele falhou exatamente como projetado. Foi substituído por testes que afirmam o arco
alcançável — não removido em silêncio.

### D3 — a ordem do dicionário decidia

```
'um fashion film editorial'   -> {'fashion': 2, 'film': 1}   escolhe 'fashion'
```

O resultado estava certo, mas pelo motivo errado: `fashion` vem antes de `film` na tabela. E
havia casos em que a regra errada aparecia:

```
'reels para vender meu produto na loja'   counts={'reels': 1, 'commercial': 3}
   ordem='reels'   especificidade='commercial'   <== DIVERGEM
'story para vender produto na loja'       counts={'story': 1, 'commercial': 3}
   ordem='story'   especificidade='commercial'   <== DIVERGEM
```

### D8 — o diretor descrevia um ritmo que não entregava

```
reels  pacing='cortes rápidos, 1.5s por plano'
       mas beats duram [5.0, 5.0, 5.0, 5.0]  total=20.0s
```

Todo formato recebia 4×5 = 20s idênticos. A frase prometia 1.5s por plano.

---

## 2. O que foi feito

### 2.1 Formato por especificidade, não por posição

```python
detect_formats("reels para vender meu produto na loja")
# [("commercial", 3), ("reels", 1)]
```

Ranqueia por contagem de palavras-chave. `sorted` é estável, então empate mantém a ordem de
declaração — regra documentada em vez de acidente. Todos os resultados pinados por teste
continuaram idênticos.

### 2.2 Empate é dito, não decidido em silêncio

```python
detect_format_conflict("fashion story")   # ('fashion', 'story')
```

Com empate real a `clarification` nomeia os dois candidatos, no idioma do usuário. Uma
intenção clara continua sem pergunta — `"Quero vender uma camiseta"` segue com
`clarification == ""`, como o teste exige.

### 2.3 `documentary` como formato de primeira classe

Palavras-chave nos dois idiomas, `concept`/`music`/`pacing` próprios, declarado antes de
`film` (a leitura documental é a mais específica quando os dois vocabulários aparecem).

```
'documentário sobre artesãos locais'   format=documentary
  familias=['establishing', 'documentary', 'documentary', 'documentary', 'resolution']
'a documentary about local artisans'   format=documentary   (idem)
'um trailer de cinema'                 format=film          (não roubado)
```

### 2.4 Ritmo declarado = ritmo entregue

`pacing` carrega `{shot}`, preenchido com a duração real dos beats:

```
duration_per_scene=5.0  ->  'cortes rápidos, 5s por plano'
duration_per_scene=1.5  ->  'cortes rápidos, 1.5s por plano'
```

Não mudei as durações: `test_expand_preserves_the_storyboard_camera_ladder` fixa beats a 5.0s
e o `StoryboardEngine` depende de `duration_per_scene` explícito (o teste de teto espera
exatamente `360.0s`). A correção honesta era parar de mentir na frase.

### 2.5 Oito beats distintos

`objectives` e `emotions` passaram de 4 para 8 entradas por idioma, casando com `MAX_BEATS`.
O primeiro objetivo de cada idioma foi preservado — é pinado por `test_core_api.py:58`.

---

## 3. Um furo meu, encontrado e fechado

A primeira prova de não-vacuidade **não provou nada**: reintroduzi o first-match por ordem de
dicionário e a suíte continuou **689 passed**. Meu teste de ranking chamava `detect_formats`,
que eu não tinha revertido — então passava por construção.

Achei então entradas onde as duas regras divergem de fato (`"reels para vender meu produto na
loja"`) e escrevi `test_specificity_overrides_declaration_order` sobre elas. Refeita a prova:

```
1 failed, 689 passed
FAILED test_specificity_overrides_declaration_order
```

Segunda prova, o `1.5s` hardcoded de volta no pacing:

```
2 failed, 688 passed
FAILED test_pacing_states_the_duration_the_beats_actually_carry
FAILED test_no_pacing_line_contradicts_its_own_beats
```

---

## 4. Um teste atualizado, com o motivo declarado

`test_casting_is_not_emotion_aware` falhou porque fixava o conjunto de emoções em quatro.
Sua asserção importante é a segunda: que nenhuma emoção do diretor casa por token com as
intenções em inglês da biblioteca (senão o pareamento por emoção seria código morto vestido
de funcionalidade).

Antes de atualizar, verifiquei as oito contra as **300** intenções da biblioteca:

```
curiosidade/desejo/tensão/convicção                    match=[]
reconhecimento/intimidade/reverência/pertencimento      match=[]
```

Zero matches em todas. A invariante continua valendo; só o vocabulário pinado foi atualizado,
e o docstring diz isso.

---

## 5. Não alterado, de propósito

- **`CAMERA_LADDER` continua com 4 e ciclando.** Estabelecer → conduzir → intensificar →
  isolar é gramática visual, fixada por `beats[4].camera == beats[0].camera`. Beat 5 tem
  objetivo novo e câmera repetida, o que é legítimo: a progressão narrativa avança, o
  vocabulário de câmera é um conjunto fechado.
- **`expand()` sem teto próprio** (D9 refutado acima).
- **Nenhum LLM.** `_enrich` segue opcional e degradando em silêncio. Nenhum modelo é
  declarado carregado.
- **`/api/v1/storyboards/expand` intocado.** Continua delegando a `DirectorAgent.expand`.

---

## 6. Verificações literais

| Verificação | Antes | **Depois** |
| --- | --- | --- |
| `director_agent.py` cobertura | 98% | **100%** |
| `storyboard_engine.py` cobertura | 100% | **100%** |
| `test_core_director_agent.py` | 20 testes | **41** |
| `test_core_storyboard_engine.py` | 47 testes | **49** |
| `pytest backend/tests -q` | 633 | **692 passed** |
| 22 testes originais · independência | 22 · 17 | **22 · 17** |
| Rotas `/api/v1` · core · WS | 54 · 27 · 2 | **54 · 27 · 2** |
| `npm run build` | ✓ | **✓** |
| Arquivos deletados desde `3708784` | 0 | **0** |

---

## 7. Arquivos

| Arquivo | Mudança |
| --- | --- |
| `backend/app/core/director_agent.py` | `detect_formats`, `detect_format_conflict`, `_pacing`, `_clarification`, formato `documentary`, 8 objetivos/emoções — 100% de cobertura |
| `backend/tests/test_core_director_agent.py` | +21 testes |
| `backend/tests/test_core_storyboard_engine.py` | teste-lembrança substituído por 3 testes do arco alcançável; vocabulário de emoções atualizado |
| `CHANGELOG.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `README.md`, `backend/README.md` | atualizados |

Nenhum arquivo deletado.
