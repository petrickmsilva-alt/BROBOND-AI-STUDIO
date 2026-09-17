# Quality AI Engine (V3.4)

Um render entra, um veredito honesto 0–100 sai: oito critérios com pesos
configuráveis, um relatório persistente por asset (problemas, pontos fortes,
sugestões) e uma recomendação — retry abaixo de 70, revisão manual em 70–84,
aprovado em 85+, masterpiece em 95+.

O Director AI e o Provider Registry não foram alterados (pré-requisitos do
sprint): o motor **avalia** outputs, não escolhe providers nem planeja cenas.
E o motor **só recomenda** — nada regenera, faz upscale ou aprova
automaticamente. Os três botões da UI registram a decisão do operador; a
execução continua nos fluxos que já existem (`/studio/render`, export).

---

## A regra de honestidade

`SYSTEM_PROMPT.md` proíbe inventar outputs, e o gate estrutural de ETAPA 14
(`core/quality.py`) se recusa a produzir um número estético justamente porque
não consegue ver a imagem. O V3.4 entrega o score 0–100 do sprint **sem
quebrar essa promessa**, declarando a origem de cada número:

| Origem | Significado |
|---|---|
| `measured` | calculado aqui, de fatos reais: geometria contra o aspect ratio pedido, estatísticas de pixel lidas do arquivo (Pillow), fps/duração contra o spec, retenção de termos entre prompt original e compilado |
| `detector` | confiança 0–100 fornecida pelo chamador a partir de um detector externo (rosto, mãos, olhos — ou qualquer critério que um probe melhor mediu) |
| *não medido* | excluído da média ponderada e listado em `unmeasured` — nunca entra como zero inventado |

O denominador da média ponderada é a soma dos pesos **do que foi medido**.
"Não aprendemos nada" é um erro (422), nunca um score.

---

## Os oito critérios (ETAPA 2)

| Critério | Peso default | Como é medido |
|---|---|---|
| `face` | 20 | só via detector externo |
| `hands` | 15 | só via detector externo |
| `eyes` | 15 | só via detector externo |
| `composition` | 15 | geometria real × aspect ratio pedido + piso/alvo de resolução |
| `lighting` | 10 | luminância média e contraste, lidos do arquivo real |
| `color` | 10 | saturação média (HSV), lida do arquivo real |
| `motion` | 10 | fps e duração contra o spec — **só vídeo** |
| `prompt_fidelity` | 15 | retenção de termos significativos entre prompt original e compilado |

Pesos são relativos e configuráveis por chamada (`weights` no request) ou por
injeção (`QualityScorer(weights=...)`). Nenhum número mágico: cada peso,
banda e limiar é uma constante nomeada em `quality_score.py`, `quality_rules.py`
e `quality_engine.py`.

Imagens são julgadas em 7 critérios (motion não se aplica); vídeos em 8.
Vídeo não é sondado por pixel (sem promessa de ffmpeg neste ambiente):
lighting/color de vídeo ficam `unmeasured` a menos que um detector os informe.

---

## As bandas de decisão (ETAPA 4)

| Score | Status | Recomendação |
|---|---|---|
| 0–69 | `retry` | `retry_recommended: true` |
| 70–84 | `manual_review` | nenhuma — o operador decide |
| 85–94 | `approved` | `upscale_recommended` se o lado curto < 1024px |
| 95–100 | `masterpiece` | idem |

Upscale só é recomendado para um render **bom porém pequeno**: ampliar um
render quebrado desperdiça GPU num defeito que o retry deveria corrigir antes.
Geometria desconhecida (lado curto 0) nunca ganha recomendação de upscale.

Por critério: score medido < 60 vira um problema (`issues[]`) com uma sugestão
concreta (`suggestions[]`); ≥ 85 vira um ponto forte (`strengths[]`).

---

## Modelo (ETAPA 3 + 6)

Migração Alembic `0006`, mesma convenção portátil SQLite/Postgres de sempre
(sem foreign keys no banco, uuids `String(36)`, JSON em `Text`):

