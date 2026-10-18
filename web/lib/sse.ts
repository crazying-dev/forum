// 通用 SSE 封装：同源 apiUrl + EventSource 监听 / 指数退避重连 / 心跳超时看门狗。
// 浏览器的 EventSource 自带断线重连，但无法感知「连接还在、服务端已不再推送」的半死连接；
// 这里统一为「出错即关闭 + 自行退避重建」，并用心跳超时兜底（世界频道心跳 15s）。
"use client";

import { apiUrl } from "./api-base";

// 统一从本模块暴露 API base 拼接函数，调用方无需再单独 import api-base。
export { apiUrl };

export interface SSEEventMeta {
  /** SSE event 名（message / hello / heartbeat …） */
  event: string;
  /** 事件 id（无 id 帧为 null） */
  id: string | null;
}

export type SSEEventHandler<T = unknown> = (data: T, meta: SSEEventMeta) => void;

export interface SSEOptions {
  /** 相对路径（自动拼 API_BASE）或完整 URL */
  url: string;
  /** 需要监听的具名事件；缺省监听 message */
  events?: string[];
  /** 任意事件（含 heartbeat）到达时回调，便于外部做「最后活跃」统计 */
  onEvent?: (event: string, data: unknown, meta: SSEEventMeta) => void;
  /** `message` 事件（最常见）的专用回调 */
  onMessage?: SSEEventHandler;
  onOpen?: () => void;
  /** 连接错误 / 心跳超时（会随后自动重连） */
  onError?: (error: Event | Error) => void;
  /** 心跳超时毫秒数，默认 45s（世界频道 15s 心跳 × 3） */
  heartbeatTimeoutMs?: number;
  /** 是否自动重连，默认 true */
  reconnect?: boolean;
  /** 重连最大退避，默认 30s（1s → 2s → 4s …） */
  maxReconnectDelayMs?: number;
  /** 跨域时是否携带 Cookie，默认 true（同源无影响） */
  withCredentials?: boolean;
  /** 是否 JSON.parse data；默认 true，失败时回退原始字符串 */
  parseJSON?: boolean;
}

export interface SSEConnection {
  /** 主动关闭（不再重连） */
  close: () => void;
  readonly closed: boolean;
  /** 原生 EventSource.readyState（0/1/2）；未创建时为 2 */
  readonly readyState: number;
}

const DEFAULT_HEARTBEAT_TIMEOUT_MS = 45_000;
const DEFAULT_MAX_RECONNECT_DELAY_MS = 30_000;

export function sseSupported(): boolean {
  return typeof window !== "undefined" && typeof window.EventSource !== "undefined";
}

/** 解析事件数据：默认 JSON，失败回退原始字符串。 */
function parseEventData(raw: string, parseJSON: boolean): unknown {
  if (!parseJSON) return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

/**
 * 创建一条 SSE 连接。返回控制器（组件卸载时务必 close，否则会持续重连）。
 * SSR 或浏览器不支持 EventSource 时返回空控制器并异步触发一次 onError。
 */
export function createSSEConnection(options: SSEOptions): SSEConnection {
  const {
    url,
    events,
    onEvent,
    onMessage,
    onOpen,
    onError,
    heartbeatTimeoutMs = DEFAULT_HEARTBEAT_TIMEOUT_MS,
    reconnect = true,
    maxReconnectDelayMs = DEFAULT_MAX_RECONNECT_DELAY_MS,
    withCredentials = true,
    parseJSON = true,
  } = options;

  let closed = false;
  let source: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;

  const clearReconnectTimer = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  const clearHeartbeatTimer = () => {
    if (heartbeatTimer) {
      clearTimeout(heartbeatTimer);
      heartbeatTimer = null;
    }
  };

  const disposeSource = () => {
    if (!source) return;
    source.onopen = null;
    source.onerror = null;
    source.onmessage = null;
    try {
      source.close();
    } catch {
      /* 已关闭，忽略 */
    }
    source = null;
  };

  const emit = (event: string, raw: string, id: string) => {
    const meta: SSEEventMeta = { event, id: id || null };
    const data = parseEventData(raw, parseJSON);
    onEvent?.(event, data, meta);
    if (event === "message") onMessage?.(data, meta);
  };

  const scheduleReconnect = (reason?: Event | Error) => {
    if (closed || !reconnect || reconnectTimer) return;
    clearHeartbeatTimer();
    disposeSource();
    const delay = Math.min(1000 * 2 ** attempt, maxReconnectDelayMs);
    attempt += 1;
    if (reason) onError?.(reason);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  };

  const armHeartbeat = () => {
    clearHeartbeatTimer();
    if (closed || heartbeatTimeoutMs <= 0) return;
    heartbeatTimer = setTimeout(() => {
      heartbeatTimer = null;
      scheduleReconnect(new Error("SSE heartbeat timeout"));
    }, heartbeatTimeoutMs);
  };

  const connect = () => {
    if (closed) return;
    if (!sseSupported()) {
      closed = true;
      onError?.(new Error("EventSource not supported"));
      return;
    }
    disposeSource();
    try {
      const target = /^https?:\/\//i.test(url) ? url : apiUrl(url);
      source = new EventSource(target, { withCredentials });
    } catch (error) {
      scheduleReconnect(error instanceof Error ? error : new Error(String(error)));
      return;
    }

    const es = source;
    es.onopen = () => {
      if (closed || source !== es) return;
      attempt = 0;
      onOpen?.();
      armHeartbeat();
    };
    es.onerror = (event) => {
      if (closed || source !== es) return;
      scheduleReconnect(event);
    };
    es.onmessage = (event: MessageEvent<string>) => {
      if (closed || source !== es) return;
      armHeartbeat();
      emit("message", event.data, event.lastEventId);
    };

    // 具名事件（hello / heartbeat / error …）逐个监听；message 已由 onmessage 统一处理。
    for (const name of events ?? []) {
      if (name === "message" || name === "open" || name === "error") continue;
      es.addEventListener(name, (event: Event) => {
        if (closed || source !== es) return;
        armHeartbeat();
        const message = event as MessageEvent<string>;
        emit(name, message.data, message.lastEventId ?? "");
      });
    }
  };

  connect();
  if (!closed) armHeartbeat();

  return {
    close: () => {
      closed = true;
      clearReconnectTimer();
      clearHeartbeatTimer();
      disposeSource();
    },
    get closed() {
      return closed;
    },
    get readyState() {
      return source ? source.readyState : 2;
    },
  };
}
