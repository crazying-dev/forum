import type { Metadata } from "next";
import { cache } from "react";
import { fetchApi, pageMetadata } from "@/lib/seo";

// 会馆成员名单动态 SEO（服务端 layout：generateMetadata；功能页 noindex）。
// 会馆不存在由父级 [slug]/layout 统一处理 404，此处仅做兜底 metadata（fetch 失败不抛错）。

interface GuildMembersSeoResp {
  guild?: { name?: string };
}

const getGuild = cache(async (slug: string) => {
  const r = await fetchApi<GuildMembersSeoResp>(`/api/v1/guilds/${encodeURIComponent(slug)}`);
  return { ok: r.ok, guild: r.data?.guild ?? null };
});

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const { ok, guild } = await getGuild(slug);
  const name = ok && guild?.name ? guild.name : "会馆";
  return pageMetadata({
    title: `${name} · 成员名单`,
    description: `${name}的成员名单：查看馆长与全部成员。`,
    path: `/huiguan/${encodeURIComponent(slug)}/members`,
    index: false,
  });
}

export default function GuildMembersLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
