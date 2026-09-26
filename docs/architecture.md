# 妖精论坛 oov2 技术架构

- **Date**: 2026-08-29
- **Status**: ov2.0

## 总览

```
┌────────────────────────────────────────────────────┐
│                    Browser (客户端)                 │
└───────────────────────┬────────────────────────────┘
                        │ HTTPS
                        ▼
┌────────────────────────────────────────────────────┐
│                 Nginx (宝塔 80/443)                │
│   /api/* /avatar/* → Go :8090                      │
│   /guild-img/* → 管理端 admin :8080                │
│   其余 → Next.js :3000                             │
└──────────┬─────────────────────────┬──────────────┘
           │                         │
           ▼                         ▼
┌───────────────────┐       ┌─────────────────────┐
│  Next.js (:3000)  │       │   Go Gin (:8090)    │
│  渲染层            │       │  服务层             │
│  - 页面渲染（SSG壳+  │       │  - RESTful API      │
│    客户端组件）     │       │  - Session 认证      │
│  - 静态资源 public/│       │  - 业务逻辑/中间件    │
│  - apiFetch 代理    │       │  - 进程内 LRU 缓存   │
└───────────────────┘       └──────────┬──────────┘
                                        │ pgx
                                        ▼
                              ┌────────────────────┐
                              │ PostgreSQL          │
                              │ 开发: 本机 Docker   │
                              │ 生产: 外部 PGSQL    │
                              └────────────────────┘
```

## 职责划分

### Next.js（渲染层）
- **页面**：App Router，全站静态壳（SSG）+ 客户端组件；`output: 'standalone'` 支持裸机部署。
- **数据获取**：客户端 `lib/api.ts` 统一 `fetch('/api/v1/...')`，`credentials: 'include'` 携带会话 cookie。
- **静态资源**：全部本地化于 `public/assets/`（图片/字体/CSS/JS/Live2D/鼠标包）。
- **状态**：`lib/store.tsx`（主题/登录用户），主题 localStorage 持久化 + 时间段自动切换。
- **开发代理**：`next.config.ts` rewrites `/api/*` → Go（`API_TARGET`），`/guild-img/*` → 管理端（`ADMIN_TARGET`，默认 `http://127.0.0.1:8080`）；生产由 Nginx 分发。

### Go（服务层）
- **框架**：Gin；数据库 pgxpool + golang-migrate；密码 bcrypt（兼容 werkzeug scrypt/pbkdf2 旧哈希）。
- **认证**：数据库 `sessions` 表 + HttpOnly cookie（`forum_session`，24h）+ 非 HttpOnly `user_id` cookie（30 天，前端乐观判断）。
- **缓存**：进程内 LRU+TTL（posts 30s / post_detail 60s / user_info 300s / guilds 30s / search 120s / comments 60s）。
- **中间件**：CORS 白名单 / CSRF（Origin+Referer）/ 限流（IP+维度）/ 安全响应头 / gzip。
- **邮件**：SMTP（net/smtp），异步 goroutine 发送（注册码/重置码/登录提醒/粉丝通知/评论提醒/Bug 通知）。
- **存储**：头像本地磁盘 `AVATAR_DIR`；彩蛋 JSON 由 `EASTER_EGG_PATH` 读取；帖子/用户/会馆/文章均在 PostgreSQL。会馆 logo 由管理端（yj-forum-admin）存储，ouo 侧仅保存 `logo_file_id` / `logo_version` 并通过 `/guild-img` 代理展示（以 uuid 定位，兼容旧数字 id）。
- **模块边界**：`handler/`（auth、users、posts、comments、guilds、misc、search）负责路由与参数校验；`database/`（users、users_credentials、posts、comments、guilds、misc）负责 SQL 查询；`models/` 定义对外数据结构；`middleware/`、`cache/`、`email/` 为横切与基础设施。会馆系统新增 `handler/guilds.go`（列表/详情/信息流/文章/入退馆）与 `database/guilds.go`（会馆、成员、入馆申请、分类、公告、文章与信息流查询）。

## 通信方式
- **RESTful JSON**：`/api/v1/*`，HTTP 状态码语义化（200/201/400/401/403/404/429/500）。
- 错误体：`{"success": false, "message": "..."}`（部分端点 HTTP 状态码携带语义）。
- 会话：HttpOnly cookie 由 Go 下发，浏览器自动携带；Next.js 与 Go 同域（Nginx 统一或开发代理）。

