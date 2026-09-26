import type { NextConfig } from "next";

const API_TARGET = process.env.API_TARGET || "http://127.0.0.1:8090";
// 会馆 logo 等图片资源由管理端提供（/guild-img/* → {ADMIN_TARGET}/api/*）
const ADMIN_TARGET = process.env.ADMIN_TARGET || "http://127.0.0.1:8080";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.1.19"],
  reactStrictMode: true,
  images: {
    unoptimized: true, // 本地资源全部走 public/，无需服务端优化
  },
  async rewrites() {
    // 开发环境：浏览器与 Next 同源，/api/* 代理到 Go 后端（生产由 Nginx 分域，此规则仍可复用）
    return [
      {
        source: "/api/:path*",
        destination: `${API_TARGET}/api/:path*`,
      },
      {
        // 会馆 logo 图片代理：/guild-img/guilds/{id}/logo → 管理端 /api/guilds/{id}/logo
        source: "/guild-img/:path*",
        destination: `${ADMIN_TARGET}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
