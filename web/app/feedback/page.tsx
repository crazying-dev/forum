"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Modal from "@/components/ui/Modal";
import { ListEmpty, ListLoading, LoadMoreButton } from "@/components/ui/ListState";
import { feedbackApi, FeedbackDetail, FeedbackListItem, FeedbackLog, FeedbackStat } from "@/lib/api";
import { formatTime, timeAgo } from "@/lib/constants";

// 反馈状态：0 未处理 / 1 处理中 / 2 已处理 / 3 关闭（颜色与后端四态一一对应）
const STATUS_META: Record<number, { label: string; color: string }> = {
  0: { label: "未处理", color: "#e6803d" },
  1: { label: "处理中", color: "#3b82f6" },
  2: { label: "已处理", color: "#22a06b" },
  3: { label: "关闭", color: "#8a97a3" },
};

const PAGE_SIZE = 12;

function statusMeta(status: number) {
  return STATUS_META[status] || { label: "未知", color: "#8a97a3" };
}

/** 状态 pill：浅底深字（十六进制 + 透明度后缀） */
function StatusPill({ status }: { status: number }) {
  const meta = statusMeta(status);
  return (
    <span className="feedback-status-pill" style={{ background: `${meta.color}1f`, color: meta.color }}>
      {meta.label}
    </span>
  );
}

