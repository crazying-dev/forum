"use client";

// ===== 消息中心 SSE =====
// - EventSource(apiUrl("/messages/stream"))，监听 hello / unread / notification / message / heartbeat
// - 断线手动重连（指数退避）；15s 无任何事件视为断线，开启 15s 轮询降级
// - notification / message 按事件 id 或业务 id 去重，重连重放不会重复追加

import { useEffect, useRef, useState } from "react";
import { apiUrl } from "@/lib/api-base";
import type {
  ChatMessage,
  MessageSummary,
  StreamHelloPayload,
  StreamNotificationItem,
  StreamNotificationPayload,
  StreamMessagePayload,
  StreamUnreadPayload,
} from "@/lib/api/messages";

/** SSE 连接状态。 */
export type MessageStreamStatus = "idle" | "connecting" | "open" | "reconnecting" | "degraded";

/** 15s 无事件视为断线（服务端 heartbeat 周期为 15s）。 */
const STREAM_IDLE_MS = 15000;
/** 降级轮询间隔。 */
const POLL_INTERVAL_MS = 15000;
/** 看门狗检查周期。 */
const WATCHDOG_INTERVAL_MS = 5000;

export interface MessageStreamHandlers {
  onHello?: (payload: StreamHelloPayload) => void;
  onUnread?: (counts: MessageSummary) => void;
  onNotification?: (item: StreamNotificationItem, eventId: string) => void;
  onMessage?: (item: ChatMessage, eventId: string) => void;
  onHeartbeat?: () => void;
  /** 降级轮询回调（summary + 当前列表/聊天刷新）。 */
  onPoll?: () => void;
  onStatusChange?: (status: MessageStreamStatus) => void;
}

function summaryOf(data: Partial<StreamUnreadPayload> | null | undefined): MessageSummary {
  return {
    likes: Number(data?.likes) || 0,
    comments: Number(data?.comments) || 0,
    system: Number(data?.system) || 0,
    chat: Number(data?.chat) || 0,
  };
}

/**
 * 消息中心 SSE hook。
 * enabled=false（未登录/已过期）时不建立连接；status 供页面展示连接状态。
 */
export function useMessageStream(enabled: boolean, handlers: MessageStreamHandlers): MessageStreamStatus {
  const [status, setStatus] = useState<MessageStreamStatus>(enabled ? "connecting" : "idle");
  const handlersRef = useRef(handlers);

  useEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    if (!enabled) {
      // 延后一个 tick，避免在 effect 内同步 setState
      const idleTimer = window.setTimeout(() => setStatus("idle"), 0);
      return () => window.clearTimeout(idleTimer);
    }

    let disposed = false;
    let source: EventSource | null = null;
    let reconnectTimer: number | undefined;
    let pollTimer: number | undefined;
    let reconnectAttempt = 0;
    let lastEventAt = Date.now();
    let degraded = false;

    // 持久事件（带 id）与聊天消息去重；上限 500，超出清理较早一半。
    const seen = new Set<string>();
    const remember = (key: string): boolean => {
      if (!key) return true;
      if (seen.has(key)) return false;
      seen.add(key);
      if (seen.size > 500) {
        const keys = Array.from(seen);
        for (const k of keys.slice(0, keys.length - 250)) seen.delete(k);
      }
      return true;
    };

    const emitStatus = (next: MessageStreamStatus) => {
      if (disposed) return;
      setStatus(next);
      handlersRef.current.onStatusChange?.(next);
    };

    const stopPolling = () => {
      degraded = false;
      if (pollTimer !== undefined) {
        window.clearInterval(pollTimer);
        pollTimer = undefined;
      }
    };

    const startPolling = () => {
      if (degraded || disposed) return;
      degraded = true;
      emitStatus("degraded");
      // 立即补一次，随后每 15s 轮询
      handlersRef.current.onPoll?.();
      pollTimer = window.setInterval(() => handlersRef.current.onPoll?.(), POLL_INTERVAL_MS);
    };

    const clearReconnect = () => {
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = undefined;
      }
    };

    const scheduleReconnect = () => {
      if (disposed || reconnectTimer !== undefined) return;
      const delay = Math.min(30000, 1000 * 2 ** Math.min(reconnectAttempt, 5));
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = undefined;
        connect();
      }, delay);
    };

    const handleEvent = (type: string, event: MessageEvent<string>) => {
      if (disposed) return;
      lastEventAt = Date.now();
      if (degraded) {
        stopPolling();
        emitStatus("open");
      }

      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!payload || typeof payload !== "object") return;

      if (type === "hello") {
        handlersRef.current.onHello?.(payload as StreamHelloPayload);
        return;
      }
      if (type === "unread") {
        handlersRef.current.onUnread?.(summaryOf(payload as StreamUnreadPayload));
        return;
      }
      if (type === "heartbeat") {
        handlersRef.current.onHeartbeat?.();
        return;
      }
      if (type === "notification") {
        const data = payload as StreamNotificationPayload;
        const item = data?.item;
        if (!item) return;
        const dedupeKey = `notification:${event.lastEventId || item.id}`;
        if (!remember(dedupeKey)) return;
        handlersRef.current.onNotification?.(item, event.lastEventId || String(item.id ?? ""));
        return;
      }
      if (type === "message") {
        const data = payload as StreamMessagePayload;
        const item = data?.item;
        if (!item || typeof item.id !== "number") return;
        const dedupeKey = `message:${event.lastEventId || item.id}`;
        if (!remember(dedupeKey)) return;
        handlersRef.current.onMessage?.(item, event.lastEventId || String(item.id));
      }
    };

    const connect = () => {
      if (disposed) return;
      clearReconnect();
      try {
        source?.close();
      } catch {
        /* 忽略 */
      }
      source = null;

      emitStatus(reconnectAttempt > 0 ? "reconnecting" : "connecting");
      try {
        // withCredentials：兼容 API 跨域部署时携带 forum_session Cookie
        source = new EventSource(apiUrl("/messages/stream"), { withCredentials: true });
      } catch {
        scheduleReconnect();
        return;
      }

      source.onopen = () => {
        if (disposed) return;
        lastEventAt = Date.now();
        reconnectAttempt = 0;
        emitStatus("open");
      };

      source.onerror = () => {
        if (disposed) return;
        try {
          source?.close();
        } catch {
          /* 忽略 */
        }
        source = null;
        if (Date.now() - lastEventAt > STREAM_IDLE_MS) startPolling();
        emitStatus("reconnecting");
        scheduleReconnect();
      };

      for (const type of ["hello", "unread", "notification", "message", "heartbeat", "error"] as const) {
        source.addEventListener(type, (event) => handleEvent(type, event as MessageEvent<string>));
      }
    };

    // 看门狗：15s 无任何事件 → 主动断开并进入轮询降级；同时尝试重连。
    const watchdogTimer = window.setInterval(() => {
      if (disposed) return;
      if (Date.now() - lastEventAt <= STREAM_IDLE_MS) return;
      if (source) {
        try {
          source.close();
        } catch {
          /* 忽略 */
        }
        source = null;
      }
      startPolling();
      scheduleReconnect();
    }, WATCHDOG_INTERVAL_MS);

    connect();

    return () => {
      disposed = true;
      clearReconnect();
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
      window.clearInterval(watchdogTimer);
      try {
        source?.close();
      } catch {
        /* 忽略 */
      }
      source = null;
    };
  }, [enabled]);

  return status;
}
