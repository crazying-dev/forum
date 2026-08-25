# 妖精论坛 API 规范（forum-new v1.1）

---

## 0. 版本变更说明

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.1  | 2026-08 | 后端重写为 modular Blueprint；认证 Cookie 收敛为仅 `token` + `ID`；新增注册 / 资料 / 改密 / 公开查询接口；响应 `end` 字段统一改为 `success` |
| 1.0  | 旧版   | （老项目 forum/ 的规范，已不适用 forum-new） |

OpenAPI 机器可读文档见同目录 [API.json](./API.json)，版本号同步为 `1.1.0`。

---

## 1. 认证

### 1.1 Cookie（仅此两个字段，无其他）

登录成功后，服务端通过 `Set-Cookie` 写入**两个 HttpOnly Cookie**，有效期默认 7 天，`Path=/`、`SameSite=Lax`：

| Cookie 名 | 内容格式 | 说明 |
|-----------|----------|------|
| `token`   | `token---{md5hex}.{hmac_sha256hex}---{send_time}` | 用户登录凭证，按 forum-new/GetToken.py 原有算法生成：<br>`md5hex = md5(repr((user_id, password_hash, client_ip))).hex`<br>`hmac = HMAC-SHA256(SECRET_KEY, repr((user_id, password_hash, client_ip))).hex`<br>send_time 为 10 位秒级时间戳 |
| `ID`      | `RL` + 16 位 HEX（仅 HG / YJ / RL 三种前缀） | 用户 ID，与 users 表 id 字段一致 |

说明：
- 推荐直接使用浏览器/客户端 Cookie 存储，前端无需手动解析 token 串。
- 响应体同时返回 `Token` 字段（与 cookie token 内容完全一致），方便客户端在不方便自动保存 Cookie 时自行保存。
- 修改密码、登出会立即清除这两个 Cookie。

### 1.2 Token 有效期 & 校验

- 默认 TTL：**7 天**（`config.TOKEN_TTL_SECONDS = 604800`）。
- 校验顺序：检查 `ID` → 查数据库确认用户未封禁 → `SHA256(token 中的 send_time + user_id)` 重算并 `hmac.compare_digest` 匹配 → TTL 未过期。
- 客户端 IP 变化时，会再做一次「不带 IP 宽松匹配」的兜底，避免频繁 WIFI/移动网络切换导致掉线。

### 1.3 401 响应

未登录 / Cookie 失效 / 用户被封禁 → 所有需登录接口返回 `401`，响应体：
```json
{ "success": false, "message": "请先登录" }
```

---

## 2. 请求协议

### 2.1 基础 URL

- 生产：`https://www.yjlt.top`
- 本地：`http://localhost:3000`

### 2.2 Content-Type

- 请求 body：统一 `application/json; charset=utf-8`
- 响应 body：统一 `application/json; charset=utf-8`

### 2.3 请求方法

按 REST 语义使用相应方法，不再强制全 POST：

| 方法 | 典型用途 | 示例 |
|------|----------|------|
| GET  | 读取资源   | GET /api/user/info、GET /api/user/<id> |
| POST | 创建 / 动作（登录、登出、注册、改密） | POST /api/user/login、POST /api/user/register |
| PUT  | 全量/部分更新 | PUT /api/user/info 更新用户资料（POST 作为别名同样接受） |

### 2.4 统一字段

**客户端 IP 上报**：所有用户相关接口内部都会通过 `tool.GETIP(client_ip)` 上报 IP。IP 取值优先级：
1. `X-Forwarded-For` 头第一个（代理后）
2. `request.remote_addr`（直连）

---

## 3. 响应

### 3.1 统一外层结构

```json
{
  "success": true | false,
  "message": "人类可读描述",
  // 可选：其他业务字段，如 user / Token / id / avatar / error
}
```

- `success`（布尔）：请求是否成功；替代旧规范的 `end` 字段。
- `message`（字符串）：永远存在，提供给前端展示给用户的文案。
- 机器可读错误码：注册冲突等场景会额外带 `error` 字段（例：`name_exists` / `email_exists`）。

### 3.2 全局错误响应

| HTTP 状态码 | 含义 | 典型场景 |
|-------------|------|----------|
| 200         | 成功 | 登录/登出/注册/查询/更新/改密成功 |
| 400         | 参数非法 / 业务拒绝 | 昵称太短、昵称已占用、原密码错误、强度不够 |
| 401         | 未登录 / 鉴权失败 | token 缺失、过期、校验失败 |
| 404         | 资源不存在 | path 不存在 / 用户 ID 查不到 / 被封禁 |
| 405         | 方法不允许 | 用 DELETE 请求只支持 GET/POST 的端点 |
| 500         | 服务端内部错误 | 未捕获的异常 |

