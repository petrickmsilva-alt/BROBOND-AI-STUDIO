# ETAPA 13 — VIDEO TIMELINE

Relatório técnico. Escopo: montagem — transformar uma sequência escalada num corte só.

**Resultado:** o estúdio deixou de produzir arquivos órfãos. `VideoTimeline` é o 11º
componente independente do Core, `media.concat` é o passo de montagem que faltava, e
`media.probe` finalmente devolve fatos em vez de JSON cru. `692 → 777` testes.
`timeline.py` em **100%** de cobertura. Zero arquivos deletados.

---

## 1. Auditoria — tudo medido antes de escrever

| # | Achado | Como foi medido |
| --- | --- | --- |
| E1 | **Não existe módulo de timeline** | `grep -ln "timeline\|Timeline"` em `backend/**/*.py` → **zero arquivos** |
| E2 | Nada concatena clipes | `grep -rn "concat\|concatenate" backend/ --include=*.py` → **zero resultados** |
| E3 | `export_h264` recebe **uma** origem | leitura de `media.py`: `def export_h264(self, source: str, ...)` |
| E4 | `media.probe` devolve JSON cru e tem **zero chamadores** | retorna `{"raw": result.stdout}`; `grep "\.probe("` só acha um helper homônimo em teste |
| E5 | `media.py` em 47% | linhas 28-33 (`probe`) e 36-46 (`export_h264`) nunca executam |
| E6 | `SYSTEM_PROMPT.md` exige "montagem" | §Diretor IA: "ajuste ritmo, lente, movimento, iluminação, **montagem**, som e duração" |

### O buraco, em concreto

O fluxo existia até a penúltima etapa: o Diretor produz beats (ETAPA 7), o engine escala em
shots reais (ETAPA 8), o compilador gera um prompt por cena (ETAPA 9), os providers renderizam
(ETAPA 10), a fila reporta progresso (ETAPA 11) e o storage guarda (ETAPA 12). **E então cada
cena ficava num arquivo separado, sem nada que os reunisse.**

`Storyboard.runtime_seconds` já somava as durações — o conceito de runtime existia. O que não
existia era ordem, pontos de entrada e saída, transição, trilha ou geometria de entrega.

---

## 2. O que foi feito

### 2.1 `VideoTimeline` — 11º componente independente

Importa `contracts` e nada mais. Entra em `INDEPENDENT_MODULES`, então a guarda estrutural de
independência (17 → 19 testes) passa a cobri-lo: subprocesso em interpretador limpo, sem
`fastapi`, `sqlalchemy`, `celery`, `boto3` ou `pydantic_settings` no grafo.

Uma `Timeline` carrega: clipes ordenados com `start_seconds`/`end_seconds`, transição por
clipe, cama de áudio com fades, `aspect_ratio`, `resolution`, `fps`.

### 2.2 Duração derivada, não somada

```python
return round(max(clip.end_seconds for clip in self.clips), 3)
```

Somar durações esconderia um buraco no meio do corte. Derivada do fim do último clipe, um
buraco aparece no número:

```
clips (0→5, 8→13)  duration_seconds = 13.0
soma das duracoes                     = 10.0
```

`validate` ainda reporta o buraco como aviso de `gap`, com o tamanho em segundos.

### 2.3 Regra de transição

| Situação | Transição |
| --- | --- |
| primeiro clipe | `cut` — não há de onde vir |
| mesma família do anterior | `dissolve` — continuação de uma ideia |
| família diferente | `cut` — mudança de ideia |
| família vazia | `cut` — dois clipes sem família não são "a mesma ideia" |

### 2.4 Geometria de entrega

`ASPECT_BY_FORMAT`: `reels` e `story` em `9:16`, os demais em `16:9`. A caixa vertical é a
tabela trocada (`1080p` → 1080×1920), não uma resolução paralela. `RESOLUTIONS` confere com
`media.QUALITY`, e um teste garante que "1080p" significa o mesmo nos dois lugares — sem isso
o timeline pediria um quadro e o export entregaria outro.

