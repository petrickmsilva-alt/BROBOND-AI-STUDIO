# ETAPA 14 — QUALITY AI

Relatório técnico. Escopo: avaliar o que foi gerado antes de entregá-lo.

**Resultado:** o output deixou de ser aceito sem exame. `QualityGate` é o 12º componente
independente do Core e roda entre a geração e a persistência; um job que não produziu arquivo
deixa de ser `complete`. `777 → 850` testes. Zero arquivos deletados.

Também corrigido no caminho: um `AttributeError` em `from app.core import *` que **eu**
introduzi na ETAPA 13 e nenhum teste pegou.

---

## 1. Auditoria — tudo medido antes de escrever

| # | Achado | Como foi medido |
| --- | --- | --- |
| F1 | **Nada examinava o output gerado** | leitura de `queue.py`: `generate` → `save_path` → `COMPLETE`, sem verificação |
| F2 | `GenerationOutput.width`/`.height` **não eram lidos por ninguém** | `grep -rn "\.width\|\.height" backend/app/` → só `persona.height_m` e o timeline da ET13 |
| F3 | Nada verifica se o arquivo existe ou não está vazio | os únicos `is_file()` de `queue.py` são de **entrada** (LoRA, referência) |
| F4 | "quality" no repo significa outra coisa | `ExportRequest.quality` = resolução; `TimeQuality` = qualidade de luz |
| F5 | `from app.core import *` quebrado | `AttributeError: module 'app.core' has no attribute 'BRIDGING_FAMILIES'` |

### A prova do defeito, antes de escrever código

Um provider que devolve um caminho inexistente e 512×512 quando o spec pedia 16:9:

```
spec pedia aspect_ratio='16:9'
worker: complete
output_url: /tmp/nao-existe-de-fato.png
o arquivo existe? False
```

O job foi entregue como concluído apontando para nada. `SYSTEM_PROMPT.md` é literal sobre
isso: "Não invente arquivos, jobs concluídos, modelos carregados ou outputs inexistentes."

### F5 — um defeito meu que sobreviveu a uma etapa

Na ETAPA 13 removi a constante `BRIDGING_FAMILIES` (era a regra de dissolve morta) mas a
entrada em `__all__` ficou. `from app.core import *` levantava `AttributeError`. Nenhum teste
pegou porque **nada faz star-import** — o pacote é importado por nome em todo lugar.

Corrigido, e agora vigiado por dois testes: um confere `__all__` contra os atributos reais, o
outro executa o star-import num subprocesso.

---

## 2. O que foi feito

### 2.1 `QualityGate` — 12º componente independente

Importa `contracts` (mais `dataclasses`/`pathlib`, e `PIL` só dentro de uma função, opcional).
Entra em `INDEPENDENT_MODULES`, então a guarda estrutural passa a cobri-lo (21 → 23 testes).

A gate roda **antes** de persistir — a ordem é verificada por teste sobre o fonte:

```python
assert source.index("quality_gate.assess") < source.index("storage.save_path")
```

### 2.2 As regras

| Regra | Bloqueia | Verificação |
| --- | --- | --- |
| `file-present` | sim | um arquivo foi escrito no caminho relatado |
| `file-not-empty` | sim | tem ao menos um byte |
| `dimensions-reported` | imagem sim / vídeo não | o produtor relatou largura e altura |
| `resolution-floor` | sim | lado curto ≥ 64px |
| `aspect-ratio` | sim | razão a até 3% da pedida |
| `duration` | sim | vídeo: runtime bate com o spec |
| `frame-rate` | não | vídeo: fps bate com o spec |
| `container` | não | extensão casa com o tipo |

"Missing" e "empty" são achados distintos de propósito: `size_of` devolve **-1** para ausente
e **0** para vazio. Um diz que o provider nunca escreveu; o outro, que escreveu nada.

### 2.3 `dimensions-reported` difere por tipo — e isso foi uma descoberta

A primeira versão tratava a ausência de geometria como violação para qualquer tipo. Medido:
`VideoGenerationOutput(path, duration_seconds, fps)` **não tem** `width` nem `height`. A
regra reprovaria **todo job de vídeo do sistema**.

Os dois contratos de saída não são iguais, então a gate os segue:

- **imagem** sem dimensões → violação (`GenerationOutput` as exige como campos obrigatórios)
- **vídeo** sem dimensões → aviso, e as verificações de geometria são puladas

### 2.4 O que a gate declara que não faz

```
GET /api/v1/core/quality/rules
model_loaded: False
does_not_assess: ['composition', 'prompt adherence', 'anatomy or artifact detection',
                  'aesthetic quality', 'persona likeness']
```

Nenhum modelo é carregado e nenhum é fingido. Nada neste processo vê a imagem, e inventar um
número que parecesse nota estética é exatamente o que `SYSTEM_PROMPT.md` proíbe.

`structural_score` é a fração das verificações estruturais aplicáveis que passaram. Com
nenhuma aplicável devolve **0.0**, porque "não aprendemos nada" não pode ler como "está bom".

`facts.dimensions_source` vale `"provider-report"`: a gate compara a **alegação** do produtor
contra o spec. `verify_dimensions` confere contra os pixels quando há leitor disponível e
devolve `verified: false` com o motivo quando não há — nunca relata verificação não feita.

---

## 3. O defeito, depois

Mesmo cenário da seção 1:

```
ANTES: complete / output_url apontando para arquivo inexistente
AGORA: status = failed
       erro   = Quality gate rejected the render — file-present: no file was produced
                at '/tmp/nao-existe-de-fato.png'; aspect-ratio: 512x512 is 1.000,
                43.7% off the requested 16:9 (1.778)
       output_url = None
       progresso  = 55
```

