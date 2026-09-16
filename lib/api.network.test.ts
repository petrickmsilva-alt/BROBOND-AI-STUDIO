/**
 * PR009.2 — Network reconciliation e2e: when is "offline" allowed to appear?
 *
 * These tests stub the global `fetch` and drive the real `lib/api.ts`
 * request path (the same one the studio's panels use), pinning the five
 * failure classes the hotfix asked for:
 *
 *   API online  → remote=true, NUNCA "offline"
 *   HTTP 500    → status 500 + motivo, NUNCA "offline"
 *   DNS inválido→ TypeError → "offline" (única classe de rede real)
 *   CORS        → TypeError → "offline" (conflação documentada: a API
 *                 respondeu 200, mas o browser esconde — ver
 *                 docs/NETWORK_RECONCILIATION_REPORT.md, correção proposta)
 *   Timeout     → AbortError → "offline" (conflação documentada: cold start
 *                 do Render free tier passa de 10s com a API viva)
 *
 * Coverage stays scoped to the four contract modules in vitest.config.ts on
 * purpose: this suite pins the fetch boundary's behavior, and `lib/api.ts`
 * remains guarded by the backend structural tests (test_frontend_honesty.py).
 */
import { afterEach, beforeEach, describe, expect, vi, it } from 'vitest';

import {
  API_URL,
  gpuInfo,
  health,
  readiness,
} from './api';
import { AUTH_TOKEN_KEY } from './memory/project_memory';

type FetchStub = ReturnType<typeof vi.fn>;

const ONLINE_BODY = { status: 'ok', service: 'brobond-api', mode: 'local' };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** AbortSignal.timeout's rejection, reproduced exactly. */
function abortError(): DOMException {
  return new DOMException('This operation was aborted', 'AbortError');
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  vi.stubGlobal('window', {
    localStorage: {
      store: new Map<string, string>(),
      getItem(key: string) { return this.store.get(key) ?? null; },
      setItem(key: string, value: string) { this.store.set(key, value); },
      removeItem(key: string) { this.store.delete(key); },
    },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// API online — the UI must never say "offline" when the server answered
// ---------------------------------------------------------------------------

describe('API online', () => {
  it('parses the body and reports remote — never offline', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));

    const result = await health();

    expect(result.remote).toBe(true);
    expect(result.status).toBe(200);
    expect(result.error).toBeUndefined();
    expect(result.data).toEqual(ONLINE_BODY);
  });

  it('sends the request to the versioned health path (HomeContract)', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));

    await health();

    const [url] = (globalThis.fetch as FetchStub).mock.calls[0];
    expect(url).toBe('/api/v1/health');
  });

  it('attaches the bearer token when the session has one', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));
    window.localStorage.setItem(AUTH_TOKEN_KEY, 'token-123');

    await readiness();

    const [, init] = (globalThis.fetch as FetchStub).mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer token-123');
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it('goes without the Authorization header when anonymous', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(200, ONLINE_BODY));

    await gpuInfo();

    const [, init] = (globalThis.fetch as FetchStub).mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Server answered with an error — a status, never "offline"
// ---------------------------------------------------------------------------

describe('HTTP errors still carry the status', () => {
  it('a 500 reports status 500 and the API detail — not offline', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(500, { detail: 'boom interno' }));

    const result = await health();

    expect(result.remote).toBe(false);
    expect(result.status).toBe(500);
    expect(result.error).toBe('boom interno');
    expect(result.error).not.toBe('offline');
  });

  it('a 401 reports status 401 — not offline', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(jsonResponse(401, { detail: 'Not authenticated' }));

    const result = await gpuInfo();

    expect(result.status).toBe(401);
    expect(result.error).toBe('Not authenticated');
    expect(result.error).not.toBe('offline');
  });

  it('a non-JSON 502 from a router still reports the status, not offline', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(new Response('<html>bad gateway</html>', { status: 502 }));

    const result = await readiness();

    expect(result.status).toBe(502);
    expect(result.error).not.toBe('offline');
  });

  it('a 204 parses to null without touching the reader', async () => {
    (globalThis.fetch as FetchStub).mockResolvedValue(new Response(null, { status: 204 }));

    const result = await health();

    expect(result.remote).toBe(true);
    expect(result.data).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// The three exception classes — the ONLY sources of the "offline" literal
// ---------------------------------------------------------------------------

describe('real network failures produce offline', () => {
  it('an invalid DNS name rejects as TypeError → offline', async () => {
    // Node reproduces DNS failure exactly like a browser: TypeError("fetch failed")
    (globalThis.fetch as FetchStub).mockRejectedValue(
      Object.assign(new TypeError('fetch failed'), { cause: { code: 'ENOTFOUND' } }),
    );

    const result = await health();

    expect(result.remote).toBe(false);
    expect(result.error).toBe('offline');
    expect(result.status).toBeUndefined();
  });

  it('a connection refused rejects as TypeError → offline', async () => {
    (globalThis.fetch as FetchStub).mockRejectedValue(
      Object.assign(new TypeError('fetch failed'), { cause: { code: 'ECONNREFUSED' } }),
    );

    const result = await readiness();

    expect(result.error).toBe('offline');
  });
});

describe('the documented conflations (server fine, browser blocks)', () => {
  it('a CORS block arrives as TypeError("Failed to fetch") → offline', async () => {
    // The API answered 200; the browser hid the response because the origin
    // was not allow-listed (measured live: preflight 400 — see the trace).
    (globalThis.fetch as FetchStub).mockRejectedValue(new TypeError('Failed to fetch'));

    const result = await health();

    expect(result.error).toBe('offline');
    expect(result.status).toBeUndefined();
  });

  it('a timeout abort arrives as AbortError → offline', async () => {
    // Render free tier cold start can exceed the 10s budget with the API
    // perfectly alive — this is the false "API Offline" in production.
    (globalThis.fetch as FetchStub).mockRejectedValue(abortError());

    const result = await readiness();

    expect(result.error).toBe('offline');
    expect(result.status).toBeUndefined();
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
