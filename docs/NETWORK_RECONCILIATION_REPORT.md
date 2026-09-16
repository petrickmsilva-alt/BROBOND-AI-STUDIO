# NETWORK RECONCILIATION REPORT — PR009.2

Por que a UI mostra **"API Offline"** quando a API responde 200?

Diagnóstico reproduzível. **Nenhuma feature nova, nenhum provider alterado,
nenhuma arquitetura alterada** — a correção fica **proposta** ao final, não
aplicada. Evidências: `docs/NETWORK_TRACE.md` (trace real, gerado por
`node scripts/network_trace.mjs`) e `lib/api.network.test.ts` (17 testes e2e
das cinco classes de falha).

---

## O bloco pedido

```
NEXT_PUBLIC_API_URL =
https://brobond-ai-api.onrender.com

URL realmente utilizada pelo fetch =
https://brobond-ai-api.onrender.com/api/v1/...   (quando a env var está bakeada no build — exata, sem transformação:
                                                  lib/api.ts faz fetch(`${API_URL}${path}`, e API_URL é a env var verbatim)
                                                  Em dev/sem a var: origem relativa (proxy do Next) — '/api/v1/...')

Resultado =
MATCH
```

`lib/api.ts:38` — `export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? '';`
Não há outro base URL no código, não há origem hard-coded, não há
transformação: o fetch usa **exatamente** o que a env var mandar (prova no
teste `the fetch base follows NEXT_PUBLIC_API_URL exactly`). No blueprint do
Render a var é injetada antes do `buildCommand`, então o bundle carrega o
valor acima — **igualdade absoluta** com o `render.yaml`.

---

## Os 3 arquivos validados

Os nomes citados na solicitação não existem com esse caminho neste
repositório (a UI vive na raiz, não em `frontend/`); os arquivos reais são:

| Arquivo citado | Arquivo real | Veredito |
|---|---|---|
| `frontend/lib/api.ts` | `lib/api.ts` | ✅ Sãoaulo correto: base vem da env var (default `''` = same-origin via proxy), sem localhost hard-coded, timeouts 10s/30s, **dois `catch` únicos** que produzem o literal `'offline'` (linhas 84 e 179) |
| `frontend/next.config.js` | `next.config.mjs` (não existe `.js`) | ✅ Correto: rewrite `/api/v1/:path*` → `BROBOND_API_PROXY_TARGET` (default `http://localhost:8000`), alvo por env, não hard-coded |
| `render.yaml` | `render.yaml` | ✅ Correto: `NEXT_PUBLIC_API_URL=https://brobond-ai-api.onrender.com` (web) == a origem do serviço `brobond-ai-api`; `BROBOND_CORS_ORIGINS` inclui a origem do web |

**Conclusão da auditoria estática: os três arquivos estão consistentes entre
si.** O bug não está na configuração — está na **semântica do `catch`**.

## ETAPA 1 — Onde exatamente nasce o "offline"

O literal `'offline'` só existe em **dois** pontos do código:

```ts
// lib/api.ts:71-85 — request()
} catch {
  return failed<T>('offline');        // ← linha 84
}

// lib/api.ts:178-180 — uploadAsset()
} catch {
  return failed<Asset>('offline');    // ← linha 179
}
```

O `catch` **não distingue a causa**. Tudo que rejeita o `fetch` vira
`'offline'`:

| Causa real da exceção | Exceção | O que a UI mostra |
|---|---|---|
| API fora do ar / recusou conexão | `TypeError` (`ECONNREFUSED`) | "API offline" — **correto** |
| DNS inválido | `TypeError` (`ENOTFOUND`) | "API offline" — **correto** |
| **CORS bloqueado** (API respondeu 200) | `TypeError` (`Failed to fetch`) | "API offline" — **falso offline** |
| **Timeout 10s** (API viva, lenta) | `TimeoutError`/`AbortError` | "API offline" — **falso offline** |

