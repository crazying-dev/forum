import type { Metadata } from "next";
import { cache } from "react";
import { notFound } from "next/navigation";
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
    const title = missing ? "会馆不存在" : "会馆";
    return {
      ...pageMetadata({
        title,
        description: missing ? "该会馆不存在或已被解散。" : "妖精论坛会馆详情。",
        path: `/huiguan/${encodeURIComponent(slug)}`,
        index: !missing,
      }),
      // 显式携带模板：子段（成员名单/馆长介绍）为字符串标题时仍保留「妖精论坛 - 」前缀
      title: { default: title, template: "妖精论坛 - %s" },
    };
  }
  const description = truncate(guild.intro || "", 140) || `${guild.name} 是妖精论坛的一个会馆，欢迎加入交流。`;
  return {
    ...pageMetadata({
      title: guild.name,
      description,
      path: `/huiguan/${encodeURIComponent(slug)}`,
    }),
    // 同上：保留前缀模板给更深层的动态页
    title: { default: guild.name, template: "妖精论坛 - %s" },
  };
}

export default async function GuildDetailLayout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const { ok, status, guild } = await getGuild(slug);
  // 会馆不存在（HTTP 404）→ 渲染 404 页（流式渲染下状态码保持 200，由自动注入 + 兜底 noindex 防收录）；临时故障不触发（避免误伤）
  if (!ok && status === 404) notFound();
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
