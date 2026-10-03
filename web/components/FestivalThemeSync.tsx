"use client";

import { useEffect } from "react";
import { getSiteConfig, isFestivalActive } from "@/lib/site-config";

/**
 * 国庆主题客户端校正（无渲染输出）：
 * - 挂载时按客户端可达的站点配置重算一次（覆盖服务端渲染时的判定）；
 * - 窗口重新获得焦点时同步（跨天 / 后台改配置后回到页面）；
 * - 配置不可用时保持现状（不撤销服务端渲染的兜底判定，与服务端「失败回默认」保持一致）。
 */
export default function FestivalThemeSync() {
  useEffect(() => {
    let disposed = false;

    const sync = async () => {
      const cfg = await getSiteConfig();
      if (disposed) return;
      // 配置不可用（null）时保持现有 class，避免后端不可达时撤销 SSR 的兜底判定
      if (!cfg) return;
      document.documentElement.classList.toggle("theme-national", isFestivalActive(cfg));
    };

    sync();
    const onFocus = () => {
      sync();
    };
    window.addEventListener("focus", onFocus);
    return () => {
      disposed = true;
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  return null;
}
