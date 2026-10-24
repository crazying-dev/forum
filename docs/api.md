# 妖精论坛 ov2 API 文档（RESTful）

- **Base URL**: `https://<domain>/api/v1`
- **认证**: Session Cookie（`forum_session`，HttpOnly）或 `Authorization: Bearer`（预留）
- 响应 JSON：`{"success": true/false, ...}`；错误：`{"success": false, "message": "..."}`
- 状态码：200 成功 / 201 创建 / 400 参数错 / 401 未登录 / 403 无权限/封禁 / 404 不存在 / 429 限流 / 500 服务器错

## 认证 Auth

| 方法 | 路径 | 说明 | 登录 |
|---|---|---|---|
| POST | `/auth/register` | 注册（name/email/password/code） | 否（成功自动登录） |
| POST | `/auth/login` | 登录（name=邮箱或用户名/password/remember） | 否 |
| POST | `/auth/logout` | 登出 | 否 |
| POST | `/auth/register/code` | 发送注册验证码（email） | 否 |
| POST | `/auth/password/reset/code` | 发送重置验证码（email） | 否 |
| POST | `/auth/password/reset` | 验证码重置密码（email/code/password） | 否 |
| GET | `/auth/verify-token?token=&type=` | 邮箱验证 token 消费 | 否 |
| GET | `/auth/oauth/callback?app_id=` | 第三方登录（TheDoorOfBings） | 否 |

## 用户 Users

| 方法 | 路径 | 说明 | 登录 |
|---|---|---|---|
| GET | `/users/me` | 当前用户信息（附 `guild` 会馆概要、`is_leader`） | 否 |
| PATCH | `/users/me` | 修改资料（Name/gender/age/intro/password） | 是 |
| POST | `/users/me/avatar` | 上传头像（multipart: avatar） | 是 |
| GET | `/users/me/replies` | 我收到的回复 | 是 |
| POST | `/users/me/verify-email` | 发送邮箱验证码 | 是 |
| POST | `/users/me/verify-email/confirm` | 验证码确认邮箱 | 是 |
| GET | `/users/:id` | 用户主页（stats/follow_stats/is_following/is_self/guild/is_leader） | 否 |
| GET | `/users/:id/posts` | 用户帖子 | 否 |
| GET | `/users/:id/favorites` | 用户收藏 | 否 |
| POST | `/users/:id/follow` | 关注/取消 | 是 |
| GET | `/users/:id/following` | 关注列表 | 否 |
| GET | `/users/:id/followers` | 粉丝列表 | 否 |

> 会馆字段：`guild` 为 `{id, uuid, slug, name, theme_color, is_leader}`，未入馆时为 `null`；顶层同名布尔字段 `is_leader` 便于前端直接判断（两者取值一致）。`uuid` 为会馆稳定标识，`id` 仅供展示/排序，前端路由与接口调用一律使用 `uuid`（`/users/me` 与 `/users/:id` 的 `guild` 对象同构）。

## 帖子 Posts

| 方法 | 路径 | 说明 | 登录 |
|---|---|---|---|
| GET | `/posts?page=&page_size=&category=` | 帖子列表（缓存 30s，page_size 上限 50） | 否 |
| GET | `/posts/random` | 随机 200 条 | 否 |
| GET | `/posts/:id` | 详情 + 评论 + liked/favorited（缓存 60s；`?track=0` 时不计数、不读写缓存，SEO 用） | 否 |
| POST | `/posts` | 发帖（title/content/category，可选 `guild_uuid` / `guild_id`） | 是 |
| POST | `/posts/:id/like` | 点赞/取消 | 是 |
| POST | `/posts/:id/favorite` | 收藏/取消 | 是 |
| POST | `/posts/:id/delete` | 删除（仅作者，软删） | 是 |
| POST | `/posts/:id/report` | 举报（reason/detail） | 是 |

