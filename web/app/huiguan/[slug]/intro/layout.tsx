import type { Metadata } from "next";
import { cache } from "react";
import { fetchApi, pageMetadata, stripHtml, truncate } from "@/lib/seo";

// 会馆介绍页动态 SEO（服务端 layout：generateMetadata；功能页 noindex）。
// 会馆不存在由父级 [slug]/layout 统一处理 404，此处仅做兜底 metadata（fetch 失败不抛错）。

interface GuildIntroSeoResp {
  guild?: { name?: string; intro?: string };
  content?: string;
}

const getIntroPage = cache(async (slug: string) => {
  const r = await fetchApi<GuildIntroSeoResp>(`/api/v1/guilds/${encodeURIComponent(slug)}/intro`);
  return { ok: r.ok, data: r.data ?? null };
});

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const { ok, data } = await getIntroPage(slug);
  const name = ok && data?.guild?.name ? data.guild.name : "会馆";
  const description =
    truncate(data?.guild?.intro || "", 140) ||
    truncate(stripHtml(data?.content), 140) ||
    `${name}的会馆介绍。`;
  return pageMetadata({
    title: `${name} · 会馆介绍`,
    description,
    path: `/huiguan/${encodeURIComponent(slug)}/intro`,
    index: false,
  });
}

export default function GuildIntroLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
