import type { Metadata } from "next";
import { cache } from "react";
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
  const r = await fetchApi<UserProfileResp>(`/api/v1/users/${encodeURIComponent(id)}`);
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
  const { user } = await getUser(id);
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