Qualquer resposta HTTP — 200, 401, 403, 422, 500, 502 — **nunca** vira
"offline": vira `status` + `error` com o motivo (guardado pelos testes).
Os 8 pontos que imprimem "API offline" na UI (`app/page.tsx` e páginas de
studio) reagem a `error === 'offline'` — ou seja, só aos dois `catch` acima.

## ETAPA 2 — Network Trace (medido, não simulado)

`docs/NETWORK_TRACE.md` — 15 chamadas reais. Resumo:

- **Proxy same-origin** (design do repo, `API_URL=''`): `/api/v1/health`,
  `/system/readiness`, `/system/gpu` → **200** em 8–150ms pelo mesmo caminho
  que o browser usa. Rotas com token, anônimas → **401** (status, não offline).
- **Direct API** (`NEXT_PUBLIC_API_URL` apontando para a API): mesmas rotas →
  **200**. Preflight CORS com a origem do web service **fora da allow-list
  local** → **400** (sem header `access-control-allow-origin`) = o browser
  bloquearia o GET que seria 200. Com origem na allow-list → **200 + echo**
  — demonstração viva do mecanismo.
- **Produção** (`*.onrender.com`): egress HTTPS arbitrário é bloqueado neste
  sandbox (`socket disconnected before secure TLS connection was
  established`) — linhas **inconclusivas** sobre o Render, registradas como
  medidas; em uma máquina com saída livre o mesmo script decide.

## ETAPA 3 — `NEXT_PUBLIC_API_URL` × `render.yaml`

```
render.yaml (web brobond-studio-web):  NEXT_PUBLIC_API_URL = https://brobond-ai-api.onrender.com
lib/api.ts (fetch base):               API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''
fetch efetivo (produção):              https://brobond-ai-api.onrender.com/api/v1/<path>
Resultado: MATCH
```

Detalhes que garantem a igualdade: (1) injeção via `envVars` do blueprint
acontece **antes** do `buildCommand` (`npm ci && npm run build`), e
`NEXT_PUBLIC_*` é bakeado no bundle neste momento; (2) nenhum outro código
lê a var; (3) o serviço nomeado no valor é o mesmo `brobond-ai-api`
declarado no blueprint. Único risco real de MISMATCH: rebuild esquecido após
trocar a var (bundle velho) — operacional, não de código.

## ETAPA 4 — As rotas chamadas pela Home

Ordem real da montagem (`app/page.tsx`, `useEffect` da linha 104):

| # | Chamada | Rota | Auth | Status medido (API de pé) |
|---|---|---|---|---|
| 1 | `gpuInfo()` | `GET /api/v1/system/gpu` | pública | 200 |
| 2 | `readiness()` | `GET /api/v1/system/readiness` | pública | 200 |
| 3 | `listAssets()` | `GET /api/v1/assets` | token | 200 (com token) / **401** anônimo |
| 4 | `listPersonaProfiles()` | `GET /api/v1/personas` | token | 200 (com token) / **401** anônimo |

(`health()` existe em `lib/api.ts` e está correta — `GET /api/v1/health`,
200 — mas a Home não a chama; as três rotas pedidas foram validadas e estão
200 pelo proxy **e** direto, conforme o trace.)

**Qual delas dispara o catch? Nenhuma — com a API de pé.** O `catch` dispara
por classe de exceção, não por rota. As duas situações reais em que essas
rotas produzem "API offline" com a API respondendo 200:

1. **CORS** — chamada direta (cross-origin) com a origem do browser fora de
   `BROBOND_CORS_ORIGINS`: preflight **400** (medido), browser bloqueia,
   `TypeError` → "offline". O blueprint atual configura a allow-list
   corretamente; qualquer drift de domínio recria o sintoma.
2. **Timeout** — Render free tier dorme; o primeiro GET acorda o serviço
   (30–60s) e `AbortSignal.timeout(10000)` estoura **com a API perfeita**.
   É o falso "API Offline" mais comum em produção.

## ETAPA 5 — Testes e2e (`lib/api.network.test.ts`, 17 testes)

