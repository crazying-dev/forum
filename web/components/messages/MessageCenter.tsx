"use client";

// ===== 消息中心主容器 =====
// - 桌面：260px 类型栏 + 自适应详情
// - 移动：类型列表 → 详情两屏，返回按钮 + ?type= 深链
// - SSE 未读/通知/聊天事件 + 15s 无事件轮询降级

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import GlobalLoading from "@/components/GlobalLoading";
import { ApiException } from "@/lib/api";
import {
  messagesApi,
  type ChatMessage,
  type MessageCategory,
  type MessageSummary,
  type StreamNotificationItem,
} from "@/lib/api/messages";
import { useStore } from "@/lib/store";
import ChatPanel from "./ChatPanel";
import MessageList from "./MessageList";
import MessageTypeList from "./MessageTypeList";
import {
  isMessageType,
  MESSAGE_TYPE_META,
  notificationToFeedItem,
  type FeedItem,
  type MessageType,
} from "./types";
import { useMessageFeed } from "./useMessageFeed";
import { useMessageStream, type MessageStreamStatus } from "./useMessageStream";

const EMPTY_SUMMARY: MessageSummary = { likes: 0, comments: 0, system: 0, chat: 0 };

function connectionLabel(status: MessageStreamStatus): string {
  if (status === "open") return "实时连接已建立";
  if (status === "connecting") return "正在连接…";
  if (status === "reconnecting") return "正在重连…";
  if (status === "degraded") return "轮询模式（15 秒）";
  return "未连接";
}

