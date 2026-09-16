/**
 * V3.2.1 ETAPA 8 — the network layer's own contract, unit-level.
 *
 * `lib/api.network.test.ts` drives the layer through `lib/api.ts` (the
 * panels' path); this suite pins `runRequest` itself: the exception →
 * `NetworkErrorType` mapping, the retry policy (GET only, 300/600/1200ms),
 * the cold-start window, the trace id and the PII-free log line.
 *
 * Retry waits are exercised under fake timers, so the backoff schedule is
 * asserted exactly (attempt boundaries at 300/900/2100ms) without real
 * sleeping.
 */
import { afterEach, beforeEach, describe, expect, vi, it } from 'vitest';

import {
  COLD_START_MAX_MS,
  COLD_START_MIN_MS,
  DEFAULT_TIMEOUT_MS,
  NetworkError,
  NetworkErrorType,
  classifyException,
  httpErrorType,
  isColdStart,
  networkProblemText,
  readError,
  runRequest,
} from './request';

type FetchStub = ReturnType<typeof vi.fn>;

const fetchStub = () => globalThis.fetch as FetchStub;

function jsonResponse(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function abortError(name = 'AbortError'): DOMException {
  return new DOMException('This operation was aborted', name);
}

/** A fetch that always rejects with an abort after `ms` of fake time. */
function hangingFetch(ms: number, name?: string): FetchStub {
  return vi.fn(
    () => new Promise<Response>((_, reject) => { setTimeout(() => reject(abortError(name)), ms); }),
  ) as FetchStub;
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
  vi.stubGlobal('window', { location: { origin: 'http://localhost:3000' } });
  vi.spyOn(console, 'info').mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_API_URL;
});

// ---------------------------------------------------------------------------
// Success path: trace header, log line, outcome shape
// ---------------------------------------------------------------------------

describe('runRequest — success', () => {
  it('returns the response with trace id and duration, logging the path without the query', async () => {
    fetchStub().mockResolvedValue(jsonResponse(200, { ok: true }));

    const outcome = await runRequest('/api/v1/health?verbose=secret-token');

    expect(outcome.kind).toBe('response');
    if (outcome.kind !== 'response') return;
    expect(outcome.response.status).toBe(200);
    expect(outcome.traceId).toEqual(expect.any(String));
    expect(typeof outcome.durationMs).toBe('number');

    const [, init] = fetchStub().mock.calls[0];
    expect((init.headers as Record<string, string>)['x-brobond-trace']).toBe(outcome.traceId);

    // ETAPA 6: URL, latency, status — and no PII (the query string stays out).
    expect(console.info).toHaveBeenCalledTimes(1);
    const line = (console.info as unknown as FetchStub).mock.calls[0][0] as string;
    expect(line).toContain(`[brobond:network] ${outcome.traceId} GET /api/v1/health -> 200`);
    expect(line).toContain('ms)');
    expect(line).not.toContain('secret-token');
  });

  it('sends the request to API_URL + path and defaults the timeout to 10s', async () => {
    fetchStub().mockResolvedValue(jsonResponse(200));

    await runRequest('/api/v1/health');

    const [url, init] = fetchStub().mock.calls[0];
    expect(url).toBe('/api/v1/health');
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(DEFAULT_TIMEOUT_MS).toBe(10_000);
  });

  it('merges the caller signal: aborting it aborts the wire signal', async () => {
    fetchStub().mockResolvedValue(jsonResponse(200));
    const controller = new AbortController();

    const pending = runRequest('/api/v1/health', { signal: controller.signal });
    const [, init] = fetchStub().mock.calls[0];
    controller.abort();
    await pending;

    expect((init as RequestInit).signal?.aborted).toBe(true);
  });

  it('falls back to the timeout signal alone when AbortSignal.any is unavailable', async () => {
    fetchStub().mockResolvedValue(jsonResponse(200));
    const anyFn = (AbortSignal as unknown as Record<string, unknown>).any;
    (AbortSignal as unknown as Record<string, unknown>).any = undefined;
    try {
      const pending = runRequest('/api/v1/health', { signal: new AbortController().signal });
      const [, init] = fetchStub().mock.calls[0];
      await pending;
      expect(init.signal).toBeInstanceOf(AbortSignal);
    } finally {
      (AbortSignal as unknown as Record<string, unknown>).any = anyFn;
    }
  });
});

// ---------------------------------------------------------------------------
// ETAPA 1 — the exception → type mapping (where the false "offline" died)
// ---------------------------------------------------------------------------

