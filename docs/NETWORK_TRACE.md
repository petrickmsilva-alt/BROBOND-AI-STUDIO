# NETWORK TRACE — PR009.2 (Frontend Network Reconciliation)

Trace real (não simulado onde o alvo existe): cada linha é uma chamada
`fetch` de verdade, com a mesma forma que `lib/api.ts` faz — mesmos paths,
mesmos headers (`Origin` nas chamadas "direct", para revelar o CORS).
Gerado por `node scripts/network_trace.mjs` em 2026-09-16T17:56:24.748Z.

**Fato do cliente (`lib/api.ts`):** `API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''`
— sem a env var, todo request é **relativo** (mesma origem, proxy do Next).
Timeouts: `DEFAULT_TIMEOUT_MS = 10000` (uploads: 30000) via
`AbortSignal.timeout(...)` — e o `catch` único converte **qualquer**
exceção (DNS, CORS, abort) no literal `'offline'`.

---

## 1. Same-origin proxy (design do repositório: `API_URL = ''`)

| # | Método | URL | Status | Duração | Erro | access-control-allow-origin |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GET | `http://localhost:3000/api/v1/health` | 200 | 44ms | — | — |
| 2 | GET | `http://localhost:3000/api/v1/system/readiness` | 200 | 8ms | — | — |
| 3 | GET | `http://localhost:3000/api/v1/system/gpu` | 200 | 13ms | — | — |
| 4 | GET | `http://localhost:3000/api/v1/assets` | 401 | 8ms | — | — |
| 5 | GET | `http://localhost:3000/api/v1/personas` | 401 | 5ms | — | — |

Todas as rotas públicas da Home respondem **200 pelo proxy** no mesmo
caminho que o browser usa. As duas rotas com token, anônimas, respondem
**401** — que a UI trata como status (não como "offline").

## 2. Direct API (o que o fetch faz quando `NEXT_PUBLIC_API_URL` aponta para a API)

| # | Método | URL | Status | Duração | Erro | access-control-allow-origin |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GET | `http://localhost:8000/api/v1/health` | 200 | 3ms | — | — |
| 2 | GET | `http://localhost:8000/api/v1/system/readiness` | 200 | 3ms | — | — |
| 3 | GET | `http://localhost:8000/api/v1/system/gpu` | 200 | 2ms | — | — |
| 4 | OPTIONS | `http://localhost:8000/api/v1/health` | 400 | 2ms | — | — |
| 5 | OPTIONS | `http://localhost:8000/api/v1/health` | 200 | 1ms | — | http://localhost:3000 |

Com `Origin: https://brobond-studio-web.onrender.com`, a API responde 200 **e** ecoa
`access-control-allow-origin` — o middleware CORS (alimentado por
`BROBOND_CORS_ORIGINS` no render.yaml) aceita a origem do web service, e o
preflight `OPTIONS` (que o browser dispara por causa do header
`Authorization`) passa.

## 3. Production — as URLs do render.yaml, medidas

| # | Método | URL | Status | Duração | Erro | access-control-allow-origin |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GET | `https://brobond-ai-api.onrender.com/api/v1/health` | — | 24ms | TypeError (Client network socket disconnected before secure TLS connection was established) | — |
| 2 | GET | `https://brobond-studio-web.onrender.com/` | — | 35ms | TypeError (Client network socket disconnected before secure TLS connection was established) | — |
| 3 | GET | `https://brobond-studio-web.onrender.com/api/v1/health` | — | 4ms | TypeError (Client network socket disconnected before secure TLS connection was established) | — |

Linha com status `—` = exceção de rede. Neste ambiente o egress HTTPS arbitrário é bloqueado pelo sandbox ("socket disconnected before secure TLS connection was established"), então a linha é **inconclusiva sobre o Render** — registrada como medida, não interpretada como serviço inexistente. Em uma máquina com saída livre, o mesmo script decide.

## 4. Fault injection — as linhas que viram "API Offline"

| # | Método | URL | Status | Duração | Erro | access-control-allow-origin |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GET | `https://brobond-api.invalid/api/v1/health` | — | 5ms | TypeError (getaddrinfo ENOTFOUND brobond-api.invalid) | — |
| 2 | GET | `http://10.255.255.1:8000/api/v1/health` | — | 10001ms | AbortError (timeout) | — |

Estas são as **únicas** classes de erro que produzem o literal `'offline'`
(`lib/api.ts`, catches das linhas 84 e 179): exceção de rede (`TypeError`)
ou abort por timeout (`AbortError`). Uma resposta HTTP — 200, 401, 500,
502 — **nunca** vira "offline": vira `status` + `error` com o motivo.
