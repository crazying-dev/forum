"use client";

import { useMemo } from "react";
import { escapeHtml, sanitizeHtml } from "@/lib/sanitize";

/**
 * 富文本渲染（渲染管理端编辑的 HTML，不做 Markdown 解析）。
 * - DOMPurify 净化：移除 script/iframe 等危险标签与 on* 事件属性（与 Markdown 共用 sanitize.ts）
 * - 外部链接改写为 /GoTo?to=... 过渡页
 * - SSR/净化不可用时降级为转义纯文本，不输出未净化 HTML
 */
export default function RichContent({ content, className = "" }: { content?: string | null; className?: string }) {
  const html = useMemo(() => {
    if (!content) return "";
    const sanitized = sanitizeHtml(content);
    return sanitized === null ? escapeHtml(content) : sanitized;
  }, [content]);

  return <div className={className || undefined} dangerouslySetInnerHTML={{ __html: html }} />;
}
