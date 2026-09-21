/**
 * PR009.6.2.1 — ETAPA 4: the rewrite proxy, which is what actually emitted
 * `ECONNREFUSED http://localhost:8000` in production.
 *
 * `next.config.mjs` runs in Node and is the only place that can produce a
 * Node-level connection error, so its precedence is asserted here directly
 * against the real file rather than a copy of its logic.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

const RENDER_API = 'https://brobond-ai-api.onrender.com';
const CONFIG = '../../next.config.mjs';

type Rewrite = { source: string; destination: string };

function setEnv(name: 'NODE_ENV' | 'NEXT_PUBLIC_API_URL', value: string | undefined): void {
  // `process.env` is an exotic object that rejects defineProperty; plain
  // assignment is the only way in. NODE_ENV is typed read-only by Next, so
  // the cast is confined to this one helper.
  const env = process.env as Record<string, string | undefined>;
  if (value === undefined) delete env[name];
  else env[name] = value;
}

async function rewritesUnder(env: {
  NODE_ENV?: string;
  NEXT_PUBLIC_API_URL?: string;
}): Promise<Rewrite[]> {
  const previousNode = process.env.NODE_ENV;
  const previousApi = process.env.NEXT_PUBLIC_API_URL;
  vi.resetModules();
  setEnv('NODE_ENV', env.NODE_ENV);
  setEnv('NEXT_PUBLIC_API_URL', env.NEXT_PUBLIC_API_URL);
  // The config warns on an unconfigured production build; keep it quiet.
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  try {
    const mod = await import(/* @vite-ignore */ `${CONFIG}?t=${Date.now()}`);
    return (await mod.default.rewrites()) as Rewrite[];
  } finally {
    warn.mockRestore();
    setEnv('NODE_ENV', previousNode);
    setEnv('NEXT_PUBLIC_API_URL', previousApi);
    vi.resetModules();
  }
}

afterEach(() => { vi.resetModules(); });

describe('next.config rewrites', () => {
  it('proxies to the configured API in production', async () => {
    const rewrites = await rewritesUnder({ NODE_ENV: 'production', NEXT_PUBLIC_API_URL: RENDER_API });
    expect(rewrites).toHaveLength(2);
    expect(rewrites[0]).toEqual({
      source: '/api/v1/:path*',
      destination: `${RENDER_API}/api/v1/:path*`,
    });
    expect(rewrites[1].destination).toBe(`${RENDER_API}/ws/:path*`);
  });

  /**
   * THE REGRESSION GUARD. Render can report NODE_ENV=development; the old
   * config checked that first and proxied production traffic to
   * localhost:8000, where nothing listens → ECONNREFUSED.
   */
  it('honours NEXT_PUBLIC_API_URL even when NODE_ENV says development', async () => {
    const rewrites = await rewritesUnder({ NODE_ENV: 'development', NEXT_PUBLIC_API_URL: RENDER_API });
    for (const rule of rewrites) {
      expect(rule.destination).toContain(RENDER_API);
      expect(rule.destination).not.toContain('localhost');
    }
  });

  it('proxies to the local FastAPI in development when nothing is configured', async () => {
    const rewrites = await rewritesUnder({ NODE_ENV: 'development' });
    expect(rewrites[0].destination).toBe('http://localhost:8000/api/v1/:path*');
  });

  it('registers NO proxy in production without a URL, rather than one to localhost', async () => {
    const rewrites = await rewritesUnder({ NODE_ENV: 'production' });
    expect(rewrites).toEqual([]);
    expect(JSON.stringify(rewrites)).not.toContain('localhost');
  });

  it('warns the operator when a production build has no API URL', async () => {
    const previousNode = process.env.NODE_ENV;
    const previousApi = process.env.NEXT_PUBLIC_API_URL;
    vi.resetModules();
    setEnv('NODE_ENV', 'production');
    setEnv('NEXT_PUBLIC_API_URL', undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      await import(/* @vite-ignore */ `${CONFIG}?warn=${Date.now()}`);
      expect(warn).toHaveBeenCalled();
      expect(String(warn.mock.calls[0][0])).toContain('NEXT_PUBLIC_API_URL');
    } finally {
      warn.mockRestore();
      setEnv('NODE_ENV', previousNode);
      setEnv('NEXT_PUBLIC_API_URL', previousApi);
      vi.resetModules();
    }
  });
});
