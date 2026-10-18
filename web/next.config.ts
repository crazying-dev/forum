import type { NextConfig } from "next";

const API_TARGET = process.env.API_TARGET || "http://127.0.0.1:8090";
// 会馆图片资源（logo、馆长介绍页图片、会馆介绍页封面与正文图片）由管理端提供（/guild-img/* → {ADMIN_TARGET}/api/*）
const ADMIN_TARGET = process.env.ADMIN_TARGET || "http://127.0.0.1:8080";

// HTML-limited bots：命中名单的 UA 会等待元数据解析完成后再发包（阻塞式渲染），
// 确保 title/og:* 标签稳定出现在 <head>。默认的流式元数据在冷缓存场景可能把标签
// 追加到 <body>（实测：微信爬虫冷请求命中过该竞态），会导致微信/QQ 分享卡片解析失败。
// 名单 = Next.js 运行时默认值（next/dist/shared/lib/router/utils/html-bots.js）
// + 中文社交爬虫 / 微信内置浏览器（MicroMessenger / WeChat / QQ / Weibo / Bytespider）。
const htmlLimitedBots =
  /[\w-]+-Google|Google-[\w-]+|Chrome-Lighthouse|Slurp|DuckDuckBot|baiduspider|yandex|sogou|bitlybot|tumblr|vkShare|quora link preview|redditbot|ia_archiver|Bingbot|BingPreview|applebot|facebookexternalhit|facebookcatalog|Twitterbot|LinkedInBot|Slackbot|Discordbot|WhatsApp|SkypeUriPreview|Yeti|googleweblight|MicroMessenger|WeChat|QQ\/|Weibo|Bytespider|BytedanceBot/i;

const nextConfig: NextConfig = {
  htmlLimitedBots,
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.1.19"],
  reactStrictMode: true,
  images: {
    unoptimized: true, // 本地资源全部走 public/，无需服务端优化
  },
  async rewrites() {
    // 开发环境：浏览器与 Next 同源，/api/* 代理到 Go 后端（生产由 Nginx 分域，此规则仍可复用）
    return [
      {
        // 新 API（canonical）：浏览器同源请求 /ov2/api/* → Go 后端
        source: "/ov2/api/:path*",
        destination: `${API_TARGET}/ov2/api/:path*`,
      },
      {
        // 旧兼容层 + /api/v1 别名
        source: "/api/:path*",
        destination: `${API_TARGET}/api/:path*`,
      },
      {
        // 旧头像兼容：/avatar/<uuid>.webp → Go 后端（生产由 Nginx 分发）
        source: "/avatar/:path*",
        destination: `${API_TARGET}/avatar/:path*`,
      },
      {
        // 会馆图片代理：/guild-img/guilds/{uuid}/logo（logo）、/guild-img/guilds/{uuid}/leader-images/{fileId}（馆长介绍页图片）、/guild-img/guilds/{uuid}/intro-images/{fileId}（会馆介绍页封面/正文图片）→ 管理端 /api/*
        source: "/guild-img/:path*",
        destination: `${ADMIN_TARGET}/api/:path*`,
      },
      {
        // 论坛指南正文图片代理：/guide-img/* → 管理端 /api/*（与 /guild-img 同模式）
        source: "/guide-img/:path*",
        destination: `${ADMIN_TARGET}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
