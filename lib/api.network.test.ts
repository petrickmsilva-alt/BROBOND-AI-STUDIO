/**
 * PR009.2 / V3.2.1 — Network contract e2e: when is failure allowed to say
 * what actually happened?
 *
 * These tests stub the global `fetch` and drive the real `lib/api.ts`
 * request path (the same one the studio's panels use), now delegating to
 * `lib/network/request.ts`. The five failure classes the hotfix asked for
 * are pinned — each with its typed `NetworkErrorType` on `errorType`, a
 * human message on `error`, and the trace id — and NONE of them may ever
 * degrade to the old bare `'offline'` string:
 *
 *   API online   → remote=true, NUNCA erro
 *   HTTP 500     → status 500 + SERVER_ERROR + retry (3×, GET only)
 *   HTTP 401     → status 401 + UNAUTHORIZED, sem retry
 *   DNS inválido → TypeError → OFFLINE (typed, message explains the network)
 *   CORS         → TypeError + cross-origin → CORS (a API respondeu; o
 *                  browser escondeu — docs/NETWORK_RECONCILIATION_REPORT.md)
 *   Timeout      → AbortError → TIMEOUT; dentro da janela 8–60s é cold
 *                  start: "Servidor iniciando…", nunca "offline".
 */
import { afterEach, beforeEach, describe, expect, vi, it } from 'vitest';

import {
  API_URL,
  authenticate,
  gpuInfo,
  health,
  imageModels,
  listAssets,
  readiness,
} from './api';
import { AUTH_TOKEN_KEY } from './memory/project_memory';
import { NetworkErrorType } from './network/request';

type FetchStub = ReturnType<typeof vi.fn>;

const ONLINE_BODY = { status: 'ok', service: 'brobond-api', mode: 'local' };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** AbortSignal.timeout's rejection, reproduced exactly (browsers name it
 * AbortError, newer engines TimeoutError — both map to TIMEOUT). */
function abortError(): DOMException {
  return new DOMException('This operation was aborted', 'AbortError');
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  vi.stubGlobal('window', {
    location: { origin: 'http://localhost:3000' },
    localStorage: {
      store: new Map<string, string>(),
      getItem(key: string) { return this.store.get(key) ?? null; },
      setItem(key: string, value: string) { this.store.set(key, value); },
      removeItem(key: string) { this.store.delete(key); },
    },
  });
  // The layer logs one line per attempt; silence it in tests.
  vi.spyOn(console, 'info').mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// API online — the UI must never report a failure when the server answered
// ---------------------------------------------------------------------------

describe('API online', () => {
  it('parses the body, reports remote, and carries the trace id', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));

    const result = await health();

    expect(result.remote).toBe(true);
    expect(result.status).toBe(200);
    expect(result.error).toBeUndefined();
    expect(result.errorType).toBeUndefined();
    expect(result.data).toEqual(ONLINE_BODY);
    expect(result.traceId).toEqual(expect.any(String));
  });

  it('sends the request to the versioned health path (HomeContract)', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));

    await health();

    const [url] = (globalThis.fetch as FetchStub).mock.calls[0];
    expect(url).toBe('/api/v1/health');
  });

  it('attaches the bearer token, an abort signal and the trace header', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));
    window.localStorage.setItem(AUTH_TOKEN_KEY, 'token-123');

    await readiness();

    const [, init] = (globalThis.fetch as FetchStub).mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer token-123');
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect((init.headers as Record<string, string>)['x-brobond-trace']).toEqual(expect.any(String));
  });

  it('goes without the Authorization header when anonymous', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));

    await gpuInfo();

    const [, init] = (globalThis.fetch as FetchStub).mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Server answered with an error — a status and a type, never "offline"
// ---------------------------------------------------------------------------

describe('HTTP errors carry the status and the typed failure', () => {
  it('a 500 reports status 500, SERVER_ERROR and the API detail — retried 3× first', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(500, { detail: 'boom interno' }));

    const result = await health();

    expect(result.remote).toBe(false);
    expect(result.status).toBe(500);
    expect(result.errorType).toBe(NetworkErrorType.SERVER_ERROR);
    expect(result.error).toBe('boom interno');
    // ETAPA 3: first attempt + 3 retries, exponential backoff.
    expect((globalThis.fetch as FetchStub).mock.calls).toHaveLength(4);
    // One logical request, one trace id across every attempt.
    const traces = new Set(
      (globalThis.fetch as FetchStub).mock.calls.map(
        ([, init]) => (init.headers as Record<string, string>)['x-brobond-trace'],
      ),
    );
    expect(traces.size).toBe(1);
    expect(traces.has(result.traceId as string)).toBe(true);
  }, 15_000);

  it('a 401 reports status 401 + UNAUTHORIZED and is never retried', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(401, { detail: 'Not authenticated' }));

    const result = await gpuInfo();

    expect(result.status).toBe(401);
    expect(result.errorType).toBe(NetworkErrorType.UNAUTHORIZED);
    expect((globalThis.fetch as FetchStub).mock.calls).toHaveLength(1);
  });

  it('a non-JSON 502 from a router still reports the status', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(new Response('<html>bad gateway</html>', { status: 502 }));

    const result = await readiness();

    expect(result.status).toBe(502);
    expect(result.errorType).toBe(NetworkErrorType.SERVER_ERROR);
    expect(result.error).toBe('API 502');
  });

  it('a 422 maps to UNKNOWN with the API detail', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(422, { detail: [{ msg: 'field required' }] }));

    const result = await imageModels();

    expect(result.status).toBe(422);
    expect(result.errorType).toBe(NetworkErrorType.UNKNOWN);
    expect(result.error).toBe('field required');
  });

  it('a 204 parses to null without touching the reader', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(new Response(null, { status: 204 }));

    const result = await health();

    expect(result.remote).toBe(true);
    expect(result.data).toBeNull();
  });

  it('POST is never retried, even on a 500', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(500, { detail: 'nope' }));

    const result = await authenticate('/api/v1/auth/login', { username: 'user', password: 'pass' });

    expect(result.errorType).toBe(NetworkErrorType.SERVER_ERROR);
    expect((globalThis.fetch as FetchStub).mock.calls).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// The real network failure classes — each typed, none stringly "offline"
