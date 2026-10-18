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
  prefix?: string;
  email_verified?: number;
  created_at?: string;
  // 已注销用户（GET /users/:id 返回的用户附带 deleted=true，仅最小档案）
  deleted?: boolean;
  // 灵力值（签到累计）与最近签到日期（YYYY-MM-DD，未签到为空）
  spirit: number;
  last_sign_in?: string;
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
  // 正文格式：'markdown'（旧帖）| 'html'（富文本编辑器产出）
  content_format?: string;
  // 定时发布时间（RFC3339；本人视角下的定时帖为未来时间）
  published_at?: string;
  // 会馆（null/undefined 表示公共空间）
  guild_id?: number | null;
  guild_name?: string;
  guild_theme_color?: string;
  // 作者身份标签（后端契约）：所属会馆 + 是否馆长
  user_guild_name?: string | null;
  user_guild_theme_color?: string | null;
  user_is_leader?: boolean;
}

// 引用选择器默认项（登录用户；帖子 Tab 未输入关键词时展示）
export interface PickerDefaults {
  following_posts: Post[];
  favorite_posts: Post[];
}

export interface Comment {
  id: string;
  post_id: string;
  user_id: string;
  content: string;
  // 正文格式：'markdown'（历史数据）| 'html'（富文本评论）
  content_format?: string;
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
  // 馆长称号（管理端填写，可能为空）
  title?: string;
}

// 会馆成员（成员名单页）
export interface GuildMember {
  id: string;
  name: string;
  avatar: string;
  prefix?: string;
  intro?: string;
  is_leader?: boolean;
  joined_at?: string;
}

