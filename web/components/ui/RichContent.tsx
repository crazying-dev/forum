"use client";

import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import type { Root } from "react-dom/client";
import { QuoteCard, QuoteCardSkeleton } from "@/components/quote/QuoteCards";
import { EmbedSpec, embedKey, loadEmbeds, parseEmbedElement } from "@/lib/embed";
import { escapeHtml, sanitizeHtml } from "@/lib/sanitize";

/** SSR 下 useLayoutEffect 降级为 useEffect（避免服务端告警） */
const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

/** 站内媒体图片：仅同源相对路径（新老 API 前缀）+ MD 媒体 ID（可选 query）。
 *  不匹配带外部域名的 URL，避免作者让读者浏览器向任意主机发请求。 */
const MEDIA_SRC_RE = /^\/(ov2\/api|api\/v1)\/media\/(MD[0-9a-fA-F]{16,})(\?.*)?$/;

/** 正文媒体图响应式 sizes（与后端 ?w=480 / ?w=1280 变体配合） */
const MEDIA_IMG_SIZES = "(max-width: 640px) 100vw, (max-width: 1024px) 90vw, 820px";

/**
 * 异步卸载 roots：绝不在 React 渲染/提交阶段同步调用 root.unmount（React 19 限制）。
 * 统一用 setTimeout(0) 让出当前同步任务后再卸载；对已脱离文档的容器同样安全。
 */
function scheduleUnmount(roots: Root[]) {
  if (roots.length === 0) return;
  setTimeout(() => {
    for (const root of roots) {
      try {
        root.unmount();
      } catch {
        /* 已卸载/已脱离文档，忽略 */
      }
    }
  }, 0);
}

/**
 * 富文本渲染（渲染管理端编辑的 HTML，不做 Markdown 解析）。
 * - DOMPurify 净化：移除 script/iframe 等危险标签与 on* 事件属性（与 Markdown 共用 sanitize.ts）
 * - 外部链接改写为 /GoTo?to=... 过渡页
 * - SSR/净化不可用时降级为转义纯文本，不输出未净化 HTML
 * - 图片宽度：站点全局 `svg, img { width: inherit }` 会压过 HTML width 属性，
 *   故渲染后把合法 width 应用为内联样式（内联优先级最高）；仅接受纯正整数并上限 2400px，无新增 XSS 面
 * - 站内媒体图片：effect 内补 srcset（后端 ?w=480 / ?w=1280 变体）、sizes、loading=lazy、
 *   decoding=async；加载失败时移除 srcset 回退原图。只改 DOM，不改 dangerouslySetInnerHTML 的内容
 * - 引用节点（[data-embed]）：批量解析成一次请求（模块缓存 + 进行中去重）后，
 *   每个节点用 createRoot 隔离渲染 QuoteCard；effect 重跑/卸载时仅“安排异步卸载”旧 roots
 *   （同步 root.unmount 会因路由切换等渲染时机触发 React 19 的
 *   「Attempted to synchronously unmount a root while React was already rendering」）
 */
export default function RichContent({ content, className = "" }: { content?: string | null; className?: string }) {
  // 自动追加 rich-content：启用 styles/rich-content.css 的正文基础排版（列表符号 / 标题 / 表格等）
  const rootClassName = ["rich-content", className].filter(Boolean).join(" ");

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

    // 站内媒体图片：补 srcset（后端 ?w= 变体）+ 懒加载。仅操作 DOM，注入的 HTML 字符串保持原样（SSR 安全）。
    root.querySelectorAll("img").forEach((img) => {
      const src = img.getAttribute("src") ?? "";
      const match = MEDIA_SRC_RE.exec(src);
      if (!match) return;
      if (img.hasAttribute("srcset")) return; // 已自带响应式候选：不覆盖
      // 带 query（w= 或其它参数）时跳过：变体 URL 只能由无 query 的原 URL 派生，避免拼出 ?w=480?w=1280
		if (match[3] !== undefined) return;
      img.srcset = `${src}?w=480 480w, ${src}?w=1280 1280w`;
      img.sizes = MEDIA_IMG_SIZES;
      img.setAttribute("loading", "lazy");
      img.setAttribute("decoding", "async");
      img.setAttribute("data-media-srcset", "1"); // 标记：错误时只回退我们生成的 srcset
    });

    // error 不冒泡，在容器捕获阶段委托；只处理上面标记过的图片
    const onMediaError = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLImageElement)) return;
      if (!target.hasAttribute("data-media-srcset")) return;
      target.removeAttribute("data-media-srcset");
      target.removeAttribute("srcset");
      target.removeAttribute("sizes");
      const original = target.getAttribute("src");
      if (!original) return;
      // 重设 src 强制重新拉取原图（部分浏览器仅移除 srcset 不会重试）
      target.removeAttribute("src");
      target.setAttribute("src", original);
    };
    root.addEventListener("error", onMediaError, true);
    return () => root.removeEventListener("error", onMediaError, true);
  }, [html]);

  // 引用节点渲染（useEffect：仅“安排异步卸载”，绝不在此同步调用 root.unmount）
  useEffect(() => {
    const container = ref.current;
    if (!container) return;

    const targets: { el: Element; spec: EmbedSpec }[] = [];
    container.querySelectorAll("[data-embed]").forEach((el) => {
      const spec = parseEmbedElement(el);
      if (spec) targets.push({ el, spec });
    });
    if (targets.length === 0) return;

    let cancelled = false;
    const roots: Root[] = [];
    void (async () => {
      // 动态引入：避免 react-dom/client 进入服务端渲染路径
      const { createRoot } = await import("react-dom/client");
      if (cancelled) return;
      const mounted = targets.map(({ el, spec }) => {
        el.textContent = ""; // 防御：节点内只应有我们挂载的宿主
        const host = document.createElement("div");
        host.className = "quote-embed-host";
        el.appendChild(host);
        const root = createRoot(host);
        roots.push(root);
        root.render(<QuoteCardSkeleton variant={spec.variant} />); // 先骨架
        return { key: embedKey(spec.type, spec.id), spec, root };
      });
      const data = await loadEmbeds(targets.map((t) => t.spec));
      if (cancelled) return;
      for (const item of mounted) {
        item.root.render(<QuoteCard spec={item.spec} data={data.get(item.key) ?? null} />);
      }
    })();

    return () => {
      cancelled = true;
      // cleanup 可能发生在路由切换的渲染阶段：只能异步卸载（见 scheduleUnmount 注释）
      scheduleUnmount(roots);
    };
  }, [html]);

  return <div ref={ref} className={rootClassName} dangerouslySetInnerHTML={{ __html: html }} />;
}
