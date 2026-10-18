"use client";

// ===== 消息中心 UI 类型 =====
// 把三类通知（赞/评论/系统）统一成 FeedItem，供「全部（聚合）」与单类列表复用。

import type {
  ChatMessage,
  CommentMessage,
  LikeMessage,
  MessageCategory,
  StreamNotificationItem,
  SystemMessage,
} from "@/lib/api/messages";

export type MessageType = "all" | "likes" | "comments" | "system" | "chat";

export interface MessageTypeMeta {
  label: string;
  icon: string;
  title: string;
  subtitle: string;
  empty: string;
}

/** 侧栏类型顺序：全部（聚合）/ 赞 / 评论 / 管理团队 / 系统。 */
export const MESSAGE_TYPE_ORDER: MessageType[] = ["all", "likes", "comments", "chat", "system"];

export const MESSAGE_TYPE_META: Record<MessageType, MessageTypeMeta> = {
  all: {
    label: "全部",
    icon: "fa-bell",
    title: "全部消息",
    subtitle: "赞、评论与系统通知聚合",
    empty: "暂无消息",
  },
  likes: {
    label: "赞",
    icon: "fa-heart",
    title: "收到的赞",
    subtitle: "帖子与评论收到的赞",
    empty: "还没有收到赞",
  },
  comments: {
    label: "评论",
    icon: "fa-comment",
    title: "评论与回复",
    subtitle: "帖子下的新评论与对你的回复",
    empty: "还没有评论消息",
  },
  chat: {
    label: "管理团队",
    icon: "fa-comments",
    title: "管理团队",
    subtitle: "与论坛管理团队的私密会话",
    empty: "还没有消息，给管理团队留言吧",
  },
  system: {
    label: "系统",
    icon: "fa-bullhorn",
    title: "系统通知",
    subtitle: "站内公告与系统提醒",
    empty: "暂无系统通知",
  },
};

/** URL `?type=` 校验（非法值回退到全部）。 */
export function isMessageType(value: string | null | undefined): value is MessageType {
  return value === "all" || value === "likes" || value === "comments" || value === "system" || value === "chat";
}

/** 三类通知统一后的列表条目。 */
export type FeedItem =
  | { kind: "like"; key: string; created_at: string; like: LikeMessage }
  | { kind: "comment"; key: string; created_at: string; comment: CommentMessage }
  | { kind: "system"; key: string; created_at: string; system: SystemMessage };

/** 赞消息去重键：同一操作者对同一目标只保留一条。 */
export function likeFeedKey(m: LikeMessage): string {
  return `like:${m.target_type}:${m.target_id}:${m.actor.id || m.actor.name}`;
}

/** 评论消息去重键：一条评论只通知一次。 */
export function commentFeedKey(m: CommentMessage): string {
  return `comment:${m.comment_id || m.id}`;
}

/** 系统消息去重键：广播/用户通知 id 可能重叠，带 type + 时间。 */
export function systemFeedKey(m: SystemMessage): string {
  return `system:${m.id}:${m.type}:${m.created_at}`;
}

export function likeToFeedItem(m: LikeMessage): FeedItem {
  return { kind: "like", key: likeFeedKey(m), created_at: m.created_at, like: m };
}

export function commentToFeedItem(m: CommentMessage): FeedItem {
  return { kind: "comment", key: commentFeedKey(m), created_at: m.created_at, comment: m };
}

export function systemToFeedItem(m: SystemMessage): FeedItem {
  return { kind: "system", key: systemFeedKey(m), created_at: m.created_at, system: m };
}

/** FeedItem 对应的已读分类。 */
export function categoryOfFeedItem(item: FeedItem): MessageCategory {
  if (item.kind === "like") return "likes";
  if (item.kind === "comment") return "comments";
  return "system";
}

/** 解析时间戳（非法值当作 0，排序垫底）。 */
export function feedItemTime(item: FeedItem): number {
  const t = Date.parse(item.created_at);
  return Number.isNaN(t) ? 0 : t;
}

/** 合并并去重（时间倒序；同一 key 保留先出现的版本）。 */
export function mergeFeedItems(existing: FeedItem[], incoming: FeedItem[]): FeedItem[] {
  if (incoming.length === 0) return existing;
  const map = new Map<string, FeedItem>();
  for (const item of existing) map.set(item.key, item);
  for (const item of incoming) if (!map.has(item.key)) map.set(item.key, item);
  return Array.from(map.values()).sort((a, b) => feedItemTime(b) - feedItemTime(a) || (a.key < b.key ? 1 : -1));
}

/** 某类型包含的通知分类。 */
export function categoriesOfType(type: MessageType): MessageCategory[] {
  if (type === "likes") return ["likes"];
  if (type === "comments") return ["comments"];
  if (type === "system") return ["system"];
  if (type === "all") return ["likes", "comments", "system"];
  return [];
}

/**
 * SSE notification 事件 → FeedItem。
 * 后端推送条目字段与列表接口不完全一致（例如点赞推送带 actor_*，系统推送带 title/body_html），
 * 此处做统一映射；无法识别的类型返回 null。
 */
export function notificationToFeedItem(item: StreamNotificationItem): FeedItem | null {
  const createdAt = item.created_at || new Date().toISOString();
  const actor = {
    id: item.actor_id || "",
    name: item.actor_name || "匿名",
    avatar: item.actor_avatar || "",
  };

  if (item.type === "post_like" || item.type === "comment_like") {
    const targetType: "post" | "comment" = item.target_type === "comment" || item.type === "comment_like" ? "comment" : "post";
    const targetId = item.target_id || (targetType === "post" ? item.post_id : item.comment_id) || "";
    return likeToFeedItem({
      id: `notif:${item.id}`,
      actor,
      target_type: targetType,
      target_id: targetId,
      post_id: item.post_id || "",
      post_title: item.post_title || "",
      comment_id: item.comment_id || "",
      comment_excerpt: item.comment_excerpt || item.excerpt || "",
      created_at: createdAt,
    });
  }

  if (item.type === "post_comment" || item.type === "comment_reply") {
    const commentId = item.comment_id || item.target_id || "";
    if (!commentId) return null;
    return commentToFeedItem({
      id: `notif:${item.id}`,
      actor,
      comment_id: commentId,
      post_id: item.post_id || "",
      post_title: item.post_title || "",
      excerpt: item.excerpt || item.comment_excerpt || "",
      parent_id: item.parent_id || "",
      created_at: createdAt,
    });
  }

  if (item.type === "system") {
    return systemToFeedItem({
      id: item.id,
      type: item.type,
      title: item.title || "系统通知",
      body_html: item.body_html || "",
      link: item.link || "",
      created_at: createdAt,
    });
  }

  return null;
}

/** 聊天消息按 id 去重并升序（旧 → 新）。 */
export function mergeChatMessages(existing: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  if (incoming.length === 0) return existing;
  const map = new Map<number, ChatMessage>();
  for (const item of existing) map.set(item.id, item);
  for (const item of incoming) map.set(item.id, item); // 新数据覆盖同 id（SSE 版通常更完整）
  return Array.from(map.values()).sort((a, b) => a.id - b.id);
}
