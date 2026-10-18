"use client";

// ===== 管理团队共享会话 =====
// - 左右气泡：user 在右、admin 在左；admin 展示绑定账号头像/名称 + 「管理团队」tag
// - 富文本统一 RichContent 渲染；输入复用 CommentEditor（scene=chat_message，2000 字上限）
// - 发送 2 秒限流提示；进入/新消息时 POST /messages/chat/read
// - SSE 新消息与轮询刷新均按 id 去重合并

import { useCallback, useEffect, useRef, useState } from "react";
import CommentEditor from "@/components/editor/CommentEditor";
import RichContent from "@/components/ui/RichContent";
import { useToast } from "@/components/Toast";
import { UserAvatar } from "@/components/ui/UserAvatar";
import { ApiException, type User } from "@/lib/api";
import { messagesApi, type ChatMessage } from "@/lib/api/messages";
import { timeAgo } from "@/lib/constants";
import { useStore } from "@/lib/store";
import { mergeChatMessages } from "./types";

/** 聊天单页条数（服务端上限 50）。 */
const CHAT_PAGE_SIZE = 30;
/** 服务端 2 秒/用户限流。 */
const SEND_INTERVAL_MS = 2000;

function hasRichContent(html: string): boolean {
  const text = html.replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim();
  return !!text || /<img\b/i.test(html) || /data-embed=/i.test(html);
}

function ChatSkeleton() {
  return (
    <div className="msg-chat-skeleton" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div className={`msg-chat-skel-row ${i % 2 === 0 ? "them" : "me"}`} key={i}>
          <span className="msg-skeleton-avatar"></span>
          <span className="msg-chat-skel-bubble"></span>
        </div>
      ))}
    </div>
  );
}

function ChatBubble({ message, me }: { message: ChatMessage; me: User | null }) {
  const isAdmin = message.sender_type === "admin";
  const isMe = !isAdmin;
  const name = message.sender_name || (isAdmin ? "管理团队" : "我");
  const avatar = message.sender_avatar || (isMe ? me?.avatar || "" : "");
  return (
    <div className={`msg-chat-row ${isMe ? "me" : "them"}`}>
      <span className="msg-chat-avatar">
        <UserAvatar src={avatar} alt={`${name} 的头像`} userId={isMe ? me?.id : null} />
      </span>
      <div className="msg-chat-main">
        <div className="msg-chat-meta">
          <span className="msg-chat-name">{name}</span>
          {isAdmin && <span className="msg-chat-tag">管理团队</span>}
          <span className="msg-chat-time">{timeAgo(message.created_at)}</span>
        </div>
        <div className="msg-chat-bubble">
          <RichContent content={message.content_html} className="msg-chat-rich" />
        </div>
      </div>
    </div>
  );
}