> - 会馆归属字段：列表项（`posts[]`）与详情（`post`）均新增 `guild_id`（number 或 `null`，`null` = 公共广场）、`guild_name`、`guild_theme_color`（公共帖为空/省略）。
> - 作者会馆字段：上述列表项与详情还含作者所属会馆的 `user_guild_name` / `user_guild_theme_color` / `user_is_leader`（无会馆时为 `""` / `""` / `false`）；评论、信息流（`items[]`）与搜索结果（`posts`）中的帖子同构。
> - 发帖请求体：`{title, content, category, guild_uuid?, guild_id?}`；`guild_uuid`（string）为会馆稳定标识且优先，`guild_id`（number）为旧字段兼容——**仅在未传 `guild_uuid` 时生效**；`guild_uuid` 对应的会馆不存在（含非法 UUID 文本）返回 404「会馆不存在」。归属会馆时必须是该会馆成员（否则 403），`category` 由该馆自定义分类归一（缺省/非法值回退「综合」或第一项）；不传会馆标识时 `category` 走公共白名单。
> - 公共分类白名单：`general` / `talk` / `question` / `share` / `creative`，并兼容旧中文 `求助` / `创意`；缺省或非法值统一归一为 `general`。
> - 浏览量计数：`GET /posts/:id` 默认对同一访客（匿名按 IP / 登录按 uid）同帖 30 分钟内只计一次；`?track=0`（服务端 SEO 拉取）完全不计、不读不写缓存（响应头 `X-Cache: BYPASS`）。

## 评论 Comments

| 方法 | 路径 | 说明 | 登录 |
|---|---|---|---|
| GET | `/posts/:id/comments` | 评论列表（缓存 60s） | 否 |
| POST | `/posts/:id/comments` | 评论/回复（content/parent_id） | 是 |
| DELETE | `/comments/:id` | 删除评论（仅作者） | 是 |

> 评论列表与「我收到的回复」均含评论作者的会馆字段 `user_guild_name` / `user_guild_theme_color` / `user_is_leader`（无会馆时为空串 / 空串 / `false`）。

## 会馆 / 信息流 Guilds & Feed

| 方法 | 路径 | 说明 | 登录 |
|---|---|---|---|
| GET | `/guilds` | 会馆列表（`guilds[]`，按 `id` 升序；匿名缓存 30s） | 否 |
| GET | `/guilds/:slug` | 会馆详情（`guild` 含馆长/成员数/分类/公告 + `my_state`） | 否 |
| GET | `/guilds/:slug/feed` | 会馆信息流：帖子 + 文章混排（按时间倒序） | 否 |
| GET | `/feed` | 全站信息流：`space=all\|public\|guild`、`guild_id`、`category` | 否 |
| GET | `/articles/:id` | 文章详情（浏览量 +1；含作者 / 参与人 / 所属会馆） | 否 |
| POST | `/guilds/:slug/join` | 提交入馆申请（可选 `reason`，≤500 字） | 是 |
| POST | `/guilds/:slug/join/cancel` | 撤回待审申请 | 是 |
| POST | `/guilds/:slug/leave` | 退出会馆（馆长需先卸任） | 是 |

**响应字段**

- `guilds[]` 列表项：`id`(int，仅供展示/排序) / `uuid`(string，稳定标识) / `slug` / `name` / `intro` / `theme_color` / `member_count` / `has_logo` / `logo_version` / `leader`（`{id, name, avatar, intro}`，无馆长为 `null`）。
- `guild` 详情：列表项字段（含 `uuid`）+ `leader_user_id`(string\|null) / `leader_bio` / `created_at` / `updated_at` / `categories[]`（`{id, guild_id, name, sort}`）/ `announcements[]`（`{id, guild_id, content, created_at, updated_at}`，新→旧）。会馆 logo 使用 `logo_file_id`（媒体 ID，`MD` 开头）拼 `/ov2/api/media/<id>` 直出，`has_logo` 表示是否设置过；旧 GridFS 文件（24 位 ObjectID）无法直出，前端回退占位图。
- `my_state`：登录时 `{is_member, is_leader, has_pending_request, request_id?}`，未登录为 `null`。
- 信息流 `items[]`（帖子与文章同构）：`type`（`post` / `article`）/ `id`(string) / `title` / `summary` / `category`（文章为空串）/ `likes` / `views` / `comment_count` / `created_at` / `updated_at` / `user_id` / `user_name` / `user_avatar` / `user_guild_name` / `user_guild_theme_color` / `user_is_leader` / `guild_id`(number\|null) / `guild_name` / `guild_theme_color` / `author`（文章作者 `{id, name, avatar}`，帖子为 `null`）/ `participants_count`。
- 分页：`page` / `page_size`（默认 20，上限 50）+ `has_more`（布尔，是否为多取一条探测所得）。

**行为说明**

