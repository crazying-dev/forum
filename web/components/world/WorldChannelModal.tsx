"use client";

// 世界频道：桌面入口按钮 + 受控独立的浮动窗口 / 移动端近全屏底部模态框。
// - 桌面：固定视口右上（Header 下方 16px）纵向矩形按钮；窗口标题栏可拖拽、边界 clamp、localStorage 记忆位置
// - 移动：底部滑入近全屏；顶部标题 + 关闭；底部输入条；Android 返回键优先关闭（popstate）
// - 消息：首屏 50、向上边界自动加载 200 条、SSE 增量去重、断线轮询降级、贴底/新消息提示
// - 输入：复用 CommentEditor（scene=world_message；2000 字 / 9 图 / 2 秒限流提示）

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { createPortal } from "react-dom";
import CommentEditor from "@/components/editor/CommentEditor";
import Markdown from "@/components/Markdown";
import RichContent from "@/components/ui/RichContent";
import { UserAvatar, UserName } from "@/components/ui/UserAvatar";
import { UserGuildChip } from "@/components/ui/UserGuildChip";
import { useToast } from "@/components/Toast";
import { ApiException } from "@/lib/api";
import {
  WORLD_HISTORY_SIZE,
  WORLD_MAX_CHARS,
  WORLD_MAX_IMAGES,
  WORLD_MAX_LIMIT,
  WORLD_PAGE_SIZE,
  WORLD_SEND_COOLDOWN_MS,
  worldApi,
  type WorldHelloPayload,
  type WorldMessage,
  type WorldMessagesResponse,
} from "@/lib/api/world";
import { formatTime, timeAgo } from "@/lib/constants";
import { useStore } from "@/lib/store";
import { createSSEConnection, type SSEConnection } from "@/lib/sse";

/** 移动端断点：与 Header 抽屉一致 */
const MOBILE_MEDIA_QUERY = "(max-width: 700px)";
/** 窗口位置记忆 key */
const POSITION_STORAGE_KEY = "ouo:world-channel:window-position";
/** Header 高度 + 16px 间距（桌面入口与窗口最小 top） */
const HEADER_BOTTOM = 70;
const DESKTOP_TOP = HEADER_BOTTOM + 16;
const EDGE_GAP = 8;
/** SSE 断裂时的轮询间隔 */
const POLL_INTERVAL_MS = 5000;

const EMPTY_SUBSCRIBE = () => () => {};

/** 仅客户端渲染（portal 需要 document；避免 SSR hydration 不一致） */
function useIsClient(): boolean {
  return useSyncExternalStore(
    EMPTY_SUBSCRIBE,
    () => true,
    () => false
  );
}

interface WindowPosition {
  left: number;
  top: number;
}

function readStoredPosition(): WindowPosition | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(POSITION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<WindowPosition> | null;
    if (!parsed || typeof parsed.left !== "number" || typeof parsed.top !== "number") return null;
    if (!Number.isFinite(parsed.left) || !Number.isFinite(parsed.top)) return null;
    return { left: parsed.left, top: parsed.top };
  } catch {
    return null;
  }
}

function saveStoredPosition(position: WindowPosition) {
  try {
    window.localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(position));
  } catch {
    /* 隐私模式/配额不足时忽略 */
  }
}

