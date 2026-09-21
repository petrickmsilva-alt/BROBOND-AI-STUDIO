/**
 * PR013 — V4.0.1 Cinematic Asset Studio: the multipart upload runner.
 *
 * Why a sibling of `request.ts` instead of another `runRequest` option:
 * upload progress (loaded/total events, real bytes-per-second) requires
 * `XMLHttpRequest` — `fetch` has no upload-progress events in the browsers
 * this studio targets. The discipline of the network layer is unchanged:
 *
 *   single boundary  — components never instantiate XHR; this module is
 *                      the only place that does (the factory is injectable
 *                      for tests);
 *   typed failures   — network classes map to the same `NetworkErrorType`
 *                      taxonomy as `request.ts` (OFFLINE / CORS / TIMEOUT),
 *                      and HTTP answers arrive as a real `Response` so the
 *                      caller reuses `readError` and `httpErrorType`;
 *   trace id         — one `x-brobond-trace` header per upload, logged
 *                      without query strings or PII, exactly like GETs;
 *   no silent retry  — uploads are mutations; the caller decides whether
 *                      re-sending the bytes is safe. This runner never
 *                      retries on its own.
 *
 * The factory seam (`xhrFactory`) mirrors how `request.ts` isolates
 * `fetch`: jsdom's XHR never completes against a vitest run, so tests
 * drive events through a fake transport while the mapping logic stays
 * identical in production.
 */

import { apiConfigurationError } from './api-base-url';
import {
  API_URL,
  NetworkError,
  NetworkErrorType,
} from './request';

export const UPLOAD_XHR_TIMEOUT_MS = 60000;

/** One progress sample, emitted from `xhr.upload.onprogress`. */
export type UploadProgress = {
  /** Bytes the server has received so far. */
  loaded: number;
  /** Total request body bytes when computable (progressEvent.lengthComputable). */
  total: number;
  /** 0–100; equals 0 until the total is known. */
  percent: number;
  /** Smoothed throughput since the upload started, bytes per second. */
  bytesPerSecond: number;
  /** Monotonic clock reading in milliseconds (Date.now of the sample). */
  at: number;
};

export type UploadOutcome =
  | { kind: 'response'; response: Response; traceId: string; durationMs: number }
  | { kind: 'error'; error: NetworkError };

export type UploadRequest = {
  file: Blob;
  /** The multipart field name the API expects (`file` today). */
  fieldName?: string;
  /** Extra multipart text fields (project, persona, tags, ...). */
  fields?: Record<string, string>;
  filename?: string;
  headers?: Record<string, string>;
  timeoutMs?: number;
  onProgress?: (progress: UploadProgress) => void;
};

/** The XHR surface this module uses, so a fake can stand in. */
export type UploadTransport = {
  open(method: string, url: string): void;
  setRequestHeader(name: string, value: string): void;
  send(body: FormData): void;
  abort(): void;
  timeout: number;
  upload: { addEventListener(type: 'progress', listener: (event: ProgressEvent) => void): void } | null;
  addEventListener(type: 'load' | 'error' | 'timeout' | 'abort', listener: () => void): void;
  status: number;
  statusText: string;
  responseText: string;
};

export type UploadTransportFactory = () => UploadTransport;

function defaultTransportFactory(): UploadTransport {
  return new XMLHttpRequest() as unknown as UploadTransport;
}

