# BROBOND AI STUDIO — EVENT CATALOG

**PR010.0 — Platform Freeze, ETAPA 5.** Registro oficial de todos os eventos da
plataforma.

A regra que este documento institui:

> **Nenhum evento novo pode surgir sem documentação.** Um nome de evento que
> não estiver catalogado aqui falha em
> [`backend/tests/test_event_catalog.py`](../backend/tests/test_event_catalog.py).

Evento é contrato de wire. Um cliente conectado a um WebSocket reage a `event`,
não ao que o servidor quis dizer. Renomear um evento, emitir um nome novo ou
parar de emitir um existente quebra esse cliente em silêncio — e é exatamente
isso que o congelamento impede.

---

## Honestidade primeiro

O PR010.0 nomeia sete eventos oficiais. **Três existem e são emitidos hoje;
quatro são vocabulário reservado** para o AI Core, que ainda não foi escrito.

Este PR **não implementa** os quatro que faltam: ele é um PR de estabilização,
com zero alteração funcional. Reservar o nome agora é o que impede que o AI
Core invente um nome diferente depois, ou que alguém emita `plan_created` com
um payload improvisado antes de o contrato existir.

`test_event_catalog.py` verifica as duas metades: que os implementados são
emitidos de verdade e que os reservados **não** são emitidos por ninguém.

| Evento oficial | Estado | Onde |
| --- | --- | --- |
| `request_received` | **Reservado** — AI Core | — |
| `plan_created` | **Reservado** — AI Core | — |
| `scene_started` | **Implementado** | `render/progress.py` |
| `scene_completed` | **Implementado** | `render/progress.py` |
| `quality_finished` | **Reservado** — AI Core | — |
| `render_finished` | **Implementado** como `batch_completed` | `render/progress.py` |
| `asset_created` | **Reservado** — AI Core | — |

`render_finished` é o nome de domínio de um evento que já existe com o nome de
wire `batch_completed`. O nome de wire **não** foi alterado: mudá-lo quebraria
`app/studio/render/page.tsx` e `lib/api.ts`, que já o consomem. O catálogo
registra os dois e a equivalência.

---

## 1. Ciclo de vida de job — `app/events.py`

Emitidos por `queue.transition()`, o **único** ponto onde status ou progresso
de um job são escritos (ETAPA 11). Escrever estado e emitir acontecem no mesmo
passo, então não existe como mover um job em silêncio.

Transporte: WebSocket `/api/v1/queue/events/{job_id}`, autenticado por `?token=`.

| Evento | Constante | Quando | Emitido hoje |
| --- | --- | --- | --- |
| `queued` | `EVENT_QUEUED` | Job aceito e enfileirado | **Não** — declarado, sem emissor |
| `started` | `EVENT_STARTED` | Worker pegou o job (progresso 10) | Sim |
| `progress` | `EVENT_PROGRESS` | Marco intermediário (25/40/55/90) | Sim |
| `complete` | `EVENT_COMPLETE` | Job terminou com artefato (progresso 100) | Sim |
| `failed` | `EVENT_FAILED` | Job terminou com erro | Sim |
| `cancelled` | `EVENT_CANCELLED` | Cancelado pelo usuário ou antes de executar | Sim |

`queued` está declarado em `JOB_EVENTS` e importado por `queue.py`, mas nenhuma
chamada o emite: a criação do job devolve o snapshot pela resposta HTTP. É uma
lacuna medida, registrada aqui em vez de escondida — e o guard garante que ela
não mude sem que este documento mude junto.

### Payload

```json
{
  "job_id": "3f2b…",
  "event": "progress",
  "status": "running",
  "progress": 55,
  "at": "2026-09-17T12:00:00+00:00",
  "output_url": "…",
  "error": "…"
}
```

`output_url` e `error` só aparecem quando existem. As demais chaves são sempre
enviadas.

### `status` ≠ `event`

A distinção mais fácil de errar deste catálogo:

* **`event`** é o identificador de contrato. Mantém o nome interno —
  `complete`, não `completed`.
* **`status`** é o estado externo do job, e passa por
  `events.external_status()`: o interno `complete` vira **`completed`** no wire
  (PR002, Bible §14).

Ou seja, um job terminado com sucesso emite `{"event": "complete", "status":
"completed"}`. Os dois valores são diferentes de propósito e nenhum dos dois
pode ser "corrigido" para parecer com o outro.

### Estados terminais

`complete`, `failed`, `cancelled` (`TERMINAL_STATUSES`). Depois de um deles,
nada mais acontece com o job e o WebSocket fecha. O socket nunca emite o evento
terminal duas vezes: se o buffer já carregava um, a rota não sintetiza outro.

---

## 2. Render por lote — `app/render/progress.py`

Emitidos pelo `RenderOrchestrator` no `RenderProgressHub` (push, sem polling).
São **cinco** nomes, e falhas e cancelamentos viajam no payload (`status` /
`error`), não em nomes extras — um cliente trata exatamente cinco tipos.

