import type { Metadata } from "next";

// ===== 服务端 SEO 工具（仅服务端组件 / generateMetadata / sitemap 使用）=====
// 注意：本文件不要 import "@/lib/api"——后者是客户端模块（"use client"）；
// 此处独立实现服务端轻量拉取，保证 fetch 语义与缓存配置不被客户端 bundle 影响。

const SITE_FALLBACK = "https://yjlt.top";

/** 站点规范域名：SITE_URL → NEXT_PUBLIC_SITE_URL → https://yjlt.top（去尾斜杠） */
export function siteUrl(): string {
  return (process.env.SITE_URL || process.env.NEXT_PUBLIC_SITE_URL || SITE_FALLBACK).replace(/\/+$/, "");
}

/** 相对路径转绝对 URL（已是绝对 URL 时原样返回） */
export function absoluteUrl(pathOrUrl: string): string {
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  return siteUrl() + (pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`);
}

/** 后端 API 地址：与 next.config.ts rewrites 的 API_TARGET 同一约定（默认本地 8090） */
function apiBase(): string {
  return (process.env.API_TARGET || "http://127.0.0.1:8090").replace(/\/+$/, "");
}

export interface ApiFetchResult<T> {
  ok: boolean;
  status: number;
  data: T | null;
}

/**
 * 服务端拉取论坛 API（永不抛错，失败返回 ok:false）。
 * 用于 generateMetadata / layout 内 JSON-LD / sitemap；revalidate 默认 300s。
 */
export async function fetchApi<T = unknown>(path: string, revalidate = 300): Promise<ApiFetchResult<T>> {
  try {
    const res = await fetch(apiBase() + path, {
      next: { revalidate },
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return { ok: false, status: res.status, data: null };
    const data = (await res.json().catch(() => null)) as (T & { success?: boolean }) | null;
    if (!data || data.success === false) return { ok: false, status: res.status, data: null };
    return { ok: true, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: null };
  }
}

/** 去除 HTML 标签并压缩空白（生成 description 用） */
export function stripHtml(input?: string | null): string {
  return (input || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

/** 截断到 max 字符（超长补省略号），默认 140 */
export function truncate(input: string, max = 140): string {
  const s = (input || "").trim();
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
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
      images: [OG_IMAGE.url],
    },
  };
}
