"use client";

import { useEffect, useState } from "react";
import { getSiteConfig, type SiteAnnouncement } from "@/lib/site-config";

/** 公告关闭态 localStorage key：值为已关闭的 announcement.version */
export const ANNOUNCEMENT_DISMISS_KEY = "forum-announcement-dismissed-version";

/** 读取关闭态（隐私模式 / 禁用存储时按未关闭处理，不阻塞公告展示） */
function isDismissed(version: number): boolean {
  try {
    return localStorage.getItem(ANNOUNCEMENT_DISMISS_KEY) === String(version);
  } catch {
    return false;
  }
}

/**
 * 首页公告条（仅由 app/page.tsx 渲染，位于 Header 下方）。
 * - 数据来自 GET /site/config 的 data.announcement；关闭后按 version 写 localStorage，
 *   后端递增 version 后公告会重新出现；
 * - 非富文本：公告文案只作为文本节点渲染，不使用 dangerouslySetInnerHTML；
 * - 移动端换行由 CSS 处理（overflow-wrap:anywhere），关闭按钮不参与压缩。
 */
export default function AnnouncementBanner() {
  const [announcement, setAnnouncement] = useState<SiteAnnouncement | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const cfg = await getSiteConfig();
      if (cancelled) return;
      const data = cfg?.announcement;
      if (!data || !data.enabled) return;
      const text = data.text.trim();
      if (!text) return;
      if (isDismissed(data.version)) return;
      setAnnouncement({ ...data, text });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!announcement) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(ANNOUNCEMENT_DISMISS_KEY, String(announcement.version));
    } catch {
      /* 存储不可用时仅本次隐藏 */
    }
    setAnnouncement(null);
  };

  return (
    <div className="announcement-wrap">
      <aside className="announcement-banner" role="status" aria-live="polite">
        <span className="announcement-icon" aria-hidden="true">
          <i className="fa fa-bullhorn"></i>
        </span>
        <p className="announcement-text">{announcement.text}</p>
        <button type="button" className="announcement-close" onClick={dismiss} aria-label="关闭公告" title="关闭公告">
          <i className="fa fa-times" aria-hidden="true"></i>
        </button>
      </aside>
    </div>
  );
}
