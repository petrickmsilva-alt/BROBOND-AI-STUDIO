/**
 * PR009.6.2.1 — ETAPA 5: what the app does when a production bundle has no
 * NEXT_PUBLIC_API_URL.
 *
 * The rule: never guess an origin, never retry, never blame the network.
 * A request that cannot know where to go fails immediately with a typed
 * MISCONFIGURED error carrying the friendly "API não configurada" text, so
 * the operator fixes the deploy instead of debugging connectivity.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

function setEnv(name: 'NODE_ENV' | 'NEXT_PUBLIC_API_URL', value: string | undefined): void {
  const env = process.env as Record<string, string | undefined>;
  if (value === undefined) delete env[name];
  else env[name] = value;
}

/** Load the network modules as a production bundle with no API URL. */
async function asUnconfiguredProduction<T>(
  run: (mods: {
    request: typeof import('./request');
    upload: typeof import('./upload');
    status: typeof import('./status');
  }) => T | Promise<T>,
): Promise<T> {
  const previousNode = process.env.NODE_ENV;
  const previousApi = process.env.NEXT_PUBLIC_API_URL;
  vi.resetModules();
  setEnv('NODE_ENV', 'production');
  setEnv('NEXT_PUBLIC_API_URL', undefined);
  const info = vi.spyOn(console, 'info').mockImplementation(() => {});
  try {
    return await run({
      request: await import('./request'),
      upload: await import('./upload'),
      status: await import('./status'),
    });
  } finally {
    info.mockRestore();
    setEnv('NODE_ENV', previousNode);
    setEnv('NEXT_PUBLIC_API_URL', previousApi);
    vi.resetModules();
  }
}

afterEach(() => { vi.resetModules(); });

describe('runRequest with no configured API', () => {
  it('fails immediately as MISCONFIGURED without touching the network', async () => {
    await asUnconfiguredProduction(async ({ request }) => {
      const fetchSpy = vi.fn();
      vi.stubGlobal('fetch', fetchSpy);
      try {
        const outcome = await request.runRequest('/api/v1/health', {}, { retries: 3 });
        expect(outcome.kind).toBe('error');
        if (outcome.kind !== 'error') throw new Error('expected an error');
        expect(outcome.error.type).toBe(request.NetworkErrorType.MISCONFIGURED);
        // No request, and no retry storm against an unknown origin.
        expect(fetchSpy).not.toHaveBeenCalled();
        expect(outcome.error.durationMs).toBe(0);
      } finally {
        vi.unstubAllGlobals();
      }
    });
  });

  it('explains the real cause instead of reporting a connection problem', async () => {
    await asUnconfiguredProduction(({ request }) => {
      const error = new request.NetworkError(request.NetworkErrorType.MISCONFIGURED, {
        traceId: 't', durationMs: 0,
      });
      const text = request.networkProblemText(error);
      expect(text).toContain('API não configurada');
      expect(text).toContain('NEXT_PUBLIC_API_URL');
      expect(text).not.toContain('Sem conexão');
    });
  });
});

describe('uploadWithProgress with no configured API', () => {
  it('fails as MISCONFIGURED without opening an XHR', async () => {
    await asUnconfiguredProduction(async ({ upload, request }) => {
      const open = vi.fn();
      const transportFactory = vi.fn(() => ({
        upload: { addEventListener: vi.fn() },
        addEventListener: vi.fn(),
        open,
        send: vi.fn(),
        setRequestHeader: vi.fn(),
        status: 0,
        statusText: '',
        responseText: '',
        timeout: 0,
      }));
      const outcome = await upload.runUpload(
        '/api/v1/assets/upload',
        { file: new Blob(['x']), filename: 'x.png' },
        // The factory must never be reached.
        transportFactory as never,
      );
      expect(outcome.kind).toBe('error');
      if (outcome.kind !== 'error') throw new Error('expected an error');
      expect(outcome.error.type).toBe(request.NetworkErrorType.MISCONFIGURED);
      expect(open).not.toHaveBeenCalled();
    });
  });
});

describe('the Status Center surfaces the misconfiguration', () => {
  it('maps MISCONFIGURED to its own state, outranking every other signal', async () => {
    await asUnconfiguredProduction(({ status, request }) => {
      expect(status.deriveStatus([{ errorType: request.NetworkErrorType.MISCONFIGURED }])).toBe('misconfigured');
      // It outranks even "initializing": a cold start cannot explain a
      // missing URL, and only the deploy fix helps.
      expect(status.deriveStatus([
        { errorType: request.NetworkErrorType.TIMEOUT },
        { errorType: request.NetworkErrorType.MISCONFIGURED },
      ])).toBe('misconfigured');
    });
  });

  it('labels it for a human and points at the fix, with no retry promise', async () => {
    await asUnconfiguredProduction(({ status }) => {
      const meta = status.STATUS_CENTER_META.misconfigured;
      expect(meta.label).toBe('API não configurada');
      expect(meta.action).toContain('NEXT_PUBLIC_API_URL');
      expect(meta.color).toMatch(/^#/);
    });
  });

  it('is not treated as unreachable — the network is fine', async () => {
    await asUnconfiguredProduction(({ status, request }) => {
      expect(status.isUnreachable({ errorType: request.NetworkErrorType.MISCONFIGURED })).toBe(false);
    });
  });
});