export default function MessageCenter() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, userId, loadingUser } = useStore();
  const authedUserId = user?.id || userId;
  const ready = !loadingUser && !!authedUserId;

  const typeParam = searchParams.get("type");
  // URL 是唯一数据源：?type= 深链 / 浏览器前进后退均自动生效
  const activeType: MessageType = isMessageType(typeParam) ? typeParam : "all";
  // 移动端两屏由 URL 决定：有合法 ?type= 即显示详情，无则显示类型列表（浏览器前进/后退自动同步）
  const mobileDetailOpen = isMessageType(typeParam);
  // 逻辑用（不参与渲染）：移动端初始即按媒体查询判断，避免首屏误标已读
  const [isMobile, setIsMobile] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 768px)").matches
  );

  const [summary, setSummary] = useState<MessageSummary>(EMPTY_SUMMARY);
  const [initialUnread, setInitialUnread] = useState<MessageSummary>(EMPTY_SUMMARY);
  const initialUnreadRef = useRef<MessageSummary | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const [authExpired, setAuthExpired] = useState(false);

  const [incoming, setIncoming] = useState<FeedItem[]>([]);
  const [liveUnreadKeys, setLiveUnreadKeys] = useState<Set<string>>(() => new Set());
  const [liveMessages, setLiveMessages] = useState<ChatMessage[]>([]);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px)");
    const onChange = () => setIsMobile(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const loadSummary = useCallback(async () => {
    if (!ready) return;
    try {
      const r = await messagesApi.summary();
      const counts: MessageSummary = {
        likes: Number(r.likes) || 0,
        comments: Number(r.comments) || 0,
        system: Number(r.system) || 0,
        chat: Number(r.chat) || 0,
      };
      setSummary(counts);
      if (!initialUnreadRef.current) {
        initialUnreadRef.current = counts;
        setInitialUnread(counts);
      }
      setSummaryError("");
      setAuthExpired(false);
    } catch (err) {
      if (err instanceof ApiException && err.status === 401) {
        setAuthExpired(true);
      } else {
        setSummaryError(err instanceof Error && err.message ? err.message : "未读数加载失败");
      }
    }
  }, [ready]);

  useEffect(() => {
    if (!ready) return;
    // 延后一个 tick，避免在 effect 内同步触发加载态更新
    const t = window.setTimeout(() => void loadSummary(), 0);
    return () => window.clearTimeout(t);
  }, [ready, loadSummary]);

  // ---- SSE 回调 ----
  const handleUnread = useCallback((counts: MessageSummary) => {
    setSummary(counts);
    if (!initialUnreadRef.current) {
      initialUnreadRef.current = counts;
      setInitialUnread(counts);
    }
    setSummaryError("");
    setAuthExpired(false);
  }, []);

  const handleNotification = useCallback((item: StreamNotificationItem) => {
    const feedItem = notificationToFeedItem(item);
    if (!feedItem) return;
    setIncoming((prev) => {
      const next = [...prev, feedItem];
      return next.length > 200 ? next.slice(-100) : next;
    });
    setLiveUnreadKeys((prev) => {
      const next = new Set(prev);
      next.add(feedItem.key);
      return next;
    });
  }, []);

  const handleMessage = useCallback((item: ChatMessage) => {
    setLiveMessages((prev) => [...prev.slice(-99), item]);
  }, []);

  const refresh = useCallback(() => {
    void loadSummary();
    setRefreshToken((n) => n + 1);
  }, [loadSummary]);

  const streamStatus = useMessageStream(ready && !authExpired, {
    onUnread: handleUnread,
    onNotification: handleNotification,
    onMessage: handleMessage,
    onPoll: refresh,
  });

  // ---- 列表 / 聊天 ----
  const detailVisible = !isMobile || mobileDetailOpen;
  const feedEnabled = ready && !authExpired && detailVisible && activeType !== "chat";
  const handleRead = useCallback((category: MessageCategory) => {
    setSummary((prev) => ({ ...prev, [category]: 0 }));
  }, []);
  const handleChatRead = useCallback(() => {
    setSummary((prev) => ({ ...prev, chat: 0 }));
  }, []);

  const feed = useMessageFeed(activeType, feedEnabled, incoming, handleRead, refreshToken);

  const selectType = useCallback(
    (type: MessageType) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("type", type);
      router.replace(`/messages?${params.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  const backToList = useCallback(() => {
    router.replace("/messages", { scroll: false });
  }, [router]);

  if (loadingUser) {
    return (
      <div className="route-loading">
        <GlobalLoading />
      </div>
    );
  }

  if (!ready || authExpired) {
    return (
      <div className="msg-page">
        <div className="msg-gate">
          <i className="fa fa-envelope-o msg-gate-icon" aria-hidden="true"></i>
          <h1>消息中心</h1>
          <p>{authExpired ? "登录状态已过期，请重新登录" : "登录后查看点赞、评论与管理团队消息"}</p>
          <Link href="/auth" className="msg-gate-btn">
            <i className="fa fa-sign-in" aria-hidden="true"></i> 去登录
          </Link>
        </div>
      </div>
    );
  }

  const meta = MESSAGE_TYPE_META[activeType];

  return (
    <div className="msg-page">
      <div className={`msg-shell${mobileDetailOpen ? " mobile-detail-open" : ""}`}>
        <aside className="msg-sidebar">
          <div className="msg-sidebar-head">
            <h1 className="msg-sidebar-title">
              <i className="fa fa-envelope-o" aria-hidden="true"></i> 消息中心
            </h1>
            <p className="msg-sidebar-sub">赞、评论与官方消息</p>
          </div>
          <MessageTypeList active={activeType} unread={summary} onSelect={selectType} />
          <div className={`msg-conn ${streamStatus}`} title={connectionLabel(streamStatus)}>
            <span className="msg-conn-dot" aria-hidden="true"></span>
            {connectionLabel(streamStatus)}
          </div>
        </aside>

        <section className="msg-detail">
          <header className="msg-detail-head">
            <button type="button" className="msg-back-btn" onClick={backToList} aria-label="返回消息类型">
              <i className="fa fa-angle-left" aria-hidden="true"></i> 返回
            </button>
            <div className="msg-detail-heading">
              <h2 className="msg-detail-title">{meta.title}</h2>
              <span className="msg-detail-sub">{meta.subtitle}</span>
            </div>
            <button type="button" className="msg-refresh-btn" onClick={refresh} title="刷新" aria-label="刷新消息">
              <i className="fa fa-refresh" aria-hidden="true"></i>
            </button>
          </header>

          {streamStatus === "degraded" && (
            <div className="msg-stream-note" role="status">
              <i className="fa fa-exclamation-triangle" aria-hidden="true"></i> 实时连接中断，已切换为每 15 秒轮询
            </div>
          )}
          {summaryError && (
            <div className="msg-stream-note is-error" role="alert">
              未读数加载失败：{summaryError}
              <button type="button" onClick={() => void loadSummary()}>
                重试
              </button>
            </div>
          )}

          <div className={`msg-detail-body${activeType === "chat" ? " is-chat" : ""}`}>
            {activeType === "chat" ? (
              <ChatPanel
                visible={detailVisible}
                liveMessages={liveMessages}
                refreshToken={refreshToken}
                onRead={handleChatRead}
              />
            ) : (
              <MessageList
                type={activeType}
                items={feed.items}
                loading={feed.loading}
                error={feed.error}
                hasMore={feed.hasMore}
                loadingMore={feed.loadingMore}
                unreadSnapshot={initialUnread}
                liveUnreadKeys={liveUnreadKeys}
                emptyText={meta.empty}
                onRetry={feed.refresh}
                onLoadMore={feed.loadMore}
              />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