// 馆长介绍页数据（GET /guilds/:slug/leader）
export interface GuildLeaderPageData {
  guild: { uuid: string; slug: string; name: string; theme_color: string };
  leader: GuildLeader | null;
  leader_bio?: string;
  content?: string;
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

// 会馆介绍页数据（GET /guilds/:slug/intro）
export interface GuildIntroPageData {
  guild: {
    uuid: string;
    slug: string;
    name: string;
    intro: string;
    theme_color: string;
    created_at?: string;
    member_count: number;
    category_count: number;
    cover_file_id: string;
  };
  content?: string;
}

// 文章搜索项/结果（GET /articles/search，k≥2）
export interface ArticleSearchItem {
  id: string;
  title: string;
  guild_name: string;
  created_at?: string;
}

export interface ArticleSearchResult {
  articles: ArticleSearchItem[];
  total: number;
  has_more: boolean;
  page: number;
  page_size: number;
}

// 引用卡片（GET /embeds）：三类数据，查不到的 id 不出现在数组里
export type EmbedKind = "user" | "post" | "article";

export interface EmbedUserItem {
  id: string;
  name: string;
  avatar: string;
  prefix: string;
  intro: string;
  guild: { name: string; slug: string; theme_color: string } | null;
}

export interface EmbedPostItem {
  id: string;
  title: string;
  user_id: string;
  user_name: string;
  user_avatar: string;
  category: string;
  created_at?: string;
  guild_name: string;
}

export interface EmbedArticleItem {
  id: string;
  title: string;
  author_id: string;
  author_name: string;
  author_avatar: string;
  created_at?: string;
  guild_name: string;
}

// 批量解析结果（每类 ≤30）
export interface EmbedResolved {
  users: EmbedUserItem[];
  posts: EmbedPostItem[];
  articles: EmbedArticleItem[];
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
  // 正文格式：'markdown'（旧文）| 'html'（富文本编辑器产出）
  content_format?: string;
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
  prefix?: string;
  intro?: string;
  is_self?: boolean;
  is_following?: boolean;
  // 共同关注：viewer 是否也关注了该用户（仅 following 列表下发；粉丝列表/匿名/本人恒 false）
  is_mutual?: boolean;
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

// ---- 反馈中心（公开读取，接口均不含提交人信息）----

// 反馈状态：0 未处理 / 1 处理中 / 2 已处理 / 3 关闭
export interface FeedbackListItem {
  id: number;
  title: string;
  detail: string;
  status: number;
  created_at?: string;
}

// 反馈详情（较列表多 steps）
export interface FeedbackDetail extends FeedbackListItem {
  steps?: string;
}

// 状态流转日志（from_status 首条可为 null）
export interface FeedbackLog {
  from_status: number | null;
  to_status: number;
  note: string;
  created_at?: string;
}

// 状态统计项（0/1/2/3 四态恒返回）
export interface FeedbackStat {
  status: number;
  count: number;
}

export interface FeedbackListResult {
  items: FeedbackListItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

// ---- 指南（guides）----

// 指南节点列表项（不含正文）
export interface GuideNodeItem {
  id: string;
  parent_id: string | null;
  title: string;
  // 节点类型：folder（目录）/ doc（文档）
  kind: string;
  sort: number;
  updated_at?: string;
}

// 指南节点详情（含正文）
export interface GuideNodeDetail extends GuideNodeItem {
  content: string;
  content_format?: string;
}

import { API_BASE } from "./api-base";

const API_BASE_PATH = API_BASE;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = API_BASE_PATH + path;
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
  // altcha：ALTCHA v2 人机验证 payload（可选；服务端启用 ALTCHA 时必填）
  login: (name: string, password: string, remember = true, altcha?: string) =>
    request<{ id: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ name, password, remember, ...(altcha ? { altcha } : {}) }),
    }),
  logout: () => request<{ success: boolean }>("/auth/logout", { method: "POST" }),
  register: (name: string, email: string, password: string, code: string, altcha?: string) =>
    request<{ id: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password, code, ...(altcha ? { altcha } : {}) }),
    }),
  sendRegisterCode: (email: string, altcha?: string) =>
    request<{ message: string }>("/auth/register/code", {
      method: "POST",
      body: JSON.stringify({ email, ...(altcha ? { altcha } : {}) }),
    }),
  // 发送重置链接（10 分钟内有效、最多可打开 3 次；邮箱不存在也返回成功提示，429 = 过于频繁）
  sendResetLink: (email: string, altcha?: string) =>
    request<{ message: string }>("/auth/password/reset/link", {
      method: "POST",
      body: JSON.stringify({ email, ...(altcha ? { altcha } : {}) }),
    }),
  // 校验重置链接 token（返回掩码邮箱；400 = 无效/过期/次数用尽）
  validateResetToken: (token: string) =>
    request<{ data: { email: string } }>(`/auth/password/reset/validate?token=${encodeURIComponent(token)}`),
  // 使用重置链接设置新密码
  confirmResetPassword: (token: string, password: string, altcha?: string) =>
    request<{ message: string }>("/auth/password/reset/confirm", { method: "POST", body: JSON.stringify({ token, password, ...(altcha ? { altcha } : {}) }) }),
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
    request<{ users: UserBrief[]; page?: number; page_size?: number; has_more?: boolean }>(`/users/${id}/following?page=${page}&page_size=${pageSize}`),
  followers: (id: string, page = 1, pageSize = 20) =>
    request<{ users: UserBrief[]; page?: number; page_size?: number; has_more?: boolean }>(`/users/${id}/followers?page=${page}&page_size=${pageSize}`),
  // 共同关注（匿名 / 看自己时后端返回空数组）
  mutual: (id: string, page = 1, pageSize = 20) =>
    request<{ users: UserBrief[]; page: number; page_size: number; has_more?: boolean }>(`/users/${id}/mutual?page=${page}&page_size=${pageSize}`),
  comments: (id: string, page = 1, pageSize = 20) =>
    request<{ comments: ReplyItem[]; total: number }>(`/users/${id}/comments?page=${page}&page_size=${pageSize}`),
  updateMe: (data: Record<string, unknown>) =>
    request<{ success: boolean }>("/users/me", { method: "PATCH", body: JSON.stringify(data) }),
  replies: (page = 1, pageSize = 50) =>
    request<{ replies: Comment[]; total: number }>(`/users/me/replies?page=${page}&page_size=${pageSize}`),
  // 每日签到（+10 灵力；409 = 今日已签）
  signIn: () =>
    request<{ data: { spirit: number; last_sign_in: string } }>("/users/me/sign-in", { method: "POST" }),
  verifyEmail: () => request<{ message: string }>("/users/me/verify-email", { method: "POST" }),
  verifyEmailConfirm: (code: string) =>
    request<{ message: string }>("/users/me/verify-email/confirm", { method: "POST", body: JSON.stringify({ code }) }),
  // 注销账号：mode=purge（彻底删除）/ anonymize（匿名化保留）；需密码 + 用户名确认
  deleteAccount: (data: { mode: "purge" | "anonymize"; password: string; confirmName: string }) =>
    request<{ message: string }>("/users/me/delete", { method: "POST", body: JSON.stringify(data) }),
  // 邮箱换绑：① 验证当前邮箱 ② 绑定新邮箱
  sendEmailChangeOldCode: () => request<{ message?: string }>("/users/me/email-change/code", { method: "POST" }),
  verifyEmailChangeOld: (code: string) =>
    request<{ message?: string }>("/users/me/email-change/verify-old", { method: "POST", body: JSON.stringify({ code }) }),
  sendEmailChangeNewCode: (newEmail: string) =>
    request<{ message?: string }>("/users/me/email-change/new-code", { method: "POST", body: JSON.stringify({ newEmail }) }),
  confirmEmailChange: (code: string) =>
    request<{ message?: string }>("/users/me/email-change/confirm", { method: "POST", body: JSON.stringify({ code }) }),
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
  // 引用选择器默认项（登录；关注/收藏各至多 20 条）
  pickerDefaults: () => request<{ data: PickerDefaults }>("/posts/picker-defaults"),
  // guildUuid 传入时帖子归属该会馆（需为该馆成员），否则发到公共空间；publishedAt 为 RFC3339（可选，未来时间即定时发布）
  create: (title: string, content: string, category: string, guildUuid?: string, publishedAt?: string) =>
    request<{ id: string }>("/posts", {
      method: "POST",
      body: JSON.stringify({
        title,
        content,
        category,
        ...(guildUuid ? { guild_uuid: guildUuid } : {}),
        ...(publishedAt ? { published_at: publishedAt } : {}),
      }),
    }),
  like: (id: string) => request<{ liked: boolean; likes: number }>(`/posts/${id}/like`, { method: "POST" }),
  favorite: (id: string) => request<{ favorited: boolean }>(`/posts/${id}/favorite`, { method: "POST" }),
  remove: (id: string) => request<{ success: boolean }>(`/posts/${id}/delete`, { method: "POST" }),
  report: (id: string, reason: string, detail = "") =>
    request<{ success: boolean }>(`/posts/${id}/report`, { method: "POST", body: JSON.stringify({ reason, detail }) }),
  comments: (id: string, page = 1, pageSize = 50) =>
    request<{ comments: Comment[] }>(`/posts/${id}/comments?page=${page}&page_size=${pageSize}`),
  createComment: (id: string, content: string, parentId?: string, contentFormat?: string) =>
    request<{ comment: Comment }>(`/posts/${id}/comments`, {
      method: "POST",
      body: JSON.stringify({
        content,
        parent_id: parentId || null,
        ...(contentFormat ? { content_format: contentFormat } : {}),
      }),
    }),
  deleteComment: (id: string) => request<{ success: boolean }>(`/comments/${id}`, { method: "DELETE" }),
  likeComment: (id: string) => request<{ liked: boolean; likes: number }>(`/comments/${id}/like`, { method: "POST" }),
};

