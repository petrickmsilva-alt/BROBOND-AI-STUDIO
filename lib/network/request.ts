/**
 * V3.2.1 — Network Reliability Layer: the single `fetch` boundary.
 *
 * Every request the studio makes goes through `runRequest` — no component
 * (and no other `lib` module) may call `fetch` directly (guarded by
 * `backend/tests/test_frontend_honesty.py`). Responsibilities, per the
 * sprint contract:
 *
 *   timeout       — `AbortSignal.timeout` (10s default, 30s uploads);
 *   retry         — GET only, 3 retries with exponential backoff
 *                   (300ms → 600ms → 1200ms) on network classes and 5xx;
 *   abort         — a caller-provided `init.signal` is merged with the
 *                   timeout signal (`AbortSignal.any` when available);
 *   error mapping — every failure becomes a typed `NetworkError`
 *                   (`NetworkErrorType`), never a bare string;
 *   trace id      — one `x-brobond-trace` UUID per request, echoed in the
 *                   log line (URL without query — no PII, latency, status).
 *
 * The false "API Offline" was born in an undiscriminating `catch`
 * (PR009.2 diagnosed it): CORS blocks and cold-start timeouts arrived as
 * exceptions and were reported exactly like a dead server. The mapping
 * below separates them, and `isColdStart` recognizes the 8–60s window so
 * the UI can say "Servidor iniciando…" instead of "offline".
 */

import { getApiBaseUrl } from './api-base-url';

/** The single base used by API requests, uploads and authentication. */
export const API_URL = getApiBaseUrl();

export const DEFAULT_TIMEOUT_MS = 10000;
export const UPLOAD_TIMEOUT_MS = 30000;

/** V3.2.1 retry policy: 3 retries (after the first attempt) with
 * exponential backoff. GET only — mutations are the caller's problem. */
export const STATUS_RETRY_ATTEMPTS = 3;
export const RETRY_DELAYS_MS: readonly number[] = [300, 600, 1200];

/** V3.2.1 cold-start window: a timeout that lands here is a server waking
 * up, not a dead one (Render free tier sleeps). */
export const COLD_START_MIN_MS = 8000;
export const COLD_START_MAX_MS = 60000;

/** The failure taxonomy. `ONLINE` is the healthy value — the enum doubles
 * as the status vocabulary, so nothing in the UI compares raw strings. */
export enum NetworkErrorType {
  ONLINE = 'online',
  TIMEOUT = 'timeout',
  OFFLINE = 'offline',
  CORS = 'cors',
  UNAUTHORIZED = 'unauthorized',
  SERVER_ERROR = 'server_error',
  UNKNOWN = 'unknown',
}

export class NetworkError extends Error {
  readonly type: NetworkErrorType;
  readonly status?: number;
  /** The API's own error body, when one arrived (`readError`). */
  readonly detail?: string;
  readonly traceId: string;
  readonly durationMs: number;

  constructor(
    type: NetworkErrorType,
    options: { status?: number; detail?: string; traceId: string; durationMs: number },
  ) {
    super(`${type}${options.status ? ` (${options.status})` : ''}`);
    this.name = 'NetworkError';
    this.type = type;
    this.status = options.status;
    this.detail = options.detail;
    this.traceId = options.traceId;
    this.durationMs = options.durationMs;
  }
}

export type RequestOutcome =
  | { kind: 'response'; response: Response; traceId: string; durationMs: number }
  | { kind: 'error'; error: NetworkError };

export type RunOptions = {
  timeoutMs?: number;
  retries?: number;
  retryDelaysMs?: readonly number[];
};

