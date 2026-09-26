// API 客户端层：统一 fetch + 类型 + 错误处理
"use client";

export type ApiError = { message: string; status: number };

export class ApiException extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface ApiResponse<T = unknown> {
  success: boolean;
  message?: string;
  [key: string]: unknown;
}

export interface User {
  id: string;
  name: string;
  avatar: string;
  email?: string;
  gender?: number;
  age?: string;
  intro?: string;
  vip?: string;
  prefix?: string;
  email_verified?: number;
  created_at?: string;
}

export interface Post {
  id: string;
  user_id: string;
  title: string;
  content?: string;
  summary?: string;
  category: string;
  likes: number;
  views: number;
  comment_count?: number;
  status?: number;
  created_at?: string;
  user_name: string;
  user_avatar: string;
  // 会馆（null/undefined 表示公共空间）
  guild_id?: number | null;
  guild_name?: string;
  guild_theme_color?: string;
  // 作者身份标签（后端契约）：所属会馆 + 是否馆长
  user_guild_name?: string | null;
  user_guild_theme_color?: string | null;
  user_is_leader?: boolean;
}

export interface Comment {
  id: string;
  post_id: string;
  user_id: string;
  content: string;
  parent_id?: string | null;
  likes: number;
  liked_by_me?: boolean;
  created_at?: string;
  user_name: string;
  user_avatar: string;
  // 作者身份标签（后端契约）：所属会馆 + 是否馆长
  user_guild_name?: string | null;
  user_guild_theme_color?: string | null;
  user_is_leader?: boolean;
}

// 评论列表项：带所属帖子标题（个人中心评论列表用）
export interface ReplyItem extends Comment {
  post_title?: string;
}

// ---- 会馆 ----

// 馆长摘要（列表/详情共用）
export interface GuildLeader {
  id: string;
  name: string;
  avatar: string;
  intro: string;
  bio?: string;
}

// 会馆列表项
export interface GuildListItem {
  id: number;
  uuid: string;
  slug: string;
  name: string;
  intro: string;
  theme_color: string;
  member_count: number;
  has_logo: boolean;
  logo_version: number;
  created_at?: string;
  leader?: GuildLeader | null;
}

// 会馆自定义分类
export interface GuildCategory {
  id: number;
  guild_id: number;
  name: string;
  sort: number;
}

// 会馆公告
export interface GuildAnnouncement {
  id: number;
  guild_id: number;
  content: string;
  created_at?: string;
  updated_at?: string;
}

// 会馆详情（logo_file_id 为管理端内部字段，接口不下发）
export interface GuildDetail {
  id: number;
  uuid: string;
  slug: string;
  name: string;
  intro: string;
  logo_version: number;
  theme_color: string;
  leader_user_id?: string | null;
  leader_bio?: string;
  created_at?: string;
  updated_at?: string;
  leader?: GuildLeader | null;
  member_count: number;
  has_logo: boolean;
  categories: GuildCategory[];
  announcements: GuildAnnouncement[];
}

// 当前用户与会馆的关系（详情页；未登录为 null）
export interface GuildMyState {
  is_member: boolean;
  is_leader: boolean;
  has_pending_request: boolean;
  request_id?: number;
}

// 动态流条目（帖子或文章）
export interface FeedItem {
  type: "post" | "article";
  id: string;
  title: string;
  summary: string;
  category: string;
  likes: number;
  views: number;
  comment_count: number;
  created_at?: string;
  updated_at?: string;
  user_id: string;
  user_name: string;
  user_avatar: string;
  guild_id?: number | null;
  guild_name?: string | null;
  guild_theme_color?: string | null;
  user_guild_name?: string | null;
  user_guild_theme_color?: string | null;
  user_is_leader?: boolean;
  author?: GuildLeader | null;
  participants_count: number;
}

// 文章参与人
export interface GuildArticleParticipant {
  user_id: string;
  user_name: string;
  avatar: string;
}

// 会馆文章
export interface GuildArticle {
  id: string;
  guild_id: number;
  title: string;
  summary: string;
  content?: string;
  author_user_id?: string;
  views: number;
  created_at?: string;
  updated_at?: string;
  author?: GuildLeader | null;
  participants: GuildArticleParticipant[];
  guild_slug?: string;
  guild_name?: string;
  guild_theme_color?: string;
}