`output_url` fica `None`: um job que não produziu nada não carrega uma URL.

---

## 4. Um bug meu na implementação, e quatro nos testes

### 4.1 O helper `check()` conflava "passou" com "sem achado"

Escrevi o ramo de vídeo sem geometria como `check(..., passed=not is_image, status=WARNING)`
esperando um aviso. O helper só registra achado quando `passed` é `False` — então o aviso
**nunca era emitido**. O teste pegou. Reescrito com o `append` explícito, porque uma única
chamada não expressa "conta como aprovado **e** ainda assim avise".

### 4.2 Quatro asserções minhas erradas

- `structural_score` arredonda a 4 casas; comparei com a divisão crua e o `approx` falhou.
- `test_the_gate_is_deterministic` construía **dois** specs, e `GenerationSpec.spec_id` é um
  `uuid4` por construção — o teste comparava UUIDs, não veredito. Reescrito para reaproveitar
  um spec, mais um teste que isola o `spec_id` de propósito.
- `fps: 0` é **válido** (significa "não reportado"); eu esperava 422.
- Proibi `PIL` no grafo de imports, mas é um import opcional **dentro** de
  `verify_dimensions`, com `try/except ImportError`.

E um erro de sintaxe meu: `."''` em vez de `."""`. Meu primeiro script de correção também
quebrou, pelas aspas aninhadas — corrigido por número de linha.

---

## 5. Não-vacuidade

| Defeito reintroduzido | Resultado |
| --- | --- |
| gate removida do worker (pré-ET14) | **3 failed**, 842 passed |
| gate que sempre aprova | **9 failed**, 836 passed |

Restaurado: **850 passed**.

---

## 6. Fixtures corrigidas — e por quê

Seis fakes de provider em três arquivos devolviam caminhos que nunca eram escritos
(`tmp_path / "out.png"`, e um `"unused.png"` relativo). Antes da ETAPA 14 nada conferia,
então passavam. Agora escrevem o arquivo.

Isso não enfraquece teste algum: cada um deles afirma **entrega de spec** ou **marcos de
progresso**, e essas asserções estão intocadas. O fixture é que era irrealista.

| Arquivo | Fixtures |
| --- | --- |
| `test_generation_spec_providers.py` | 3 |
| `test_provider_adapters.py` | 2 |
| `test_queue_events.py` | 1 |

---

## 7. Verificações literais

| Verificação | Antes | **Depois** |
| --- | --- | --- |
| `pytest backend/tests -q` | 777 | **850 passed** |
| Sem cache / hermético | 777 | **850 / 850** |
| 22 testes originais | 22 | **22** |
| `test_core_independence.py` | 21 | **23** |
| `test_core_quality.py` (novo) | — | **69** |
| `core/quality.py` cobertura | — | **94%** |
| Cobertura total `backend/app` | 88% | **89%** |
| Rotas `/api/v1` · core · WS | 56 · 29 · 2 | **58 · 31 · 2** |
| `npm run build` | ✓ | **✓** |
| Arquivos deletados desde `3708784` | 0 | **0** |
| `from app.core import *` | **AttributeError** | **ok** |

As duas guardas de inventário foram atualizadas (56 → 58 rotas, +2 paths core) — ambas
existem para crescer.

---

## 8. O que **não** foi verificado, dito explicitamente

- **Nenhuma avaliação estética existe.** Não é uma lacuna desta etapa, é o escopo: sem modelo
  carregado não há como julgar composição, anatomia ou aderência ao prompt, e fingir violaria
  `SYSTEM_PROMPT.md`. O endpoint diz isso na resposta.
- **A geometria não é conferida contra os pixels.** Pillow **não está instalado**
  (`ModuleNotFoundError: No module named 'PIL'`), então as linhas 387-396 de `quality.py` — o
  ramo de `verify_dimensions` que lê a imagem — permanecem descobertas e foram exercitadas só
  no caminho que devolve `verified: false`. A gate confere a **alegação** do provider.
- **As linhas 349-350** (`except (OSError, ValueError)` em `size_of`) não são disparáveis
  portavelmente: `Path("\x00bad").is_file()`, caminhos com 5000 segmentos e `"/"` todos
  devolvem `False` em vez de levantar, então o `-1` vem do ramo normal. Preferi documentar a
  inventar um teste que finja o cenário.
- **Nenhum job real de GPU foi avaliado.** Os providers foram substituídos por fakes que
  escrevem arquivos de verdade; `diffusers`/`torch` não estão instalados.

---

## 9. Arquivos

| Arquivo | Mudança |
| --- | --- |
| `backend/app/core/quality.py` | **novo** — 481 l, 94% de cobertura |
| `backend/app/queue.py` | gate entre `generate` e `save_path`; singleton `quality_gate` |
| `backend/app/core/__init__.py` | 12 componentes; `BRIDGING_FAMILIES` fantasma removido de `__all__` |
| `backend/app/schemas.py` | 5 schemas de qualidade |
| `backend/app/main.py` | `quality_gate` no composition root + 2 rotas |
| `backend/tests/test_core_quality.py` | **novo** — 69 testes, 721 l |
| `backend/tests/test_core_independence.py` | `app.core.quality` em `INDEPENDENT_MODULES` + 2 guardas de `__all__`/star-import |
| `backend/tests/test_core_api.py` | guardas de inventário 56 → 58 e +2 paths core |
| `test_generation_spec_providers.py`, `test_provider_adapters.py`, `test_queue_events.py` | 6 fixtures passam a escrever o arquivo |
| `CHANGELOG.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `README.md`, `backend/README.md` | atualizados |

Nenhum arquivo deletado. `DirectorAgent`, `StoryboardEngine`, `PromptCompiler`, `VideoTimeline`
e os providers não foram alterados.