---

## 4. 用户相关接口（当前已实现）

> 对应 Blueprint：`api.user.user_bp`，挂载前缀 `/api/user`

### 4.1 登录 —— POST /api/user/login

- **鉴权**：不需要
- **Body**：
  ```jsonc
  {
    "name":     "小黑",         // 与 email 二选一
    "email":    "a@yjlt.top",   // 与 name 二选一
    "password": "Hello123"      // 必填
  }
  ```
- **成功 200**：返回当前用户资料，并 Set-Cookie 两个字段。
- **失败 401**：账号/密码错误或用户被封禁。

### 4.2 登出 —— POST /api/user/logout

- **鉴权**：不需要（登出是幂等的，未登录也返回成功）
- **成功 200**：删除 `token` 与 `ID` Cookie。

### 4.3 注册 —— POST /api/user/register

- **鉴权**：不需要
- **Body**：
  ```jsonc
  {
    "name":     "小白",        // 2-20 字符，唯一
    "email":    "b@yjlt.top",  // 合法邮箱，唯一
    "password": "Hello456"     // ≥8 位，必须同时含字母与数字
  }
  ```
- **成功 200**：写库 + 自动登录（写 token/ID Cookie），随机分配默认头像。
- **失败 400**：字段校验失败或唯一冲突。冲突时额外返回 `error` 枚举：
  - `name_exists` — 用户名已占用
  - `email_exists` — 邮箱已注册

### 4.4 获取当前用户资料 —— GET /api/user/info

- **鉴权**：需要（未登录 401）
- **成功 200**：
  ```jsonc
  {
    "success": true,
    "user": {
      "id": "URxxxxxxxxxxxxxxxx",
      "name": "小黑",
      "avatar": "https://...",
      "email": "a@yjlt.top",   // 仅本人可见
      "gender": 1,
      "age": "20",
      "intro": "...",
      "vip": "0",
      "prefix": "",
      "email_verified": 0,
      "created_at": "2026-08-24T12:00:00+08:00",
      "last_login": "2026-08-24T19:30:00+08:00"
    }
  }
  ```

### 4.5 更新当前用户资料 —— PUT /api/user/info（别名：POST /api/user/info）

- **鉴权**：需要
- **Body**：至少包含以下字段中的一个（可写字段白名单）：
  | 字段   | 类型 | 说明 |
  |--------|------|------|
  | avatar | str  | 头像 URL |
  | gender | int  | 0 / 1 / 2 |
  | age    | str  | ≤32 字符 |
  | intro  | str  | 个人简介 |
  | name   | str  | 新昵称（2-20 字符，做唯一性校验） |
  | prefix | str  | 称号前缀（≤32 字符） |
- **成功 200**：返回更新后的最新资料。
- **失败 400**：字段非法 / 昵称冲突。

### 4.6 修改密码 —— POST /api/user/password

- **鉴权**：需要
- **Body**：
  ```jsonc
  {
    "old_password": "Hello123",
    "new_password": "World456"   // 强度同注册，且不能等于旧密码
  }
  ```
- **成功 200**：密码更新，清除 `token` / `ID` Cookie（强制重新登录）。
- **失败 400**：旧密码错误 / 新密码不符合强度 / 新旧相同。

### 4.7 查询任意用户公开资料 —— GET /api/user/{user_id}

- **鉴权**：不需要
- **Path 参数**：`user_id` = 用户 ID（RL 前缀字符串；仅支持 HG / YJ / RL 三种前缀）
- **成功 200**：返回字段比「本人资料」**少一个 email**，其他相同。
- **失败 404**：ID 不存在或用户被封禁。

---

## 5. 系统接口

### 5.1 健康检查 —— GET /healthz

- 无鉴权
- 成功：`200 {"ok": true, "service": "forum-new"}`

### 5.2 根路径 —— GET /

- 无鉴权
- 成功：`200 {"ok": true, "service": "forum-new", "api": {"user": "/api/user/*"}}`

---

## 6. 数据校验规则（前后端统一）

| 字段 | 规则 | 对应函数 |
|------|------|----------|
| 用户名 | 2-20 字符，不为空 | `validate_username()` in api/encrypt.py |
| 邮箱   | 符合 `^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$` | `is_valid_email()` |
| 密码   | ≥8 位 + 至少 1 个字母 + 至少 1 个数字 | `validate_password()` |
| 昵称修改 | 同用户名规则 + 数据库唯一性校验 | `update_user()` |

