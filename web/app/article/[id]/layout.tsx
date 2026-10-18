import type { Metadata } from "next";
import { cache } from "react";
import { notFound } from "next/navigation";
import JsonLd from "@/components/ui/JsonLd";
import { absoluteUrl, fetchApi, pageMetadata, siteUrl, stripHtml, truncate } from "@/lib/seo";

// 会馆文章详情动态 SEO（服务端 layout：generateMetadata + Article JSON-LD）。

interface ArticleDetailResp {
  article?: {
    id: string;
    title: string;
    summary?: string;
    content?: string;
    created_at?: string;
    updated_at?: string;
    author?: { id: string; name: string; avatar?: string } | null;
  };
}

const getArticle = cache(async (id: string) => {
  const r = await fetchApi<ArticleDetailResp>(`/articles/${encodeURIComponent(id)}`);
  return { ok: r.ok, status: r.status, article: r.data?.article ?? null };
});

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const { ok, status, article } = await getArticle(id);
  if (!ok || !article) {
    const missing = status === 404;
    return pageMetadata({
      title: missing ? "文章不存在" : "文章",
      description: missing ? "该文章不存在或已被删除。" : "妖精论坛会馆文章详情。",
      path: `/article/${encodeURIComponent(id)}`,
      index: !missing,
    });
  }
  const description = truncate(stripHtml(article.summary || article.content), 140) || `妖精论坛文章：${article.title}`;
  return pageMetadata({
    title: article.title,
    description,
    path: `/article/${encodeURIComponent(id)}`,
    type: "article",
    publishedTime: article.created_at,
    authors: article.author?.name ? [article.author.name] : undefined,
  });
}

export default async function ArticleDetailLayout({ children, params }: { children: React.ReactNode; params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { ok, status, article } = await getArticle(id);
  // 内容不存在（HTTP 404）→ 渲染 404 页（流式渲染下状态码保持 200，由自动注入 + 兜底 noindex 防收录）；临时故障不触发（避免误伤）
  if (!ok && status === 404) notFound();
  return (
    <>
      {children}
      {article && (
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "Article",
            headline: article.title,
            url: absoluteUrl(`/article/${article.id}`),
            datePublished: article.created_at,
            dateModified: article.updated_at,
            author: article.author?.name
              ? {
                  "@type": "Person",
                  name: article.author.name,
                  url: article.author.id ? absoluteUrl(`/users/${article.author.id}`) : undefined,
                }
              : undefined,
            publisher: {
              "@type": "Organization",
              name: "妖精论坛",
              url: siteUrl(),
              logo: { "@type": "ImageObject", url: absoluteUrl("/assets/img/favicon-512.png") },
            },
            image: absoluteUrl("/og-image.png"),
          }}
        />
      )}
    </>
  );
}
