import type { MetadataRoute } from "next";
import { fetchApi, siteUrl } from "@/lib/seo";

// 全量 sitemap：静态页 + 会馆 + 帖子/文章（分页遍历 /api/v1/feed，带上限保护）。
// revalidate 1 小时；API 不可用时降级为静态路由（不影响构建与访问）。

export const revalidate = 3600;

const MAX_FEED_PAGES = 200; // 200 页 × 50 条 ≈ 10000 条内容上限（安全保护）

/** 静态文档页最近评审日期（避免每次再生都刷新 lastmod，稀释其可信度） */
const DOCS_UPDATED = new Date("2026-09-26T00:00:00.000Z");

interface FeedItemLite {
  type: "post" | "article";
  id: string;
  created_at?: string;
  updated_at?: string;
}

interface GuildLite {
  slug: string;
  created_at?: string;
}

/** 合法日期字符串 → Date；非法/缺失返回 undefined */
function toDate(v?: string): Date | undefined {
  if (!v) return undefined;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? undefined : d;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = siteUrl();
  const now = new Date();

  // 静态路由（文档类页面用固定评审日期）
  const entries: MetadataRoute.Sitemap = [
    { url: `${base}/`, lastModified: now, changeFrequency: "daily", priority: 1 },
    { url: `${base}/forum`, lastModified: now, changeFrequency: "hourly", priority: 0.9 },
    { url: `${base}/huiguan`, lastModified: now, changeFrequency: "daily", priority: 0.8 },
    { url: `${base}/WIKI`, lastModified: DOCS_UPDATED, changeFrequency: "weekly", priority: 0.6 },
    { url: `${base}/WIKI/GuanFang`, lastModified: DOCS_UPDATED, changeFrequency: "monthly", priority: 0.4 },
    { url: `${base}/WIKI/Personal`, lastModified: DOCS_UPDATED, changeFrequency: "weekly", priority: 0.5 },
    { url: `${base}/WIKI/Personal/mouse`, lastModified: DOCS_UPDATED, changeFrequency: "monthly", priority: 0.4 },
    { url: `${base}/WIKI/Personal/mouse/Liunx`, lastModified: DOCS_UPDATED, changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/WIKI/Personal/Live2D`, lastModified: DOCS_UPDATED, changeFrequency: "monthly", priority: 0.4 },
    { url: `${base}/privacy`, lastModified: DOCS_UPDATED, changeFrequency: "yearly", priority: 0.2 },
  ];

  // 会馆详情页
  const guilds = await fetchApi<{ guilds: GuildLite[] }>("/guilds", 3600);
  if (guilds.ok && Array.isArray(guilds.data?.guilds)) {
    for (const g of guilds.data.guilds) {
      if (!g?.slug) continue;
      entries.push({
        url: `${base}/huiguan/${encodeURIComponent(g.slug)}`,
        lastModified: toDate(g.created_at),
        changeFrequency: "daily",
        priority: 0.7,
      });
    }
  }

  // 帖子 / 文章（分页遍历至 has_more=false）
  for (let page = 1; page <= MAX_FEED_PAGES; page++) {
    const r = await fetchApi<{ items: FeedItemLite[]; has_more: boolean }>(
      `/feed?space=all&page=${page}&page_size=50`,
      3600
    );
    if (!r.ok || !Array.isArray(r.data?.items)) {
      // 中途失败：告警并保留已收集条目（避免静默截断无从排查）
      console.warn(`[seo] sitemap feed 第 ${page} 页拉取失败（status=${r.status}），提前结束`);
      break;
    }
    for (const it of r.data.items) {
      if (!it?.id) continue;
      const path =
        it.type === "article"
          ? `/article/${encodeURIComponent(it.id)}`
          : `/post/${encodeURIComponent(it.id)}`;
      entries.push({
        url: base + path,
        lastModified: toDate(it.updated_at) ?? toDate(it.created_at),
        changeFrequency: "weekly",
        priority: 0.6,
      });
    }
    if (!r.data.has_more) break;
  }

  return entries;
}
