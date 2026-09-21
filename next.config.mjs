/** @type {import('next').NextConfig} */

/**
 * PR009.6.2.1 — the rewrite proxy that caused `ECONNREFUSED localhost:8000`.
 *
 * This file is the Node side of the same decision `lib/network/api-base-url.ts`
 * makes for the browser, and it must agree with it exactly:
 *
 *   1. NEXT_PUBLIC_API_URL always wins, whatever NODE_ENV claims;
 *   2. only with nothing configured does `development` mean localhost;
 *   3. in production with nothing configured there is NO proxy at all —
 *      registering one pointed at localhost is precisely the bug, and a
 *      hardcoded fallback host is how a stale URL outlives a rename.
 *      With the rewrite absent, `/api/v1/*` 404s honestly instead of the
 *      server burning 10s per request on a connection nobody will accept.
 *
 * The old code branched on NODE_ENV *first*, so a Render service whose
 * environment said `development` rewrote every API call to localhost —
 * where no FastAPI listens inside that container.
 */

const configuredApiUrl = (process.env.NEXT_PUBLIC_API_URL ?? '').trim().replace(/\/+$/, '');
const isDevelopment = process.env.NODE_ENV === 'development';

// The proxy target, or null when we must not proxy at all.
const backend = configuredApiUrl || (isDevelopment ? 'http://localhost:8000' : null);

if (!backend) {
  // Loud at build/boot time, because the browser can only report the
  // symptom. The build still succeeds: the app renders and says
  // "API não configurada" instead of failing opaquely.
  console.warn(
    '[brobond] NEXT_PUBLIC_API_URL is not set — no /api/v1 proxy will be registered. ' +
      'Set it on the Render web service (e.g. https://brobond-ai-api.onrender.com).',
  );
}

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (!backend) return [];
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backend}/api/v1/:path*`,
      },
      {
        source: '/ws/:path*',
        destination: `${backend}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
