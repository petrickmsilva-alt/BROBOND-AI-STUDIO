# BROBOND AI STUDIO — NETWORK LAYER (V3.2.1)

A camada de rede do studio virou padrão enterprise: **um único módulo faz
`fetch`**, toda falha tem um tipo, toda requisição tem um trace id, e o
"API Offline" mentiroso — documentado em
`docs/NETWORK_RECONCILIATION_REPORT.md` (PR009.2) — morreu de vez.

**Nenhuma funcionalidade nova — apenas robustez.** Provider Registry, Render
Engine e Director AI não foram alterados. As contagens de rota do
`docs/API.md` não mudam.

---

## O módulo: `lib/network/request.ts`

`runRequest(path, init?, options?)` é a única fronteira de rede do frontend.
Nenhum componente e nenhum outro módulo de `lib/` chama `fetch` — regra
guardada por `backend/tests/test_frontend_honesty.py::test_fetch_lives_only_in_the_network_layer`.

```ts
type RequestOutcome =
  | { kind: 'response'; response: Response; traceId: string; durationMs: number }
  | { kind: 'error'; error: NetworkError };
```

Responsabilidades (todas testadas em `lib/network/request.test.ts`):

| Responsabilidade | Implementação |
| --- | --- |
| Timeout | `AbortSignal.timeout` — 10s padrão (`DEFAULT_TIMEOUT_MS`), 30s upload (`UPLOAD_TIMEOUT_MS`) |
| Abort do chamador | `init.signal` mesclado com o timeout via `AbortSignal.any` |
| Retry | **Somente GET**, 3 tentativas extras (`STATUS_RETRY_ATTEMPTS`), backoff exponencial **300/600/1200ms** (`RETRY_DELAYS_MS`) |
| Erro tipado | toda falha vira `NetworkError` com `NetworkErrorType` — nunca string solta |
| Trace id | header `x-brobond-trace` (UUID por requisição lógica, mesmo id em todas as tentativas) |
| Log sem PII | `[brobond:network] {traceId} {METHOD} {path-sem-query} -> {status|tipo} ({ms}ms)` |

## ETAPA 1 — a taxonomia `NetworkErrorType`

```ts
enum NetworkErrorType {
  ONLINE = 'online',            // saudável (o enum dobra como vocabulário de status)
  TIMEOUT = 'timeout',          // AbortError/TimeoutError do orçamento de 10s/30s
  OFFLINE = 'offline',          // TypeError com navigator.onLine === false, ou same-origin inalcançável
  CORS = 'cors',              // TypeError online + cross-origin: a API respondeu, o browser escondeu
  UNAUTHORIZED = 'unauthorized',// HTTP 401
  SERVER_ERROR = 'server_error',// HTTP ≥ 500
  UNKNOWN = 'unknown',          // o resto (4xx de negócio, erros estranhos)
}
```

O mapeamento de exceções (`classifyException`) é onde o falso offline morria:

* `TimeoutError`/`AbortError` → **TIMEOUT** (antes: "offline");
* `TypeError` + `navigator.onLine === false` → **OFFLINE**;
* `TypeError` online + cross-origin → **CORS** (medido no PR009.2: preflight
  400 para origem fora da allow-list — a API respondia 200);
* HTTP 401 → **UNAUTHORIZED**; HTTP ≥ 500 → **SERVER_ERROR** (`httpErrorType`).

## ETAPA 2 — `lib/api.ts` delega

`lib/api.ts` não tem mais `fetch`, `try/catch` de rede nem o literal
`'offline'`. O `request()` monta headers (Authorization quando há sessão) e
chama `runRequest`; o resultado vira `ApiResult`:

```ts
type ApiResult<T> = {
  data: T; remote: boolean; status?: number; error?: string;
  errorType?: NetworkErrorType;  // V3.2.1 — a falha tipada
  traceId?: string;              // V3.2.1 — o x-brobond-trace da requisição
};
```

`remote` continua significando "chegou dado utilizável". A UI **ramifica por
`errorType`** (`isUnreachable`, `failureMessage` em `lib/network/status.ts`),
nunca por comparação de string. Mensagem humana: `networkProblemText(error)`.

## ETAPA 3 — Retry policy das rotas de status

