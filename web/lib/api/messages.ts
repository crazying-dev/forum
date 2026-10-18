"use client";

// ===== 消息中心 API（Batch 2 契约 §2）=====
// - 点赞 / 评论 / 系统消息：cursor 分页
// - 管理团队：共享会话（用户与管理团队同房间），2 秒/用户限流
// - 已读：分类级 read + 聊天级 chat/read
// - SSE：/messages/stream（hello / unread / notification / message / heartbeat / error）

import { request } from "@/lib/api";
import { apiUrl } from "@/lib/api-base";

/** 消息条目中的操作者（点赞/评论者）。 */
export interface MessageActor {
  id: string;
  name: string;
  avatar: string;
}

/** 点赞消息：帖子被赞 / 评论被赞。 */
export interface LikeMessage {
  id: string;
  actor: MessageActor;
  target_type: "post" | "comment";
  target_id: string;
  post_id: string;
  post_title: string;
  comment_id: string;
  comment_excerpt: string;
  created_at: string;
}

/** 评论消息：帖子下的新评论 + 对我的回复。 */
export interface CommentMessage {
  id: string;
  actor: MessageActor;
  comment_id: string;
  post_id: string;
  post_title: string;
  excerpt: string;
  parent_id: string;
  created_at: string;
}

/** 系统消息：广播通知或 per-user system 通知。 */
export interface SystemMessage {
  id: number;
  type: string;
  title: string;
  body_html: string;
  link: string;
  created_at: string;
}

/** 管理团队聊天消息。 */
export interface ChatMessage {
  id: number;
  sender_type: "user" | "admin";
  sender_name: string;
  sender_avatar: string;
  admin_id: string;
  content_html: string;
  content_format: string;
  created_at: string;
}

/** 四类未读数（summary 与 SSE unread 事件共用）。 */
export interface MessageSummary {
  likes: number;
  comments: number;
  system: number;
  chat: number;
}

/** cursor 分页响应（items/has_more/next_cursor）。 */
export interface MessagePage<T> {
  success: boolean;
  items: T[];
  has_more: boolean;
  next_cursor: string;
}

/** summary 接口响应。 */
export interface MessageSummaryResponse extends MessageSummary {
  success: boolean;
}

/** 可标记已读的通知分类（chat 使用 /messages/chat/read）。 */
export type MessageCategory = "likes" | "comments" | "system";

/** POST /messages/read 请求体。 */
export interface MarkMessageReadInput {
  category: MessageCategory;
  /** RFC3339；服务端只前进不后退 */
  last_read_at: string;
}

/** POST /messages/chat 响应。 */
export interface SendChatResponse {
  success: boolean;
  id: number;
}

/** 管理团队消息分页（与通用 MessagePage 结构一致，单独命名便于阅读）。 */
export type ChatMessagePage = MessagePage<ChatMessage>;

// ---- SSE 事件载荷 ----

/** hello 事件。 */
export interface StreamHelloPayload {
  success: boolean;
  user_id: string;
  server_time: string;
}

/** unread 事件（字段与 summary 相同）。 */
export interface StreamUnreadPayload extends MessageSummary {
  success: boolean;
}

/** notification 事件里的通知条目（字段由 posts/comments 推送处组装）。 */
export interface StreamNotificationItem {
  id: number;
  type: string;
  actor_id?: string;
  actor_name?: string;
  actor_avatar?: string;
  target_type?: string;
  target_id?: string;
  comment_id?: string;
  post_id?: string;
  post_title?: string;
  excerpt?: string;
  comment_excerpt?: string;
  parent_id?: string;
  title?: string;
  body_html?: string;
  link?: string;
  created_at?: string;
}

/** notification 事件。 */
export interface StreamNotificationPayload {
  success: boolean;
  item: StreamNotificationItem;
}

/** message 事件（管理团队新消息）。 */
export interface StreamMessagePayload {
  success: boolean;
  item: ChatMessage;
}

/** heartbeat 事件。 */
export interface StreamHeartbeatPayload {
  success: boolean;
  ts: string;
}

/** 单页条数（服务端上限 50）。 */
export const MESSAGE_PAGE_SIZE = 20;

function normalizeLimit(limit: number): number {
  if (!Number.isFinite(limit) || limit <= 0) return MESSAGE_PAGE_SIZE;
  return Math.min(Math.floor(limit), 50);
}

/** 拼接 cursor/limit 查询串（cursor 为空表示第一页）。 */
function pageQuery(cursor?: string, limit = MESSAGE_PAGE_SIZE): string {
  const qs = new URLSearchParams();
  qs.set("limit", String(normalizeLimit(limit)));
  const c = (cursor ?? "").trim();
  if (c) qs.set("cursor", c);
  return qs.toString();
}

/** 消息中心 SSE 地址（浏览器端同源 base）。 */
export function messagesStreamUrl(): string {
  return apiUrl("/messages/stream");
}

/** 消息中心 API。 */
export const messagesApi = {
  /** 四类未读数。 */
  summary: () => request<MessageSummaryResponse>("/messages/summary"),

  /** 点赞消息（帖子赞 + 评论赞，按时间倒序 cursor 分页）。 */
  likes: (cursor?: string, limit = MESSAGE_PAGE_SIZE) =>
    request<MessagePage<LikeMessage>>(`/messages/likes?${pageQuery(cursor, limit)}`),

  /** 评论/回复消息。 */
  comments: (cursor?: string, limit = MESSAGE_PAGE_SIZE) =>
    request<MessagePage<CommentMessage>>(`/messages/comments?${pageQuery(cursor, limit)}`),

  /** 系统消息（广播 + per-user）。 */
  system: (cursor?: string, limit = MESSAGE_PAGE_SIZE) =>
    request<MessagePage<SystemMessage>>(`/messages/system?${pageQuery(cursor, limit)}`),

  /** 标记某类通知已读（只前进不后退）。 */
  read: (category: MessageCategory, lastReadAt: string) =>
    request<{ success: boolean }>("/messages/read", {
      method: "POST",
      body: JSON.stringify({ category, last_read_at: lastReadAt } satisfies MarkMessageReadInput),
    }),

  /** 管理团队会话（id 倒序 cursor 分页）。 */
  chat: (cursor?: string, limit = MESSAGE_PAGE_SIZE) =>
    request<ChatMessagePage>(`/messages/chat?${pageQuery(cursor, limit)}`),

  /** 发送管理团队消息（content_html 为存储态 HTML；服务端 2 秒/用户限流）。 */
  sendChat: (contentHtml: string) =>
    request<SendChatResponse>("/messages/chat", {
      method: "POST",
      body: JSON.stringify({ content_html: contentHtml }),
    }),

  /** 标记管理团队会话已读到指定消息 id。 */
  readChat: (lastMessageId: number) =>
    request<{ success: boolean }>("/messages/chat/read", {
      method: "POST",
      body: JSON.stringify({ last_message_id: lastMessageId }),
    }),
};