describe('classifyException', () => {
  it('maps TimeoutError and AbortError to TIMEOUT', () => {
    expect(classifyException(abortError('TimeoutError'), false)).toBe(NetworkErrorType.TIMEOUT);
    expect(classifyException(abortError('AbortError'), false)).toBe(NetworkErrorType.TIMEOUT);
  });

  it('maps a TypeError with navigator.onLine === false to OFFLINE', () => {
    vi.stubGlobal('navigator', { onLine: false });
    expect(classifyException(new TypeError('fetch failed'), false)).toBe(NetworkErrorType.OFFLINE);
    expect(classifyException(new TypeError('fetch failed'), true)).toBe(NetworkErrorType.OFFLINE);
  });

  it('maps an online TypeError to CORS when cross-origin, OFFLINE when same-origin', () => {
    // Node's navigator.onLine is true; the browser reports the same for wifi-up.
    expect(classifyException(new TypeError('Failed to fetch'), true)).toBe(NetworkErrorType.CORS);
    expect(classifyException(new TypeError('Failed to fetch'), false)).toBe(NetworkErrorType.OFFLINE);
    // A TypeError recognized by name only (cross-realm objects are not instanceof).
    expect(classifyException({ name: 'TypeError' }, true)).toBe(NetworkErrorType.CORS);
  });

  it('maps anything else to UNKNOWN', () => {
    expect(classifyException(new RangeError('nope'), false)).toBe(NetworkErrorType.UNKNOWN);
    expect(classifyException(null, false)).toBe(NetworkErrorType.UNKNOWN);
  });
});

describe('httpErrorType', () => {
  it('maps 401 → UNAUTHORIZED, ≥500 → SERVER_ERROR, the rest → UNKNOWN', () => {
    expect(httpErrorType(401)).toBe(NetworkErrorType.UNAUTHORIZED);
    expect(httpErrorType(500)).toBe(NetworkErrorType.SERVER_ERROR);
    expect(httpErrorType(503)).toBe(NetworkErrorType.SERVER_ERROR);
    expect(httpErrorType(404)).toBe(NetworkErrorType.UNKNOWN);
    expect(httpErrorType(422)).toBe(NetworkErrorType.UNKNOWN);
  });
});

// ---------------------------------------------------------------------------
// ETAPA 4 — the cold-start window
// ---------------------------------------------------------------------------

describe('isColdStart', () => {
  it('is true only for TIMEOUT inside the 8–60s window', () => {
    expect(isColdStart(NetworkErrorType.TIMEOUT, COLD_START_MIN_MS - 1)).toBe(false);
    expect(isColdStart(NetworkErrorType.TIMEOUT, COLD_START_MIN_MS)).toBe(true);
    expect(isColdStart(NetworkErrorType.TIMEOUT, 20_000)).toBe(true);
    expect(isColdStart(NetworkErrorType.TIMEOUT, COLD_START_MAX_MS)).toBe(true);
    expect(isColdStart(NetworkErrorType.TIMEOUT, COLD_START_MAX_MS + 1)).toBe(false);
    expect(isColdStart(NetworkErrorType.OFFLINE, 20_000)).toBe(false);
  });
});

describe('networkProblemText', () => {
  const error = (type: NetworkErrorType, extra: { status?: number; detail?: string } = {}) =>
    new NetworkError(type, { traceId: 't', durationMs: isColdStart(type, 10_000) ? 10_000 : 0, ...extra });

  it('says the server is starting for a cold-start timeout — never "offline"', () => {
    expect(networkProblemText(error(NetworkErrorType.TIMEOUT))).toBe(
      'Servidor iniciando — o primeiro acesso pode demorar alguns segundos.',
    );
  });

  it('says it is a timeout when the wait was too short to be a cold start', () => {
    expect(networkProblemText(new NetworkError(NetworkErrorType.TIMEOUT, { traceId: 't', durationMs: 500 }))).toBe(
      'A API não respondeu a tempo (timeout).',
    );
  });

  it('explains offline, CORS and session expiry in the user\'s terms', () => {
    expect(networkProblemText(error(NetworkErrorType.OFFLINE))).toBe(
      'Sem conexão com a API — verifique sua rede ou inicie o FastAPI.',
    );
    expect(networkProblemText(error(NetworkErrorType.CORS))).toBe(
      'Requisição bloqueada pelo navegador (CORS) — origem não autorizada.',
    );
    expect(networkProblemText(error(NetworkErrorType.UNAUTHORIZED))).toBe(
      'Sessão expirada ou ausente — entre novamente.',
    );
  });

  it('carries the status and detail for server errors and unknowns', () => {
    expect(networkProblemText(error(NetworkErrorType.SERVER_ERROR, { status: 500, detail: 'boom' }))).toBe(
      'Erro interno da API (500): boom',
    );
    expect(networkProblemText(error(NetworkErrorType.SERVER_ERROR))).toBe('Erro interno da API');
    expect(networkProblemText(error(NetworkErrorType.UNKNOWN, { detail: 'estranho' }))).toBe(
      'Falha na requisição: estranho',
    );
    expect(networkProblemText(error(NetworkErrorType.UNKNOWN))).toBe('Falha desconhecida na requisição.');
  });
});

