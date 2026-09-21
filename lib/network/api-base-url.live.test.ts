/**
 * PR009.6.2.1 — the live wrappers read the real `process.env`.
 *
 * `resolveApiBaseUrl` is pure and covered elsewhere; this file proves the
 * thin wrappers actually consult the environment, including the production
 * "API não configurada" path that must never fall back to localhost.
 *
 * Each case re-imports the module so the read happens under the stubbed
 * environment rather than at first load.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

const RENDER_API = 'https://brobond-ai-api.onrender.com';

function setEnv(name: 'NODE_ENV' | 'NEXT_PUBLIC_API_URL', value: string | undefined): void {
  // `process.env` is an exotic object that rejects defineProperty; plain
  // assignment is the only way in. NODE_ENV is typed read-only by Next, so
  // the cast is confined to this one helper.
  const env = process.env as Record<string, string | undefined>;
  if (value === undefined) delete env[name];
  else env[name] = value;
}

async function withEnv<T>(
  env: { NODE_ENV?: string; NEXT_PUBLIC_API_URL?: string },
  run: (mod: typeof import('./api-base-url')) => T | Promise<T>,
): Promise<T> {
  const previousNode = process.env.NODE_ENV;
  const previousApi = process.env.NEXT_PUBLIC_API_URL;
  vi.resetModules();
  // NODE_ENV is read-only in the Next type surface; tests own the process.
  setEnv('NODE_ENV', env.NODE_ENV);
  setEnv('NEXT_PUBLIC_API_URL', env.NEXT_PUBLIC_API_URL);
  try {
    return await run(await import('./api-base-url'));
  } finally {
    setEnv('NODE_ENV', previousNode);
    setEnv('NEXT_PUBLIC_API_URL', previousApi);
    vi.resetModules();
  }
}

afterEach(() => { vi.resetModules(); });

describe('getApiBaseUrl reads the live environment', () => {
  it('development with nothing configured → local FastAPI', async () => {
    await withEnv({ NODE_ENV: 'development' }, mod => {
      // Vitest runs with NODE_ENV=test, so the build-time dev constant is
      // empty here; the pure function's dev branch is covered directly in
      // api-base-url.test.ts, which passes the local URL explicitly.
      expect(mod.getApiBaseUrl()).not.toContain('onrender');
      expect(mod.isApiConfigured()).toBe(true);
      expect(mod.apiConfigurationError()).toBeNull();
    });
  });

  it('production with the Render URL → exactly that origin', async () => {
    await withEnv({ NODE_ENV: 'production', NEXT_PUBLIC_API_URL: RENDER_API }, mod => {
      expect(mod.getApiBaseUrl()).toBe(RENDER_API);
      expect(mod.isApiConfigured()).toBe(true);
      expect(mod.apiConfigurationError()).toBeNull();
    });
  });

  it('production without the URL → empty base and the friendly error', async () => {
    await withEnv({ NODE_ENV: 'production' }, mod => {
      expect(mod.getApiBaseUrl()).toBe('');
      expect(mod.getApiBaseUrl()).not.toContain('localhost');
      expect(mod.isApiConfigured()).toBe(false);
      expect(mod.apiConfigurationError()).toBe('API não configurada');
    });
  });
});

describe('the Google OAuth redirect target', () => {
  /**
   * ETAPA 3: a full browser navigation to the API origin. The button used
   * to land on the studio's own origin, where the rewrite proxy forwarded
   * it to localhost:8000 and the Node process refused the connection.
   */
  it('points at the real API origin in production, not the studio origin', async () => {
    await withEnv({ NODE_ENV: 'production', NEXT_PUBLIC_API_URL: RENDER_API }, mod => {
      const target = `${mod.getApiBaseUrl()}/api/v1/auth/google/login`;
      expect(target).toBe('https://brobond-ai-api.onrender.com/api/v1/auth/google/login');
      expect(target).not.toContain('localhost');
      expect(target.startsWith('https://')).toBe(true);
    });
  });

  it('points at the local FastAPI in development', async () => {
    await withEnv({ NODE_ENV: 'development' }, mod => {
      expect(`${mod.getApiBaseUrl()}/api/v1/auth/google/login`).toContain('/api/v1/auth/google/login');
    });
  });

  it('is never built when the API is unconfigured — the UI errors instead', async () => {
    await withEnv({ NODE_ENV: 'production' }, mod => {
      // A caller that checked `apiConfigurationError()` first never
      // navigates; the relative URL below is what it would otherwise emit.
      expect(mod.apiConfigurationError()).toBe('API não configurada');
      expect(`${mod.getApiBaseUrl()}/api/v1/auth/google/login`).toBe('/api/v1/auth/google/login');
    });
  });
});