### 2.5 `media.concat` e o `probe` parseado

`concat` monta com o demuxer do FFmpeg, re-encode em vez de `-c copy` (clipes de providers
diferentes não compartilham timebase nem formato de pixel) e mapeia a cama de música como
segunda entrada com `-shortest`.

`probe_fields` extrai `duration_seconds`, `width`, `height`, `fps`, codecs e container.
`24000/1001` vira `23.976`. Payload inválido devolve `{}` em vez de levantar.

A construção dos argumentos vive em **funções puras** (`concat_command`, `probe_fields`,
`scale_filter`) — foi o que permitiu testar de verdade num sandbox sem FFmpeg.

---

## 3. Três defeitos meus, encontrados e corrigidos

### 3.1 Minha regra de transição nasceu morta

A primeira versão dissolvia em `StoryboardEngine.TRANSITION_FAMILIES` (`transition`,
`atmosphere`) — vocabulário existente, então parecia fundamentado. Medido:

```
familias que os arcos de fato usam:
  action, documentary, establishing, fashion, intimacy,
  introduction, product, resolution, tension
intersecao com {transition, atmosphere}: VAZIA
```

**Nenhum arco de `ARC_BY_FORMAT` escala essas famílias.** Um dissolve nunca poderia ter sido
emitido. A biblioteca tem 24 shots `transition` e shots `atmosphere`, mas nenhum arco os usa —
o mesmo padrão de "código morto vestido de funcionalidade" que o repositório já vigia em
`test_casting_is_not_emotion_aware`.

Trocado pela regra de continuação de família, que dispara em cinco dos sete arcos. `film` e o
arco padrão mudam de ideia a cada beat e ficam todos em corte — as duas metades da mesma
regra, ambas fixadas por teste.

### 3.2 Um dataclass que eu criei e nunca usei

`TimelineFinding` nasceu no módulo e `validate` devolve dicts simples. A cobertura apontou a
única linha descoberta do arquivo: era o `to_dict` dele. Removido.

### 3.3 Três asserções minhas erradas

- Fatias do argv conferidas no índice errado (`command[3:7]` em vez de `[2:6]`).
- `command.index("-i", 5)` devolvia o **primeiro** `-i`, não o segundo.
- `"ffmpeg" not in module.lower()` — a palavra aparece na docstring do módulo explicando
  justamente que ele **não** chama FFmpeg. Reescrito para verificar o grafo de imports.

E uma asserção forte demais: exigi dissolve em **todo** arco. `film` e o arco padrão não têm
família repetida, então zero dissolve ali é o comportamento **correto**. O teste passou a
afirmar a relação, não a presença.

---

## 4. Um furo de cobertura que quase passou

Prova de não-vacuidade do `probe`: reverti `media.probe` ao modo pré-ET13 (`{"raw": ...}`) e a
suíte continuou **770 passed**. Nada pegou.

Motivo: sem FFmpeg, `media.probe` levanta `MediaError` antes de chegar ao `return`. Meus
testes cobriam `probe_fields` (a função pura), mas **não a ligação** entre ela e `probe`.

Fechado com quatro testes que stubam `subprocess.run` e monkeypatcheiam `available` — o que é
honesto porque testa a minha ligação e o tratamento de erro, não o ffprobe. Refeita a prova:

```
1 failed, 773 passed
FAILED test_probe_merges_the_parsed_fields_into_its_result
```

As outras duas provas:

| Defeito reintroduzido | Resultado |
| --- | --- |
| regra de dissolve morta | **4 failed**, 766 passed |
| `is_rendered` sempre `True` (fingir mídia) | **8 failed**, 762 passed |
| `probe` devolvendo só `{"raw": ...}` | **1 failed**, 773 passed |

---

## 5. Verificações literais

