/**
 * PR009.6.2.1 — the single origin decision of the frontend.
 *
 * The production incident this file fixes:
 *
 *   ECONNREFUSED http://localhost:8000
 *
 * `ECONNREFUSED` is a *Node* error, not a browser one — a browser reports a
 * blocked request as a TypeError. So the failing caller was the Next.js
 * server itself: the rewrite proxy in `next.config.mjs`, forwarding
 * `/api/v1/*` to `http://localhost:8000`, where nothing listens inside a
 * Render web service. Both this helper and that config picked their target
 * by branching on `NODE_ENV` *before* looking at `NEXT_PUBLIC_API_URL`, so
 * any deploy whose environment says `development` (Render's Node runtime
 * happily accepts one) silently rewired production traffic to localhost.
 *
 * The rule inverted here, and mirrored byte for byte in `next.config.mjs`:
 *
 *   1. an explicitly configured NEXT_PUBLIC_API_URL always wins — it is a
 *      deliberate operator decision, and no NODE_ENV may override it;
 *   2. only with nothing configured does `development` mean localhost;
 *   3. in production with nothing configured we refuse to guess: the base
 *      stays empty and `apiConfigurationError()` explains why. Falling back
 *      to localhost is exactly the bug, and falling back to a hardcoded
 *      Render URL is how a stale host survives a rename — the deploy is
 *      misconfigured and must say so.
 *   4. every other runtime (unit tests, SSR probes) keeps a same-origin
 *      base, as before.
 *
 * Nothing here touches JWT, the e-mail/password flow, PostgreSQL, users,
 * routes or the API contract: this is the communication layer only.
 */

/** Where FastAPI listens when you run it next to the studio. */
export const LOCAL_API_URL = 'http://localhost:8000';

/**
 * The dev fallback as the *bundler* sees it.
 *
 * Next inlines `process.env.NODE_ENV` at build time, so in a production
 * bundle this collapses to `''` and webpack drops the localhost literal
 * entirely — the DoD's "zero localhost in production" is then a property
 * of the artifact, verifiable with grep, not just of the control flow.
 * `resolveApiBaseUrl` stays pure by taking this as a defaulted argument.
 */
export const BUILD_LOCAL_API_URL = process.env.NODE_ENV === 'development' ? LOCAL_API_URL : '';

/** The friendly text a misconfigured production deploy shows (ETAPA 5). */
export const API_NOT_CONFIGURED_MESSAGE = 'API não configurada';

/** The environment slice the resolution depends on — passed in, so the
 *  decision is a pure function and every branch is testable. */
export type ApiEnv = {
  NODE_ENV?: string;
  NEXT_PUBLIC_API_URL?: string;
};

export type ApiBaseResolution = {
  /** The origin every request is prefixed with ('' means same-origin). */
  baseUrl: string;
  /** True when a production bundle has no API URL configured. */
  misconfigured: boolean;
  /** Which rule decided — useful in logs and in the tests. */
  source: 'configured' | 'development' | 'missing' | 'same-origin';
};

/** Trailing slashes would double up against paths that start with `/`. */
function normalize(url: string): string {
  return url.trim().replace(/\/+$/, '');
}

/**
 * The whole decision, as a pure function over the environment.
 *
 * Exported so `next.config.mjs`'s mirror and the test suite can assert the
 * exact same precedence instead of re-deriving it.
 */
export function resolveApiBaseUrl(
  env: ApiEnv,
  localApiUrl: string = BUILD_LOCAL_API_URL,
): ApiBaseResolution {
  // 1. An explicit configuration always wins — including when NODE_ENV
  //    wrongly says "development" inside a Render service.
  const configured = normalize(env.NEXT_PUBLIC_API_URL ?? '');
  if (configured) return { baseUrl: configured, misconfigured: false, source: 'configured' };

  // 2. Local development, with nothing configured: the local FastAPI.
  if (env.NODE_ENV === 'development' && localApiUrl) {
    return { baseUrl: localApiUrl, misconfigured: false, source: 'development' };
  }

  // 3. Production with nothing configured: refuse to invent an origin.
  if (env.NODE_ENV === 'production') {
    return { baseUrl: '', misconfigured: true, source: 'missing' };
  }

  // 4. Unit tests and other non-browser runtimes: same-origin.
  return { baseUrl: '', misconfigured: false, source: 'same-origin' };
}

/**
 * Read the live environment. `process.env.NEXT_PUBLIC_*` is inlined by Next
 * at build time, so this must stay a literal member access — destructuring
 * or dynamic keys would leave it `undefined` in the browser bundle.
 */
function currentEnv(): ApiEnv {
  return {
    NODE_ENV: process.env.NODE_ENV,
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  };
}

/** The public origin every browser request, upload and redirect uses. */
export function getApiBaseUrl(): string {
  return resolveApiBaseUrl(currentEnv()).baseUrl;
}

/** False only when a production bundle shipped without NEXT_PUBLIC_API_URL. */
export function isApiConfigured(): boolean {
  return !resolveApiBaseUrl(currentEnv()).misconfigured;
}

/**
 * The friendly message for a misconfigured deploy, or `null` when the
 * origin is known. Callers render this instead of firing a request that
 * could only fail.
 */
export function apiConfigurationError(): string | null {
  return resolveApiBaseUrl(currentEnv()).misconfigured ? API_NOT_CONFIGURED_MESSAGE : null;
}
