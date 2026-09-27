import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/vision/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
      {
        source: "/video",
        destination: "http://127.0.0.1:8000/video",
      },
    ];
  },
};

export default nextConfig;
