/**
 * PR009.6.2.1 — the origin decision, pinned.
 *
 * The production incident: `ECONNREFUSED http://localhost:8000` on Render.
 * `ECONNREFUSED` is a Node error, so the caller was the Next.js rewrite
 * proxy — both it and this helper branched on NODE_ENV *before* reading
 * NEXT_PUBLIC_API_URL, so a service whose environment said `development`
 * sent production traffic to a localhost that nothing listens on.
 *
 * These tests fix the precedence that prevents a recurrence. The
 * regression guard is `resolves configured over a development NODE_ENV`:
 * revert the fix and that test fails.
 */
import { describe, expect, it } from 'vitest';
import {
  API_NOT_CONFIGURED_MESSAGE,
  LOCAL_API_URL,
  resolveApiBaseUrl,
} from './api-base-url';

const RENDER_API = 'https://brobond-ai-api.onrender.com';

describe('resolveApiBaseUrl — development', () => {
  it('uses the local FastAPI when nothing is configured', () => {
    const result = resolveApiBaseUrl({ NODE_ENV: 'development' }, LOCAL_API_URL);
    expect(result.baseUrl).toBe(LOCAL_API_URL);
    expect(result.baseUrl).toBe('http://localhost:8000');
    expect(result.misconfigured).toBe(false);
    expect(result.source).toBe('development');
  });

  it('still honours an explicit URL in development (pointing dev at a remote API)', () => {
    const result = resolveApiBaseUrl({
      NODE_ENV: 'development',
      NEXT_PUBLIC_API_URL: RENDER_API,
    }, LOCAL_API_URL);
    expect(result.baseUrl).toBe(RENDER_API);
    expect(result.source).toBe('configured');
  });
});

describe('resolveApiBaseUrl — production', () => {
  it('uses the configured Render API', () => {
    const result = resolveApiBaseUrl({
      NODE_ENV: 'production',
      NEXT_PUBLIC_API_URL: RENDER_API,
    });
    expect(result.baseUrl).toBe(RENDER_API);
    expect(result.misconfigured).toBe(false);
  });

  /**
   * THE REGRESSION GUARD for the reported bug. Render's Node runtime will
   * happily report NODE_ENV=development; the old ladder checked that first
   * and rewired every call to localhost:8000 → ECONNREFUSED.
   */
  it('resolves configured over a development NODE_ENV (the ECONNREFUSED bug)', () => {
    const result = resolveApiBaseUrl({
      NODE_ENV: 'development',
      NEXT_PUBLIC_API_URL: RENDER_API,
    }, LOCAL_API_URL);
    expect(result.baseUrl).toBe(RENDER_API);
    expect(result.baseUrl).not.toContain('localhost');
  });

  it('never falls back to localhost when the URL is missing', () => {
    const result = resolveApiBaseUrl({ NODE_ENV: 'production' });
    expect(result.baseUrl).toBe('');
    expect(result.baseUrl).not.toContain('localhost');
    expect(result.misconfigured).toBe(true);
    expect(result.source).toBe('missing');
  });

  it('treats a blank or whitespace-only URL as missing, not as an origin', () => {
    for (const value of ['', '   ', '\t\n']) {
      const result = resolveApiBaseUrl({ NODE_ENV: 'production', NEXT_PUBLIC_API_URL: value });
      expect(result.misconfigured).toBe(true);
      expect(result.baseUrl).toBe('');
    }
  });

  it('does not invent a hardcoded fallback host', () => {
    // A hardcoded default is how a stale URL outlives a service rename;
    // the deploy must declare its own API.
    const result = resolveApiBaseUrl({ NODE_ENV: 'production' });
    expect(result.baseUrl).not.toContain('onrender.com');
  });
});

describe('resolveApiBaseUrl — normalisation', () => {
  it('strips trailing slashes so paths do not double up', () => {
    expect(resolveApiBaseUrl({ NEXT_PUBLIC_API_URL: `${RENDER_API}/` }).baseUrl).toBe(RENDER_API);
    expect(resolveApiBaseUrl({ NEXT_PUBLIC_API_URL: `${RENDER_API}///` }).baseUrl).toBe(RENDER_API);
  });

  it('trims surrounding whitespace pasted from a dashboard', () => {
    expect(resolveApiBaseUrl({ NEXT_PUBLIC_API_URL: `  ${RENDER_API}  ` }).baseUrl).toBe(RENDER_API);
  });

  it('never emits localhost when the build stripped the dev constant', () => {
    // A production bundle compiles BUILD_LOCAL_API_URL away to ''; even a
    // stray NODE_ENV=development then cannot produce a localhost origin.
    const result = resolveApiBaseUrl({ NODE_ENV: 'development' }, '');
    expect(result.baseUrl).toBe('');
    expect(result.baseUrl).not.toContain('localhost');
  });

  it('keeps a same-origin base in test and other runtimes', () => {
    const result = resolveApiBaseUrl({ NODE_ENV: 'test' });
    expect(result.baseUrl).toBe('');
    expect(result.misconfigured).toBe(false);
    expect(result.source).toBe('same-origin');
    expect(resolveApiBaseUrl({}).source).toBe('same-origin');
  });
});

describe('the operator-facing message', () => {
  it('is the exact friendly text the sprint asks for', () => {
    expect(API_NOT_CONFIGURED_MESSAGE).toBe('API não configurada');
  });
});