// ---------------------------------------------------------------------------

describe('real network failures arrive typed (never the bare "offline" string)', () => {
  it('an invalid DNS name rejects as TypeError → OFFLINE', async () => {
    // Node reproduces DNS failure exactly like a browser: TypeError("fetch failed")
    (globalThis.fetch as FetchStub).mockRejectedValue(
      Object.assign(new TypeError('fetch failed'), { cause: { code: 'ENOTFOUND' } }),
    );

    const result = await listAssets();

    expect(result.remote).toBe(false);
    expect(result.errorType).toBe(NetworkErrorType.OFFLINE);
    expect(result.status).toBeUndefined();
    expect(result.error).toBe('Sem conexão com a API — verifique sua rede ou inicie o FastAPI.');
    expect(result.traceId).toEqual(expect.any(String));
  });

  it('a cross-origin TypeError is CORS: the API answered, the browser hid it', async () => {
    // Measured live (PR009.2): preflight 400 for a non-allow-listed origin —
    // the old stack reported this as "API Offline".
    vi.resetModules();
    const previous = process.env.NEXT_PUBLIC_API_URL;
    process.env.NEXT_PUBLIC_API_URL = 'https://brobond-ai-api.onrender.com';
    try {
      const mod = await import('./api');
      (globalThis.fetch as FetchStub).mockRejectedValue(new TypeError('Failed to fetch'));

      const result = await mod.listAssets();

      expect(result.errorType).toBe(NetworkErrorType.CORS);
      expect(result.error).toBe('Requisição bloqueada pelo navegador (CORS) — origem não autorizada.');
    } finally {
      if (previous === undefined) delete process.env.NEXT_PUBLIC_API_URL;
      else process.env.NEXT_PUBLIC_API_URL = previous;
      vi.resetModules();
    }
  });

  it('an instant timeout abort arrives as TIMEOUT (too fast to be a cold start)', async () => {
    (globalThis.fetch as FetchStub).mockRejectedValue(abortError());

    const result = await listAssets();

    expect(result.errorType).toBe(NetworkErrorType.TIMEOUT);
    expect(result.error).toBe('A API não respondeu a tempo (timeout).');
  });

  it('a timeout inside the cold-start window says the server is starting', async () => {
    // Render free tier cold start: the connection hangs ~8.5s per attempt and
    // then aborts. Every retry lands in the 8–60s window → "Servidor iniciando".
    vi.useFakeTimers();
    (globalThis.fetch as FetchStub).mockImplementation(
      () => new Promise<Response>((_, reject) => { setTimeout(() => reject(abortError()), 8500); }),
    );

    const pending = health();
    await vi.runAllTimersAsync();
    const result = await pending;

    expect(result.errorType).toBe(NetworkErrorType.TIMEOUT);
    expect(result.error).toBe('Servidor iniciando — o primeiro acesso pode demorar alguns segundos.');
    expect((globalThis.fetch as FetchStub).mock.calls).toHaveLength(4);
  });
});

// ---------------------------------------------------------------------------
// URL reconciliation: what the fetch really uses
// ---------------------------------------------------------------------------

describe('the fetch base follows NEXT_PUBLIC_API_URL exactly', () => {
  const RENDER_API_URL = 'https://brobond-ai-api.onrender.com';

  it('defaults to the same origin (empty base, Next proxy)', async () => {
    expect(API_URL).toBe('');
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));

    await health();

    const [url] = (globalThis.fetch as FetchStub).mock.calls[0];
    expect(url.startsWith('/api/v1/')).toBe(true);
  });

  it('with render.yaml value set at build time, the fetch uses exactly that origin', async () => {
    vi.resetModules();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, ONLINE_BODY)));
    const previous = process.env.NEXT_PUBLIC_API_URL;
    process.env.NEXT_PUBLIC_API_URL = RENDER_API_URL;
    try {
      const mod = await import('./api');
      expect(mod.API_URL).toBe(RENDER_API_URL);

      await mod.health();

      const [url] = (globalThis.fetch as FetchStub).mock.calls[0];
      expect(url).toBe(`${RENDER_API_URL}/api/v1/health`);
    } finally {
      if (previous === undefined) delete process.env.NEXT_PUBLIC_API_URL;
      else process.env.NEXT_PUBLIC_API_URL = previous;
      vi.resetModules();
    }
  });
});

// ---------------------------------------------------------------------------
// The Home contract: the three public status routes, exactly as documented
// ---------------------------------------------------------------------------

describe('the Home status routes', () => {
  const stubOnline = () => (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));

  it('health() → GET /api/v1/health', async () => {
    stubOnline();
    await health();
    expect((globalThis.fetch as FetchStub).mock.calls[0][0]).toBe('/api/v1/health');
  });

  it('readiness() → GET /api/v1/system/readiness', async () => {
    stubOnline();
    await readiness();
    expect((globalThis.fetch as FetchStub).mock.calls[0][0]).toBe('/api/v1/system/readiness');
  });

  it('gpuInfo() → GET /api/v1/system/gpu', async () => {
    stubOnline();
    await gpuInfo();
    expect((globalThis.fetch as FetchStub).mock.calls[0][0]).toBe('/api/v1/system/gpu');
  });
});
