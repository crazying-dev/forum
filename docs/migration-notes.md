# 迁移对照笔记（legacy Flask → ov2 Next.js + Go）

## 端点对照表

| legacy (Flask) | ov2 (Go RESTful) | 说明 |
|---|---|---|
| `POST /api/register` | `POST /api/v1/auth/register` | 注册 |
| `POST /api/login` | `POST /api/v1/auth/login` | 登录 |
| `POST /api/logout` | `POST /api/v1/auth/logout` | 登出 |
| `POST /api/send-register-code` | `POST /api/v1/auth/register/code` | 注册验证码 |
| `POST /api/send-code-reset-password` | `POST /api/v1/auth/password/reset/code` | 重置验证码 |
| `POST /api/reset-password-by-code` | `POST /api/v1/auth/password/reset` | 验证码重置 |
| `GET /api/user/info` | `GET /api/v1/users/me` | 当前用户 |
| `POST /api/users/change` | `PATCH /api/v1/users/me` | 改资料 |
| `POST /api/user/avatar/upload` | `POST /api/v1/users/me/avatar` | 传头像 |
| `GET /api/users/<id>/info` | `GET /api/v1/users/:id` | 用户主页 |
| `GET /api/users/<id>/posts` | `GET /api/v1/users/:id/posts` | 用户帖子 |
| `GET /api/users/<id>/favorites` | `GET /api/v1/users/:id/favorites` | 收藏 |
| `POST /api/users/<id>/follow` | `POST /api/v1/users/:id/follow` | 关注 |
| `GET /api/users/<id>/following` | `GET /api/v1/users/:id/following` | 关注列表 |
| `GET /api/users/<id>/followers` | `GET /api/v1/users/:id/followers` | 粉丝列表 |
| `GET /api/users/me/replies` | `GET /api/v1/users/me/replies` | 回复 |
| `POST /api/posts/create` | `POST /api/v1/posts` | 发帖 |
| `GET /api/posts` | `GET /api/v1/posts` | 帖子列表 |
| `GET /api/posts/random` | `GET /api/v1/posts/random` | 随机 |
| `GET /api/posts/<id>` | `GET /api/v1/posts/:id` | 详情 |
| `POST /api/posts/<id>/like` | `POST /api/v1/posts/:id/like` | 点赞 |
| `POST /api/posts/<id>/favorite` | `POST /api/v1/posts/:id/favorite` | 收藏 |
| `POST /api/posts/<id>/delete` | `POST /api/v1/posts/:id/delete` | 删除 |
| `POST /api/posts/<id>/report` | `POST /api/v1/posts/:id/report` | 举报 |
| `GET /api/posts/<id>/comments` | `GET /api/v1/posts/:id/comments` | 评论列表 |
| `POST /api/posts/<id>/comments/create` | `POST /api/v1/posts/:id/comments` | 发评论 |
| `POST /api/comments/<id>/delete` | `DELETE /api/v1/comments/:id` | 删评论 |
| `POST /api/World/Send` | _已移除_ | 旧实时消息接口下线（0003 迁移 DROP `world`） |
| `GET /api/World/ALL` | `GET /api/v1/feed?space=public` | 公共广场信息流（会馆信息流另见 `/guilds/:slug/feed`） |
| `GET /api/search` | `GET /api/v1/search` | 搜索 |
| `POST /api/vote/version` | `POST /api/v1/votes/version` | 投票 |
| `GET /api/vote/version/stats` | `GET /api/v1/votes/version/stats` | 投票统计 |
| `POST /api/report-bug` | `POST /api/v1/reports/bug` | Bug 举报 |
| `GET /api/huiguan` | `GET /api/v1/guilds` | 动态会馆列表（旧 `hui-guan.json` 与 `GET /api/v1/hui-guan` 均已删除） |
| `GET /Easter-Egg` | `GET /api/v1/easter-egg` | 彩蛋 |
| `GET /avatar/<filename>` | `GET /avatar/:filename` | 头像（Go 提供） |
| `GET /api/login/otherAPP` | `GET /api/v1/auth/oauth/callback` | 第三方登录（兼容） |

