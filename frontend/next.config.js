/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: ["puppeteer-core"],
  },
  async rewrites() {
    return {
      afterFiles: [
        {
          source: "/api/:path*",
          destination: `${process.env.BACKEND_URL || "http://localhost:8001"}/api/:path*`,
        },
      ],
    };
  },
};

module.exports = nextConfig;
