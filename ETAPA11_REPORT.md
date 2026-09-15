# ETAPA 11 — QUEUE & WEBSOCKET

Relatório técnico. Escopo: fila de jobs e progressão em tempo real.

**Resultado:** o defeito P0-3 (`EventHub.publish` sem chamador algum), aberto desde
`AUDIT.md`, está corrigido e provado de ponta a ponta. `605 → 633` testes. Zero arquivos
deletados. Nenhuma outra etapa foi adiantada.

---

## 1. Auditoria — tudo medido antes de escrever

Nada foi suposto. Cada achado abaixo veio de uma leitura ou de uma execução.

| # | Achado | Como foi medido |
| --- | --- | --- |
| B1 | `hub.publish` tem **zero chamadores** | `grep "hub\.\|\.publish("` → só `hub.connect`/`hub.disconnect` em `main.py:290,296` |
| B2 | A rota WS enviava 1 snapshot e bloqueava em `await websocket.receive_text()` | leitura da rota: era um loop de **leitura**, não de envio |
| B3 | O progresso saltava 10 → 100 | `grep` das mutações em `queue.py` (l.55-56, 59-60, 130-131, 133) |
| B4 | Dois mecanismos WS distintos e não reconciliados | queue (quebrado) × training (polling `asyncio.sleep(2)`, funciona) |
| B5 | `process_generation` é síncrono × `EventHub` é asyncio-only | `asyncio.Lock` + `await send_text` não são chamáveis de uma task Celery |
| B6 | Hub in-process não alcança worker em outro processo | arquitetural — exige Redis pub/sub |
| B7 | `MemoryStore` é em memória (P0-2b) | `store.py`, 41 linhas |
| B8 | O comportamento dos WebSockets **nunca foi testado** | a única guarda existente era `len(websockets) == 2` (`test_core_api.py:235-236`) |

### Prova empírica de B1, antes de tocar no código

Job criado (`queued/0`) → `process_generation` executado → job em `complete/100`.
Um cliente conectado **antes** do worker rodar recebeu **nenhuma** mensagem adicional
(timeout de 2 s). O estado mudou; o socket ficou mudo. É isso que o usuário via.

---

## 2. O que foi feito

### 2.1 `transition()` — o único ponto de mutação

A raiz do problema não era "faltou chamar `publish`". Era que **não existia um instante que
significasse "o job andou"**: cada call site atribuía `job.status` e `job.progress`
diretamente, espalhado pelo worker.

```python
transition(job, JobStatus.RUNNING, PROGRESS_RENDERING, event=EVENT_PROGRESS)
```

Escreve os dois campos **e** emite o evento, no mesmo passo. Os 9 call sites foram roteados
por ela. `status` e `progress` são ambos opcionais, para que um tick de progresso não precise
reafirmar o status.

Não é convenção, é imposição: `test_the_worker_never_writes_job_state_directly` varre o AST
de `queue.py` e falha se qualquer função que não seja `transition` escrever `job.status` ou
`job.progress`.

### 2.2 Seis marcos de progresso

`PROGRESS_STARTED` 10 · `PROGRESS_SPEC_COMPILED` 25 · `PROGRESS_INPUTS_RESOLVED` 40 ·
`PROGRESS_RENDERING` 55 · `PROGRESS_PERSISTED` 90 · `PROGRESS_DONE` 100.

Com dois pontos não há barra de progresso possível. `test_the_worker_no_longer_jumps_from_ten_to_a_hundred`
exige ≥ 4 valores distintos, monotonicamente não decrescentes.

### 2.3 `publish_sync` — por que `publish` não bastava

O worker é task Celery **síncrona**; o hub é asyncio-only. `await hub.publish(...)` nunca
seria chamável dali — essa é a razão real de o método ter nascido órfão.

`publish_sync` **grava o evento incondicionalmente** e só despacha se houver loop rodando.
Gravar é o que torna a transição visível a um cliente neste processo; o despacho é
melhor-esforço.

### 2.4 Buffer de replay com cursor

`EVENT_BUFFER_SIZE` = 64 por job. A rota: snapshot do estado atual → drena
`hub.history(job_id, cursor)` → empurra → fecha em status terminal → libera o buffer no
`finally`. Um cliente que conecta depois do fim recebe o histórico, em vez de ficar preso sem
resposta.

### 2.5 Contrato de evento

`{job_id, event, status, progress, at}` sempre. `output_url` e `error` só quando significam
algo. Nomes em `JOB_EVENTS`; `TERMINAL_STATUSES = {complete, failed, cancelled}` encerra o
stream.

---

## 3. Prova de ponta a ponta, depois

O mesmo cenário da seção 1:

```
1. snapshot   status=queued    progress=0
2. started    status=running   progress=10
3. complete   status=complete  progress=100
```

Caminho de falha, com um provider que levanta exceção:

