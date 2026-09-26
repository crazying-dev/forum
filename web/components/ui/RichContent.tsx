"use client";

import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { escapeHtml, sanitizeHtml } from "@/lib/sanitize";

/** SSR 下 useLayoutEffect 降级为 useEffect（避免服务端告警） */
const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

/**
 * 富文本渲染（渲染管理端编辑的 HTML，不做 Markdown 解析）。
 * - DOMPurify 净化：移除 script/iframe 等危险标签与 on* 事件属性（与 Markdown 共用 sanitize.ts）
 * - 外部链接改写为 /GoTo?to=... 过渡页
 * - SSR/净化不可用时降级为转义纯文本，不输出未净化 HTML
 * - 图片宽度：站点全局 `svg, img { width: inherit }` 会压过 HTML width 属性，
 *   故渲染后把合法 width 应用为内联样式（内联优先级最高）；仅接受纯正整数并上限 2400px，无新增 XSS 面
 */
export default function RichContent({ content, className = "" }: { content?: string | null; className?: string }) {
  const html = useMemo(() => {
    if (!content) return "";
    const sanitized = sanitizeHtml(content);
    return sanitized === null ? escapeHtml(content) : sanitized;
  }, [content]);

  const ref = useRef<HTMLDivElement>(null);

  useIsoLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    root.querySelectorAll("img[width]").forEach((node) => {
      const raw = (node.getAttribute("width") ?? "").trim();
      if (!/^\d+$/.test(raw)) return; // 仅纯正整数（拒绝 "100%"/"500px" 等，避免误解析为小图）
      const width = Number.parseInt(raw, 10);
      if (width > 0) {
        (node as HTMLImageElement).style.width = `${Math.min(width, 2400)}px`;
      }
    });
  }, [html]);

  return <div ref={ref} className={className || undefined} dangerouslySetInnerHTML={{ __html: html }} />;
}
