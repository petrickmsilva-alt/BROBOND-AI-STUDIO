/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep browser requests relative to the studio. Next proxies them to FastAPI
  // so deployments never expose localhost to browser-side code.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