---

## 7. Token 生成算法精确描述（与 tool/GetToken.py 完全一致）

```python
import hashlib, hmac, os

SECRET_KEY = os.getenv("SECRET_KEY", "TestKeyFor1").encode("utf-8")

def GetToken(*args):
    raw_data = repr(args).encode("utf-8")
    sig    = hmac.new(SECRET_KEY, raw_data, hashlib.sha256).hexdigest()   # 64 hex
    digest = hashlib.md5(raw_data).hexdigest()                             # 32 hex
    return f"{digest}.{sig}"
```

登录写入 cookie 时，实际调用：
```
core = GetToken(user_id, password_hash, client_ip)
full_token_str = f"token---{core}---{int(time.time())}"   # 写入 cookie 的 token
```

> 任何外部实现要自行生成 token（例如第三方 App），需要严格保持 `repr(args)` 的 Python 原生格式字符串，否则哈希会不匹配。

---

## 8. 后续扩展规范

新增业务模块（world / post / comment / file ...）时按同样结构扩展：

1. 在 `api/<module>/__init__.py` 创建一个 Blueprint，命名 `<module>_bp`。
2. 在 `api/__init__.py::register_blueprints(app)` 中按
   ```python
   app.register_blueprint(<module>_bp, url_prefix="/api/<module>")
   ```
   注册。
3. 所有写操作使用 `db.execute_query` / `db.execute_insert`，禁止裸连接。
4. 所有鉴权统一走 `cookieAuth`（即 token + ID Cookie），不要新增其他 Token 类型或 Header 方案。
5. 文档同步更新：API.json 追加 `paths` / `components`；本文件追加对应接口章节。


---

## 9. 帖子相关接口（/api/posts/*）

> Blueprint：`api.post.post_bp`，挂载前缀 `/api/posts`。

### 9.1 帖子列表 —— GET /api/posts

- 查询参数：`page`（默认 1）、`page_size`（默认 20，最大 100）、`category`（可选）、`sort`（可选，默认 `time`）
  - `sort=time`：按发布时间倒序（最新在前）
  - `sort=comprehensive`：综合热度排序（likes×3 + views 降序）
  - `sort=random`：随机排序
- 成功 200：`{success, posts: [PostListItem], page, page_size}`
- `PostListItem`：id / user_id / title / summary（正文前 200 字）/ category / likes / views / created_at / user_name / user_avatar

### 9.2 随机帖子 —— GET /api/posts/random

- 成功 200：`{success, posts: [...]}`（最多 200 条，随机排序）

### 9.3 帖子详情 —— GET /api/posts/{post_id}

- 无需登录；登录时额外返回 `liked` / `favorited` 状态
- 每次访问浏览量 +1
- 成功 200：`{success, post: PostDetail, comments: [Comment], liked, favorited}`
- 失败 404：帖子不存在

### 9.4 发布帖子 —— POST /api/posts/create

- **鉴权**：需要
- Body：`title`（≤100 字，必填）、`content`（HTML，必填，入库前 XSS 净化）、`category`（默认 `general`，白名单：general / 叶羽 / 创意 / 求助）
- 成功 200：`{success, id}`
- 发帖后异步邮件通知粉丝（失败静默，不影响发布）

### 9.5 点赞 / 取消点赞 —— POST /api/posts/{post_id}/like

- **鉴权**：需要；切换式（已赞则取消）
- 成功 200：`{success, liked, likes}`

### 9.6 收藏 / 取消收藏 —— POST /api/posts/{post_id}/favorite

- **鉴权**：需要；切换式
- 成功 200：`{success, favorited}`

### 9.7 举报帖子 —— POST /api/posts/{post_id}/report

- **鉴权**：需要
- Body：`reason`（必填）、`detail`（≤500 字）

### 9.8 删除帖子 —— POST /api/posts/{post_id}/delete

- **鉴权**：需要，仅作者本人
- 失败 403：无权删除；404：帖子不存在

---

## 10. 评论相关接口（/api/posts/{post_id}/comments* 与 /api/comments/*）

> Blueprint：`api.comment.comment_bp`，挂载前缀 `/api`。

### 10.1 评论列表 —— GET /api/posts/{post_id}/comments

- 查询参数：`page`（默认 1）、`page_size`（默认 50，最大 100）
- 成功 200：`{success, comments: [Comment], page, page_size}`
- `Comment`：id（CM 前缀）/ user_id / content / parent_id（楼中楼）/ likes / created_at / user_name / user_avatar

