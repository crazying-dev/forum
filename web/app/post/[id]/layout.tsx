import type { Metadata } from "next";
import { cache } from "react";
import { notFound } from "next/navigation";
import JsonLd from "@/components/ui/JsonLd";
import { absoluteUrl, fetchApi, pageMetadata, stripHtml, truncate } from "@/lib/seo";

// 帖子详情动态 SEO（服务端 layout 方案：页面本体保持客户端组件不变，
// 此布局负责 generateMetadata、JSON-LD 与 404 判定）。
// 说明：React cache 在生产构建下使 metadata 与布局复用同一次拉取（dev 下可能重复一次）。

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
}

const getPost = cache(async (id: string) => {
  const r = await fetchApi<PostDetailResp>(`/api/v1/posts/${encodeURIComponent(id)}`);
  return { ok: r.ok, status: r.status, post: r.data?.post ?? null };
});

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const { ok, status, post } = await getPost(id);
  if (!ok || !post) {
    // 不存在时给出兜底标题（配合 layout 的 notFound 渲染 404 UI；流式渲染下状态码保持 200，已由 noindex 兜底）
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
  const { ok, status, post } = await getPost(id);
  // 内容不存在（HTTP 404）→ 渲染 404 页（流式渲染下状态码保持 200，由自动注入 + 兜底 noindex 防收录）；临时故障不触发（避免误伤）
  if (!ok && status === 404) notFound();
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
