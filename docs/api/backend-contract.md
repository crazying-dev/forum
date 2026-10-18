# 后端实现契约（Batch 2 并行模块共享）

> 所有新端点挂在 `/ov2/api`（`/api/v1` 自动别名）。模块 agent 只新增自己的文件与 `RegisterXxxRoutes(api *gin.RouterGroup, deps ...)`，**不要改 `router.go` / `main.go` / 迁移 / `media` 核心**。

## 0. 通用

- 成功：`{"success":true,...}`；失败：`{"success":false,"message":"..."}`。
- 鉴权：`forum_session` Cookie；需要登录的路由加 `authH.AuthRequired()`。
- 时间：RFC3339（Go `time.Time` JSON）。
- 分页：`cursor`（字符串，内部为 id 或时间） + `limit`；响应 `{items,has_more,next_cursor}`。

## 1. ALTCHA v2 + 黑名单

- `GET /captcha/config` → `{success,enabled,algorithm,cost}`。
- `GET /captcha/challenge` → ALTCHA 官方 Challenge JSON（直接返回 library 的 challenge，不要包 success）。
- `POST /captcha/verify` body `{altcha:"<base64 payload>"}` → `{success,grant:"<一次性 token>",expires_in:300}`；失败 400 `CAPTCHA_REQUIRED`。
- 登录/注册/发码/忘记密码/重置提交/Bug 提交接受 `altcha` 或 `grant` 字段；兼容层跳过。
- 黑名单命中：400 `{success:false,message:"邮箱异样"}`。

## 2. 消息中心

- `GET /messages/summary` → `{success,likes,comments,system,chat}`（四个未读数）。
- `GET /messages/likes?cursor=&limit=20` → `{success,items:[{id,actor:{id,name,avatar},target_type:"post"|"comment",target_id,post_id,post_title,comment_id,comment_excerpt,created_at}],has_more,next_cursor}`。
- `GET /messages/comments?cursor=&limit=20` → `{success,items:[{id,actor:{...},comment_id,post_id,post_title,excerpt,parent_id,created_at}],has_more,next_cursor}`。
- `GET /messages/system?cursor=&limit=20` → `{success,items:[{id,type,title,body_html,link,created_at}],has_more,next_cursor}`。
- `POST /messages/read` body `{category:"likes"|"comments"|"system",last_read_at:"RFC3339"}` → `{success}`。
- `GET /messages/chat?cursor=&limit=20` → `{success,items:[{id,sender_type:"user"|"admin",sender_name,sender_avatar,admin_id,content_html,content_format,created_at}],has_more,next_cursor}`。
- `POST /messages/chat` body `{content_html}` → `{success,id}`；2 秒/用户限流。
- `POST /messages/chat/read` body `{last_message_id}` → `{success}`。
- `GET /messages/stream` SSE：`hello`、`message`、`notification`、`unread`、`heartbeat`、`error`；持久事件带 `id:`。

## 3. 世界频道

- `GET /world/messages?before_id=&after_id=&limit=50` → `{success,items:[{id,sender_id,sender_name,sender_avatar,content,content_format,parent_id,guild_id,guild_name,is_leader,is_admin,created_at}],has_more,next_before_id}`。
- `POST /world/messages` body `{content_html,parent_id?}` → `{success,id}`；登录；2 秒；2000 字/9 图。
- `GET /world/stream?last_id=` SSE：首包 `hello` + 200 条 `message`，随后推送；心跳 15s。
- 清理：每天 03:00 Asia/Shanghai，cutoff 保留最新 10000 条，分批删除。

## 4. 旧 APP 兼容层

- 前缀 `/api/*`，独立 group，跳过 CSRF；两代路径；响应形状见 `routes-contract.md`。
- `GET /api/World/ALL`、`GET /api/world/ALL` 裸数组（最多 100，`since`，`max-age=2`）。
- `POST /api/World/Send`、`POST /api/world/Send` → `{success,message,msg}`。
- 登录/注册写 legacy `token`+`ID` 与 `forum_session`。
- 读路径 HTML→Markdown；写路径 `content_format='markdown'`。
- `/api/app/*` 与 426 闸门。

## 5. 站点功能

- `GET /site/config` → 保持 `{theme,daily_quote,announcement}`；announcement `{enabled,text,version,updated_at}`。
- `GET /changelogs?page=&page_size=20` → `{success,items:[{id,version,title,content_html,published_at}],total,page,page_size}`。
- `GET /changelogs/:id` → `{success,item}`。
- `GET /downloads/releases?page=&page_size=20&platform=` → `{success,items:[{version,channel,date,size,url,filename,sha256,notes,mandatory,platform}],total,page,page_size}`。
- `GET /downloads/latest?platform=` → `{success,item}`。
- `GET /downloads/check?platform=&version=` → `{success,available,mandatory,current,latest,min_version,release,download_url}`。
- `GET /downloads/mirror/:platform/:filename` → 流式代理 GitHub 资产（Range）。
- `GET /site/daily-quote` → `{success,text,source}`；后端缓存 60s。

## 6. 灵力/通知/outbox 内部接口

- `AwardSpirit(ctx, tx, userID, action, sourceID)`：advisory lock + 日上限 + 唯一 source；返回 awarded/amount。
- `CreateNotification(ctx, tx, in)`：dedupe_key 幂等。
- `EnqueueEmail(ctx, tx, in)`：一行一收件人；dedupe_key。
- `EnqueueFanout(ctx, tx, postID, actorID)`：`email_fanout_jobs`，worker 展开。
- outbox worker：每 5 秒取 20 条 pending，指数退避，死信。
- `cache_invalidations` consumer：每秒取 50 条未处理，删除对应缓存 key，标记 processed；失败重试。