function isMobileViewport(): boolean {
  return typeof window !== "undefined" && window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

/** 边界 clamp：窗口始终完整留在视口内（桌面 top 不低于 Header 下方 16px） */
function clampWindowPosition(left: number, top: number, width: number, height: number): WindowPosition {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const minTop = isMobileViewport() ? EDGE_GAP : DESKTOP_TOP;
  const maxLeft = Math.max(EDGE_GAP, vw - width - EDGE_GAP);
  const maxTop = Math.max(minTop, vh - height - EDGE_GAP);
  return {
    left: Math.min(Math.max(left, EDGE_GAP), maxLeft),
    top: Math.min(Math.max(top, minTop), maxTop),
  };
}

function compareMessages(a: WorldMessage, b: WorldMessage): number {
  return a.id - b.id;
}

/** 单条消息：左右布局 + 头像/名称/身份标签 + 富文本（历史 markdown 走 Markdown） */
function WorldMessageItem({
  message,
  isMe,
  parentName,
}: {
  message: WorldMessage;
  isMe: boolean;
  parentName?: string;
}) {
  const isHtml = !message.content_format || message.content_format === "html";
  const senderName = message.sender_name || "匿名";
  return (
    <article className={`world-msg${isMe ? " me" : ""}`} data-message-id={message.id}>
      <Link
        className="world-msg-avatar"
        href={`/users/${encodeURIComponent(message.sender_id)}`}
        aria-label={`${senderName} 的个人中心`}
      >
        <UserAvatar src={message.sender_avatar} userId={message.sender_id} />
      </Link>
      <div className="world-msg-main">
        <div className="world-msg-meta">
          <Link className="world-msg-name" href={`/users/${encodeURIComponent(message.sender_id)}`}>
            <UserName name={senderName} />
          </Link>
          {message.is_admin && (
            <span className="world-admin-chip" title="论坛管理团队">
              <i className="fa fa-shield" aria-hidden="true"></i>
              管理团队
            </span>
          )}
          <UserGuildChip name={message.guild_name} isLeader={message.is_leader} />
          <time className="world-msg-time" title={formatTime(message.created_at)} dateTime={message.created_at || undefined}>
            {timeAgo(message.created_at)}
          </time>
        </div>
        {parentName && (
          <div className="world-msg-reply">
            <i className="fa fa-reply" aria-hidden="true"></i> 回复 {parentName}
          </div>
        )}
        <div className="world-msg-bubble">
          {isHtml ? (
            <RichContent content={message.content} className="world-msg-content" />
          ) : (
            <Markdown content={message.content} className="world-msg-content" />
          )}
        </div>
      </div>
    </article>
  );
}

/** 加载骨架 */
function WorldMessagesSkeleton() {
  return (
    <div className="world-skeleton-list" aria-label="正在加载世界频道消息">
      {[0, 1, 2].map((i) => (
        <div className="world-skeleton" key={i}>
          <span className="world-skeleton-avatar"></span>
          <span className="world-skeleton-lines">
            <i></i>
            <i></i>
          </span>
        </div>
      ))}
    </div>
  );
}

export interface WorldChannelModalProps {
  /** 是否打开 */
  open: boolean;
  /** 关闭回调（桌面 X / ESC / 移动端返回键 / 顶部关闭） */
  onClose: () => void;
}

/**
 * 世界频道受控模态框。
 * 桌面为独立浮动窗口（拖拽 + 位置记忆），移动端为底部滑入近全屏。
 */
export default function WorldChannelModal({ open, onClose }: WorldChannelModalProps) {
  const isClient = useIsClient();
  const { user, userId } = useStore();
  const { toast } = useToast();

  const [messages, setMessages] = useState<WorldMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingNew, setPendingNew] = useState(0);
  const [live, setLive] = useState<boolean | null>(null);
  const [position, setPosition] = useState<WindowPosition | null>(null);
  const [dragging, setDragging] = useState(false);

  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<WorldMessage[]>([]);
  const lastIdRef = useRef(0);
  const hasMoreRef = useRef(false);
  const nearBottomRef = useRef(true);
  const loadingInitialRef = useRef(false);
  const loadingOlderRef = useRef(false);
  const loadSeqRef = useRef(0);
  const sendingRef = useRef(false);
  const cooldownUntilRef = useRef(0);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollInFlightRef = useRef(false);
  const sseRef = useRef<SSEConnection | null>(null);
  const openRef = useRef(open);
  const userIdRef = useRef(userId);
  const positionRef = useRef<WindowPosition | null>(null);
  const dragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    left: number;
    top: number;
  } | null>(null);
  const historyPushedRef = useRef(false);

  const onCloseRef = useRef(onClose);
  const requestCloseRef = useRef<() => void>(() => {});

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    openRef.current = open;
    userIdRef.current = userId;
  }, [open, userId]);

  /** 关闭入口：若为移动端压入的历史条目，先回退再关闭 */
  const requestClose = useCallback(() => {
    if (historyPushedRef.current) {
      historyPushedRef.current = false;
      try {
        window.history.back();
      } catch {
        /* 忽略 */
      }
    }
    onCloseRef.current();
  }, []);

  useEffect(() => {
    requestCloseRef.current = requestClose;
  }, [requestClose]);

  const applyPosition = useCallback((next: WindowPosition) => {
    positionRef.current = next;
    setPosition(next);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const el = scrollRef.current;
    if (!el) return;
    try {
      el.scrollTo({ top: el.scrollHeight, behavior });
    } catch {
      el.scrollTop = el.scrollHeight;
    }
    nearBottomRef.current = true;
    setPendingNew(0);
  }, []);

  /** 用首屏响应重置列表（最新 50 条） */
  const applyInitialPage = useCallback(
    (response: WorldMessagesResponse) => {
      const ordered = [...response.items].sort(compareMessages);
      messagesRef.current = ordered;
      setMessages(ordered);
      lastIdRef.current = ordered.length > 0 ? ordered[ordered.length - 1].id : 0;
      hasMoreRef.current = Boolean(response.has_more && response.next_before_id > 0);
      setHasMore(hasMoreRef.current);
      setPendingNew(0);
      nearBottomRef.current = true;
      requestAnimationFrame(() => scrollToBottom("auto"));
    },
    [scrollToBottom]
  );

  /** 首屏 50 条（打开时/重试/续传缺口重载） */
  const loadInitial = useCallback(async () => {
    if (loadingInitialRef.current) return;
    loadingInitialRef.current = true;
    const seq = ++loadSeqRef.current;
    setLoading(true);
    setError("");
    try {
      const response = await worldApi.list({ limit: WORLD_PAGE_SIZE });
      if (seq !== loadSeqRef.current) return;
      applyInitialPage(response);
    } catch (err) {
      if (seq !== loadSeqRef.current) return;
      setError(err instanceof ApiException ? err.message : "世界频道加载失败");
    } finally {
      if (seq === loadSeqRef.current) {
        loadingInitialRef.current = false;
        setLoading(false);
      }
    }
  }, [applyInitialPage]);

  /** 向上边界加载 200 条并保持滚动位置 */
  const loadOlder = useCallback(async () => {
    if (!openRef.current || loadingOlderRef.current || !hasMoreRef.current) return;
    const oldest = messagesRef.current[0]?.id;
    if (!oldest) return;
    loadingOlderRef.current = true;
    setLoadingOlder(true);
    const el = scrollRef.current;
    const previousHeight = el?.scrollHeight ?? 0;
    const previousTop = el?.scrollTop ?? 0;
    try {
      const response = await worldApi.list({ beforeId: oldest, limit: WORLD_HISTORY_SIZE });
      const older = [...response.items].sort(compareMessages);
      if (older.length > 0) {
        const known = new Set(messagesRef.current.map((m) => m.id));
        const merged = [...older.filter((m) => !known.has(m.id)), ...messagesRef.current].sort(compareMessages);
        messagesRef.current = merged;
        setMessages(merged);
      }
      hasMoreRef.current = Boolean(response.has_more && response.next_before_id > 0);
      setHasMore(hasMoreRef.current);
      requestAnimationFrame(() => {
        const scrubber = scrollRef.current;
        if (scrubber) scrubber.scrollTop = previousTop + (scrubber.scrollHeight - previousHeight);
      });
    } catch {
      toast("加载更早消息失败", "error");
    } finally {
      loadingOlderRef.current = false;
      setLoadingOlder(false);
    }
  }, [toast]);

  /** 追加消息（按 id 去重 + 排序；贴底或显示新消息提示） */
  const appendIncoming = useCallback(
    (incoming: WorldMessage[], options?: { forceBottom?: boolean }) => {
      if (incoming.length === 0) return 0;
      const map = new Map<number, WorldMessage>(messagesRef.current.map((m) => [m.id, m]));
      let added = 0;
      for (const message of incoming) {
        if (!message || typeof message.id !== "number" || map.has(message.id)) continue;
        map.set(message.id, message);
        added += 1;
      }
      if (added === 0) return 0;
      const next = [...map.values()].sort(compareMessages);
      messagesRef.current = next;
      setMessages(next);
      const newest = next[next.length - 1]?.id ?? 0;
      if (newest > lastIdRef.current) lastIdRef.current = newest;
      if (options?.forceBottom || nearBottomRef.current) {
        setPendingNew(0);
        requestAnimationFrame(() => scrollToBottom("auto"));
      } else {
        setPendingNew((count) => count + added);
      }
      return added;
    },
    [scrollToBottom]
  );

  /** 断线/发送后用 after_id 补拉 */
  const refreshAfter = useCallback(async () => {
    const lastId = lastIdRef.current;
    if (lastId <= 0) {
      await loadInitial();
      return;
    }
    const response = await worldApi.list({ afterId: lastId, limit: WORLD_MAX_LIMIT });
    appendIncoming(response.items);
  }, [appendIncoming, loadInitial]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  /** 轮询降级：每 5s 用 after_id 增量拉取（失败静默，下一次继续） */
  const pollOnce = useCallback(async () => {
    if (!openRef.current || pollInFlightRef.current) return;
    pollInFlightRef.current = true;
    try {
      const lastId = lastIdRef.current;
      if (lastId <= 0) {
        const response = await worldApi.list({ limit: WORLD_PAGE_SIZE });
        if (response.items.length > 0) applyInitialPage(response);
        return;
      }
      const response = await worldApi.list({ afterId: lastId, limit: WORLD_MAX_LIMIT });
      appendIncoming(response.items);
    } catch {
      /* 网络抖动：保持轮询，下一次重试 */
    } finally {
      pollInFlightRef.current = false;
    }
  }, [appendIncoming, applyInitialPage]);

  const startPolling = useCallback(() => {
    if (pollTimerRef.current !== null) return;
    void pollOnce();
    pollTimerRef.current = setInterval(() => void pollOnce(), POLL_INTERVAL_MS);
  }, [pollOnce]);

  /** 发送：前端 2 秒冷却 + 2000 字/9 图兜底校验；成功后 after_id 补拉保证即时可见 */
  const handleSubmit = useCallback(async () => {
    if (sendingRef.current) return;
    if (!userIdRef.current && !user) {
      toast("请先登录后参与世界频道", "warning");
      return;
    }
    const now = Date.now();
    if (now < cooldownUntilRef.current) {
      const seconds = Math.max(1, Math.ceil((cooldownUntilRef.current - now) / 1000));
      toast(`发言太快，请 ${seconds} 秒后再试`, "warning");
      return;
    }
    const html = draft.trim();
    if (!html) {
      toast("请先输入内容", "warning");
      return;
    }
    const imageCount = (html.match(/<img\b/gi) ?? []).length;
    if (imageCount > WORLD_MAX_IMAGES) {
      toast(`图片最多 ${WORLD_MAX_IMAGES} 张`, "warning");
      return;
    }
    sendingRef.current = true;
    setSending(true);
    try {
      await worldApi.create({ contentHtml: html });
      setDraft("");
      cooldownUntilRef.current = Date.now() + WORLD_SEND_COOLDOWN_MS;
      await refreshAfter();
      requestAnimationFrame(() => scrollToBottom("smooth"));
    } catch (err) {
      if (err instanceof ApiException) {
        if (err.status === 429) cooldownUntilRef.current = Date.now() + WORLD_SEND_COOLDOWN_MS;
        toast(err.message || "发送失败", "error");
      } else {
        toast("发送失败，请稍后重试", "error");
      }
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }, [draft, refreshAfter, scrollToBottom, toast, user]);

  // 打开：加载首屏 + 锁滚动 + 焦点圈定 + ESC 关闭
  useEffect(() => {
    if (!open || !isClient) return;
    // 微任务中启动，避免在 effect 同步阶段触发 setState（loading/ready）
    void Promise.resolve()
      .then(() => loadInitial())
      .finally(() => setReady(true));

    const previousActive = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => closeButtonRef.current?.focus(), 0);

    const onKeyDown = (event: KeyboardEvent) => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      if (event.key === "Escape") {
        // 编辑器内的链接弹窗/引用选择器优先处理 ESC
        if (dialog.querySelector(".donate-modal, .quote-picker-modal")) return;
        event.preventDefault();
        event.stopPropagation();
        requestCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      ).filter((el) => el.getClientRects().length > 0);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !dialog.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      previousActive?.focus?.();
    };
  }, [open, isClient, loadInitial]);

  // 关闭：停止 SSE / 轮询
  useEffect(() => {
    if (open) return;
    stopPolling();
    sseRef.current?.close();
    sseRef.current = null;
  }, [open, stopPolling]);

  // SSE：首屏就绪后按当前 last_id 续传；断线/心跳超时→轮询降级；重连成功→停轮询
  useEffect(() => {
    if (!open || !ready || !isClient) return;
    let stopped = false;
    const connection = createSSEConnection({
      url: `/world/stream?last_id=${lastIdRef.current}`,
      events: ["hello", "message", "heartbeat"],
      heartbeatTimeoutMs: 45_000,
      onOpen: () => {
        if (stopped) return;
        setLive(true);
        stopPolling();
      },
      onError: () => {
        if (stopped) return;
        setLive(false);
        startPolling();
      },
      onMessage: (data) => {
        if (stopped) return;
        appendIncoming([data as WorldMessage], { forceBottom: false });
      },
      onEvent: (event, data) => {
        if (stopped || event !== "hello") return;
        const hello = data as WorldHelloPayload | null;
        if (hello?.truncated) {
          toast("消息缺口过大，已重新载入最新消息", "info");
          void loadInitial();
        }
      },
    });
    sseRef.current = connection;
    return () => {
      stopped = true;
      connection.close();
      if (sseRef.current === connection) sseRef.current = null;
      setLive(null);
    };
  }, [open, ready, isClient, appendIncoming, loadInitial, startPolling, stopPolling, toast]);

  // 窗口位置：打开时读取 localStorage 并 clamp；resize 时重新 clamp
  useEffect(() => {
    if (!open || !isClient) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const width = dialog.offsetWidth || 400;
    const height = dialog.offsetHeight || 560;
    const stored = readStoredPosition();
    const fallbackLeft = window.innerWidth - width - 88;
    applyPosition(
      clampWindowPosition(stored?.left ?? fallbackLeft, stored?.top ?? DESKTOP_TOP, width, height)
    );
  }, [open, isClient, applyPosition]);

  useEffect(() => {
    if (!open || !isClient) return;
    const onResize = () => {
      const dialog = dialogRef.current;
      const current = positionRef.current;
      if (!dialog || !current) return;
      applyPosition(clampWindowPosition(current.left, current.top, dialog.offsetWidth, dialog.offsetHeight));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [open, isClient, applyPosition]);

  // 移动端 Android 返回键：先关闭世界频道（popstate）
  useEffect(() => {
    if (!open || !isClient || !isMobileViewport()) return;
    historyPushedRef.current = true;
    try {
      const currentState = window.history.state as Record<string, unknown> | null;
      window.history.pushState({ ...(currentState ?? {}), worldChannel: true }, "");
    } catch {
      historyPushedRef.current = false;
    }
    const onPopState = () => {
      if (!historyPushedRef.current) return;
      historyPushedRef.current = false;
      onCloseRef.current();
    };
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
      historyPushedRef.current = false;
    };
  }, [open, isClient]);

  // 回到前台时补拉一次，避免后台期间 SSE/轮询被浏览器节流造成缺口
  useEffect(() => {
    if (!open) return;
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void refreshAfter();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [open, refreshAfter]);

  const parentNames = useMemo(() => {
    const map = new Map<number, string>();
    for (const message of messages) map.set(message.id, message.sender_name || "匿名");
    return map;
  }, [messages]);

  const handleMessagesScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= 96;
    nearBottomRef.current = nearBottom;
    if (nearBottom) setPendingNew(0);
    if (el.scrollTop <= 48 && hasMoreRef.current) void loadOlder();
  }, [loadOlder]);

  const handleDragStart = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 || isMobileViewport()) return;
    const target = event.target as HTMLElement;
    if (target.closest("button, a, input, textarea, select")) return;
    const dialog = dialogRef.current;
    const current = positionRef.current;
    if (!dialog || !current) return;
    dragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      left: current.left,
      top: current.top,
    };
    setDragging(true);
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId);
    } catch {
      /* 指针已释放等场景，忽略 */
    }
    event.preventDefault();
  };

  const handleDragMove = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragStateRef.current;
    const dialog = dialogRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !dialog) return;
    applyPosition(
      clampWindowPosition(
        drag.left + event.clientX - drag.startX,
        drag.top + event.clientY - drag.startY,
        dialog.offsetWidth,
        dialog.offsetHeight
      )
    );
  };

  const handleDragEnd = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragStateRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragStateRef.current = null;
    setDragging(false);
    try {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    } catch {
      /* 忽略 */
    }
    if (positionRef.current) saveStoredPosition(positionRef.current);
  };

  if (!isClient || !open) return null;

  const windowStyle: CSSProperties | undefined = position
    ? { left: `${position.left}px`, top: `${position.top}px` }
    : undefined;

  return createPortal(
    <>
      <div className="world-channel-overlay" aria-hidden="true" />
      <section
        ref={dialogRef}
        className={`world-window${dragging ? " dragging" : ""}`}
        style={windowStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="world-channel-title"
        tabIndex={-1}
      >
        <div
          className="world-window-header"
          onPointerDown={handleDragStart}
          onPointerMove={handleDragMove}
          onPointerUp={handleDragEnd}
          onPointerCancel={handleDragEnd}
        >
          <div className="world-window-title-wrap">
            <span className="world-window-title" id="world-channel-title">
              <i className="fa fa-globe" aria-hidden="true"></i>
              世界频道
            </span>
            <span
              className={`world-live ${live === true ? "live" : live === false ? "polling" : "connecting"}`}
              title={live === true ? "SSE 实时推送" : live === false ? "SSE 不可用，已降级为轮询" : "正在连接实时推送"}
            >
              <i className="fa fa-circle" aria-hidden="true"></i>
              {live === true ? "实时" : live === false ? "轮询" : "连接中"}
            </span>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="world-window-close"
            aria-label="关闭世界频道"
            title="关闭（ESC）"
            onClick={requestClose}
          >
            <i className="fa fa-times" aria-hidden="true"></i>
          </button>
        </div>

        <div className="world-message-wrap">
          <div className="world-messages" ref={scrollRef} onScroll={handleMessagesScroll} aria-live="polite">
            {loading && messages.length === 0 ? (
              <WorldMessagesSkeleton />
            ) : error && messages.length === 0 ? (
              <div className="world-state world-state-error">
                <i className="fa fa-exclamation-circle" aria-hidden="true"></i>
                <span>{error}</span>
                <button type="button" className="world-state-btn" onClick={() => void loadInitial()}>
                  重新加载
                </button>
              </div>
            ) : messages.length === 0 ? (
              <div className="world-state">
                <i className="fa fa-comments-o" aria-hidden="true"></i>
                <span>世界频道还很安静，来说第一句话吧。</span>
              </div>
            ) : (
              <>
                {hasMore ? (
                  <button
                    type="button"
                    className="world-load-older"
                    disabled={loadingOlder}
                    onClick={() => void loadOlder()}
                  >
                    {loadingOlder ? (
                      <>
                        <i className="fa fa-spinner fa-spin" aria-hidden="true"></i> 加载中…
                      </>
                    ) : (
                      <>
                        <i className="fa fa-arrow-up" aria-hidden="true"></i> 加载更早消息
                      </>
                    )}
                  </button>
                ) : (
                  <div className="world-start">已加载全部消息</div>
                )}
                {messages.map((message) => (
                  <WorldMessageItem
                    key={message.id}
                    message={message}
                    isMe={Boolean(userId) && message.sender_id === userId}
                    parentName={message.parent_id ? parentNames.get(message.parent_id) : undefined}
                  />
                ))}
              </>
            )}
          </div>
          {pendingNew > 0 && (
            <button type="button" className="world-new-messages" onClick={() => scrollToBottom("smooth")}>
              <i className="fa fa-arrow-down" aria-hidden="true"></i>
              {pendingNew} 条新消息
            </button>
          )}
        </div>

        {error && messages.length > 0 && (
          <div className="world-error-inline">
            <i className="fa fa-exclamation-circle" aria-hidden="true"></i>
            <span>{error}</span>
            <button type="button" onClick={() => void loadInitial()}>
              重试
            </button>
          </div>
        )}

        <div className="world-input-bar">
          <div className="world-input-hint">
            <span className="world-input-channel">
              <i className="fa fa-globe" aria-hidden="true"></i> 世界频道
            </span>
            <span>
              {WORLD_MAX_CHARS} 字 / {WORLD_MAX_IMAGES} 图 · 2 秒内限发一条
              {!user && (
                <>
                  {" · "}
                  <Link href="/auth">登录</Link>后发言
                </>
              )}
            </span>
          </div>
          <CommentEditor
            value={draft}
            onChange={setDraft}
            onSubmit={() => void handleSubmit()}
            placeholder={user ? "在世界频道说点什么…" : "登录后即可参与世界频道…"}
            submitting={sending}
            maxChars={WORLD_MAX_CHARS}
            maxImages={WORLD_MAX_IMAGES}
            uploadScene="world_message"
            allowQuotePicker={false}
          />
        </div>
      </section>
    </>,
    document.body
  );
}

