/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const apiUrl = process.env.API_PROXY_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8002";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`
      },
      {
        source: "/uploads/:path*",
        destination: `${apiUrl}/uploads/:path*`
      }
    ];
  }
};

export default nextConfig;
