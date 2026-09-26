import type { FeedItem, Post } from "./api";

/** 信息流条目（type=post）→ 帖子卡片模型（字段对齐 PostCard 所需） */
export function feedItemToPost(item: FeedItem): Post {
  return {
    id: item.id,
    user_id: item.user_id,
    title: item.title,
    summary: item.summary,
    category: item.category,
    likes: item.likes,
    views: item.views,
    comment_count: item.comment_count,
    created_at: item.created_at,
    user_name: item.user_name,
    user_avatar: item.user_avatar,
    guild_id: item.guild_id ?? null,
    guild_name: item.guild_name ?? undefined,
    guild_theme_color: item.guild_theme_color ?? undefined,
    user_guild_name: item.user_guild_name ?? undefined,
    user_guild_theme_color: item.user_guild_theme_color ?? undefined,
    user_is_leader: item.user_is_leader,
  };
}