/** 反馈中心：状态统计 + 筛选 chips + 3 列瀑布流卡片 + 详情弹窗（处理流程时间线） */
export default function FeedbackPage() {
  const [stats, setStats] = useState<FeedbackStat[]>([]);
  const [statusFilter, setStatusFilter] = useState<number | null>(null);
  const [items, setItems] = useState<FeedbackListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<FeedbackDetail | null>(null);
  const [logs, setLogs] = useState<FeedbackLog[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  // 请求序号：筛选切换 / 详情切换时丢弃过期响应
  const listSeqRef = useRef(0);
  const detailSeqRef = useRef(0);

  const loadList = useCallback(async (status: number | null, page: number, append: boolean) => {
    const seq = ++listSeqRef.current;
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const r = await feedbackApi.list(status, page, PAGE_SIZE);
      if (seq !== listSeqRef.current) return;
      const list = r.data.items || [];
      setItems((prev) => (append ? [...prev, ...list] : list));
      setTotal(r.data.total || 0);
      setHasMore(!!r.data.has_more);
    } catch {
      if (seq !== listSeqRef.current) return;
      if (!append) {
        setItems([]);
        setTotal(0);
        setHasMore(false);
      }
    } finally {
      if (seq === listSeqRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, []);

  useEffect(() => {
    // 延后一个 tick 发起请求，避免在 effect 内同步触发加载态更新
    const t = window.setTimeout(() => loadList(statusFilter, 1, false), 0);
    return () => window.clearTimeout(t);
  }, [statusFilter, loadList]);

  useEffect(() => {
    let alive = true;
    feedbackApi
      .stats()
      .then((r) => {
        if (alive) setStats(r.data.stats || []);
      })
      .catch(() => {
        if (alive) setStats([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  const countOf = (status: number) => stats.find((s) => s.status === status)?.count ?? 0;
  const totalCount = stats.reduce((sum, s) => sum + s.count, 0);
  // 「全部」计数：优先统计数据，统计未返回时回退列表接口的 total
  const allCount = stats.length > 0 ? totalCount : total;

  const openDetail = async (id: number) => {
    const seq = ++detailSeqRef.current;
    setDetailOpen(true);
    setDetail(null);
    setLogs([]);
    setDetailLoading(true);
    try {
      const r = await feedbackApi.detail(id);
      if (seq !== detailSeqRef.current) return;
      setDetail(r.data.report);
      setLogs(r.data.logs || []);
    } catch {
      if (seq !== detailSeqRef.current) return;
      setDetail(null);
    } finally {
      if (seq === detailSeqRef.current) setDetailLoading(false);
    }
  };

  const loadMore = () => {
    loadList(statusFilter, Math.ceil(items.length / PAGE_SIZE) + 1, true);
  };

  const chips: { key: number | null; label: string; count: number }[] = [
    { key: null, label: "全部", count: allCount },
    ...([0, 1, 2, 3] as const).map((s) => ({ key: s as number | null, label: statusMeta(s).label, count: countOf(s) })),
  ];

  return (
    <div className="forum-container feedback-page">
      <div className="forum-header">
        <h1 className="forum-title">反馈中心</h1>
        <p className="forum-subtitle">公开查看反馈与处理进度</p>
      </div>

      {/* 统计区：分隔标题 + 四态大数字（可点击筛选） */}
      <div className="feedback-stats-section">
        <div className="feedback-stats-title">反馈处理情况</div>
        <div className="feedback-stats">
          {([0, 1, 2, 3] as const).map((s) => (
            <button
              key={s}
              type="button"
              className={`feedback-stat ${statusFilter === s ? "active" : ""}`}
              onClick={() => setStatusFilter(statusFilter === s ? null : s)}
            >
              <span className="feedback-stat-num">{countOf(s)}</span>
              <span className="feedback-stat-label">{statusMeta(s).label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 状态筛选 chips */}
      <div className="feedback-chips">
        {chips.map((c) => (
          <button
            key={c.key === null ? "all" : c.key}
            type="button"
            className={`feedback-chip ${statusFilter === c.key ? "active" : ""}`}
            onClick={() => setStatusFilter(c.key)}
          >
            {c.label} <span className="feedback-chip-count">{c.count}</span>
          </button>
        ))}
      </div>

      {loading ? (
        <ListLoading />
      ) : items.length === 0 ? (
        <ListEmpty text="暂无反馈" />
      ) : (
        <div className="feedback-waterfall">
          {items.map((it) => (
            <button type="button" className="feedback-card" key={it.id} onClick={() => openDetail(it.id)}>
              <span className="feedback-card-top">
                <StatusPill status={it.status} />
                <span className="feedback-card-anon">匿名</span>
              </span>
              <span className="feedback-card-title">{it.title}</span>
              <span className="feedback-card-summary">{it.detail}</span>
              <span className="feedback-card-time">{timeAgo(it.created_at)}</span>
            </button>
          ))}
        </div>
      )}

      {hasMore && !loading && <LoadMoreButton loading={loadingMore} onClick={loadMore} id="feedback-load-more" />}

      <div className="feedback-submit-entry">
        <span>没找到你遇到的问题？</span>
        <Link className="forum-create-btn" href="/feedback/submit">
          <i className="fa fa-bug"></i> 提交反馈
        </Link>
      </div>

      {/* 详情弹窗 */}
      <Modal open={detailOpen} onClose={() => setDetailOpen(false)} cardStyle={{ maxWidth: 560 }}>
        {detailLoading ? (
          <ListLoading />
        ) : !detail ? (
          <ListEmpty text="反馈不存在" />
        ) : (
          <div className="feedback-detail">
            <h3 className="feedback-detail-title">{detail.title}</h3>
            <div className="feedback-detail-meta">
              <StatusPill status={detail.status} />
              <span className="feedback-detail-time">{formatTime(detail.created_at)}</span>
            </div>
            <div className="feedback-detail-body">{detail.detail}</div>
            {detail.steps && (
              <>
                <div className="feedback-detail-subtitle">复现步骤</div>
                <div className="feedback-detail-body feedback-detail-steps">{detail.steps}</div>
              </>
            )}
            <div className="feedback-detail-subtitle">处理流程</div>
            <div className="feedback-timeline">
              {/* 首节点：提交反馈（未处理） */}
              <div className="feedback-timeline-item">
                <span className="feedback-timeline-dot" style={{ background: STATUS_META[0].color }}></span>
                <div className="feedback-timeline-content">
                  <div className="feedback-timeline-head">
                    <span className="feedback-timeline-status">提交反馈</span>
                    <span className="feedback-timeline-time">{formatTime(detail.created_at)}</span>
                  </div>
                  <div className="feedback-timeline-note">反馈已提交，等待处理（未处理）</div>
                </div>
              </div>
              {logs.map((log, idx) => {
                const meta = statusMeta(log.to_status);
                return (
                  <div className="feedback-timeline-item" key={`${log.to_status}-${idx}`}>
                    <span className="feedback-timeline-dot" style={{ background: meta.color }}></span>
                    <div className="feedback-timeline-content">
                      <div className="feedback-timeline-head">
                        <span className="feedback-timeline-status" style={{ color: meta.color }}>{meta.label}</span>
                        <span className="feedback-timeline-time">{formatTime(log.created_at)}</span>
                      </div>
                      {log.note && <div className="feedback-timeline-note">{log.note}</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
