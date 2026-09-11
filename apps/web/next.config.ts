import type { NextConfig } from "next";

const apiOrigin = process.env.VEDIOGEN_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  distDir: process.env.VEDIOGEN_NEXT_DIST_DIR ?? ".next",
  // Synchronous GPT endpoints can outlast Next's default 30-second proxy timeout.
  experimental: { proxyTimeout: 650_000 },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiOrigin}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
