/** @type {import('next').NextConfig} */

// The browser must never be told to reach a hard-coded origin. Everything under
// /api/v1 is proxied to the FastAPI backend, so the UI can use relative URLs and
// work unchanged behind any host — a laptop, a container, or a preview proxy.
// Before this, `lib/api.ts` defaulted to http://localhost:8000, which only works
// when the browser happens to be on the same machine as the API.
const backend = process.env.BROBOND_API_PROXY_TARGET ?? 'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backend}/api/v1/:path*`,
      },
      // PR008: the render progress socket speaks the same relative language —
      // the browser opens /ws/render/{batch_id} on its own origin.
      {
        source: '/ws/:path*',
        destination: `${backend}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
