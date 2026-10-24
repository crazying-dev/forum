# 妖精论坛 ov2 API 文档

> 本目录维护 ouo 自身的 API 契约。`openapi.yaml` 是机器可读清单，`endpoints.md` 是自动生成的端点索引，模块文档给出请求/响应示例与边界。

## 1. 基础

| 项 | 说明 |
|---|---|
| canonical base | `/ov2/api`（无 v1 段） |
| 新 shape 别名 | `/api/v1`（一个版本周期，响应头 `Deprecation: true`） |
| 旧 APP 兼容层 | `/api/*`（legacy shape；两代路径；独立 handler） |
| 认证 | `forum_session` HttpOnly Cookie；旧 APP 另认 `token`+`ID` |
| 时间 | RFC3339（服务端 Go `time.Time` JSON） |
| 分页 | `cursor` + `limit`；响应 `{items,has_more,next_cursor}` |

## 2. 统一响应

成功：
```json
{ "success": true, "...": "..." }
```
失败：
```json
{ "success": false, "message": "可读错误" }
```

状态码：200/201 成功，400 参数/验证失败，401 未登录，403 禁止，404 不存在，409 冲突，413 过大，426 旧 APP 版本过低，429 限流，500 服务器错误，503 配置未就绪。

## 3. 认证与 ALTCHA

- 登录/注册/注册发码/忘记密码/重置提交/Bug 提交在 ALTCHA 启用时接受 `altcha`（Base64 payload）或 `grant`。
- `GET /captcha/config` 返回是否启用；`GET /captcha/challenge` 返回官方 challenge；`POST /captcha/verify` 返回 5 分钟 grant。
- 注册发码与注册提交都检查邮箱黑名单；命中返回 400 `{"success":false,"message":"邮箱异样"}`。

## 4. SSE

- `GET /world/stream`（公开）与 `GET /messages/stream`（登录）。
- 事件：`hello`、`message`/`notification`/`unread`、`heartbeat`、`error`。
- 持久事件带 `id:`；断线用 `Last-Event-ID` 续传。
- 响应头：`Cache-Control: no-cache, no-transform`、`X-Accel-Buffering: no`。

## 5. 媒体

- 上传：`POST /media/images`（multipart `file` + `scene`）。
- 读取：`GET /media/:id`，按 `visibility` 做 ACL（public / 本人 / 聊天成员 / 定时帖作者）。
- 新 URL：`/ov2/api/media/<id>`；旧 `/api/v1/media/<id>`、`/avatar/*`、`/static/*` 继续可用；`/guild-img/*`、`/guide-img/*` 已退役。

## 6. 文档索引

- [openapi.yaml](./openapi.yaml) — OpenAPI 3.1 路径清单
- [endpoints.md](./endpoints.md) — 全部端点（自动生成）
- [auth.md](./auth.md) — 认证/ALTCHA/黑名单
- [media.md](./media.md) — 媒体上传/ACL/兼容
- [messages.md](./messages.md) — 消息中心/管理团队/SSE
- [world.md](./world.md) — 世界频道/SSE/清理
- [site.md](./site.md) — 站点配置/公告/更新日志/每日一言
- [downloads.md](./downloads.md) — 下载/版本检查/镜像
- [compat.md](./compat.md) — 旧 APP 兼容层
- [routes-contract.md](./routes-contract.md) — 路由优先级与 legacy 契约
- [backend-contract.md](./backend-contract.md) — 并行模块共享契约
