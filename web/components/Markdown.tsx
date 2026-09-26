"use client";

import { useMemo } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

/** 与 legacy _isExternalLink 一致：相对路径放行，同域 yjlt.top 放行，其余外部链接改写 */
function isExternalLink(href: string): boolean {
  if (!href) return false;
  if (href.charAt(0) === "/" || href.charAt(0) === "#" || href.charAt(0) === "?") return false;
  const m = /^([a-zA-Z][a-zA-Z0-9+.\-]*):\/\/([^/?#]+)/.exec(href);
  if (!m) return false;
  const host = m[2].toLowerCase();
  if (host === "yjlt.top" || host.endsWith(".yjlt.top")) return false;
  return true;
}

/** 转义 HTML 实体：净化不可用时以纯文本渲染，避免原样输出未净化 HTML */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

let hookAdded = false;
/** 在浏览器中注册一次链接改写 hook（幂等） */
function ensureHook() {
  if (hookAdded) return;
  if (typeof DOMPurify.sanitize !== "function") return; // Node/SSR 下不可用
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      const href = node.getAttribute("href") || "";
      if (href.toLowerCase().startsWith("javascript:")) return;
      if (isExternalLink(href)) {
        node.setAttribute("href", "/GoTo?to=" + encodeURIComponent(href));
        node.setAttribute("rel", "nofollow noopener noreferrer");
        if (!node.getAttribute("target")) node.setAttribute("target", "_blank");
      }
    }
  });
  hookAdded = true;
}

/**
 * Markdown 渲染（原生 React 组件，替代 legacy 的 marked + _sanitizeHtml）。
 * - 与 legacy 一致：breaks:true, gfm:true
 * - DOMPurify 净化：移除 script/iframe 等危险标签与 on* 事件属性（等价 legacy _sanitizeHtml）
 * - 外部链接改写为 /GoTo?to=... 过渡页（等价 legacy 链接改写）
 * 注意：正文由客户端 API 加载，首次渲染 content 为空，因此 SSR 不会输出未净化 HTML。
 */
export default function Markdown({ content, className = "" }: { content?: string; className?: string }) {
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
    if (typeof DOMPurify.sanitize !== "function") return escapeHtml(raw);
    let sanitized: string | null = null;
    try {
      ensureHook();
      sanitized = DOMPurify.sanitize(raw, {
        USE_PROFILES: { html: true },
        FORBID_TAGS: ["script", "iframe", "object", "embed", "form", "style", "link", "meta"],
      });
    } catch {
      // 净化异常：降级为转义文本（不输出未净化 HTML）
    }
    return sanitized === null ? escapeHtml(raw) : sanitized;
  }, [content]);

  return <div className={className || undefined} dangerouslySetInnerHTML={{ __html: html }} />;
}