export interface WorldChannelLauncherProps {
  /** 点击打开世界频道 */
  onOpen: () => void;
  className?: string;
  /** 未读角标（可选；0 不显示） */
  badge?: number;
}

/** 桌面入口：固定视口右上角（Header 下方 16px）的纵向矩形按钮（≤700px 由 CSS 隐藏）。 */
export function WorldChannelLauncher({ onOpen, className = "", badge = 0 }: WorldChannelLauncherProps) {
  return (
    <button
      type="button"
      className={`world-channel-launcher${className ? ` ${className}` : ""}`}
      onClick={onOpen}
      aria-haspopup="dialog"
      aria-label="打开世界频道"
      title="打开世界频道"
    >
      <i className="fa fa-globe" aria-hidden="true"></i>
      <span className="world-channel-launcher-text">世界频道</span>
      {badge > 0 && (
        <span className="world-channel-launcher-badge" aria-label={`${badge} 条未读`}>
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </button>
  );
}

export interface WorldChannelEntryProps {
  defaultOpen?: boolean;
}

/** 便捷组合：内部管理 open 状态，渲染桌面入口按钮 + 受控模态框。 */
export function WorldChannelEntry({ defaultOpen = false }: WorldChannelEntryProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <>
      {!open && <WorldChannelLauncher onOpen={() => setOpen(true)} />}
      <WorldChannelModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