### 10.2 发表评论 —— POST /api/posts/{post_id}/comments/create

- **鉴权**：需要
- Body：`content`（≤500 字，必填）、`parent_id`（可选，回复指定评论）
- 成功 200：`{success, comment: Comment}`

### 10.3 删除评论 —— POST /api/comments/{comment_id}/delete

- **鉴权**：需要，仅作者本人（软删除：status=0）

---

## 11. 世界频道（/api/world/*）

> Blueprint：`api.world.world_bp`，挂载前缀 `/api/world`。

### 11.1 消息列表 —— GET /api/world/ALL

- 无鉴权；成功 200 直接返回消息数组（最近 100 条，时间倒序）
- 响应头 `Cache-Control: max-age=2`

### 11.2 发送消息 —— POST /api/world/Send

- **鉴权**：需要；每用户 2 秒一条（超限 429）
- Body：`content`（≤500 字，必填）、`parent_id`（可选）
- 发送时自动清理 5 分钟前的历史消息

---

## 12. 搜索（/api/search）

- `GET /api/search?k=<关键词>&page=1&page_size=20&type=both`
- `type`：`posts` / `users` / `both`（默认 both）
- 关键词 ≥2 字符（否则 400）；支持空格分隔多关键词（AND 关系）
- 相关性排序：标题/名称命中 > 内容/称号 > 分类/简介
- 成功 200：`{success, keyword, posts, posts_total, posts_has_more, users, users_total, users_has_more, page, page_size}`

---

## 13. 邮箱验证 / 找回密码（/api/email/*）

> Blueprint：`api.email.email_bp`，挂载前缀 `/api`；依赖 SMTP（config.SMTP_*）。

### 13.1 发送邮箱验证邮件 —— POST /api/email/send-verify-email

- **鉴权**：需要；邮箱已验证时返回 400
- 成功 200：`验证邮件已发送`；SMTP 不可用时 503

### 13.2 验证邮箱 —— POST /api/email/verify-email

- Body：`token`（邮件链接中的 token，有效期 30 分钟）
- 成功 200：邮箱验证成功（`email_verified = 1`）

### 13.3 发送重置密码邮件 —— POST /api/email/send-reset-password

- Body：`email`
- 防邮箱枚举：邮箱未注册时同样返回成功提示

### 13.4 重置密码 —— POST /api/email/reset-password

- Body：`token` + `password`（≥8 位，字母+数字）
- 成功 200：密码重置成功

---

## 14. 用户社交（并入 /api/user/*）

### 14.1 关注 / 取消关注 —— POST /api/user/{user_id}/follow

- **鉴权**：需要；切换式；不能关注自己（400）
- 成功 200：`{success, following}`

### 14.2 关注列表 —— GET /api/user/{user_id}/following

- 无鉴权；返回 `users: [FollowUser]`（含 `is_following` / `is_self` 当前访问者视角字段）

### 14.3 粉丝列表 —— GET /api/user/{user_id}/followers

- 同上

### 14.4 用户统计（并入用户资料）

- `GET /api/user/info` 与 `GET /api/user/{user_id}` 的 `user` 对象新增 `stats` 字段：
  - `post_count` / `total_likes` / `total_views`（帖子统计）
  - `following_count` / `follower_count`（关注统计）
- 公开资料接口额外返回 `is_following` / `is_self`

### 14.5 上传头像 —— POST /api/user/avatar/upload

- **鉴权**：需要；`multipart/form-data`，字段名 `avatar`（≤5MB）
- 服务端裁剪压缩为 400×400 WebP（质量 85），上传 Cloudflare Images
- 未配置存储服务返回 503；上传失败返回 502
- 成功 200：`{success, avatar: <URL>}`

---

## 15. 杂项接口

### 15.1 Bug 反馈 —— POST /api/report-bug

- 游客可提交；登录用户自动记录 reporter_id / reporter_name
- Body：`title`（≤200，必填）、`detail`（≤5000，必填）、`steps`（≤3000）、`contact`（≤200）、`page_url`
- 成功 200：`{success, id}`

### 15.2 会馆列表 —— GET /api/huiguan

- 读取静态数据 `huiguan.json`，返回 `{success, list}`

### 15.3 彩蛋 —— GET /Easter-Egg

- 从 `EasterEgg/1.json` 随机返回一条

### 15.4 RSS —— GET /rss.xml

- 生成最新 20 条帖子的 RSS 2.0（`application/rss+xml`）

---

## 16. 已实现接口总览