`health()`, `readiness()` e `gpuInfo()` usam `getStatus`: GET com **3 retries
(300/600/1200ms)**. Um 5xx ou uma classe de rede na sondagem se resolve na
segunda tentativa em vez de pintar a shell de offline. `UNAUTHORIZED` nunca é
repetido; mutações (POST/PUT/DELETE) nunca são repetidas.

## ETAPA 4 — Cold start detection

Uma janela dedicada ao free tier do Render (que dorme):

```ts
COLD_START_MIN_MS = 8000; COLD_START_MAX_MS = 60000;
isColdStart(TIMEOUT, durationMs) // true ⇒ "o servidor está acordando"
```

Timeout com duração na janela 8–60s ⇒ **"Servidor iniciando — o primeiro
acesso pode demorar alguns segundos."** — nunca "API Offline". Abaixo de 8s é
timeout comum; acima de 60s é servidor realmente morto.

## ETAPA 5 — StatusCenter (`app/components/StatusCenter.tsx`)

Montado no shell (`app/layout.tsx`), sonda `health` + `readiness` pela camada
(logo, com retry) e mostra **um** estado, com cor e ação:

| Estado | Cor | Ação |
| --- | --- | --- |
| Online | verde | nada a fazer |
| Inicializando | âmbar | mantém sondando a cada 3s até o servidor acordar |
| Sem internet | vermelho | verificar a conexão / botão "Tentar novamente" |
| Sessão expirada | roxo | entrar novamente |
| Erro interno | vermelho | "Tentar novamente" |

A derivação (`deriveStatus`) prioriza: inicializando > sem internet > sessão
expirada > erro interno. Eventos `online`/`offline` do browser são sinais
gratuitos e atualizam o estado sem requisição.

## ETAPA 6 — Trace ID

Cada requisição lógica gera um id (`crypto.randomUUID`, fallback `req-…`),
enviado no header `x-brobond-trace` e presente no log e no `ApiResult.traceId`
— o mesmo id atravessa as tentativas de retry. O log imprime URL **sem query
string** (sem PII), método, latência e desfecho.

## ETAPA 7 — Nenhum catch retorna "offline"

Substituído em toda a UI (`app/page.tsx` e todos os `app/studio/*/page.tsx`):

* comparações `error === 'offline'` → `isUnreachable(result)` /
  `failureMessage(result, texto-do-painel)`;
* `describeError(error, status)` dos painéis → `describeError(result)` tipado;
* o texto "API offline — inicie o FastAPI…" sobrevive apenas como **cópia de
  orientação** dentro de `failureMessage`, acionada pelo **tipo** — nunca como
  retorno de um catch.

## ETAPA 8 — Testes e cobertura

* `lib/network/request.test.ts` — o contrato da camada: DNS (TypeError →
  OFFLINE), CORS (TypeError cross-origin), Timeout (rápido e cold start),
  500 (retry 3× e desistência), 401 (sem retry), POST sem retry, agenda exata
  de backoff (300/900/2100ms), trace id com fallback, log sem query, merge de
  sinal de abort, `readError` com todos os formatos do FastAPI.
* `lib/network/status.test.ts` — derivação do StatusCenter, `isUnreachable`,
  `failureMessage` e os metadados dos cinco estados.
* `lib/api.network.test.ts` — reescrito para o contrato novo (o resultado das
  classes de falha carrega `errorType`, `traceId` e texto correto; retry
  visível através de `health()`; URL base `NEXT_PUBLIC_API_URL` verbatim).
* **Cobertura mínima de `lib/network/**`: 98%** — enforcement no
  `vitest.config.ts` (statements/branches/functions/lines), hoje em
  ~99.5/99/100/99.5. A suíte inteira do frontend (124 testes) segue verde.

## Guardas estruturais (backend)

`backend/tests/test_frontend_honesty.py` ganhou
`test_fetch_lives_only_in_the_network_layer`: `fetch(` só pode existir em
`lib/network/request.ts`; `lib/api.ts` não pode ter `'offline'` nem `fetch(`;
o enum e o header de trace têm que estar lá. Os pins antigos
(`runRequest(` em `lib/api.ts`, `errorType?` no `ApiResult`) continuam
valeando a delegação.
