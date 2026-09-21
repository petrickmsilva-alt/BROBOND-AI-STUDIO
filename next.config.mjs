/** @type {import('next').NextConfig} */

// Render builds with NEXT_PUBLIC_API_URL set to the separately hosted FastAPI
// service. Local development keeps using the local API. A production build
// can never silently proxy to localhost.
const apiBaseUrl = process.env.NODE_ENV === 'development'
  ? 'http://localhost:8000'
  : (process.env.NEXT_PUBLIC_API_URL || 'https://brobond-ai-api.onrender.com');
const backend = apiBaseUrl.replace(/\/$/, '');

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
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
