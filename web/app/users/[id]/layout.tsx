import type { Metadata } from "next";
import { cache } from "react";
import { notFound } from "next/navigation";
import JsonLd from "@/components/ui/JsonLd";
import { absoluteUrl, fetchApi, pageMetadata, truncate } from "@/lib/seo";

// 用户主页动态 SEO（服务端 layout：generateMetadata + ProfilePage JSON-LD）。

interface UserProfileResp {
  user?: {
    id: string;
    name: string;
    avatar?: string;
    intro?: string;
    created_at?: string;
  };
}

const getUser = cache(async (id: string) => {
  const r = await fetchApi<UserProfileResp>(`/users/${encodeURIComponent(id)}`);
  return { ok: r.ok, status: r.status, user: r.data?.user ?? null };
});

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const { ok, status, user } = await getUser(id);
  if (!ok || !user) {
    const missing = status === 404;
    return pageMetadata({
      title: missing ? "用户不存在" : "用户",
      description: missing ? "该用户不存在或已注销。" : "妖精论坛用户主页。",
      path: `/users/${encodeURIComponent(id)}`,
      index: !missing,
    });
  }
  const description = truncate(user.intro || "", 140) || `${user.name} 在妖精论坛的个人主页：帖子、评论与关注。`;
  return pageMetadata({
    title: `${user.name} 的主页`,
    description,
    path: `/users/${encodeURIComponent(id)}`,
  });
}

export default async function UserProfileLayout({ children, params }: { children: React.ReactNode; params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { ok, status, user } = await getUser(id);
  // 用户不存在（HTTP 404）→ 渲染 404 页（流式渲染下状态码保持 200，由自动注入 + 兜底 noindex 防收录）；临时故障不触发（避免误伤）
  if (!ok && status === 404) notFound();
  return (
    <>
      {children}
      {user && (
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "ProfilePage",
            mainEntity: {
              "@type": "Person",
              name: user.name,
              description: user.intro || undefined,
              image: user.avatar ? absoluteUrl(user.avatar) : undefined,
              url: absoluteUrl(`/users/${user.id}`),
            },
          }}
        />
      )}
    </>
  );
}