| Onde | Conteúdo |
|---|---|
| `quality_reports` | uma linha por execução do motor sobre um asset: score, status, flags de recomendação, o documento completo do relatório e a versão do motor. **Append-only**: reavaliar acrescenta, nunca reescreve uma opinião antiga |
| `assets.quality_score` / `quality_status` / `quality_report` / `quality_version` | o último veredito, desnormalizado para a Asset Library filtrar e exibir badge sem join. `NULL` = nunca avaliado (fato diferente de qualquer score) |

`QualityRepository.save_assessment` grava os dois **numa única transação** —
o badge e o histórico não podem divergir. Todo acesso é escopo de workspace:
id estrangeiro responde **404**, nunca 403.

A decisão do operador (`regenerate` / `upscale` / `approve`) é carimbada no
documento do último relatório (`operator_decision`, `operator_decided_at`) —
um registro de intenção humana, nunca uma execução.

---

## Rotas

| Método | Rota | Identidade |
|---|---|---|
| `POST` | `/api/v1/quality/assets/{id}/assess` | exige token; grava relatório + badge + audit `quality.assessed` |
| `GET` | `/api/v1/quality/assets/{id}/report` | exige token; último relatório (404 se nunca avaliado) |
| `GET` | `/api/v1/quality/assets/{id}/history` | exige token; todas as avaliações, mais recente primeiro |
| `POST` | `/api/v1/quality/assets/{id}/decision` | exige token; registra a decisão + audit `quality.decision` |
| `GET` | `/api/v1/quality/config` | pública — critérios, pesos default, bandas e origens (dados de referência, como `/core/quality/rules`) |

O request de `assess` aceita: geometria/timing conhecidos (o motor sonda a
geometria do arquivo real quando ausentes), `aspect_ratio` pedido, os dois
prompts para fidelidade, `signals` (confianças 0–100 de detector) e `weights`
(rebalanceamento por chamada).

---

## UI (ETAPA 5)

`/studio/quality`: Asset Library com badge do último veredito, score radial
SVG, radar chart sobre os critérios **medidos** (não medidos são listados por
nome, não desenhados como zero), problemas/pontos fortes/sugestões, e os três
botões — **Regenerar**, **Upscale**, **Aprovar** — que registram a decisão e
dizem na tela que nada foi executado.

---

## Camadas

```text
quality_score.py      critérios, pesos, agregação ponderada     (puro)
quality_rules.py      bandas, findings, recomendações           (puro)
quality_engine.py     heurísticas measured + sinais detector    (puro + Pillow)
quality_models.py     a tabela quality_reports                  (SQLAlchemy)
quality_repository.py única fronteira com o banco               (SessionLocal)
main.py               5 rotas: fatos entram, relatório sai      (sem lógica de score)
```

Mesma regra de camadas de `campaign/` e `continuity/`: os módulos de decisão
não importam framework, o repositório é o único que toca o banco, e as rotas
delegam.

O gate estrutural `core/quality.py` continua intocado: ele decide se um
artefato **existe** (arquivo, tamanho, geometria vs. contrato); este domínio
julga **quão bom** é um artefato existente.

---

## Testes (ETAPA 7)

`test_quality_score.py` (agregação e pesos), `test_quality_rules.py` (bandas,
upscale e prosa), `test_quality_engine.py` (cada heurística contra arquivos
Pillow reais, override de detector, forma do relatório),
`test_quality_repository.py` (persistência, append-only, tenant, decisão
sem execução) e `test_quality_api.py` (as cinco rotas ponta a ponta, 401/404/
422, audit, badge na listagem). O pacote `backend/app/quality/` está em
**100% de cobertura** (o sprint pede ≥ 98%).

Verificar:

```bash
PYTHONPATH=backend coverage run --source=backend/app/quality -m pytest \
  backend/tests/test_quality_*.py -q
coverage report --include='backend/app/quality/*'
```