function newTraceId(): string {
  const cryptoRef = globalThis.crypto as { randomUUID?: () => string } | undefined;
  if (cryptoRef?.randomUUID) return cryptoRef.randomUUID();
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function isCrossOrigin(path: string): boolean {
  if (!API_URL) return false;
  try {
    const target = new URL(path, API_URL);
    const here = typeof window !== 'undefined' && window.location?.origin;
    return here ? target.origin !== here : target.origin !== new URL(API_URL).origin;
  } catch {
    return API_URL.startsWith('http');
  }
}

/** The exception → type mapping. This is where the false "offline" dies:
 * timeout, CORS and offline each get their own type. */
export function classifyException(error: unknown, crossOrigin: boolean): NetworkErrorType {
  const name = (error as { name?: string } | null)?.name;
  if (name === 'TimeoutError' || name === 'AbortError') return NetworkErrorType.TIMEOUT;
  if (error instanceof TypeError || name === 'TypeError') {
    // navigator.onLine is the only honest signal: the browser knows when
    // there is no network at all. A TypeError while online is the browser
    // refusing/hiding the response — cross-origin that is CORS, same-origin
    // it is an unreachable server.
    const navigatorRef = globalThis.navigator as { onLine?: boolean } | undefined;
    if (navigatorRef?.onLine === false) return NetworkErrorType.OFFLINE;
    return crossOrigin ? NetworkErrorType.CORS : NetworkErrorType.OFFLINE;
  }
  return NetworkErrorType.UNKNOWN;
}

export function httpErrorType(status: number): NetworkErrorType {
  if (status === 401) return NetworkErrorType.UNAUTHORIZED;
  if (status >= 500) return NetworkErrorType.SERVER_ERROR;
  return NetworkErrorType.UNKNOWN;
}

/** A timeout inside the cold-start window means the server is waking up. */
export function isColdStart(type: NetworkErrorType, durationMs: number): boolean {
  return (
    type === NetworkErrorType.TIMEOUT &&
    durationMs >= COLD_START_MIN_MS &&
    durationMs <= COLD_START_MAX_MS
  );
}

/** The human text for a typed failure. Never a bare "offline": TIMEOUT in
 * the cold-start window says the server is starting. */
export function networkProblemText(error: NetworkError): string {
  switch (error.type) {
    case NetworkErrorType.TIMEOUT:
      return isColdStart(error.type, error.durationMs)
        ? 'Servidor iniciando — o primeiro acesso pode demorar alguns segundos.'
        : 'A API não respondeu a tempo (timeout).';
    case NetworkErrorType.OFFLINE:
      return 'Sem conexão com a API — verifique sua rede ou inicie o FastAPI.';
    case NetworkErrorType.CORS:
      return 'Requisição bloqueada pelo navegador (CORS) — origem não autorizada.';
    case NetworkErrorType.UNAUTHORIZED:
      return 'Sessão expirada ou ausente — entre novamente.';
    case NetworkErrorType.SERVER_ERROR:
      return `Erro interno da API${error.status ? ` (${error.status})` : ''}${error.detail ? `: ${error.detail}` : ''}`;
    default:
      return error.detail ? `Falha na requisição: ${error.detail}` : 'Falha desconhecida na requisição.';
  }
}

/** Pull a useful message out of a FastAPI error body, which has a known shape. */
export async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return String(body.detail[0].msg);
    if (body?.detail) return JSON.stringify(body.detail);
  } catch {
    // A non-JSON error body is still an error; fall through to the status text.
  }
  return `API ${response.status} ${response.statusText}`.trim();
}

function log(traceId: string, method: string, path: string, outcome: string, durationMs: number): void {
  // No PII: only the path (query strings can carry user content).
  const cleanPath = path.split('?')[0];
  console.info(`[brobond:network] ${traceId} ${method} ${cleanPath} -> ${outcome} (${durationMs}ms)`);
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => { setTimeout(resolve, ms); });
}

async function attempt(
  path: string,
  init: RequestInit,
  timeoutMs: number,
  traceId: string,
): Promise<{ response: Response; durationMs: number } | { error: unknown; durationMs: number }> {
  const started = Date.now();
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const callerSignal = init.signal;
  const signal =
    callerSignal && typeof AbortSignal.any === 'function'
      ? AbortSignal.any([timeoutSignal, callerSignal])
      : timeoutSignal;
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      signal,
      headers: {
        'x-brobond-trace': traceId,
        ...(init.headers ?? {}),
      },
    });
    return { response, durationMs: Date.now() - started };
  } catch (error) {
    return { error, durationMs: Date.now() - started };
  }
}

/**
 * Run one logical request: timeout, trace header, retry (GET only) and the
 * error mapping. Returns either the live `Response` (body not yet consumed)
 * or a typed `NetworkError` — the caller decides how to parse and present.
 */
export async function runRequest(
  path: string,
  init: RequestInit = {},
  options: RunOptions = {},
): Promise<RequestOutcome> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const retries = options.retries ?? 0;
  const retryDelaysMs = options.retryDelaysMs ?? RETRY_DELAYS_MS;
  const traceId = newTraceId();
  const method = (init.method ?? 'GET').toUpperCase();
  const crossOrigin = isCrossOrigin(path);
  const started = Date.now();

  for (let attemptIndex = 0; ; attemptIndex += 1) {
    const result = await attempt(path, init, timeoutMs, traceId);
    const totalMs = Date.now() - started;

    if ('response' in result) {
      const { response } = result;
      if (response.ok || !isRetryableOutcome(method, response.status, retries, attemptIndex)) {
        log(traceId, method, path, String(response.status), result.durationMs);
        return { kind: 'response', response, traceId, durationMs: totalMs };
      }
      log(traceId, method, path, `${response.status} (retry)`, result.durationMs);
    } else {
      const type = classifyException(result.error, crossOrigin);
      if (!isRetryableOutcome(method, null, retries, attemptIndex, type)) {
        log(traceId, method, path, `${type}`, result.durationMs);
        return {
          kind: 'error',
          error: new NetworkError(type, { traceId, durationMs: totalMs }),
        };
      }
      log(traceId, method, path, `${type} (retry)`, result.durationMs);
    }

    // The index is capped into range; `?? 0` is only a defensive default.
    /* v8 ignore next */
    const backoff = retryDelaysMs[Math.min(attemptIndex, retryDelaysMs.length - 1)] ?? 0;
    if (backoff > 0) {
      await delay(backoff);
    }
  }
}

function isRetryableOutcome(
  method: string,
  status: number | null,
  retries: number,
  attemptIndex: number,
  type?: NetworkErrorType,
): boolean {
  if (attemptIndex >= retries) return false;
  if (method !== 'GET') return false; // Somente GET.
  if (status !== null) return status >= 500;
  return type !== undefined && type !== NetworkErrorType.UNAUTHORIZED;
}