function newUploadTraceId(): string {
  const cryptoRef = globalThis.crypto as { randomUUID?: () => string } | undefined;
  if (cryptoRef?.randomUUID) return cryptoRef.randomUUID();
  return `upl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function log(traceId: string, path: string, outcome: string, durationMs: number): void {
  // No PII: only the path — query strings can carry user content.
  console.info(`[brobond:upload] ${traceId} POST ${path.split('?')[0]} -> ${outcome} (${durationMs}ms)`);
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

/**
 * Run one multipart upload with real progress events.
 *
 * Resolves — never rejects — with either the transport's response (any
 * status; interpreting it is the caller's job) or a typed `NetworkError`.
 */
export function runUpload(
  path: string,
  request: UploadRequest,
  transportFactory: UploadTransportFactory = defaultTransportFactory,
): Promise<UploadOutcome> {
  const traceId = newUploadTraceId();
  const started = Date.now();
  const crossOrigin = isCrossOrigin(path);
  const finish = (outcome: UploadOutcome) => {
    log(traceId, path, outcome.kind === 'response' ? String(outcome.response.status) : outcome.error.type, Date.now() - started);
    return outcome;
  };

  // PR009.6.2.1 — same guard as `runRequest`: with no configured origin in
  // a production bundle there is nowhere to POST, so name the real cause
  // instead of letting XHR fail as a generic network error.
  if (apiConfigurationError()) {
    return Promise.resolve(finish({
      kind: 'error',
      error: new NetworkError(NetworkErrorType.MISCONFIGURED, { traceId, durationMs: 0 }),
    }));
  }

  return new Promise(resolve => {
    let transport: UploadTransport;
    try {
      transport = transportFactory();
    } catch {
      // A transport that cannot even be built (no XHR in this runtime) is
      // an unreachable API — typed, never an unhandled rejection.
      resolve(finish({
        kind: 'error',
        error: new NetworkError(NetworkErrorType.OFFLINE, { traceId, durationMs: Date.now() - started }),
      }));
      return;
    }
    const body = new FormData();
    Object.entries(request.fields ?? {}).forEach(([name, value]) => body.append(name, value));
    body.append(request.fieldName ?? 'file', request.file, request.filename);

    transport.addEventListener('load', () => {
      resolve(finish({
        kind: 'response',
        response: new Response(transport.responseText, { status: transport.status, statusText: transport.statusText }),
        traceId,
        durationMs: Date.now() - started,
      }));
    });
    transport.addEventListener('error', () => {
      resolve(finish({
        kind: 'error',
        error: new NetworkError(crossOrigin ? NetworkErrorType.CORS : NetworkErrorType.OFFLINE, { traceId, durationMs: Date.now() - started }),
      }));
    });
    transport.addEventListener('timeout', () => {
      resolve(finish({
        kind: 'error',
        error: new NetworkError(NetworkErrorType.TIMEOUT, { traceId, durationMs: Date.now() - started }),
      }));
    });
    transport.addEventListener('abort', () => {
      resolve(finish({
        kind: 'error',
        error: new NetworkError(NetworkErrorType.TIMEOUT, { traceId, durationMs: Date.now() - started }),
      }));
    });

    transport.upload?.addEventListener('progress', event => {
      if (!request.onProgress) return;
      const total = event.lengthComputable ? event.total : 0;
      const elapsedSeconds = Math.max((Date.now() - started) / 1000, 0.001);
      request.onProgress({
        loaded: event.loaded,
        total,
        percent: total > 0 ? Math.min(Math.round((event.loaded / total) * 100), 100) : 0,
        bytesPerSecond: Math.round(event.loaded / elapsedSeconds),
        at: Date.now(),
      });
    });

    try {
      transport.open('POST', `${API_URL}${path}`);
      transport.timeout = request.timeoutMs ?? UPLOAD_XHR_TIMEOUT_MS;
      transport.setRequestHeader('x-brobond-trace', traceId);
      Object.entries(request.headers ?? {}).forEach(([name, value]) => transport.setRequestHeader(name, value));
      transport.send(body);
    } catch {
      // open() itself can throw (an invalid URL, a pre-networked DOM);
      // that is an unreachable API, typed — never an unhandled rejection.
      resolve(finish({
        kind: 'error',
        error: new NetworkError(NetworkErrorType.OFFLINE, { traceId, durationMs: Date.now() - started }),
      }));
    }
  });
}
