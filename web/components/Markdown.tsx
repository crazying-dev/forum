"use client";

import { useMemo } from "react";
import { marked } from "marked";
import { escapeHtml, sanitizeHtml } from "@/lib/sanitize";

/**
 * Markdown 渲染（原生 React 组件，替代 legacy 的 marked + _sanitizeHtml）。
 * - 与 legacy 一致：breaks:true, gfm:true
 * - DOMPurify 净化：移除 script/iframe 等危险标签与 on* 事件属性（等价 legacy _sanitizeHtml）
 * - 外部链接改写为 /GoTo?to=... 过渡页（等价 legacy 链接改写）
 * 注意：正文由客户端 API 加载，首次渲染 content 为空，因此 SSR 不会输出未净化 HTML。
 */
export default function Markdown({ content, className = "" }: { content?: string; className?: string }) {
  // 自动追加 rich-content：启用 styles/rich-content.css 的正文基础排版（列表符号 / 标题 / 表格等）
  const rootClassName = ["rich-content", className].filter(Boolean).join(" ");

  const html = useMemo(() => {
    if (!content) return "";
    let raw: string | null = null;
    try {
      raw = marked.parse(content, { breaks: true, gfm: true }) as string;
    } catch {
      // 解析异常：降级为转义文本（不输出未净化 HTML）
    }
    if (raw === null) return escapeHtml(content);
    // 浏览器环境净化；SSR/未初始化等净化不可用时转义为纯文本，不输出未净化 HTML
    const sanitized = sanitizeHtml(raw);
    return sanitized === null ? escapeHtml(raw) : sanitized;
  }, [content]);

  return <div className={rootClassName} dangerouslySetInnerHTML={{ __html: html }} />;
}