export interface UserBrief {
  id: string;
  name: string;
  avatar: string;
  vip?: string;
  prefix?: string;
  intro?: string;
  is_self?: boolean;
  is_following?: boolean;
}

// 用户所在会馆概要（个人中心标签）
export interface GuildMembership {
  id: number;
  uuid: string;
  slug: string;
  name: string;
  theme_color: string;
  is_leader: boolean;
}

export interface SearchResult {
  keyword: string;
  page?: number;
  page_size?: number;
  posts?: Post[];
  posts_total?: number;
  posts_has_more?: boolean;
  users?: UserBrief[];
  users_total?: number;
  users_has_more?: boolean;
}

const API_BASE = "/api/v1";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = API_BASE + path;
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  const res = await fetch(url, {
    credentials: "include",
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || (data && data.success === false)) {
    throw new ApiException(res.status, (data as ApiResponse).message || `请求失败 (${res.status})`);
  }
  return data as T;
}

// ---- 认证 ----
export const authApi = {
  login: (name: string, password: string, remember = true) =>
    request<{ id: string }>("/auth/login", { method: "POST", body: JSON.stringify({ name, password, remember }) }),
  logout: () => request<{ success: boolean }>("/auth/logout", { method: "POST" }),
  register: (name: string, email: string, password: string, code: string) =>
    request<{ id: string }>("/auth/register", { method: "POST", body: JSON.stringify({ name, email, password, code }) }),
  sendRegisterCode: (email: string) =>
    request<{ message: string }>("/auth/register/code", { method: "POST", body: JSON.stringify({ email }) }),
  sendResetCode: (email: string) =>
    request<{ message: string }>("/auth/password/reset/code", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (email: string, code: string, password: string) =>
    request<{ message: string }>("/auth/password/reset", { method: "POST", body: JSON.stringify({ email, code, password }) }),
};

// ---- 用户 ----
export const userApi = {
  me: () => request<{ user?: User; guild?: GuildMembership | null; is_leader?: boolean }>("/users/me"),
  profile: (id: string) =>
    request<{
      user: User;
      stats?: { post_count: number; total_likes: number; total_views: number };
      follow_stats?: { following_count: number; follower_count: number };
      is_following?: boolean;
      is_self?: boolean;
      guild?: GuildMembership | null;
      is_leader?: boolean;
    }>(`/users/${id}`),
  posts: (id: string, page = 1, pageSize = 20) =>
    request<{ posts: Post[]; page: number; page_size: number }>(`/users/${id}/posts?page=${page}&page_size=${pageSize}`),
  favorites: (id: string, page = 1, pageSize = 20) =>
    request<{ posts: Post[] }>(`/users/${id}/favorites?page=${page}&page_size=${pageSize}`),
  follow: (id: string) => request<{ following: boolean }>(`/users/${id}/follow`, { method: "POST" }),
  following: (id: string, page = 1, pageSize = 20) =>
    request<{ users: UserBrief[] }>(`/users/${id}/following?page=${page}&page_size=${pageSize}`),
  followers: (id: string, page = 1, pageSize = 20) =>
    request<{ users: UserBrief[] }>(`/users/${id}/followers?page=${page}&page_size=${pageSize}`),
  comments: (id: string, page = 1, pageSize = 20) =>
    request<{ comments: ReplyItem[]; total: number }>(`/users/${id}/comments?page=${page}&page_size=${pageSize}`),
  updateMe: (data: Record<string, unknown>) =>
    request<{ success: boolean }>("/users/me", { method: "PATCH", body: JSON.stringify(data) }),
  replies: (page = 1, pageSize = 50) =>
    request<{ replies: Comment[]; total: number }>(`/users/me/replies?page=${page}&page_size=${pageSize}`),
  verifyEmail: () => request<{ message: string }>("/users/me/verify-email", { method: "POST" }),
  verifyEmailConfirm: (code: string) =>
    request<{ message: string }>("/users/me/verify-email/confirm", { method: "POST", body: JSON.stringify({ code }) }),
  uploadAvatar: (file: File) => {
    const fd = new FormData();
    fd.append("avatar", file);
    return request<{ avatar: string }>("/users/me/avatar", { method: "POST", body: fd });
  },
};

// ---- 帖子 ----
export const postApi = {
  list: (page = 1, pageSize = 20, category = "") =>
    request<{ posts: Post[]; page: number; page_size: number }>(`/posts?page=${page}&page_size=${pageSize}${category ? `&category=${encodeURIComponent(category)}` : ""}`),
  random: () => request<{ posts: Post[] }>("/posts/random"),
  detail: (id: string) =>
    request<{ post: Post; comments: Comment[]; liked: boolean; favorited: boolean }>(`/posts/${id}`),
  // guildUuid 传入时帖子归属该会馆（需为该馆成员），否则发到公共空间
  create: (title: string, content: string, category: string, guildUuid?: string) =>
    request<{ id: string }>("/posts", {
      method: "POST",
      body: JSON.stringify(guildUuid ? { title, content, category, guild_uuid: guildUuid } : { title, content, category }),
    }),
  like: (id: string) => request<{ liked: boolean; likes: number }>(`/posts/${id}/like`, { method: "POST" }),
  favorite: (id: string) => request<{ favorited: boolean }>(`/posts/${id}/favorite`, { method: "POST" }),
  remove: (id: string) => request<{ success: boolean }>(`/posts/${id}/delete`, { method: "POST" }),
  report: (id: string, reason: string, detail = "") =>
    request<{ success: boolean }>(`/posts/${id}/report`, { method: "POST", body: JSON.stringify({ reason, detail }) }),
  comments: (id: string, page = 1, pageSize = 50) =>
    request<{ comments: Comment[] }>(`/posts/${id}/comments?page=${page}&page_size=${pageSize}`),
  createComment: (id: string, content: string, parentId?: string) =>
    request<{ comment: Comment }>(`/posts/${id}/comments`, { method: "POST", body: JSON.stringify({ content, parent_id: parentId || null }) }),
  deleteComment: (id: string) => request<{ success: boolean }>(`/comments/${id}`, { method: "DELETE" }),
  likeComment: (id: string) => request<{ liked: boolean; likes: number }>(`/comments/${id}/like`, { method: "POST" }),
};

// ---- 会馆 ----
export const guildApi = {
  list: () => request<{ guilds: GuildListItem[] }>("/guilds"),
  detail: (slug: string) =>
    request<{ guild: GuildDetail; my_state: GuildMyState | null }>(`/guilds/${encodeURIComponent(slug)}`),
  feed: (slug: string, page = 1, pageSize = 20, category = "") =>
    request<{ items: FeedItem[]; has_more: boolean; page: number; page_size: number; guild: { id: number; uuid?: string; slug: string; name: string; theme_color: string } }>(
      `/guilds/${encodeURIComponent(slug)}/feed?page=${page}&page_size=${pageSize}${category ? `&category=${encodeURIComponent(category)}` : ""}`
    ),
  article: (id: string) =>
    request<{ article: GuildArticle }>(`/articles/${encodeURIComponent(id)}`),
  join: (slug: string, reason = "") =>
    request<{ request_id: number; message: string }>(`/guilds/${encodeURIComponent(slug)}/join`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  cancelJoin: (slug: string) =>
    request<{ message: string }>(`/guilds/${encodeURIComponent(slug)}/join/cancel`, { method: "POST" }),
  leave: (slug: string) =>
    request<{ message: string }>(`/guilds/${encodeURIComponent(slug)}/leave`, { method: "POST" }),
};

// ---- 全站信息流 ----
export const feedApi = {
  // space: all | public | guild（guild 时可用 guildId 指定具体会馆；不带则全部会馆帖子）
  list: (space: "all" | "public" | "guild" = "all", guildId = 0, category = "", page = 1, pageSize = 20) =>
    request<{ items: FeedItem[]; has_more: boolean; page: number; page_size: number; space: string }>(
      `/feed?space=${space}&guild_id=${guildId}&page=${page}&page_size=${pageSize}${category ? `&category=${encodeURIComponent(category)}` : ""}`
    ),
};

// ---- 搜索/杂项 ----
export const miscApi = {
  search: (k: string, type = "both", page = 1, pageSize = 20) =>
    request<SearchResult>(`/search?k=${encodeURIComponent(k)}&type=${type}&page=${page}&page_size=${pageSize}`),
  reportBug: (data: { title: string; detail: string; steps?: string; contact?: string; page_url?: string }) =>
    request<{ id: number }>("/reports/bug", { method: "POST", body: JSON.stringify(data) }),
  easterEgg: () => request<{ ID: string; Name: string; Text: string }>("/easter-egg"),
};

export { request };