// ---------------------------------------------------------------------------
// readError — FastAPI's error shapes
// ---------------------------------------------------------------------------

describe('readError', () => {
  const response = (status: number, body?: string) =>
    body === undefined
      ? new Response(null, { status, statusText: 'Too Many Requests' })
      : new Response(body, { status, statusText: 'Bad Gateway' });

  it('reads a string detail', async () => {
    expect(await readError(response(400, JSON.stringify({ detail: 'bad input' })))).toBe('bad input');
  });

  it('reads the first message of a validation array', async () => {
    const body = JSON.stringify({ detail: [{ msg: 'field required' }, { msg: 'other' }] });
    expect(await readError(response(422, body))).toBe('field required');
  });

  it('serializes an object detail', async () => {
    const body = JSON.stringify({ detail: { reason: 'locked' } });
    expect(await readError(response(409, body))).toBe('{"reason":"locked"}');
  });

  it('falls back to the status line for a non-JSON body', async () => {
    expect(await readError(response(502, '<html>bad gateway</html>'))).toBe('API 502 Bad Gateway');
  });

  it('falls back to the status line when there is no body at all', async () => {
    expect(await readError(response(429))).toBe('API 429 Too Many Requests');
  });
});

// ---------------------------------------------------------------------------
// ETAPA 2/3 — retry policy: GET only, 3×, 300/600/1200ms
// ---------------------------------------------------------------------------

describe('runRequest — retry policy', () => {
  it('retries a GET 5xx and succeeds on a later attempt', async () => {
    vi.useFakeTimers();
    fetchStub()
      .mockResolvedValueOnce(jsonResponse(502))
      .mockResolvedValueOnce(jsonResponse(500))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    const pending = runRequest('/api/v1/system/readiness', { method: 'GET' }, { retries: 3 });
    await vi.runAllTimersAsync();
    const outcome = await pending;

    expect(fetchStub()).toHaveBeenCalledTimes(3);
    expect(outcome.kind).toBe('response');
  });

  it('waits exactly 300/900/2100ms before the 2nd/3rd/4th attempts', async () => {
    vi.useFakeTimers();
    const at: number[] = [];
    fetchStub().mockImplementation(async () => {
      at.push(Date.now());
      return jsonResponse(500);
    });

    const pending = runRequest('/api/v1/system/readiness', { method: 'GET' }, { retries: 3 });
    await vi.runAllTimersAsync();
    await pending;

    expect(fetchStub()).toHaveBeenCalledTimes(4);
    expect(at[1] - at[0]).toBe(300);
    expect(at[2] - at[1]).toBe(600);
    expect(at[3] - at[2]).toBe(1200);
  });

  it('gives up after the last retry and returns the response for the caller to map', async () => {
    vi.useFakeTimers();
    fetchStub().mockResolvedValue(jsonResponse(500));

    const pending = runRequest('/api/v1/system/readiness', { method: 'GET' }, { retries: 3 });
    await vi.runAllTimersAsync();
    const outcome = await pending;

    expect(fetchStub()).toHaveBeenCalledTimes(4);
    if (outcome.kind === 'response') expect(outcome.response.status).toBe(500);
    else expect.unreachable('a 500 is a response, not an exception');
  });

  it('never retries a POST', async () => {
    vi.useFakeTimers();
    fetchStub().mockResolvedValue(jsonResponse(500));

    const pending = runRequest('/api/v1/generations/images', { method: 'POST' }, { retries: 3 });
    await vi.runAllTimersAsync();
    await pending;

    expect(fetchStub()).toHaveBeenCalledTimes(1);
  });

  it('retries network classes on GET and returns the typed error after the last attempt', async () => {
    vi.useFakeTimers();
    fetchStub().mockRejectedValue(new TypeError('fetch failed'));

    const pending = runRequest('/api/v1/assets', { method: 'GET' }, { retries: 1, retryDelaysMs: [10] });
    await vi.runAllTimersAsync();
    const outcome = await pending;

    expect(fetchStub()).toHaveBeenCalledTimes(2);
    expect(outcome.kind).toBe('error');
    if (outcome.kind !== 'error') return;
    expect(outcome.error).toBeInstanceOf(NetworkError);
    expect(outcome.error.type).toBe(NetworkErrorType.OFFLINE);
    expect(outcome.error.traceId).toEqual(expect.any(String));
  });

  it('never retries a 401', async () => {
    vi.useFakeTimers();
    fetchStub().mockResolvedValue(jsonResponse(401));

    const pending = runRequest('/api/v1/assets', { method: 'GET' }, { retries: 3 });
    await vi.runAllTimersAsync();
    const outcome = await pending;

    expect(fetchStub()).toHaveBeenCalledTimes(1);
    if (outcome.kind === 'response') expect(outcome.response.status).toBe(401);
    else expect.unreachable('a 401 is a response, not an exception');
  });

  it('honors a custom retry schedule, including a zero backoff', async () => {
    vi.useFakeTimers();
    const at: number[] = [];
    fetchStub().mockImplementation(async () => {
      at.push(Date.now());
      return jsonResponse(500);
    });

    const pending = runRequest('/api/v1/x', { method: 'GET' }, { retries: 2, retryDelaysMs: [50, 70] });
    await vi.runAllTimersAsync();
    await pending;

    expect(at[1] - at[0]).toBe(50);
    expect(at[2] - at[1]).toBe(70);

    const instant = runRequest('/api/v1/x', { method: 'GET' }, { retries: 1, retryDelaysMs: [0] });
    await vi.runAllTimersAsync();
    await instant;
    expect(fetchStub()).toHaveBeenCalledTimes(5); // 3 (first schedule) + 2 (zero-delay pair)
  });
});

