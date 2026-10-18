"use client";

// 世界频道：桌面入口按钮 + 受控独立的浮动窗口 / 移动端近全屏底部模态框。
// - 桌面：固定视口右上（Header 下方 16px）纵向矩形按钮；窗口标题栏可拖拽、右/下/右下角可 resize、
//   边界 clamp、localStorage 记忆位置与尺寸；纯悬浮窗（无遮罩/不锁滚动/不拦截底层页面）
// - 移动：底部滑入近全屏；顶部标题 + 关闭；底部输入条；Android 返回键优先关闭（popstate）
// - 消息：首屏 50、向上边界自动加载 200 条、SSE 增量去重、断线轮询降级、贴底/新消息提示
// - 传输：标题栏「实时 / 轮询」手动切换（localStorage 记忆），poll 不建立 SSE；SSE 失败仍自动降级
// - 输入：复用 CommentEditor（scene=world_message；2000 字 / 9 图 / 2 秒限流提示）

import Link from "next/link";
import {
  memo,
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
/** 窗口尺寸记忆 key */
const SIZE_STORAGE_KEY = "ouo:world-channel:window-size";
/** 传输模式记忆 key（'sse' | 'poll'） */
const TRANSPORT_STORAGE_KEY = "ouo:world-channel:transport";
/** Header 高度 + 16px 间距（桌面入口与窗口最小 top） */
const HEADER_BOTTOM = 70;
const DESKTOP_TOP = HEADER_BOTTOM + 16;
const EDGE_GAP = 8;
/** SSE 断裂时的轮询间隔 */
const POLL_INTERVAL_MS = 5000;
/** 桌面窗口默认尺寸（保持改造前约 408×620） */
const DEFAULT_WINDOW_WIDTH = 408;
const DEFAULT_WINDOW_HEIGHT = 620;
/** 桌面窗口最小尺寸 */
const MIN_WINDOW_WIDTH = 340;
const MIN_WINDOW_HEIGHT = 420;
/** 极端小视口兜底下限（避免尺寸出现负数/不可用） */
const MIN_RENDER_SIZE = 240;

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

interface WindowSize {
  width: number;
  height: number;
}

interface SizeLimits {
  minWidth: number;
  minHeight: number;
  maxWidth: number;
  maxHeight: number;
}

type TransportMode = "sse" | "poll";
type ResizeDirection = "e" | "s" | "se";

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

function readStoredSize(): WindowSize | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SIZE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<WindowSize> | null;
    if (!parsed || typeof parsed.width !== "number" || typeof parsed.height !== "number") return null;
    if (!Number.isFinite(parsed.width) || !Number.isFinite(parsed.height)) return null;
    return { width: parsed.width, height: parsed.height };
  } catch {
    return null;
  }
}

function saveStoredSize(size: WindowSize) {
  try {
    window.localStorage.setItem(SIZE_STORAGE_KEY, JSON.stringify(size));
  } catch {
    /* 隐私模式/配额不足时忽略 */
  }
}

function readStoredTransport(): TransportMode {
  if (typeof window === "undefined") return "sse";
  try {
    return window.localStorage.getItem(TRANSPORT_STORAGE_KEY) === "poll" ? "poll" : "sse";
  } catch {
    return "sse";
  }
}

function saveStoredTransport(mode: TransportMode) {
  try {
    window.localStorage.setItem(TRANSPORT_STORAGE_KEY, mode);
  } catch {
    /* 隐私模式/配额不足时忽略 */
  }
}

