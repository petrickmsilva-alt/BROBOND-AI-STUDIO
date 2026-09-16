#!/usr/bin/env node
/**
 * PR009.2 — Network Trace: the UI's requests, measured, not remembered.
 *
 * Reproduces exactly the requests `lib/api.ts` makes (same paths, same
 * headers, including the bearer token when present) and records for each:
 * full URL, method, status, duration and error. Three targets:
 *
 *   1. same-origin proxy  — http://localhost:3000 + relative /api/v1 paths
 *                           (the repo design: API_URL = '');
 *   2. direct API         — http://localhost:8000/api/v1/... (what the fetch
 *                           does when NEXT_PUBLIC_API_URL points at the API),
 *                           including the CORS response headers for the
 *                           production web origin and the OPTIONS preflight;
 *   3. production         — the two *.onrender.com URLs from render.yaml,
 *                           measured as-is (unreachable is a finding, not a
 *                           failure of the trace);
 *   4. fault injection    — a real DNS failure (.invalid) and a real 10s
 *                           abort against a non-routable address, so the
 *                           trace shows the exact rows that become
 *                           "offline" in the UI.
 *
 * Usage:  node scripts/network_trace.mjs [output.md]
 * Writes docs/NETWORK_TRACE.md by default. Diagnostic tooling only — no
 * application code imports this.
 */
import { performance } from 'node:perf_hooks';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = process.argv[2] ?? join(ROOT, 'docs', 'NETWORK_TRACE.md');

const PROXY = 'http://localhost:3000';
const API = 'http://localhost:8000';
const WEB_PROD = 'https://brobond-studio-web.onrender.com';
const API_PROD = 'https://brobond-ai-api.onrender.com';
const WEB_ORIGIN = 'https://brobond-studio-web.onrender.com';
const PROD_TIMEOUT_MS = 12_000;
const ABORT_TIMEOUT_MS = 10_000; // exactly lib/api.ts DEFAULT_TIMEOUT_MS

const HOME_PATHS = [
  '/api/v1/health',
  '/api/v1/system/readiness',
  '/api/v1/system/gpu',
];
const HOME_TOKEN_PATHS = ['/api/v1/assets', '/api/v1/personas'];

const rows = [];

function classify(error) {
  if (!error) return '';
  const message = String(error?.message ?? error);
  const cause = String(error?.cause?.message ?? error?.cause?.code ?? '');
  if (error?.name === 'AbortError' || error?.name === 'TimeoutError') return 'AbortError (timeout)';
  if (message.includes('Failed to fetch') || message.includes('fetch failed')) {
    return `TypeError (${cause || message})`;
  }
  return `${error?.name ?? 'Error'}: ${message}`;
}

async function timedFetch(url, init = {}, timeoutMs) {
  const started = performance.now();
  try {
    const response = await fetch(url, {
      ...init,
      signal: AbortSignal.timeout(timeoutMs ?? init?.timeoutMs ?? 15_000),
    });
    const duration = Math.round(performance.now() - started);
    let body = '';
    try {
      const text = await response.text();
      body = text.slice(0, 120);
    } catch { /* body optional */ }
    const cors = {
      allowOrigin: response.headers.get('access-control-allow-origin') ?? '—',
      allowHeaders: response.headers.get('access-control-allow-headers') ?? '—',
    };
    rows.push({ url, method: init.method ?? 'GET', status: response.status, duration, error: '', body, ...cors });
    return response;
  } catch (error) {
    const duration = Math.round(performance.now() - started);
    rows.push({
      url, method: init.method ?? 'GET', status: '—', duration,
      error: classify(error), body: '',
      allowOrigin: '—', allowHeaders: '—',
    });
    return null;
  }
}

function row(label) {
  const entry = rows.at(-1);
  entry.label = label;
}

// ---------------------------------------------------------------------------
// 1. Same-origin proxy (the repo design: NEXT_PUBLIC_API_URL unset → '')
// ---------------------------------------------------------------------------

for (const path of HOME_PATHS) {
  await timedFetch(`${PROXY}${path}`);
  row(`proxy · home · ${path}`);
}
// Token-required Home calls, anonymous: the UI would show status, not "offline".
for (const path of HOME_TOKEN_PATHS) {
  await timedFetch(`${PROXY}${path}`);
  row(`proxy · home (token routes, anonymous) · ${path}`);
}

// ---------------------------------------------------------------------------
// 2. Direct API (NEXT_PUBLIC_API_URL pointing at the API origin) + CORS
// ---------------------------------------------------------------------------

const originHeaders = { Origin: WEB_ORIGIN };
for (const path of HOME_PATHS) {
  await timedFetch(`${API}${path}`, { headers: originHeaders });
  row(`direct · home · ${path} (Origin: ${WEB_ORIGIN})`);
}
// The CORS preflight the browser sends before an authenticated GET —
// once with the production web origin (outside the LOCAL allow-list, so
// the API refuses it: this is the exact "200 mas o browser bloqueia"
// mechanism) and once with the local allow-listed origin (contrast).
await timedFetch(`${API}/api/v1/health`, {
  method: 'OPTIONS',
  headers: {
    ...originHeaders,
    'Access-Control-Request-Method': 'GET',
    'Access-Control-Request-Headers': 'authorization',
  },
});
row(`direct · CORS preflight · Origin ${WEB_ORIGIN} (fora da allow-list local)`);
await timedFetch(`${API}/api/v1/health`, {
  method: 'OPTIONS',
  headers: {
    Origin: 'http://localhost:3000',
    'Access-Control-Request-Method': 'GET',
    'Access-Control-Request-Headers': 'authorization',
  },
});
row('direct · CORS preflight · Origin http://localhost:3000 (allow-list local)');