| 模块 | 方法 | 路径 | 鉴权 |
|------|------|------|------|
| 认证 | POST | /api/user/register | 无 |
| 认证 | POST | /api/user/login | 无 |
| 认证 | POST | /api/user/logout | 无 |
| 用户 | GET | /api/user/info | 需登录 |
| 用户 | PUT/POST | /api/user/info | 需登录 |
| 用户 | POST | /api/user/password | 需登录 |
| 用户 | POST | /api/user/avatar/upload | 需登录 |
| 用户 | GET | /api/user/{user_id} | 无 |
| 用户 | POST | /api/user/{user_id}/follow | 需登录 |
| 用户 | GET | /api/user/{user_id}/following | 无 |
| 用户 | GET | /api/user/{user_id}/followers | 无 |
| 帖子 | GET | /api/posts | 无 |
| 帖子 | GET | /api/posts/random | 无 |
| 帖子 | GET | /api/posts/{post_id} | 无 |
| 帖子 | POST | /api/posts/create | 需登录 |
| 帖子 | POST | /api/posts/{post_id}/like | 需登录 |
| 帖子 | POST | /api/posts/{post_id}/favorite | 需登录 |
| 帖子 | POST | /api/posts/{post_id}/report | 需登录 |
| 帖子 | POST | /api/posts/{post_id}/delete | 需登录（作者） |
| 评论 | GET | /api/posts/{post_id}/comments | 无 |
| 评论 | POST | /api/posts/{post_id}/comments/create | 需登录 |
| 评论 | POST | /api/comments/{comment_id}/delete | 需登录（作者） |
| 世界 | GET | /api/world/ALL | 无 |
| 世界 | POST | /api/world/Send | 需登录 |
| 搜索 | GET | /api/search | 无 |
| 邮箱 | POST | /api/email/send-verify-email | 需登录 |
| 邮箱 | POST | /api/email/verify-email | 无 |
| 邮箱 | POST | /api/email/send-reset-password | 无 |
| 邮箱 | POST | /api/email/reset-password | 无 |
| 反馈 | POST | /api/report-bug | 无（登录可选） |
| 杂项 | GET | /api/huiguan | 无 |
| 杂项 | GET | /Easter-Egg | 无 |
| 杂项 | GET | /rss.xml | 无 |
| 系统 | GET | /healthz | 无 |
| 系统 | GET | / | 无 |


---

## 17. 前端页面（forum-new v1.2 新增）

前端已全面重构并接入 forum-new API（token + ID Cookie），资源本地化于 `static/` 与 `templates/`。

### 17.1 页面路由

| 路径 | 模板 | 说明 |
|------|------|------|
| / | index.html | 首页（随机推荐 + 收藏） |
| /forum | forum.html | 帖子列表（分类筛选 / 加载更多） |
| /post/{post_id} | post_detail.html | 帖子详情 + 评论 |
| /post/create | post_create.html | 发布帖子（需登录） |
| /login | auth.html | 登录（世界频道栏隐藏） |
| /register | auth.html | 注册（世界频道栏隐藏） |
| /reset-password | auth.html | 找回密码（世界频道栏隐藏） |
| /search | search.html | 搜索（帖子 / 用户） |
| /users/{user_id} | users.html | 用户资料 + 帖子 |
| /privacy | privacy.html | 隐私政策 |
| /Live2D | live2d.html | 罗小黑 Live2D 模型展示（独立页，隐藏世界频道栏） |

### 17.2 世界频道（右侧常驻面板）

- 不再使用独立页面 /World，改为**全局右侧常驻面板**（登录/注册等精简页除外）
- 默认展开；桌面端可**拖拽左侧手柄调整宽度**（240~560px，localStorage 记忆）；可点击按钮**收起/展开**
- 移动端（≤900px）**自动收起**，右下角浮动按钮呼出
- **长连接**：WebSocket `ws(s)://<host>/ws/world`
  - 连接即推送 `{type: "history", messages: [...]}`（最近 100 条，含发送人头像）
  - 新消息实时推送 `{type: "message", message: {...}}`
  - 断线自动指数退避重连（2s → 30s）
- 发送消息仍走 `POST /api/world/Send`，服务端广播给所有在线连接
- 消息保留策略：保留最近 1000 条（不再 5 分钟清理）

### 17.3 静态资源

- `static/css/main.css`：精简样式（保持原青绿风格，亮/暗双主题，约 12KB）
- `static/js/AfterBody.js`：前端主脚本（API 封装 / 认证 / 主题 / 世界频道 / 页面渲染）
- 不再依赖 CDN 的 main.css / AfterBody.js（font-awesome 图标保留 CDN 引用）