| Verificação | Antes | **Depois** |
| --- | --- | --- |
| `pytest backend/tests -q` | 692 | **777 passed** |
| Sem cache / hermetico | 692 | **777 / 777** |
| 22 testes originais | 22 | **22** |
| `test_core_independence.py` | 17 | **19** |
| `test_core_timeline.py` (novo) | — | **83** |
| `core/timeline.py` cobertura | — | **100%** |
| `media.py` cobertura | 47% | **92%** |
| Cobertura total `backend/app` | 87% | **88%** |
| Rotas `/api/v1` · core · WS | 54 · 27 · 2 | **56 · 29 · 2** |
| `npm run build` | ✓ | **✓** |
| Arquivos deletados desde `3708784` | 0 | **0** |

As duas guardas de inventário (`test_route_inventory_only_grew` e
`test_openapi_documents_the_core_tag`) foram atualizadas — ambas existem para crescer, e o
comentário da primeira diz isso.

Saída real do endpoint:

```
POST /api/v1/core/timeline  {"brief": "Quero um comercial de 30 segundos ...", "scene_count": 5}
format=commercial  aspect=16:9  box=1920x1080  clips=5  duracao=25.0
complete=False  unrendered=[1,2,3,4,5]  valid=True
audio bed: percussão crescente com resolução quente
  1 SH002 establishing  0.0->5.0   cut
  2 SH028 introduction  5.0->10.0  cut
  3 SH157 product      10.0->15.0  cut
  4 SH158 product      15.0->20.0  dissolve
  5 SH253 resolution   20.0->25.0  cut
```

---

## 6. O que **não** foi verificado, dito explicitamente

- **O FFmpeg não está instalado neste sandbox** (`command -v ffmpeg` → ausente;
  `media.available == False`, `binary: None`). Portanto `media.concat` e `media.export_h264`
  **nunca foram executados de verdade**. O que está verificado é a construção dos argumentos
  (funções puras), a escrita e a limpeza do arquivo de lista do demuxer, o escapamento de
  caminhos com aspas, e a guarda que roda antes de qualquer `subprocess`. As linhas 174-182 de
  `media.py` — o corpo do `export_h264` — continuam descobertas por esse motivo, e já estavam
  antes desta etapa.
- **Nenhum arquivo de vídeo real foi montado.** Durações, resoluções e fps de clipes reais não
  foram lidos via ffprobe; `probe_fields` foi exercitado com payloads no formato do ffprobe,
  não com a saída de um binário.
- **A renderização não está ligada a uma rota.** O endpoint devolve o **plano**. Executar
  `concat` sobre clipes renderizados exige mídia real e FFmpeg, e não foi exposto — expor uma
  rota que responde 503 em todo deploy sem GPU seria pior que não existir.

---

## 7. Arquivos

| Arquivo | Mudança |
| --- | --- |
| `backend/app/core/timeline.py` | **novo** — 427 l, 100% de cobertura |
| `backend/app/media.py` | `concat`, `probe_fields`, `concat_command`, `scale_filter`; `probe` parseado; constantes de codec compartilhadas |
| `backend/app/core/__init__.py` | 11 componentes; exporta `VideoTimeline`, `Timeline`, `Clip`, `AudioTrack`, `ASPECT_BY_FORMAT`, `RESOLUTIONS`, `TRANSITIONS` |
| `backend/app/schemas.py` | 7 schemas de timeline |
| `backend/app/main.py` | `video_timeline` no composition root + 2 rotas |
| `backend/tests/test_core_timeline.py` | **novo** — 83 testes, 846 l |
| `backend/tests/test_core_independence.py` | `app.core.timeline` em `INDEPENDENT_MODULES` |
| `backend/tests/test_core_api.py` | guardas de inventário 54 → 56 e +2 paths core |
| `CHANGELOG.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `README.md`, `backend/README.md` | atualizados |

Nenhum arquivo deletado. `DirectorAgent`, `StoryboardEngine`, `PromptCompiler` e os providers
não foram alterados.
