# 旧 APP 兼容层

> 完整路由优先级与两代端点清单见 [routes-contract.md](./routes-contract.md)。

## 前缀

`/api/*`（不含 `/api/v1`）；独立 handler，显式跳过 CSRF；不转译 ov2 handler。

## 认证

- 登录/注册同时写 `token`+`ID`（legacy）与 `forum_session`。
- 后续请求优先认 `forum_session`，否则用 `legacy.TokenVerifier` 校验 `token`+`ID`：接受窗口、`password_changed_at`、`is_banned/deleted_at`；通过后轮换 `forum_session`。
- 兼容层不强制 ALTCHA；用 legacy grant/邮箱验证码 + IP/UA/版本限流 + `LEGACY_APP_SUNSET`。

## 账号与会话（旧 APP 账号中心）

以下端点供旧 APP 的注册/找回/改密/邮箱/注销流程使用，均返回 legacy shape `{success,message}`：

| 场景 | 端点 | 认证 |
|---|---|---|
| 注册发码 | `POST /api/email/send-register-code`、`/api/send-register-code` | 否 |
| 找回密码发码 | `POST /api/email/send-code-reset-password`、`/api/send-code-reset-password` | 否 |
| 验证码重置密码 | `POST /api/email/reset-password-by-code`、`/api/reset-password-by-code` | 否 |
| 修改密码 | `POST /api/email/send-change-password-code`、`POST /api/user/password` | 是 |
| 邮箱验证（验证码/链接） | `POST /api/email/send-verify-code`、`/api/email/verify-code-email`、`/api/email/send-verify-email`、`/api/email/verify-email` | 部分 |
| 换绑邮箱 | `POST /api/email/send-change-email-old-code`、`/api/email/send-change-email-code`、`POST /api/user/email` | 是 |
| 注销账号 | `POST /api/email/send-delete-account-code`、`POST /api/user/delete` | 是 |
| 用户评论列表 | `GET /api/user/{id}/comments`、`GET /api/users/{id}/comments` | 可选 |

约束：验证码一次性、限流（发码 5 次/10 分钟、重置提交 10 次/10 分钟）；改密/注销后撤销全部会话；注销按配置执行 `PurgeUser` 或 `AnonymizeUser`；邮箱黑名单命中统一返回 400 `{"success":false,"message":"邮箱异样"}`。

## 内容

- 读路径：`content_format='html'` → 保守 Markdown；`markdown` 原样；过滤 `div[data-embed]`；raw HTML 转义；链接/图片 scheme 白名单。
- 写路径：旧 APP 发帖/评论/世界消息按 `content_format='markdown'` 原样入库。

## 世界频道

- `GET /api/World/ALL`、`GET /api/world/ALL` → 裸数组（最多 100，支持 `since`，`Cache-Control: max-age=2`），字段含 `sender_avatar`。
- `POST /api/World/Send`、`POST /api/world/Send` → `{success,message,msg}`；纯文本 500 字/2 秒。

## 版本闸门

- `/api/app/*` 豁免；其他 `/api/*` 按 `X-Client-Platform`/`X-Client-Version`（UA 兜底）检查；低于 min_version 返回 426 `VERSION_TOO_LOW`，带 `download_url/download_page`。
