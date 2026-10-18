// 世界频道 API 客户端（后端契约 §3）：列表、发布、SSE 地址与共享常量。
"use client";

import { apiUrl } from "@/lib/api-base";
import { request } from "@/lib/api";

/** 消息 id（后端 int64，JSON 为 number）。 */
export type WorldMessageID = number;

/**
 * 世界频道消息（后端 `database.WorldMessage` 的对外形状）：
 * 发送者昵称/头像/会馆为发送时快照，历史消息不随改名或退馆变化。
 */
export interface WorldMessage {
  id: WorldMessageID;
  sender_id: string;
  sender_name: string;
  sender_avatar: string;
  /** 存储态 HTML（服务端已按富文本白名单净化） */
  content: string;
  /** 'html'（富文本）| 'markdown'（0018 迁移导入的历史数据） */
  content_format?: string;
  parent_id?: number | null;
  /** 会馆 UUID（未入馆为空串） */
  guild_id?: string;
  guild_name?: string;
  is_leader?: boolean;
  is_admin?: boolean;
  /** 管理团队成员 id（仅管理员消息下发，见后端 omitempty） */
  admin_id?: string;
  created_at?: string;
}

/** GET /world/messages 参数：before_id 向上翻页（降序），after_id 增量（升序）。 */
export interface WorldListParams {
  beforeId?: number | null;
  afterId?: number | null;
  limit?: number;
}

/** GET /world/messages 响应。items 在 before_id/缺省时降序，在 after_id 时升序。 */
export interface WorldMessagesResponse {
  success?: boolean;
  items: WorldMessage[];
  has_more: boolean;
  /** 继续向上翻页的游标（本页最小 id；无更多时为 0） */
  next_before_id: number;
}

/** POST /world/messages 请求体。 */
export interface WorldSendInput {
  contentHtml: string;
  parentId?: number | null;
}

/** POST /world/messages 响应。 */
export interface WorldSendResponse {
  success?: boolean;
  id: number;
}

/** SSE `hello` 事件数据（GET /world/stream）。 */
export interface WorldHelloPayload {
  server_time: string;
  heartbeat_seconds: number;
  /** 是否按 Last-Event-ID / last_id 续传 */
  resumed: boolean;
  /** 本次快照/补发条数 */
  count: number;
  /** 续传达到 500 条上限时为 true，客户端应整页重载补缺口 */
  truncated?: boolean;
}

/** SSE `heartbeat` 事件数据（后端每 15s 一次）。 */
export interface WorldHeartbeatPayload {
  time: string;
}

/** SSE 事件类型：hello（首包/续传信息）、message（消息增量）、heartbeat（15s 心跳）。 */
export type WorldStreamEvent =
  | { event: "hello"; data: WorldHelloPayload; id?: string | null }
  | { event: "message"; data: WorldMessage; id?: string | null }
  | { event: "heartbeat"; data: WorldHeartbeatPayload; id?: string | null };

/** 列表分页常量（后端 NormalizeWorldLimit：缺省 50、上限 500）。 */
export const WORLD_PAGE_SIZE = 50;
export const WORLD_HISTORY_SIZE = 200;
export const WORLD_MAX_LIMIT = 500;
/** SSE 首包历史条数（后端 worldSnapshotLimit）。 */
export const WORLD_SNAPSHOT_SIZE = 200;

/** 发布约束（与后端 worldMaxContentRunes / worldMaxImages / 2s 限流一致）。 */
export const WORLD_MAX_CHARS = 2000;
export const WORLD_MAX_IMAGES = 9;
export const WORLD_SEND_COOLDOWN_MS = 2000;

function normalizeLimit(limit?: number): number {
  if (!limit || !Number.isFinite(limit) || limit <= 0) return WORLD_PAGE_SIZE;
  return Math.min(Math.floor(limit), WORLD_MAX_LIMIT);
}

/** 世界频道 API。 */
export const worldApi = {
  /**
   * 消息列表：
   * - `beforeId`：该 id 之前的历史（降序，向上翻页）；
   * - `afterId`：该 id 之后的增量（升序，SSE 断线补拉/轮询降级）；
   * - 都不传：最新一页（降序）。
   */
  list: ({ beforeId, afterId, limit }: WorldListParams = {}) => {
    const qs = new URLSearchParams();
    if (beforeId && beforeId > 0) qs.set("before_id", String(Math.floor(beforeId)));
    if (afterId && afterId > 0) qs.set("after_id", String(Math.floor(afterId)));
    qs.set("limit", String(normalizeLimit(limit)));
    return request<WorldMessagesResponse>(`/world/messages?${qs.toString()}`);
  },

  /** 发布消息（需登录；后端 2 秒/用户限流、纯文本 1-2000 字、最多 9 图）。 */
  create: ({ contentHtml, parentId }: WorldSendInput) =>
    request<WorldSendResponse>("/world/messages", {
      method: "POST",
      body: JSON.stringify({
        content_html: contentHtml,
        ...(parentId && parentId > 0 ? { parent_id: parentId } : {}),
      }),
    }),

  /** SSE 地址（同源 API_BASE；lastId > 0 时携带 last_id 续传）。 */
  streamUrl: (lastId?: number | null) => worldStreamUrl(lastId),
};

/** 拼接世界频道 SSE URL（供 EventSource / lib/sse 使用）。 */
export function worldStreamUrl(lastId?: number | null): string {
  const id = lastId && lastId > 0 ? Math.floor(lastId) : 0;
  return apiUrl(`/world/stream${id > 0 ? `?last_id=${id}` : ""}`);
}
