import type { Metadata } from "next";

// ===== 服务端 SEO 工具（仅服务端组件 / generateMetadata / sitemap 使用）=====
// 注意：本文件不要 import "@/lib/api"——后者是客户端模块（"use client"）；
// 此处独立实现服务端轻量拉取，保证 fetch 语义与缓存配置不被客户端 bundle 影响。

const SITE_FALLBACK = "https://yjlt.top";

/**
 * 站点规范域名：SITE_URL → NEXT_PUBLIC_SITE_URL → https://yjlt.top。
 * - 非法值（如缺 http(s)://）安全回退，避免 new URL() 抛错导致全站 500；
 * - 注意：预渲染路由（首页/静态页/robots.txt）在构建期固化该值，动态详情页与 sitemap 在运行期读取。
 */
export function siteUrl(): string {
  const raw = (process.env.SITE_URL || process.env.NEXT_PUBLIC_SITE_URL || SITE_FALLBACK).trim();
  try {
    return new URL(raw).origin;
  } catch {
    console.warn(`[seo] 站点域名非法（需含 http(s)://）：${raw}，已回退 ${SITE_FALLBACK}`);
    return SITE_FALLBACK;
  }
}

/** 相对路径转绝对 URL（已是绝对 URL 时原样返回） */
export function absoluteUrl(pathOrUrl: string): string {
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  return siteUrl() + (pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`);
}

/** 后端 API 地址：与 next.config.ts rewrites 的 API_TARGET 同一约定（默认本地 8090） */
function apiBase(): string {
  return (process.env.API_TARGET || "http://127.0.0.1:8090").replace(/\/+$/, "") + "/ov2/api";
}

export interface ApiFetchResult<T> {
  ok: boolean;
  status: number;
  data: T | null;
}

export interface FetchApiOptions {
  /** 透传请求头（如转发浏览器 Cookie：服务端才能识别作者本人视角） */
  headers?: Record<string, string>;
  /** true = no-store（依赖 viewer 的请求，不得按 URL 共享缓存） */
  noStore?: boolean;
}

/**
 * 服务端拉取论坛 API（永不抛错，失败返回 ok:false）。
 * 用于 generateMetadata / layout 内 JSON-LD / sitemap；revalidate 默认 300s。
 * options.noStore=true 时强制 no-store；headers 带 Cookie 时同样强制 no-store
 * （个性化响应不得按 URL 共享缓存，即使调用方遗漏 noStore）。
 */
export async function fetchApi<T = unknown>(
  path: string,
  revalidate = 300,
  options: FetchApiOptions = {}
): Promise<ApiFetchResult<T>> {
  try {
    // 仅带 Cookie 的个性化请求降级 no-store；无 Cookie（匿名/爬虫）保持 revalidate 共享缓存
    const personalized = options.noStore === true || !!options.headers?.Cookie;
    const res = await fetch(apiBase() + path, {
      ...(personalized ? { cache: "no-store" as const } : { next: { revalidate } }),
      headers: { Accept: "application/json", ...(options.headers || {}) },
      // 超时保护：上游挂起时不拖住页面渲染 / sitemap 生成（Node fetch 默认超时为分钟级）
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) {
      console.warn(`[seo] fetchApi ${path} 返回 HTTP ${res.status}`);
      return { ok: false, status: res.status, data: null };
    }
    const data = (await res.json().catch(() => null)) as (T & { success?: boolean }) | null;
    if (!data || data.success === false) {
      console.warn(`[seo] fetchApi ${path} 响应无效或 success=false`);
      return { ok: false, status: res.status, data: null };
    }
    return { ok: true, status: res.status, data };
  } catch (e) {
    console.warn(`[seo] fetchApi ${path} 失败：${e instanceof Error ? e.message : String(e)}`);
    return { ok: false, status: 0, data: null };
  }
}

const HTML_ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#39;": "'",
  "&nbsp;": " ",
};

/** 去除 HTML 标签、解码常见实体并压缩空白（生成 description 用） */
export function stripHtml(input?: string | null): string {
  return (input || "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&(?:amp|lt|gt|quot|#39|nbsp);/g, (m) => HTML_ENTITIES[m] ?? m)
    .replace(/\s+/g, " ")
    .trim();
}

/** 截断到 max 个字符（按码点，避免截断 emoji 代理对；超长补省略号），默认 140 */
export function truncate(input: string, max = 140): string {
  const s = (input || "").trim();
  const chars = Array.from(s);
  return chars.length > max ? `${chars.slice(0, max - 1).join("")}…` : s;
}

// ===== 共享 metadata 片段 =====
// Next.js metadata 为「浅合并」：子段定义 openGraph/twitter 会整体覆盖父段，
// 故页面级 metadata 统一经 pageMetadata() 构造，保证站点名/语言/默认分享图不丢失。

export const OG_IMAGE = { url: "/og-image.png", width: 1200, height: 630, alt: "妖精论坛 - 罗小黑战记同人社区" };

/** 站点级默认标题（首页 / 兜底）与描述 */
export const SITE_TITLE = "妖精论坛 - 罗小黑战记同人社区";
export const SITE_DESCRIPTION = "妖精论坛是《罗小黑战记》同人社区：分享帖子、加入会馆、浏览 Wiki 与同人创作。";

export interface PageSeoOptions {
  /** 裸标题（不含站点名；根 layout 的 title 模板会补「妖精论坛 - 」前缀） */
  title: string;
  description: string;
  /** 以 / 开头的站内路径（用于 canonical 与 og:url） */
  path: string;
  type?: "website" | "article";
  publishedTime?: string;
  authors?: string[];
  /** false 时输出 noindex（功能页） */
  index?: boolean;
}

/** 页面级 metadata（title/description/canonical/robots + OG/Twitter 一站式） */
export function pageMetadata(opts: PageSeoOptions): Metadata {
  const openGraph: NonNullable<Metadata["openGraph"]> =
    opts.type === "article"
      ? {
          type: "article",
          siteName: "妖精论坛",
          locale: "zh_CN",
          images: [OG_IMAGE],
          title: opts.title,
          description: opts.description,
          url: opts.path,
          publishedTime: opts.publishedTime,
          authors: opts.authors,
        }
      : {
          type: "website",
          siteName: "妖精论坛",
          locale: "zh_CN",
          images: [OG_IMAGE],
          title: opts.title,
          description: opts.description,
          url: opts.path,
        };
  return {
    title: opts.title,
    description: opts.description,
    alternates: { canonical: opts.path },
    // 仅功能页输出 noindex；常规页不输出 robots（默认即 index/follow），
    // 避免 404 页出现「自动 noindex 与继承 robots」冲突的双标签
    ...(opts.index === false ? { robots: { index: false, follow: true } } : {}),
    openGraph,
    twitter: {
      card: "summary_large_image",
      title: opts.title,
      description: opts.description,
      images: [{ url: OG_IMAGE.url, alt: OG_IMAGE.alt }],
    },
  };
}