// ---- 会馆 ----
export const guildApi = {
  list: () => request<{ guilds: GuildListItem[] }>("/guilds"),
  detail: (slug: string) =>
    request<{ guild: GuildDetail; my_state: GuildMyState | null }>(`/guilds/${encodeURIComponent(slug)}`),
  // 成员名单（分页，默认每页 24；is_leader 项为馆长）
  members: (slug: string, page = 1, pageSize = 24) =>
    request<{ members: GuildMember[]; page: number; page_size: number; has_more: boolean }>(
      `/guilds/${encodeURIComponent(slug)}/members?page=${page}&page_size=${pageSize}`
    ),
  // 馆长介绍页（含寄语 leader_bio 与正文 content）
  leaderPage: (slug: string) =>
    request<GuildLeaderPageData>(`/guilds/${encodeURIComponent(slug)}/leader`),
  // 会馆介绍页（概要/统计/封面 + 富文本正文 content）
  intro: (slug: string) => request<GuildIntroPageData>(`/guilds/${encodeURIComponent(slug)}/intro`),
  // 文章搜索（k≥2 字符；引用卡片选文用）
  searchArticles: (k: string, page = 1, pageSize = 10) =>
    request<ArticleSearchResult>(`/articles/search?k=${encodeURIComponent(k)}&page=${page}&page_size=${pageSize}`),
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

// ---- 引用卡片 ----
export const embedApi = {
  // 批量解析引用 id（URLSearchParams 逗号拼接；查不到的 id 省略；每类最多 30 个）
  resolve: (ids: { users?: string[]; posts?: string[]; articles?: string[] }) => {
    const qs = new URLSearchParams();
    if (ids.users?.length) qs.set("users", ids.users.join(","));
    if (ids.posts?.length) qs.set("posts", ids.posts.join(","));
    if (ids.articles?.length) qs.set("articles", ids.articles.join(","));
    return request<EmbedResolved>(`/embeds?${qs.toString()}`);
  },
};

// ---- 媒体（发帖配图） ----
export const mediaApi = {
  // 上传图片（需登录；multipart file，≤5MB，png/jpeg/webp/gif）；scene 可选：post_image | comment_image，缺省回退 post_image
  upload: (file: File, scene?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (scene) fd.append("scene", scene);
    return request<{ id: string; url: string }>("/media/images", { method: "POST", body: fd });
  },
};

// ---- 搜索/杂项 ----
export const miscApi = {
  search: (k: string, type = "both", page = 1, pageSize = 20) =>
    request<SearchResult>(`/search?k=${encodeURIComponent(k)}&type=${type}&page=${page}&page_size=${pageSize}`),
  reportBug: (data: { title: string; detail: string; steps?: string; contact?: string; page_url?: string }, altcha?: string) =>
    request<{ id: number }>("/reports/bug", { method: "POST", body: JSON.stringify({ ...data, ...(altcha ? { altcha } : {}) }) }),
  easterEgg: () => request<{ ID: string; Name: string; Text: string }>("/easter-egg"),
};

// ---- 反馈中心（公开；status 缺省为全部，0/1/2/3 四态过滤）----
export const feedbackApi = {
  list: (status: number | null = null, page = 1, pageSize = 12) =>
    request<{ data: FeedbackListResult }>(
      `/reports/bug?page=${page}&page_size=${pageSize}${status === null ? "" : `&status=${status}`}`
    ),
  stats: () => request<{ data: { stats: FeedbackStat[] } }>("/reports/bug/stats"),
  detail: (id: number) => request<{ data: { report: FeedbackDetail; logs: FeedbackLog[] } }>(`/reports/bug/${id}`),
};

// ---- 论坛指南 ----
export const guideApi = {
  // 目录树（全部节点，不含正文）
  getTree: () => request<{ data: { nodes: GuideNodeItem[] } }>("/guides"),
  // 节点详情（含正文 content / content_format）
  getDoc: (id: string) => request<{ data: { node: GuideNodeDetail } }>(`/guides/${encodeURIComponent(id)}`),
};

export { request };