## 数据表（PostgreSQL）

| 分组 | 表 | 说明 |
|---|---|---|
| 用户/内容 | `users`、`posts`、`comments`、`post_likes`、`post_favorites`、`comment_likes`、`user_follows`、`post_reports`、`bug_reports`、`version_votes`、`verify_tokens`、`verify_codes`、`sessions` | `posts` 新增 `guild_id`（NULL = 公共广场），并建 `(guild_id, created_at DESC)` 索引 |
| 会馆（0003 迁移） | `guilds`、`guild_members`、`guild_join_requests`、`guild_categories`、`guild_announcements`、`guild_articles`、`guild_article_participants` | 会馆主表（id 人工排序 + slug/name 唯一）、成员（`user_id` 主键，一个用户至多一个会馆）、入馆申请（status 0 待审/1 通过/2 拒绝/3 撤回）、自定义分类、公告、文章与参与人（署名快照） |
| 已移除 | ~~`world`~~ | 旧实时消息表在 0003 迁移中 DROP，由公共广场与会馆信息流取代 |

- **账号 ID 变更**：0003 迁移将引用 `users(id)` 的全部既有外键（posts/comments/post_likes/post_favorites/user_follows/verify_tokens/post_reports/sessions/comment_likes）统一重建为 `ON UPDATE CASCADE`（保留原 ON DELETE 语义），新增会馆子表同样使用 `ON UPDATE CASCADE`——用于馆长 ID 变更等场景的级联更新。
- 迁移 SQL 已嵌入 Go 二进制，启动时按 `0001 → 0003` 顺序自动执行。

## 数据流示例

**登录**：
```
POST /api/v1/auth/login → Go 校验(兼容旧哈希) → 写 sessions → Set-Cookie
→ Next.js store.refreshUser() → GET /users/me → Header 显示用户名
```

**发帖**：
```
POST /api/v1/posts（auth） → SafeHTML 净化 → INSERT → 失效列表缓存 → 异步粉丝通知
→ 客户端跳转 /post/{id} → GET /posts/{id} → 渲染详情+评论
```

**入馆申请（管理端审批）**：
```
POST /api/v1/guilds/:slug/join（登录，可选 reason） → 校验未入馆/无待审 → INSERT guild_join_requests(status=0)
→ 管理端 yj-forum-admin 审核（approve / reject） → approve 后写入 guild_members → 用户可发该馆帖子并在资料页显示 guild
```

**文章浏览**：
```
GET /api/v1/articles/:id → views +1 → 读取 guild_articles + 作者/参与人/所属会馆
→ 客户端渲染（会馆页/信息流点击 item.type=article 进入）
```

## 安全设计
- **XSS**：所有用户内容经 `SafeHTML`（黑名单标签/事件属性/javascript: 协议移除）；前端 React 默认转义。
- **CSRF**：非 GET 请求必须携带同源 Origin/Referer（支持 X-Forwarded-Host 代理场景）。
- **认证**：Session cookie HttpOnly + SameSite=Lax + Secure(prod)；封禁账号拒绝登录。
- **限流**：登录 10/300s、注册 5/300s、注册验证码 3/300s（其余端点暂未启用服务端限流）。
- **头像**：仅 JPG/PNG/WebP；路径穿越防护；UUID 文件名。

## 与 legacy 的差异
| 项 | legacy (Flask) | ov2 (Next.js + Go) |
|---|---|---|
| 前端交互 | 外部 CDN AfterBody.js | React 组件化重写 |
| 样式 | CDN main.css | 本地 main.css + Tailwind 基础设施 |
| 认证 | Flask-Login 签名 cookie | 数据库 sessions 表 |
| API | /api/* 混合风格 | /api/v1/* RESTful |
| 缓存 | 内存 LRU + Vercel Blob | 进程内 LRU（单实例） |
| 会馆 | 静态 JSON 列表（外部外链） | PostgreSQL 动态会馆 + 管理端（admin）审批与 logo 存储 |
| 部署 | Vercel Serverless | 自建服务器裸机 + Nginx |