// ---------------------------------------------------------------------------
// ETAPA 4 — timeout classification end-to-end
// ---------------------------------------------------------------------------

describe('runRequest — timeout and cold start', () => {
  it('maps a fast abort to TIMEOUT without the cold-start text', async () => {
    vi.useFakeTimers();
    fetchStub().mockImplementation(() =>
      new Promise<Response>((_, reject) => { setTimeout(() => reject(abortError('TimeoutError')), 2_000); }),
    );

    const pending = runRequest('/api/v1/health', { method: 'GET' }, { retries: 0 });
    await vi.runAllTimersAsync();
    const outcome = await pending;

    if (outcome.kind !== 'error') return expect.unreachable('an abort is an error');
    expect(outcome.error.type).toBe(NetworkErrorType.TIMEOUT);
    expect(outcome.error.durationMs).toBeLessThan(COLD_START_MIN_MS);
    expect(networkProblemText(outcome.error)).toBe('A API não respondeu a tempo (timeout).');
  });

  it('classifies a timeout inside the cold-start window as a server waking up', async () => {
    vi.useFakeTimers();
    fetchStub().mockImplementation(hangingFetch(8_500));

    const pending = runRequest('/api/v1/health', { method: 'GET' }, { retries: 0 });
    await vi.runAllTimersAsync();
    const outcome = await pending;

    if (outcome.kind !== 'error') return expect.unreachable('an abort is an error');
    expect(outcome.error.type).toBe(NetworkErrorType.TIMEOUT);
    expect(outcome.error.durationMs).toBeGreaterThanOrEqual(COLD_START_MIN_MS);
    expect(networkProblemText(outcome.error)).toBe(
      'Servidor iniciando — o primeiro acesso pode demorar alguns segundos.',
    );
  });
});

// ---------------------------------------------------------------------------
// Trace id and cross-origin detection details
// ---------------------------------------------------------------------------

describe('trace id', () => {
  it('falls back to a req- id when crypto.randomUUID is unavailable', async () => {
    fetchStub().mockResolvedValue(jsonResponse(200));
    vi.stubGlobal('crypto', {});

    const outcome = await runRequest('/api/v1/health');

    if (outcome.kind !== 'response') return expect.unreachable();
    expect(outcome.traceId).toMatch(/^req-/);
  });
});

describe('cross-origin detection', () => {
  it('compares against API_URL when window is unavailable', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.example.com';
    vi.resetModules();
    const { runRequest: fresh } = await import('./request');
    vi.stubGlobal('window', undefined);
    fetchStub().mockRejectedValue(new TypeError('Failed to fetch'));

    const outcome = await fresh('/api/v1/assets', { method: 'GET' }, { retries: 0 });

    // Same origin as the base (the window is not): a plain TypeError is
    // an unreachable server, not CORS.
    if (outcome.kind !== 'error') return expect.unreachable();
    expect(outcome.error.type).toBe(NetworkErrorType.OFFLINE);
  });

  it('treats an unparseable absolute base as cross-origin', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://brobond api.example.com'; // space → invalid URL
    vi.resetModules();
    const { runRequest: fresh } = await import('./request');
    fetchStub().mockRejectedValue(new TypeError('Failed to fetch'));

    const outcome = await fresh('/api/v1/assets', { method: 'GET' }, { retries: 0 });

    if (outcome.kind !== 'error') return expect.unreachable();
    expect(outcome.error.type).toBe(NetworkErrorType.CORS);
  });
});