export default function ChatPanel({
  visible,
  liveMessages,
  refreshToken,
  onRead,
}: {
  /** 当前详情是否可见（移动端返回类型列表后为 false） */
  visible: boolean;
  /** SSE 收到的聊天消息（父级累积，组件内去重） */
  liveMessages: ChatMessage[];
  /** 轮询 / 手动刷新计数 */
  refreshToken: number;
  /** 已读成功：清侧栏「管理团队」徽标 */
  onRead: () => void;
}) {
  const { user: me } = useStore();
  const { toast } = useToast();
  const [items, setItems] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  const listRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const cursorRef = useRef("");
  const hasMoreRef = useRef(false);
  const loadedRef = useRef(false);
  const seqRef = useRef(0);
  const loadingMoreRef = useRef(false);
  const sendingRef = useRef(false);
  const lastSentRef = useRef(0);
  const lastReadRef = useRef(0);
  const lastRefreshRef = useRef(refreshToken);
  const visibleRef = useRef(visible);
  const onReadRef = useRef(onRead);

  useEffect(() => {
    visibleRef.current = visible;
  }, [visible]);

  useEffect(() => {
    onReadRef.current = onRead;
  }, [onRead]);

  /** 标记会话已读到最新消息 id（仅前进；可见时才发） */
  const markRead = useCallback((list: ChatMessage[]) => {
    if (!visibleRef.current || list.length === 0) return;
    const maxId = list.reduce((max, m) => Math.max(max, m.id), 0);
    if (maxId <= lastReadRef.current) return;
    lastReadRef.current = maxId;
    void messagesApi
      .readChat(maxId)
      .then(() => onReadRef.current())
      .catch(() => {
        /* 下条消息/轮询时重试 */
      });
  }, []);

  const loadFirst = useCallback(
    async (silent: boolean) => {
      const seq = ++seqRef.current;
      if (!silent) {
        setLoading(true);
        setError("");
      }
      try {
        const r = await messagesApi.chat(undefined, CHAT_PAGE_SIZE);
        if (seq !== seqRef.current) return;
        const page = [...(r.items || [])].reverse(); // 接口 id 倒序 → 气泡旧到新
        if (!loadedRef.current) {
          cursorRef.current = r.next_cursor || "";
          hasMoreRef.current = !!r.has_more;
          setHasMore(!!r.has_more);
          loadedRef.current = true;
          setItems(page);
        } else {
          // 轮询/手动刷新：只合并新消息，保留已加载的更早分页游标
          setItems((prev) => mergeChatMessages(prev, page));
        }
        setError("");
        markRead(page);
      } catch (err) {
        if (seq !== seqRef.current) return;
        setError(err instanceof Error && err.message ? err.message : "消息加载失败，请稍后重试");
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    },
    [markRead]
  );

  // 首次进入加载（延后一个 tick，避免在 effect 内同步触发加载态更新）
  useEffect(() => {
    const t = window.setTimeout(() => void loadFirst(false), 0);
    return () => window.clearTimeout(t);
  }, [loadFirst]);

  // 轮询 / 手动刷新（跳过挂载时的初始值）
  useEffect(() => {
    if (refreshToken === lastRefreshRef.current) return;
    lastRefreshRef.current = refreshToken;
    void loadFirst(true);
  }, [refreshToken, loadFirst]);

  // SSE 新消息：合并去重 + 可见时标已读
  useEffect(() => {
    if (liveMessages.length === 0) return;
    const t = window.setTimeout(() => {
      setItems((prev) => mergeChatMessages(prev, liveMessages));
      setError("");
      markRead(liveMessages);
    }, 0);
    return () => window.clearTimeout(t);
  }, [liveMessages, markRead]);

  // 新消息到达时贴底（用户主动上翻时不打扰）
  useEffect(() => {
    const el = listRef.current;
    if (!el || !stickRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [items]);

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMoreRef.current) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const seq = seqRef.current;
    try {
      const r = await messagesApi.chat(cursorRef.current, CHAT_PAGE_SIZE);
      if (seq !== seqRef.current) return;
      const older = [...(r.items || [])].reverse();
      cursorRef.current = r.next_cursor || "";
      hasMoreRef.current = !!r.has_more;
      setHasMore(!!r.has_more);
      setItems((prev) => mergeChatMessages(prev, older));
    } catch {
      /* 保留已加载内容，下次重试 */
    } finally {
      if (seq === seqRef.current) {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      }
    }
  }, []);

  const send = useCallback(async () => {
    if (sendingRef.current) return;
    const html = draft;
    if (!hasRichContent(html)) {
      toast("请先输入内容", "warning");
      return;
    }
    const elapsed = Date.now() - lastSentRef.current;
    if (elapsed < SEND_INTERVAL_MS) {
      toast(`发送太快，请 ${Math.max(1, Math.ceil((SEND_INTERVAL_MS - elapsed) / 1000))} 秒后再试`, "warning");
      return;
    }

    sendingRef.current = true;
    setSending(true);
    try {
      const r = await messagesApi.sendChat(html);
      lastSentRef.current = Date.now();
      const optimistic: ChatMessage = {
        id: r.id,
        sender_type: "user",
        sender_name: me?.name || "我",
        sender_avatar: me?.avatar || "",
        admin_id: "",
        content_html: html,
        content_format: "html",
        created_at: new Date().toISOString(),
      };
      stickRef.current = true;
      setItems((prev) => mergeChatMessages(prev, [optimistic]));
      setError("");
      setDraft("");
      lastReadRef.current = Math.max(lastReadRef.current, r.id);
      onReadRef.current();
    } catch (err) {
      if (err instanceof ApiException && err.status === 429) {
        lastSentRef.current = Date.now();
        toast(err.message || "发送太快，请 2 秒后再试", "warning");
      } else {
        toast(err instanceof Error && err.message ? err.message : "发送失败，请稍后重试", "error");
      }
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }, [draft, me, toast]);

  const retry = () => {
    loadedRef.current = false;
    cursorRef.current = "";
    hasMoreRef.current = false;
    setHasMore(false);
    void loadFirst(false);
  };

  return (
    <div className="msg-chat">
      <div className="msg-chat-notice">
        <i className="fa fa-shield" aria-hidden="true"></i> 仅你与论坛管理团队可见
      </div>

      {loading ? (
        <ChatSkeleton />
      ) : error ? (
        <div className="msg-state">
          <i className="fa fa-exclamation-circle msg-state-icon" aria-hidden="true"></i>
          <div className="msg-state-text">会话加载失败</div>
          <div className="msg-state-hint">{error}</div>
          <button type="button" className="msg-retry-btn" onClick={retry}>
            <i className="fa fa-refresh"></i> 重试
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="msg-state">
          <i className="fa fa-comments-o msg-state-icon" aria-hidden="true"></i>
          <div className="msg-state-text">还没有消息</div>
          <div className="msg-state-hint">给管理团队留言，我们会尽快回复</div>
        </div>
      ) : (
        <div
          className="msg-chat-list"
          ref={listRef}
          onScroll={() => {
            const el = listRef.current;
            if (el) stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
          }}
        >
          {hasMore && (
            <div className="msg-chat-more">
              <button type="button" onClick={loadMore} disabled={loadingMore}>
                {loadingMore ? "加载中..." : "加载更早消息"}
              </button>
            </div>
          )}
          {items.map((message) => (
            <ChatBubble key={message.id} message={message} me={me} />
          ))}
        </div>
      )}

      <div className="msg-chat-composer">
        <CommentEditor
          value={draft}
          onChange={setDraft}
          onSubmit={send}
          placeholder="输入消息，与管理团队沟通…"
          submitting={sending}
          uploadScene="chat_message"
          maxChars={2000}
          allowQuotePicker={false}
        />
        <div className="msg-chat-foot">
          <i className="fa fa-clock-o" aria-hidden="true"></i> 发送间隔 2 秒 · 支持图片与表情
        </div>
      </div>
    </div>
  );
}
