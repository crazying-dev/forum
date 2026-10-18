import DOMPurify from "dompurify";

// ===== HTML 净化（Markdown 与 RichContent 共用）=====
// 与 legacy _sanitizeHtml + 链接改写保持一致；本文件被客户端组件使用。

/** 与 legacy _isExternalLink 一致：相对路径放行，同域 yjlt.top 放行，其余外部链接改写 */
export function isExternalLink(href: string): boolean {
  if (!href) return false;
  if (href.charAt(0) === "/" || href.charAt(0) === "#" || href.charAt(0) === "?") return false;
  const m = /^([a-zA-Z][a-zA-Z0-9+.\-]*):\/\/([^/?#]+)/.exec(href);
  if (!m) return false;
  const host = m[2].toLowerCase();
  if (host === "yjlt.top" || host.endsWith(".yjlt.top")) return false;
  return true;
}

/** 转义 HTML 实体：净化不可用时以纯文本渲染，避免原样输出未净化 HTML */
export function escapeHtml(s: string): string {
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
 * DOMPurify 净化：移除 script/iframe 等危险标签与 on* 事件属性（等价 legacy _sanitizeHtml），
 * 并将外部链接改写为 /GoTo?to=... 过渡页。
 * 净化不可用（SSR/未初始化）或异常时返回 null，由调用方降级为转义纯文本。
 */
export function sanitizeHtml(html: string): string | null {
  if (typeof DOMPurify.sanitize !== "function") return null;
  try {
    ensureHook();
    return DOMPurify.sanitize(html, {
      USE_PROFILES: { html: true },
      // style 属性可被用来做视觉覆盖/隐藏（发布来源可信时风险低，但仍不必要）：正文宽度走 width 属性
      FORBID_ATTR: ["style"],
      FORBID_TAGS: ["script", "iframe", "object", "embed", "form", "style", "link", "meta"],
    });
  } catch {
    return null;
  }
}
