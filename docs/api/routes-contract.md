# 路由契约矩阵（冻结）

> ov2 平台升级的 API 前缀、优先级与兼容层边界。实现与测试必须以此为准。

## 1. 前缀与优先级

| 优先级 | 前缀 | 语义 | 认证 | CSRF | 说明 |
|---|---|---|---|---|---|
| 1 | `/ov2/api/**` | **新 API（canonical）** | `forum_session` Cookie | 需要（GET 豁免） | 所有新前端/新功能只走这里 |
| 2 | `/api/v1/**` | **新 shape 别名** | `forum_session` Cookie | 需要（GET 豁免） | 一个版本周期内保留；响应头 `Deprecation: true` |
| 3 | `/api/**`（除 `/api/v1/**`） | **legacy shape 兼容层** | legacy `token`+`ID` Cookie 或 `forum_session` | 显式跳过 | 旧 APP；独立 handler，不转译 ov2 |

- `/api/v1` **不是**旧 V1 路径；旧 V1 路径（如 `/api/login`、`/api/World/ALL`）属于 `/api/**` 兼容层。
- Gin 路由按静态段优先匹配：`/api/v1/...` 比 `/api/*` 更具体；兼容层不要注册 `/api/v1` 通配。
- 若发现旧 V1 与 `/api/v1` 同名不同 shape（需用真实客户端抓包确认），迁到 `/api/legacy-v1/*` 或按 `X-Client-Version` 分流，禁止覆盖 `/api/v1`。

## 2. 兼容层端点清单（初版，待真实 APP 抓包补全）

### 旧 V1 形态

`POST /api/login`、`POST /api/register`、`POST /api/logout`、`POST /api/send-register-code`、`POST /api/send-code-reset-password`、`POST /api/reset-password-by-code`、`GET /api/user/info`、`POST /api/users/change`、`GET /api/users/{id}/info`、`GET /api/users/{id}/posts|favorites|following|followers`、`POST /api/users/{id}/follow`、`GET /api/users/me/replies`、`POST /api/user/avatar/upload`、`/api/posts*`、`/api/comments*`、`GET /api/World/ALL`、`POST /api/World/Send`、`GET /api/search`、`POST /api/report-bug`、`GET /api/huiguan`、`GET /Easter-Egg`、`GET /avatar/{filename}`。

### forum-new 形态

`POST /api/user/login|register|logout`、`GET/PUT/POST /api/user/info`、`POST /api/user/password`、`POST /api/user/email`、`POST /api/user/delete`、`GET /api/user/{id}`、`GET /api/user/{id}/posts|favorites|comments|following|followers`、`/api/posts*`、`/api/comments*`、`GET /api/world/ALL`、`POST /api/world/Send`、`GET /api/search`、`POST /api/email/*`、`POST /api/captcha/challenge|verify`、`GET /captcha-embed`、`/api/app/*`、`GET /healthz`。

## 3. 兼容层响应约定

- 世界频道 GET：**裸 JSON 数组**（最多 100，支持 `since`，`Cache-Control: max-age=2`），字段 `id/sender_id/sender_name/content/parent_id/sender_avatar/created_at`。
- 登录/注册：`{success,message,Token,user}`；`Token` 为 legacy 格式；同时写 `token`+`ID` 与 `forum_session`。
- 帖子/评论：`content` 输出保守 Markdown；`content_format='html'` 时转换，`markdown` 原样返回；`div[data-embed]` 等新节点过滤；raw HTML 转义、链接/图片 scheme 白名单。
- 旧 APP 写帖/评论：按 `content_format='markdown'` 原样存，不做有损 Markdown→HTML。
- 版本闸门：`/api/app/check` 与所有 `/api/*`（除 `/api/app/*`、OPTIONS、非 `/api/`）按 `min_versions=最新 stable` 返回 426。

## 4. 认证与安全

- 兼容层显式跳过 CSRF，但要求 `X-Legacy-Client` 或已知 UA/版本；按 IP/账号限流。
- legacy token：`token---{md5}.{hmac}---{st}`；`st` 必须在 `[max(password_changed_at, LEGACY_TOKEN_NOT_BEFORE), now+5m]`，且 `now-st <= LEGACY_TOKEN_TTL`；查 `is_banned/deleted_at`；每次认证轮换 `forum_session`。
- 兼容层不强制 ALTCHA；使用 legacy grant/邮箱验证码 + 限流 + 监控；配置 `LEGACY_APP_SUNSET` 并在响应头提示下线日期。

## 5. 契约测试

- 用 `forum-legacy/API.json` + 真实 APP 版本建立黄金样例（登录、帖子详情、评论、世界裸数组、用户资料、426）。
- 断言：路径、状态码、外层结构、关键字段、Content-Type、世界数组形状。
- 每次改兼容层必须跑黄金测试；不做“只测新 API”的假兼容。