- 缓存：`/guilds` 匿名缓存 30s（键 `guilds:list`），`/guilds/:slug` 仅匿名缓存 30s（键 `guilds:detail:<slug>`）；登录用户详情实时附带 `my_state` 并标 `X-Cache: BYPASS`，响应头 `X-Cache` 取值 `HIT` / `MISS` / `BYPASS`。会馆流 / 全站流 / 文章均不缓存。
- `/guilds/:slug/feed`：返回 `items` / `has_more` / `page` / `page_size` / `guild`（摘要 `{id, slug, name, theme_color}`）；`category` 非空时**仅帖子**按该分类精确匹配（文章被排除），为空时帖子 + 该馆文章混排。
- `/feed`：`space` 缺省/非法值按 `all` 处理——`all` = 公共 + 会馆帖子 + 全部文章；`public` = 仅公共广场帖子；`guild` = 仅会馆帖子，带 `guild_id` 时附加该馆文章，不带 `guild_id` 时不含文章。`category` 非空时同样仅过滤帖子。
- 入馆申请：已在任意会馆（含本馆）或已有待审申请时返回 400；成功返回 `request_id` 与「申请已提交，等待馆长审核」。**审批由管理端（yj-forum-admin）完成**，ouo 侧仅提交/撤回/退出。并发重复提交由部分唯一索引（`(guild_id, user_id) WHERE status = 0`）兜底，同样返回 400「你已提交申请，请等待馆长审核」。
- `leave`：非成员或本人为馆长时 400（「馆长需先卸任才能退出会馆」）；退出成功后清空 `guilds:` 前缀缓存。
- `GET /articles/:id`：先校验存在性（不存在返回 404 且**不自增**浏览量），存在时 `views + 1` 并返回自增后的值；`content` 仅详情返回（列表摘要不含正文）。文章 `id` 为字符串（管理端生成）。

## 搜索 / 投票 / 杂项

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/search?k=&type=posts\|users\|both&page=` | 全文搜索（缓存 120s） |
| POST | `/votes/version` | 版本投票（choice=v1\|ov2，登录按账号/游客按 IP） |
| GET | `/votes/version/stats` | 投票统计 |
| POST | `/reports/bug` | Bug 举报（title/detail/steps/contact/page_url） |
| GET | `/easter-egg` | 随机彩蛋 |
| GET | `/avatar/:filename` | 头像文件（本地磁盘） |

> 搜索结果：`posts[]` 与帖子列表字段同构（含会馆归属与作者会馆字段）；`users[]` 为用户摘要。响应另含 `keyword` / `page` / `page_size` 与 `posts_total` / `posts_has_more` / `users_total` / `users_has_more`（按 `type` 选择性返回）。

> 兼容说明：旧 `GET /api/v1/hui-guan`（会馆 JSON 列表）**已删除**，由 `GET /api/v1/guilds` 替代；旧实时消息接口 `/api/v1/world/messages`（`/World` 页面）与 `world` 数据表一并移除，由公共广场（`/feed?space=public`）与会馆信息流取代。会馆 logo 与正文图片统一由媒体中台提供，前端请求 `/ov2/api/media/<id>`；原 `/guild-img/*` 代理已退役。

## 限流规则（key: IP）

| 端点 | 阈值 |
|---|---|
| login | 10 次/300s |
| register / register code | 5 次/300s、3 次/300s |
| 发帖 | 10 次/60s |
| 评论 | 20 次/60s |
| 投票 / Bug | 10 次/300s、5 次/300s |

## 数据模型（核心表）

- `users`：id(RL+时间戳)/name/avatar/email/password/gender/age/intro/vip/prefix/is_banned/email_verified
- `posts`：id(PS+时间戳)/user_id/title/content/category/likes/views/status/**guild_id（NULL = 公共广场）**
- `comments`：id(CM+时间戳)/post_id/user_id/content/parent_id/likes/status
- `guilds`：id(INTEGER 主键，人工排序)/**uuid(UUID，唯一，对外稳定标识；0005 迁移新增)**/slug/name/intro/logo_file_id/logo_version/theme_color/leader_user_id/leader_bio
- `guild_members`：user_id(主键)/guild_id/joined_at（一个用户同时至多属于一个会馆）
- `guild_join_requests`：id/guild_id/user_id/status（0 待审 / 1 通过 / 2 拒绝 / 3 撤回）/reason/handled_by/handled_at/handled_note/created_at（0004 迁移新增 `handled_note`，并对 `(guild_id, user_id) WHERE status = 0` 建部分唯一索引）
- `guild_categories`：id/guild_id/name/sort；`guild_announcements`：id/guild_id/content/created_at/updated_at
- `guild_articles`：id(字符串，AR 前缀)/guild_id/title/summary/content/author_user_id/views；`guild_article_participants`：article_id/user_id/user_name（署名快照）
- `sessions`（ov2 新增）：token/user_id/expires_at
- 其余：post_likes、post_favorites、user_follows、verify_tokens、post_reports、bug_reports、verify_codes、version_votes
- **已移除**：`world`（旧实时消息表，见 0003 迁移）
