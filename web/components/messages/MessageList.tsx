"use client";

// 消息列表：加载骨架 / 错误重试 / 空态 / 条目 / 加载更多。

import { useMemo } from "react";
import type { MessageSummary } from "@/lib/api/messages";
import MessageItem from "./MessageItem";
import type { FeedItem, MessageType } from "./types";

function MessageListSkeleton() {
  return (
    <div className="msg-skeleton-list" aria-hidden="true">
      {[0, 1, 2, 3, 4].map((i) => (
        <div className="msg-skeleton-row" key={i}>
          <span className="msg-skeleton-avatar"></span>
          <span className="msg-skeleton-main">
            <span className="msg-skeleton-line w60"></span>
            <span className="msg-skeleton-line w90"></span>
            <span className="msg-skeleton-line w40"></span>
          </span>
        </div>
      ))}
    </div>
  );
}

function StateBlock({
  icon,
  text,
  hint,
  action,
  onAction,
}: {
  icon: string;
  text: string;
  hint?: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="msg-state">
      <i className={`fa ${icon} msg-state-icon`} aria-hidden="true"></i>
      <div className="msg-state-text">{text}</div>
      {hint && <div className="msg-state-hint">{hint}</div>}
      {action && onAction && (
        <button type="button" className="msg-retry-btn" onClick={onAction}>
          <i className="fa fa-refresh"></i> {action}
        </button>
      )}
    </div>
  );
}

export default function MessageList({
  type,
  items,
  loading,
  error,
  hasMore,
  loadingMore,
  unreadSnapshot,
  liveUnreadKeys,
  emptyText,
  onRetry,
  onLoadMore,
}: {
  type: MessageType;
  items: FeedItem[];
  loading: boolean;
  error: string;
  hasMore: boolean;
  loadingMore: boolean;
  /** 首次进入时的未读快照：前 N 条（按分类）显示未读点 */
  unreadSnapshot: MessageSummary;
  /** SSE 实时新增条目的未读点 */
  liveUnreadKeys: Set<string>;
  emptyText: string;
  onRetry: () => void;
  onLoadMore: () => void;
}) {
  // 未读点 = 初入快照预算 + 实时新条目；不随侧栏徽标清零而消失（本次会话内可见）
  const unreadKeys = useMemo(() => {
    const set = new Set(liveUnreadKeys);
    const budget: Record<FeedItem["kind"], number> = {
      like: unreadSnapshot.likes,
      comment: unreadSnapshot.comments,
      system: unreadSnapshot.system,
    };
    const used: Record<FeedItem["kind"], number> = { like: 0, comment: 0, system: 0 };
    for (const item of items) {
      if (used[item.kind] < budget[item.kind]) set.add(item.key);
      used[item.kind] += 1;
    }
    return set;
  }, [items, unreadSnapshot, liveUnreadKeys]);

  if (loading) return <MessageListSkeleton />;
  if (error) {
    return <StateBlock icon="fa-exclamation-circle" text="消息加载失败" hint={error} action="重试" onAction={onRetry} />;
  }
  if (items.length === 0) {
    return <StateBlock icon="fa-inbox" text={emptyText} hint="有新消息时会在这里提醒你" />;
  }

  return (
    <div className="msg-list">
      {items.map((item) => (
        <MessageItem key={item.key} item={item} unread={unreadKeys.has(item.key)} showKind={type === "all"} />
      ))}
      {hasMore && (
        <div className="msg-load-more">
          <button type="button" onClick={onLoadMore} disabled={loadingMore}>
            {loadingMore ? (
              <>
                <i className="fa fa-spinner fa-spin"></i> 加载中...
              </>
            ) : (
              "加载更多"
            )}
          </button>
        </div>
      )}
    </div>
  );
}
