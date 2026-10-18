import type { Metadata } from "next";
import { cache } from "react";
import { fetchApi, pageMetadata, stripHtml, truncate } from "@/lib/seo";

// 会馆馆长介绍页动态 SEO（服务端 layout：generateMetadata；功能页 noindex）。
// 会馆不存在由父级 [slug]/layout 统一处理 404，此处仅做兜底 metadata（fetch 失败不抛错）。

interface GuildLeaderSeoResp {
  guild?: { name?: string };
  leader?: { name?: string } | null;
  leader_bio?: string;
  content?: string;
}

const getLeaderPage = cache(async (slug: string) => {
  const r = await fetchApi<GuildLeaderSeoResp>(`/guilds/${encodeURIComponent(slug)}/leader`);
  return { ok: r.ok, data: r.data ?? null };
});

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const { ok, data } = await getLeaderPage(slug);
  const guildName = ok && data?.guild?.name ? data.guild.name : "会馆";
  const leaderName = ok && data?.leader?.name ? data.leader.name : "";
  const title = leaderName ? `${leaderName} · ${guildName} 馆长介绍` : `${guildName} · 馆长介绍`;
  const description =
    truncate(data?.leader_bio || "", 140) ||
    truncate(stripHtml(data?.content), 140) ||
    `${guildName}的馆长介绍与寄语。`;
  return pageMetadata({
    title,
    description,
    path: `/huiguan/${encodeURIComponent(slug)}/leader`,
    index: false,
  });
}

export default function GuildLeaderLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
