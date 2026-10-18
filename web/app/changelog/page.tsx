"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import RichContent from "@/components/ui/RichContent";
import { ApiException } from "@/lib/api";
import { changelogApi, type ChangelogItem } from "@/lib/api/site-features";

const PAGE_SIZE = 20;

/** v 前缀归一（避免后端 version 已带 v 时出现 vv） */
function versionLabel(version: string): string {
  const v = (version || "").trim();
  if (!v) return "—";
  return /^v/i.test(v) ? v : `v${v}`;
}

/** RFC3339 → YYYY-MM-DD（无效值原样展示） */
function formatDate(value: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 更新日志：分页列表 + RichContent 富文本正文（管理端发布） */
export default function ChangelogPage() {
  const [items, setItems] = useState<ChangelogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const seqRef = useRef(0);

  const load = useCallback(async (targetPage: number) => {
    const seq = ++seqRef.current;
    setLoading(true);
    setError("");
    try {
      const data = await changelogApi.list(targetPage, PAGE_SIZE);
      if (seq !== seqRef.current) return;
      setItems(data.items || []);
      setTotal(data.total || 0);
      setPage(data.page || targetPage);
    } catch (e) {
      if (seq !== seqRef.current) return;
      setItems([]);
      setTotal(0);
      setError(e instanceof ApiException ? e.message : "更新日志加载失败，请稍后再试");
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 延后一个 tick 发起请求，避免在 effect 内同步更新加载态
    const t = window.setTimeout(() => void load(1), 0);
    return () => window.clearTimeout(t);
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const canPrev = page > 1 && !loading;
  const canNext = page < totalPages && !loading;

  return (
    <div className="changelog-page">
      <header className="changelog-header">
        <h1 className="changelog-heading">
          <i className="fa fa-history" aria-hidden="true"></i> 更新日志
        </h1>
        <p className="changelog-subtitle">记录妖精论坛的每一次更新：功能上新、体验优化与问题修复。</p>
      </header>

      {loading ? (
        <div className="changelog-status" role="status">
          <i className="fa fa-spinner fa-spin" aria-hidden="true"></i> 加载中...
        </div>
      ) : error ? (
        <div className="changelog-status changelog-error" role="alert">
          <p><i className="fa fa-exclamation-triangle" aria-hidden="true"></i> {error}</p>
          <button type="button" className="changelog-retry-btn" onClick={() => void load(page)}>重试</button>
        </div>
      ) : items.length === 0 ? (
        <div className="changelog-status changelog-empty">
          <i className="fa fa-file-text-o" aria-hidden="true"></i> 暂无更新日志
        </div>
      ) : (
        <div className="changelog-list">
          {items.map((item) => (
            <article className="changelog-item" key={item.id}>
              <div className="changelog-item-head">
                <span className="changelog-version">{versionLabel(item.version)}</span>
                <h2 className="changelog-title">{item.title || "更新"}</h2>
                <time className="changelog-date" dateTime={item.published_at || undefined}>
                  <i className="fa fa-clock-o" aria-hidden="true"></i> {formatDate(item.published_at)}
                </time>
              </div>
              {item.content_html ? (
                <RichContent content={item.content_html} className="changelog-content" />
              ) : (
                <p className="changelog-content-empty">暂无详细内容</p>
              )}
            </article>
          ))}
        </div>
      )}

      {!loading && !error && items.length > 0 && totalPages > 1 && (
        <nav className="changelog-pagination" aria-label="更新日志分页">
          <button type="button" className="changelog-page-btn" disabled={!canPrev} onClick={() => void load(page - 1)}>
            <i className="fa fa-chevron-left" aria-hidden="true"></i> 上一页
          </button>
          <span className="changelog-page-info">第 {page} / {totalPages} 页</span>
          <button type="button" className="changelog-page-btn" disabled={!canNext} onClick={() => void load(page + 1)}>
            下一页 <i className="fa fa-chevron-right" aria-hidden="true"></i>
          </button>
        </nav>
      )}
    </div>
  );
}