```
1. snapshot   status=queued   err=None
2. started    status=running  err=None
3. progress   status=running  err=None      (25, 40, 55)
4. progress   status=running  err=None
5. progress   status=running  err=None
6. failed     status=failed   err=CUDA GPU is required
```

Cliente que conecta **depois** do job terminar: recebe o snapshot (`complete/100`), o
histórico (`started`, `complete`) e o socket fecha; o buffer é liberado.

---

## 4. Três defeitos meus, encontrados e corrigidos nesta etapa

Registrados porque os testes que os pegaram são os que impedem o retorno.

1. **Evento terminal duplicado.** A primeira versão drenava o buffer **e** ainda emitia um
   `complete` sintético — o cliente via `complete/100` duas vezes. Corrigido: o sintético só
   sai se o buffer não trouxe um terminal. Fixado por `test_the_terminal_event_is_sent_once`.
2. **Suíte travada em vez de falhar.** O helper original criava um reader novo a cada
   asserção; dois threads competindo pelo mesmo socket perdiam mensagens e travavam o portal
   do TestClient (timeout de 600 s, sem nenhum teste reportado). Corrigido: um reader por
   socket, iniciado uma vez.
3. **Asserção sobre sinal inexistente.** `test_the_socket_closes_after_a_terminal_event`
   esperava uma exceção no `receive_json` após o fechamento. Medido: `TestClient.receive_json`
   **bloqueia**, não lança. O teste foi reescrito para afirmar o que é observável de verdade —
   `hub.stats()["connections"]` indo a `0` e o buffer liberado, prova de que a rota retornou.

Também: uma sonda de patch para a prova de não-vacuidade abortou em `AssertionError` porque o
texto procurado não batia. **O defeito nunca foi introduzido**, e o "632 passed" que veio em
seguida foi vacuo. Relido o código real, a prova foi refeita e aí sim falhou como devia.

---

## 5. Não-vacuidade

Reintroduzir o defeito — `transition` atribuindo os campos sem emitir, exatamente o formato
pré-ET11:

```
9 failed, 623 passed
FAILED test_a_connected_client_sees_the_job_finish
FAILED test_a_client_that_connects_late_gets_the_history
FAILED test_a_failure_reaches_the_client_with_its_reason
```

Os testes que provam o comportamento de ponta a ponta são os que caem. Restaurado o código,
`633 passed`.

---

## 6. Verificações literais

| Verificação | ETAPA 10 | **ETAPA 11** |
| --- | --- | --- |
| `pytest backend/tests -q` | 605 passed | **633 passed** |
| Sem cache / sem randomização | 605 / 605 | **633 / 633** |
| 22 testes originais (13 arquivos do commit `3708784`) | 22 | **22** |
| `test_core_independence.py` | 17 | **17** |
| `test_queue_events.py` (novo) | — | **28** |
| Rotas `/api/v1` · core · WebSockets | 54 · 27 · 2 | **54 · 27 · 2** |
| Cobertura `events.py` | — | **100%** |
| Cobertura `store.py` | — | **90%** |
| Cobertura total `backend/app` | 85% | **86%** |
| `npm run build` | ✓ | **✓** |
| Arquivos deletados desde `3708784` | 0 | **0** |

`queue.py` fica em **58%**. As linhas descobertas (124-132, 181-186, 199-236, 253-257) são os
caminhos reais de GPU, MinIO, LoRA, treinamento e despacho Celery — inexequíveis neste
sandbox, sem GPU, sem MinIO e sem Redis. Não foram simuladas para subir o número.

---

## 7. O que esta etapa **não** resolveu

Nada aqui foi fingido. Registro explícito:

- **O hub é in-process.** Num deploy real, com o worker Celery em outro processo, os eventos
  gerados lá **não** alcançam os sockets abertos na API. Resolver exige Redis pub/sub — o
  `redis_url` já está em `core/config.py`. Documentado, não simulado.
- **P0-2b segue aberto.** `MemoryStore` continua em memória; a docstring de `store.py` pede
  repositórios SQLAlchemy. Reiniciar o processo perde os jobs.
- **O WebSocket de treinamento não foi migrado.** Continua em polling `asyncio.sleep(2)`.
  Unificar os dois mecanismos é trabalho próprio, fora deste escopo.
- **A UI não consome as rotas.** O contrato está pronto e testado no backend; ligar o
  frontend é a ETAPA 15 (UX Premium).

---

## 8. Arquivos

| Arquivo | Mudança |
| --- | --- |
| `backend/app/events.py` | reescrito — 167 l, 100% de cobertura |
| `backend/app/queue.py` | `transition()` + 6 marcos + 9 call sites roteados — 257 l |
| `backend/app/main.py` | `queue_events` reescrito para push |
| `backend/tests/test_queue_events.py` | **novo** — 28 testes, 522 l |
| `CHANGELOG.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `README.md`, `backend/README.md` | atualizados |

Nenhum arquivo deletado. `backend/app/store.py` intocado (P0-2b permanece aberto).
`DirectorAgent` intocado (ETAPA 7 permanece bloqueada).