Transporte: WebSocket `/ws/render/{batch_id}`, autenticado por `?token=`.

| Evento | Constante | Quando |
| --- | --- | --- |
| `batch_started` | `EVENT_BATCH_STARTED` | Lote começou |
| `scene_started` | `EVENT_SCENE_STARTED` | Cena entrou em render |
| `scene_progress` | `EVENT_SCENE_PROGRESS` | Marco dentro da cena (spec compilada, render, persistência) |
| `scene_completed` | `EVENT_SCENE_COMPLETED` | Cena terminou — sucesso, falha ou cancelamento |
| `batch_completed` | `EVENT_BATCH_COMPLETED` | Lote terminou. **Evento terminal** (`TERMINAL_RENDER_EVENT`) |

Ordem de ciclo de vida:

```text
batch_started -> scene_started -> scene_progress -> scene_completed
             ... por cena ...  -> batch_completed
```

### Payload

```json
{
  "batch_id": "b-17",
  "event": "scene_completed",
  "at": "2026-09-17T12:00:00+00:00",
  "scene_id": "s-3",
  "scene_number": 3,
  "status": "completed",
  "progress": 100,
  "eta_seconds": 0.0,
  "error": null,
  "asset": { "object_key": "…", "thumbnail_key": "…", "prompt": "…", "seed": 7 },
  "job":   { "status": "complete", "provider_id": "mock", "attempts": 1 }
}
```

`batch_id`, `event` e `at` são sempre enviados; as demais chaves aparecem
apenas quando o emissor as define. `render_event()` recusa um nome fora de
`RENDER_EVENTS` com `ValueError` — o vocabulário é validado em runtime, não só
por teste.

### Limitação conhecida

O `EventHub` de jobs é **in-process**. Um worker Celery é outro processo, então
eventos que ele emite não chegam aos WebSockets do processo da API. `publish_sync`
garante que a transição seja **registrada** (e portanto visível para um cliente
no mesmo processo); fechar a lacuna exige um broker compartilhado. Registrado em
`ETAPA11_REPORT.md` e repetido aqui porque um catálogo que promete entrega que
não acontece é pior do que nenhum catálogo.

---

## 3. Treinamento de persona

WebSocket `/api/v1/personas/{persona_id}/training/events/{run_id}`.

**Não usa eventos nomeados.** É o único canal por polling da plataforma: a rota
lê `TrainingRun` a cada 2s e envia `{run_id, status, progress, log}`, fechando
quando o status é terminal. Está aqui para o catálogo ficar completo — e para
deixar claro que é a exceção, não o padrão a copiar.

---

## 4. Vocabulário reservado

Nomes oficiais do PR010.0 sem emissor hoje. **Nenhum código pode emiti-los**
até que o AI Core exista e o contrato seja definido aqui — o guard falha se
algum aparecer.

| Evento | Significado pretendido | Por que ainda não existe |
| --- | --- | --- |
| `request_received` | AI Core aceitou uma intenção do usuário | O AI Core não existe. Hoje a entrada é uma rota HTTP que responde de forma síncrona. |
| `plan_created` | Director/Storyboard produziram um `ProductionPlan` | `/core/director/production-plan` devolve o plano na resposta HTTP; não há nada assíncrono para anunciar. |
| `quality_finished` | Quality Engine terminou de pontuar um artefato | `QualityEngine.assess()` é síncrono e devolve o relatório. Emitir exigiria um pipeline assíncrono — feature, não congelamento. |
| `asset_created` | Um asset foi persistido | Assets são gravados por `RenderAssetPipeline` e pelo worker, mas nenhum evento é emitido. A criação é visível via `scene_completed.asset` e `GET /api/v1/assets`. |

Reservar sem implementar é deliberado. O risco real não é a falta do evento: é
o AI Core nascer emitindo `planCreated`, `plan.created` e `PlanCreated` em três
lugares diferentes. O nome está travado antes de existir o primeiro emissor.

---

## Como adicionar um evento

1. Declarar a constante ao lado das irmãs (`app/events.py` ou
   `app/render/progress.py`) e incluí-la na tupla do vocabulário
   (`JOB_EVENTS` / `RENDER_EVENTS`).
2. Adicionar a linha à tabela certa deste documento, com payload e quando é
   emitido.
3. `test_event_catalog.py` passa a reconhecê-lo. Enquanto os passos 1 e 2 não
   concordarem, a CI fica vermelha.

Renomear um evento existente é mudança **breaking**: clientes reagem ao valor
de `event`. Exige entrada no `CHANGELOG.md` e atualização de
`docs/API_SNAPSHOT.json`.

---

Documentos irmãos: [`ARCHITECTURE_MANIFEST.md`](ARCHITECTURE_MANIFEST.md) (quem
pode importar quem), [`API_SNAPSHOT.json`](API_SNAPSHOT.json) (a superfície HTTP
congelada) e [`RENDER_ENGINE.md`](RENDER_ENGINE.md) (o pipeline que emite os
cinco eventos de render).
