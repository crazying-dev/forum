import type { Metadata } from "next";
import { cache } from "react";
import JsonLd from "@/components/ui/JsonLd";
import { absoluteUrl, fetchApi, pageMetadata, stripHtml, truncate } from "@/lib/seo";

// 帖子详情动态 SEO（服务端 layout 方案：页面本体保持客户端组件不变，
// 此布局仅负责 generateMetadata 与 JSON-LD；React cache 让两者同请求只拉取一次数据）。

interface PostDetailResp {
  post?: {
    id: string;
    user_id?: string;
    title: string;
    content?: string;
    summary?: string;
    created_at?: string;
    updated_at?: string;
    user_name?: string;
    user_avatar?: string;
  };
  comments?: unknown[];
}

const getPost = cache(async (id: string) => {
  const r = await fetchApi<PostDetailResp>(`/api/v1/posts/${encodeURIComponent(id)}`);
  return { ok: r.ok, status: r.status, post: r.data?.post ?? null, commentCount: r.data?.comments?.length ?? 0 };
});

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const { ok, status, post } = await getPost(id);
  if (!ok || !post) {
    const missing = status === 404;
    return pageMetadata({
      title: missing ? "帖子不存在" : "帖子",
      description: missing ? "该帖子不存在或已被删除。" : "妖精论坛帖子详情。",
      path: `/post/${encodeURIComponent(id)}`,
      index: !missing,
    });
  }
  const description = truncate(stripHtml(post.summary || post.content), 140) || `妖精论坛帖子：${post.title}`;
  return pageMetadata({
    title: post.title,
    description,
    path: `/post/${encodeURIComponent(id)}`,
    type: "article",
    publishedTime: post.created_at,
    authors: post.user_name ? [post.user_name] : undefined,
  });
}

export default async function PostDetailLayout({ children, params }: { children: React.ReactNode; params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { post, commentCount } = await getPost(id);
  return (
    <>
      {children}
      {post && (
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "DiscussionForumPosting",
            headline: post.title,
            url: absoluteUrl(`/post/${post.id}`),
            datePublished: post.created_at,
            dateModified: post.updated_at,
            commentCount,
            author: post.user_name
              ? {
                  "@type": "Person",
                  name: post.user_name,
                  url: post.user_id ? absoluteUrl(`/users/${post.user_id}`) : undefined,
                }
              : undefined,
            image: post.user_avatar ? absoluteUrl(post.user_avatar) : undefined,
          }}
        />
      )}
    </>
  );
}