## 页面路由对照（Next.js App Router）

| legacy 路由 | Next.js 页面 |
|---|---|
| `/` | `app/page.tsx` |
| `/forum` | `app/forum/page.tsx` |
| `/post/create` | `app/post/create/page.tsx` |
| `/post/<id>` | `app/post/[id]/page.tsx` |
| `/search` | `app/search/page.tsx` |
| `/login` | `app/login/page.tsx` |
| `/users/<id>` | `app/users/[id]/page.tsx` |
| `/World` | _已移除_（由主页公共广场信息流与 `/huiguan` 会馆入口取代） |
| `/WIKI` 全套 | `app/WIKI/**` |
| `/privacy` | `app/privacy/page.tsx` |
| `/GoTo` | `app/GoTo/page.tsx` |
| `/verify-email` | `app/verify-email/page.tsx` |
| `/oauth` | `app/oauth/page.tsx` |

## 环境变量对照

| legacy | ov2 | 变化 |
|---|---|---|
| `DATABASE_URL` | `DATABASE_URL` | 同（生产用外部 PGSQL） |
| `SECRET_KEY` | `SECRET_KEY` | 同 |
| `SMTP_*` | `SMTP_*` | 同 |
| `CORS_ORIGINS` | `CORS_ORIGINS` | 同 |
| `BLOB_READ_WRITE_TOKEN` | _删除_ | ov2 无 Vercel Blob，改用进程内缓存 |
| `FLASK_ENV` | `APP_ENV` | 改名（dev/prod 控制 Secure cookie） |
| `POOL_ENABLED` | _删除_ | ov2 恒用 pgxpool |
| —— | `AVATAR_DIR` | ov2 新增（头像目录） |
| —— | `DATA_DIR` | ov2 新增（数据目录） |
| —— | `PUBLIC_BASE_URL` | ov2 新增（邮件链接域名） |

## 已知行为差异（有意保留/修复）

1. **修复**：legacy `Email.send_email` 返回值判断恒真（邮件失败误报成功）→ ov2 显式 `(success, err)`。
2. **修复**：legacy 缓存失效 key 硬编码与运行时不一致 → ov2 统一按实际参数前缀失效。
3. **修复**：legacy `SECRET_KEY` 读取 chr 混淆 bug（永远取不到环境变量）→ ov2 直接读取。
4. **修复**：legacy `main.css` 多余花括号导致 CSS 解析问题 → ov2 已修正。
5. **World 表**：legacy 的 `world` 表已在 0003 迁移中 `DROP`，实时消息功能由公共广场（`/feed?space=public`）与会馆信息流取代。
6. **分类**：公共广场白名单为 `general` / `talk` / `question` / `share` / `creative`，并兼容旧中文 `求助` / `创意`（缺省归一 `general`）；会馆帖子使用各馆自定义分类（`guild_categories`，缺省/非法值回退「综合」或第一项）。
7. 头像存储：legacy `/root/db/avatar/`（Vercel 上不可持久）→ ov2 `AVATAR_DIR` 本地磁盘。
8. **会馆**：legacy 静态 `hui-guan.json` 列表 + `hei.navifox.net` 外链 → ov2 动态会馆（PostgreSQL `guilds` 系列表）、入馆申请由管理端审批；会馆 logo 存媒体中台，前端经 `/ov2/api/media/<id>` 直出（原 `/guild-img` 代理已退役）。

## 部署要点

- 单实例裸机：Go systemd + Next.js standalone systemd + Nginx 反代。
- 数据库：开发本机 Docker PGSQL；生产外部 PGSQL（连接串）。
- 静态资源全部本地化 `web/public/assets/`，无外部 CDN 依赖（除第三方外链）。
