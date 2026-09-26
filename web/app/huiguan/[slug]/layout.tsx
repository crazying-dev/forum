import type { Metadata } from "next";
import { cache } from "react";
import JsonLd from "@/components/ui/JsonLd";
import { absoluteUrl, fetchApi, pageMetadata, truncate } from "@/lib/seo";

// 会馆详情动态 SEO（服务端 layout：generateMetadata + Organization JSON-LD）。

interface GuildDetailResp {
  guild?: {
    id: number;
    uuid?: string;
    slug: string;
    name: string;
    intro?: string;
    theme_color?: string;
    logo_version?: number;
    has_logo?: boolean;
    member_count?: number;
  };
}

const getGuild = cache(async (slug: string) => {
  const r = await fetchApi<GuildDetailResp>(`/api/v1/guilds/${encodeURIComponent(slug)}`);
  return { ok: r.ok, status: r.status, guild: r.data?.guild ?? null };
});

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const { ok, status, guild } = await getGuild(slug);
  if (!ok || !guild) {
    const missing = status === 404;
    return pageMetadata({
      title: missing ? "会馆不存在" : "会馆",
      description: missing ? "该会馆不存在或已被解散。" : "妖精论坛会馆详情。",
      path: `/huiguan/${encodeURIComponent(slug)}`,
      index: !missing,
    });
  }
  const description = truncate(guild.intro || "", 140) || `${guild.name} 是妖精论坛的一个会馆，欢迎加入交流。`;
  return pageMetadata({
    title: guild.name,
    description,
    path: `/huiguan/${encodeURIComponent(slug)}`,
  });
}

export default async function GuildDetailLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const { guild } = await getGuild(slug);
  return (
    <>
      {children}
      {guild && (
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "Organization",
            name: guild.name,
            description: guild.intro || undefined,
            url: absoluteUrl(`/huiguan/${guild.slug}`),
            logo: guild.has_logo && guild.uuid
              ? absoluteUrl(`/guild-img/guilds/${guild.uuid}/logo?v=${guild.logo_version || 0}`)
              : undefined,
          }}
        />
      )}
    </>
  );
}