function isMobileViewport(): boolean {
  return typeof window !== "undefined" && window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

/** 当前视口允许的窗口尺寸区间（最大不超过视口减边距） */
function getSizeLimits(): SizeLimits {
  const vw = typeof window === "undefined" ? DEFAULT_WINDOW_WIDTH : window.innerWidth;
  const vh = typeof window === "undefined" ? DEFAULT_WINDOW_HEIGHT : window.innerHeight;
  const maxWidth = Math.max(MIN_RENDER_SIZE, vw - EDGE_GAP * 2);
  const maxHeight = Math.max(MIN_RENDER_SIZE, vh - DESKTOP_TOP - EDGE_GAP);
  return {
    minWidth: Math.min(MIN_WINDOW_WIDTH, maxWidth),
    minHeight: Math.min(MIN_WINDOW_HEIGHT, maxHeight),
    maxWidth,
    maxHeight,
  };
}

/** 按视口边界 clamp 尺寸（打开时读取 localStorage 后使用） */
function clampWindowSize(width: number, height: number): WindowSize {
  const limits = getSizeLimits();
  return {
    width: Math.round(Math.min(Math.max(width, limits.minWidth), limits.maxWidth)),
    height: Math.round(Math.min(Math.max(height, limits.minHeight), limits.maxHeight)),
  };
}

/** 拖拽 resize：除视口上限外，还保证右/下边缘不越界（左上角锚定） */
function clampResizeSize(width: number, height: number, left: number, top: number): WindowSize {
  const limits = getSizeLimits();
  const availableWidth = Math.max(limits.minWidth, window.innerWidth - Math.max(left, EDGE_GAP) - EDGE_GAP);
  const availableHeight = Math.max(limits.minHeight, window.innerHeight - Math.max(top, DESKTOP_TOP) - EDGE_GAP);
  return {
    width: Math.round(Math.min(Math.max(width, limits.minWidth), Math.min(limits.maxWidth, availableWidth))),
    height: Math.round(Math.min(Math.max(height, limits.minHeight), Math.min(limits.maxHeight, availableHeight))),
  };
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
const WorldMessageItem = memo(function WorldMessageItem({
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
});

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
 * 桌面为独立浮动窗口（拖拽 + 可缩放 + 位置/尺寸记忆，不阻断底层页面），移动端为底部滑入近全屏。
 * 标题栏可手动切换实时（SSE）/ 轮询（5s GET），选择会持久化。
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
  const [transport, setTransport] = useState<TransportMode>(() => readStoredTransport());
  /** 仅用于「已降级时再次点击实时」强制重建 SSE */
  const [transportRetry, setTransportRetry] = useState(0);
  const [isMobile, setIsMobile] = useState<boolean>(() => isMobileViewport());
  const [position, setPosition] = useState<WindowPosition | null>(null);
  const [size, setSize] = useState<WindowSize | null>(null);
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);

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
  const sizeRef = useRef<WindowSize | null>(null);
  const dragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    left: number;
    top: number;
  } | null>(null);
  const resizeStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    width: number;
    height: number;
    direction: ResizeDirection;
  } | null>(null);
  /** 当前 resize 的 window 级监听清理函数（避免指针移出窗口后丢失 pointerup） */
  const resizeCleanupRef = useRef<(() => void) | null>(null);
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

  // 响应式断点：仅移动端启用遮罩 / 锁滚动 / 焦点圈定；桌面保持纯悬浮窗
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MEDIA_QUERY);
    const onChange = () => setIsMobile(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    // 兼容部分内嵌 WebView / 设备模拟环境：窗口尺寸变化时也重新判定断点
    window.addEventListener("resize", onChange);
    return () => {
      mq.removeEventListener("change", onChange);
      window.removeEventListener("resize", onChange);
    };
  }, []);

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

  const applySize = useCallback((next: WindowSize) => {
    sizeRef.current = next;
    setSize(next);
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

  // 打开：加载首屏（桌面/移动端一致）
  useEffect(() => {
    if (!open || !isClient) return;
    // 微任务中启动，避免在 effect 同步阶段触发 setState（loading/ready）
    void Promise.resolve()
      .then(() => loadInitial())
      .finally(() => setReady(true));
  }, [open, isClient, loadInitial]);

  // ESC 关闭：桌面悬浮窗与移动端模态框都保留
  useEffect(() => {
    if (!open || !isClient) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      // 编辑器内的链接弹窗/引用选择器优先处理 ESC
      if (dialog.querySelector(".donate-modal, .quote-picker-modal")) return;
      // 桌面非模态：焦点在别的弹窗/控件上时不抢 ESC（避免吞掉其他 Modal 的关闭）
      const active = document.activeElement;
      if (active && active !== document.body && !dialog.contains(active)) return;
      event.preventDefault();
      event.stopPropagation();
      requestCloseRef.current();
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [open, isClient]);

  // 仅移动端：锁 body 滚动 + 自动聚焦 + Tab 焦点圈定（桌面不拦截底层页面）
  useEffect(() => {
    if (!open || !isClient || !isMobile) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previousActive = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => closeButtonRef.current?.focus(), 0);

    const onKeyDown = (event: KeyboardEvent) => {
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
  }, [open, isClient, isMobile]);

  // 关闭：停止 SSE / 轮询
  useEffect(() => {
    if (open) return;
    stopPolling();
    sseRef.current?.close();
    sseRef.current = null;
    resizeCleanupRef.current?.();
    resizeStateRef.current = null;
    dragStateRef.current = null;
    // 避免在 effect 同步阶段 setState；SSE effect 的 cleanup 会同步把 live 置空
    queueMicrotask(() => {
      setResizing(false);
      setDragging(false);
    });
  }, [open, stopPolling]);

  // 连接管理：poll 只轮询（不建立 SSE）；sse 建立 SSE，断线/心跳超时自动降级轮询，重连成功停轮询
  useEffect(() => {
    if (!open || !ready || !isClient) return;

    if (transport === "poll") {
      // 手动 poll：只轮询，绝不建立 SSE（live 状态由切换 handler 置为 false）
      startPolling();
      return () => stopPolling();
    }

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
      stopPolling();
      setLive(null);
    };
  }, [
    open,
    ready,
    isClient,
    transport,
    transportRetry,
    appendIncoming,
    loadInitial,
    startPolling,
    stopPolling,
    toast,
  ]);

  // 桌面窗口尺寸/位置：打开时读取 localStorage 并 clamp（移动端保持整屏 sheet，不写内联宽高）
  useEffect(() => {
    if (!open || !isClient || isMobile) return;
    const storedSize = readStoredSize();
    const nextSize = clampWindowSize(
      storedSize?.width ?? DEFAULT_WINDOW_WIDTH,
      storedSize?.height ?? DEFAULT_WINDOW_HEIGHT
    );
    const stored = readStoredPosition();
    const fallbackLeft = window.innerWidth - nextSize.width - 88;
    // 用微任务而不是 rAF：后台标签页/无焦点窗口会暂停 rAF，导致尺寸/位置记忆不生效；
    // 微任务仍会在本次渲染前执行，且避免在 effect 同步阶段直接 setState。
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      applySize(nextSize);
      applyPosition(
        clampWindowPosition(stored?.left ?? fallbackLeft, stored?.top ?? DESKTOP_TOP, nextSize.width, nextSize.height)
      );
    });
    return () => {
      cancelled = true;
    };
  }, [open, isClient, isMobile, applyPosition, applySize]);

  // 视口变化：重新 clamp 尺寸与位置（不写入 storage，避免污染用户设定）
  useEffect(() => {
    if (!open || !isClient || isMobile) return;
    const onResize = () => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      const currentSize = sizeRef.current;
      const nextSize = clampWindowSize(
        currentSize?.width ?? dialog.offsetWidth,
        currentSize?.height ?? dialog.offsetHeight
      );
      if (!currentSize || nextSize.width !== currentSize.width || nextSize.height !== currentSize.height) {
        applySize(nextSize);
      }
      const current = positionRef.current;
      if (current) {
        applyPosition(clampWindowPosition(current.left, current.top, nextSize.width, nextSize.height));
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [open, isClient, isMobile, applyPosition, applySize]);

  // 移动端 Android 返回键：先关闭世界频道（popstate）
  useEffect(() => {
    if (!open || !isClient || !isMobile) return;
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
      // 仅在“仍打开且已跨出移动端断点”时回退，清掉为返回键压入的历史条目；
      // 正常关闭/组件卸载不在这里 back，避免打断路由导航。
      if (historyPushedRef.current && openRef.current && !isMobileViewport()) {
        historyPushedRef.current = false;
        try {
          window.history.back();
        } catch {
          /* 忽略 */
        }
      } else {
        historyPushedRef.current = false;
      }
    };
  }, [open, isClient, isMobile]);

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
    if (event.button !== 0 || isMobile) return;
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
    // 丢失 pointerup（系统弹窗/窗口失焦）时兜底结束拖拽，避免窗口粘在鼠标上
    if (event.buttons === 0) {
      handleDragEnd(event);
      return;
    }
    applyPosition(
      clampWindowPosition(
        drag.left + event.clientX - drag.startX,
        drag.top + event.clientY - drag.startY,
        sizeRef.current?.width ?? dialog.offsetWidth,
        sizeRef.current?.height ?? dialog.offsetHeight
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

  /** 手动切换传输模式：persist + 立即反馈 + 补拉缺口（实际连接由 effect 管理） */
  const handleTransportSelect = useCallback(
    (mode: TransportMode) => {
      if (mode === transport) {
        // 已降级为轮询时再次点击「实时」→ 重建 SSE 重试
        if (mode === "sse" && live === false) {
          setLive(null);
          setTransportRetry((value) => value + 1);
          void refreshAfter().catch(() => {});
        }
        return;
      }
      saveStoredTransport(mode);
      setTransport(mode);
      setLive(mode === "poll" ? false : null);
      // poll 分支的 startPolling 会立即 pollOnce，无需额外刷新；sse 需要补拉断档
      if (mode === "sse") void refreshAfter().catch(() => {});
    },
    [live, refreshAfter, transport]
  );

  const handleResizeStart = (event: ReactPointerEvent<HTMLSpanElement>, direction: ResizeDirection) => {
    if (isMobile || event.button !== 0) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (!positionRef.current) applyPosition({ left: rect.left, top: rect.top });
    resizeStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      width: sizeRef.current?.width ?? rect.width,
      height: sizeRef.current?.height ?? rect.height,
      direction,
    };
    setResizing(true);

    const cleanup = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onEnd);
      window.removeEventListener("pointercancel", onEnd);
      if (resizeCleanupRef.current === cleanup) resizeCleanupRef.current = null;
    };

    const onMove = (moveEvent: PointerEvent) => {
      const resize = resizeStateRef.current;
      if (!resize || moveEvent.pointerId !== resize.pointerId) return;
      if (moveEvent.buttons === 0) {
        onEnd(moveEvent);
        return;
      }
      const position = positionRef.current ?? { left: EDGE_GAP, top: DESKTOP_TOP };
      const deltaX = moveEvent.clientX - resize.startX;
      const deltaY = moveEvent.clientY - resize.startY;
      const rawWidth = resize.direction === "s" ? resize.width : resize.width + deltaX;
      const rawHeight = resize.direction === "e" ? resize.height : resize.height + deltaY;
      applySize(clampResizeSize(rawWidth, rawHeight, position.left, position.top));
      moveEvent.preventDefault();
    };

    const onEnd = (endEvent: PointerEvent) => {
      const resize = resizeStateRef.current;
      if (resize && endEvent.pointerId !== resize.pointerId) return;
      resizeStateRef.current = null;
      setResizing(false);
      cleanup();
      const finalSize = sizeRef.current;
      if (finalSize) saveStoredSize(finalSize);
      const position = positionRef.current;
      if (finalSize && position) {
        const nextPosition = clampWindowPosition(position.left, position.top, finalSize.width, finalSize.height);
        if (nextPosition.left !== position.left || nextPosition.top !== position.top) {
          applyPosition(nextPosition);
          saveStoredPosition(nextPosition);
        }
      }
    };

    // 先清理上一次可能残留的监听，再挂 window 级监听（指针移出窗口也能继续 resize）
    resizeCleanupRef.current?.();
    resizeCleanupRef.current = cleanup;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onEnd);
    window.addEventListener("pointercancel", onEnd);

    try {
      event.currentTarget.setPointerCapture?.(event.pointerId);
    } catch {
      /* 指针已释放等场景，忽略 */
    }
    event.preventDefault();
    event.stopPropagation();
  };

  useEffect(
    () => () => {
      resizeCleanupRef.current?.();
      resizeCleanupRef.current = null;
    },
    []
  );

  if (!isClient || !open) return null;

  // 状态 chip：手动 poll 与自动降级都显示「轮询」，但 title 区分原因
  const manualPoll = transport === "poll";
  const liveStateClass = manualPoll || live === false ? "polling" : live === true ? "live" : "connecting";
  const liveStateLabel = manualPoll || live === false ? "轮询" : live === true ? "实时" : "连接中";
  const liveStateTitle = manualPoll
    ? "已手动切换为轮询（每 5 秒拉取一次，不建立 SSE 连接）"
    : live === true
      ? "SSE 实时推送"
      : live === false
        ? "SSE 连接失败，已自动降级为轮询（每 5 秒拉取一次）"
        : "正在连接实时推送";

  // 桌面：内联尺寸/位置；移动端完全交给 CSS（底部整屏 sheet，不应用内联宽高）
  const windowStyle: CSSProperties | undefined = isMobile
    ? undefined
    : {
        ...(position ? { left: `${position.left}px`, top: `${position.top}px` } : {}),
        ...(size ? { width: `${size.width}px`, height: `${size.height}px` } : {}),
      };

  return createPortal(
    <>
      {isMobile && <div className="world-channel-overlay" aria-hidden="true" />}
      <section
        ref={dialogRef}
        className={`world-window${dragging ? " dragging" : ""}${resizing ? " resizing" : ""}`}
        style={windowStyle}
        role="dialog"
        aria-modal={isMobile ? true : undefined}
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
            <span className={`world-live ${liveStateClass}`} title={liveStateTitle}>
              <i className="fa fa-circle" aria-hidden="true"></i>
              {liveStateLabel}
            </span>
            <div className="world-transport-switch" role="group" aria-label="消息传输模式">
              <button
                type="button"
                className="world-transport-btn"
                aria-pressed={transport === "sse"}
                title="实时推送（SSE）：自动重连，连接失败时自动降级为轮询"
                onClick={() => handleTransportSelect("sse")}
              >
                实时
              </button>
              <button
                type="button"
                className="world-transport-btn"
                aria-pressed={transport === "poll"}
                title="轮询模式：每 5 秒拉取一次，不建立 SSE 连接"
                onClick={() => handleTransportSelect("poll")}
              >
                轮询
              </button>
            </div>
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

        {!isMobile && (
          <>
            <span
              className="world-resize-handle world-resize-e"
              aria-hidden="true"
              onPointerDown={(event) => handleResizeStart(event, "e")}
            />
            <span
              className="world-resize-handle world-resize-s"
              aria-hidden="true"
              onPointerDown={(event) => handleResizeStart(event, "s")}
            />
            <span
              className="world-resize-handle world-resize-se"
              aria-hidden="true"
              onPointerDown={(event) => handleResizeStart(event, "se")}
            />
          </>
        )}
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