Stub do `fetch` global dirigindo o `request()` **real** de `lib/api.ts`:

| Cenário | Resultado pinado |
|---|---|
| API online (200) | `remote=true`, dados parseados, **nunca** offline |
| 500 + corpo FastAPI | `status=500`, `error='boom interno'`, não offline |
| 401 | `status=401`, não offline |
| 502 HTML (roteador) | `status=502`, não offline |
| 204 | `data=null`, ok |
| DNS inválido (`TypeError/ENOTFOUND`) | `'offline'` — rede real |
| Conexão recusada (`ECONNREFUSED`) | `'offline'` — rede real |
| CORS (`TypeError: Failed to fetch`) | `'offline'` — **conflação documentada** |
| Timeout (`AbortError`/`TimeoutError`) | `'offline'` — **conflação documentada** |
| URL base | default relativo; com a var do render.yaml → URL absoluta **exata** (MATCH) |
| Token | `Authorization: Bearer …` presente com sessão; ausente anônimo |
| Rotas da Home | `health`/`readiness`/`gpu` com os paths exatos |

**"API Offline" só aparece em erro real de rede** — mais as duas conflações
documentadas (CORS e timeout), que são exatamente os alvos da correção
proposta abaixo.

## ETAPA 6 — Stack real dos erros (capturados ao vivo)

```
=== DNS inválido (rede real → "offline" correto) ===
TypeError: fetch failed
    at node:internal/deps/undici/undici:14976:13
    at process.processTicksAndRejections (node:internal/process/task_queues:103:5)
cause: ENOTFOUND

=== Timeout (API viva, 10s estourados → "offline" falso) ===
TimeoutError: The operation was aborted due to timeout
    at node:internal/deps/undici/undici:14976:13
```

No browser o mesmo fluxo chega ao `catch` de `lib/api.ts` como
`TypeError: Failed to fetch` (CORS/DNS/caída) ou
`DOMException: …aborted… (TimeoutError/AbortError)` — e vira o literal
`'offline'` na linha 84.

---

## Correção proposta (diagnóstico — **não aplicada**, conforme o escopo)

Em ordem de impacto, todas preservando o contrato (`ApiResult` com
`status`/`error`) e a guarda estrutural existente
(`test_frontend_honesty.py` mantém `failed<T>('offline')` como resposta de
rede real):

1. **Distinguir timeout de rede** (mata o falso offline do cold start):
   capturar a exceção nomeada no `catch` e devolver
   `failed<T>('timeout')` quando `e.name === 'TimeoutError' || e.name ===
   'AbortError'`; a UI passa a dizer "A API não respondeu em 10s — pode estar
   acordando; tente de novo" em vez de "API offline". Pequeno, sem feature.
2. **Orçamento maior (ou 1 retry com backoff curto) para as rotas de status
   da Home** (`gpu`/`readiness`/`health`): cold start do free tier passa de
   10s; 25–30s nessas três chamadas resolve o primeiro acesso do dia.
3. **Eliminar o CORS do caminho crítico**: manter `NEXT_PUBLIC_API_URL=''`
   no Render e apontar o proxy do Next com
   `BROBOND_API_PROXY_TARGET=https://brobond-ai-api.onrender.com` no web
   service — o browser fica same-origin (o proxy do Next fala com a API
   server-side, onde CORS não existe). É o design que o repositório já
   declara ("the browser never hard-codes an origin").
4. **Manter `BROBOND_CORS_ORIGINS` em lockstep com o domínio do web service**
   (o blueprint já faz; virou guarda de operação, não de código).

## Como reproduzir

```bash
node scripts/network_trace.mjs                      # re-executa o trace e regrava docs/NETWORK_TRACE.md
npx vitest run lib/api.network.test.ts              # 17 testes das classes de falha
grep -n "offline" lib/api.ts                        # as duas únicas fontes do literal
grep -n "NEXT_PUBLIC_API_URL" render.yaml lib/api.ts
```