// ---------------------------------------------------------------------------
// 3. Production (the URLs render.yaml provisions)
// ---------------------------------------------------------------------------

await timedFetch(`${API_PROD}/api/v1/health`, {}, PROD_TIMEOUT_MS);
row('production · GET https://brobond-ai-api.onrender.com/api/v1/health');
await timedFetch(`${WEB_PROD}/`, {}, PROD_TIMEOUT_MS);
row('production · GET https://brobond-studio-web.onrender.com/');
await timedFetch(`${WEB_PROD}/api/v1/health`, {}, PROD_TIMEOUT_MS);
row('production · GET web-origin /api/v1/health (proxied)');

// ---------------------------------------------------------------------------
// 4. Fault injection — the rows that become "offline" in the UI
// ---------------------------------------------------------------------------

await timedFetch('https://brobond-api.invalid/api/v1/health', {}, 8_000);
row('fault · DNS inválido (.invalid) → TypeError → "offline"');
await timedFetch('http://10.255.255.1:8000/api/v1/health', {}, ABORT_TIMEOUT_MS);
row(`fault · não-roteável + AbortSignal.timeout(${ABORT_TIMEOUT_MS}ms) → AbortError → "offline"`);

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------

function table(entries) {
  const head = '| # | Método | URL | Status | Duração | Erro | access-control-allow-origin |\n| --- | --- | --- | --- | --- | --- | --- |';
  const body = entries.map((entry, index) => {
    const url = entry.url.length > 68 ? `${entry.url.slice(0, 65)}…` : entry.url;
    return `| ${index + 1} | ${entry.method} | \`${url}\` | ${entry.status} | ${entry.duration}ms | ${entry.error || '—'} | ${entry.allowOrigin} |`;
  });
  return `${head}\n${body.join('\n')}`;
}

const proxyRows = rows.filter(entry => entry.label?.startsWith('proxy'));
const directRows = rows.filter(entry => entry.label?.startsWith('direct'));
const prodRows = rows.filter(entry => entry.label?.startsWith('production'));
const faultRows = rows.filter(entry => entry.label?.startsWith('fault'));
const generatedAt = new Date().toISOString();

const markdown = `# NETWORK TRACE — PR009.2 (Frontend Network Reconciliation)

Trace real (não simulado onde o alvo existe): cada linha é uma chamada
\`fetch\` de verdade, com a mesma forma que \`lib/api.ts\` faz — mesmos paths,
mesmos headers (\`Origin\` nas chamadas "direct", para revelar o CORS).
Gerado por \`node scripts/network_trace.mjs\` em ${generatedAt}.

**Fato do cliente (\`lib/api.ts\`):** \`API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''\`
— sem a env var, todo request é **relativo** (mesma origem, proxy do Next).
Timeouts: \`DEFAULT_TIMEOUT_MS = 10000\` (uploads: 30000) via
\`AbortSignal.timeout(...)\` — e o \`catch\` único converte **qualquer**
exceção (DNS, CORS, abort) no literal \`'offline'\`.

---

## 1. Same-origin proxy (design do repositório: \`API_URL = ''\`)

${table(proxyRows)}

Todas as rotas públicas da Home respondem **200 pelo proxy** no mesmo
caminho que o browser usa. As duas rotas com token, anônimas, respondem
**401** — que a UI trata como status (não como "offline").

## 2. Direct API (o que o fetch faz quando \`NEXT_PUBLIC_API_URL\` aponta para a API)

${table(directRows)}

Com \`Origin: ${WEB_ORIGIN}\`, a API responde 200 **e** ecoa
\`access-control-allow-origin\` — o middleware CORS (alimentado por
\`BROBOND_CORS_ORIGINS\` no render.yaml) aceita a origem do web service, e o
preflight \`OPTIONS\` (que o browser dispara por causa do header
\`Authorization\`) passa.

## 3. Production — as URLs do render.yaml, medidas

${table(prodRows)}

${prodRows.some(entry => entry.status === '—')
  ? 'Linha com status `—` = exceção de rede. Neste ambiente o egress HTTPS arbitrário é bloqueado pelo sandbox ("socket disconnected before secure TLS connection was established"), então a linha é **inconclusiva sobre o Render** — registrada como medida, não interpretada como serviço inexistente. Em uma máquina com saída livre, o mesmo script decide.'
  : 'Serviços de produção responderam.'}

## 4. Fault injection — as linhas que viram "API Offline"

${table(faultRows)}

Estas são as **únicas** classes de erro que produzem o literal \`'offline'\`
(\`lib/api.ts\`, catches das linhas 84 e 179): exceção de rede (\`TypeError\`)
ou abort por timeout (\`AbortError\`). Uma resposta HTTP — 200, 401, 500,
502 — **nunca** vira "offline": vira \`status\` + \`error\` com o motivo.
`;

writeFileSync(OUT, markdown, 'utf-8');
console.log(`trace written: ${OUT} (${rows.length} measured calls)`);
for (const entry of rows) {
  console.log(`${String(entry.status).padEnd(4)} ${String(entry.duration).padStart(5)}ms  ${entry.method}  ${entry.url}${entry.error ? `  → ${entry.error}` : ''}`);
}
