# 妖精论坛 API 文档

> 基础地址：`https://yjlt.top`  
> 响应格式：`application/json`  
> 认证方式：Cookie (Flask-Login session)

---

## 统一响应格式

所有接口返回 JSON，结构如下：

```json
{
  "success": true,
  "message": "操作成功"
}
```

- `success` (boolean)：请求是否成功
- `message` (string, 可选)：提示信息
- 其他字段根据接口不同而异

---

## 目录

- [认证相关](#认证相关)
- [用户相关](#用户相关)
- [帖子相关](#帖子相关)
- [评论相关](#评论相关)
- [世界频道](#世界频道)
- [搜索](#搜索)
- [会馆](#会馆)
- [其他](#其他)

---

## 认证相关

### 注册

```
POST /api/register
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 是 | 用户名（2-20字符，不含彩蛋） |
| email | string | 是 | 邮箱地址 |
| password | string | 是 | 密码（至少8位，需包含字母和数字） |

**响应：**

```json
{
  "success": true,
  "id": 123
}
```

**限流：** 5次 / 5分钟 / IP

---

### 登录

```
POST /api/login
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 是 | 用户名或邮箱 |
| password | string | 是 | 密码 |
| remember | boolean | 否 | 是否记住登录，默认 true |

**响应：**

```json
{
  "success": true,
  "id": 123
}
```

**说明：**
- 登录成功后设置 Session Cookie
- 账号已封禁返回 `"该账号已被封禁"`
- 用户名或密码错误统一返回 `"账号或密码错误"`（防用户枚举）

**限流：** 10次 / 5分钟 / IP

---

### 登出

```
POST /api/logout
GET  /api/logout
```

**响应：**

```json
{
  "success": true
}
```

---

### 发送邮箱验证邮件

```
POST /api/send-verify-email
```

**需要登录：** 是

**响应：**

```json
{
  "success": true,
  "message": "验证邮件已发送，请查收邮箱"
}
```

**限流：** 3次 / 5分钟 / IP

---

### 验证邮箱

```
POST /api/verify-email
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| token | string | 是 | 邮箱验证 token |

**响应：**

```json
{
  "success": true,
  "message": "邮箱验证成功"
}
```

---

### 发送重置密码邮件

```
POST /api/send-reset-password
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| email | string | 是 | 注册邮箱 |

**响应：**

```json
{
  "success": true,
  "message": "如果该邮箱已注册，重置链接已发送至邮箱"
}
```

**说明：** 无论邮箱是否注册，均返回相同消息（防邮箱枚举）。

**限流：** 3次 / 5分钟 / IP

---

### 重置密码

```
POST /api/reset-password
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| token | string | 是 | 重置密码 token |
| password | string | 是 | 新密码（至少8位，需包含字母和数字） |

**响应：**

```json
{
  "success": true,
  "message": "密码重置成功"
}
```

---

## 用户相关

### 获取当前登录用户信息

```
GET /api/user/info
```

**需要登录：** 是

**响应：**

```json
{
  "success": true,
  "user": {
    "id": 123,
    "name": "用户名",
    "avatar": "https://...",
    "vip": "0",
    "email_verified": 0
  }
}
```

---

### 获取指定用户信息

```
GET /api/users/<user_id>/info
```

**路径参数：**

| 参数 | 类型 | 说明 |
|---|---|---|
| user_id | int | 用户 ID |

**响应：**

```json
{
  "success": true,
  "user": {
    "id": 123,
    "name": "用户名",
    "avatar": "https://...",
    "gender": "male",
    "age": "19900101",
    "intro": "个人简介",
    "vip": "0",
    "email_verified": 0,
    "created_at": "2025-01-01T00:00:00",
    "last_login": "2025-01-02T00:00:00"
  },
  "stats": { "posts": 10, "followers": 5, "following": 3 },
  "follow_stats": { "followers": 5, "following": 3 },
  "is_following": false,
  "is_self": false
}
```

**缓存：** L1 5分钟 / L2 30分钟

---

### 获取用户帖子列表

```
GET /api/users/<user_id>/posts?page=1&page_size=20
```

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页条数 |

**响应：**

```json
{
  "success": true,
  "posts": [...],
  "page": 1,
  "page_size": 20
}
```

**缓存：** L1 1分钟 / L2 5分钟

---

### 修改用户资料

```
POST /api/users/change
```

**需要登录：** 是

**请求体：**

```json
{
  "Info": {
    "Name": "新用户名",
    "gender": "male",
    "age": "19900101",
    "intro": "新简介",
    "avatar": "https://..."
  }
}
```

| Info 字段 | 类型 | 说明 |
|---|---|---|
| Name | string | 用户名（2-20字符，不含彩蛋） |
| gender | string | 性别：`male` / `female` / `secret` |
| age | string | 出生日期，格式 `yyyymmdd`（纯数字） |
| intro | string | 个人简介 |
| avatar | string | 头像 URL |

**响应：**

```json
{
  "success": true
}
```

---

### 上传头像

```
POST /api/user/avatar/upload
Content-Type: multipart/form-data
```

**需要登录：** 是

**表单字段：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| avatar | file | 是 | 头像图片文件 |

**处理：** 图片将被裁剪压缩为 400×400 WebP（质量85），存储至 Vercel Blob。

**响应：**

```json
{
  "success": true,
  "avatar": "https://..."
}
```

---

### 获取用户收藏

```
GET /api/users/<user_id>/favorites?page=1&page_size=20
```

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页条数 |

**响应：**

```json
{
  "success": true,
  "posts": [...],
  "page": 1,
  "page_size": 20
}
```

---

### 关注 / 取消关注

```
POST /api/users/<user_id>/follow
```

**需要登录：** 是

**说明：** 切换关注状态（已关注则取消，未关注则关注）。

**响应：**

```json
{
  "success": true,
  "is_following": true
}
```

---

### 获取关注列表

```
GET /api/users/<user_id>/following?page=1&page_size=20
```

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页条数 |

**响应：**

```json
{
  "success": true,
  "users": [
    {
      "id": 123,
      "name": "用户名",
      "avatar": "https://...",
      "is_following": false,
      "is_self": false
    }
  ],
  "page": 1,
  "page_size": 20
}
```

---

### 获取粉丝列表

```
GET /api/users/<user_id>/followers?page=1&page_size=20
```

**查询参数：** 同上

**响应：** 同上

---

## 帖子相关

### 获取帖子列表

```
GET /api/posts?page=1&page_size=20&category=general
```

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| page | int | 1 | 页码 |
| page_size | int | 20 | 每页条数 |
| category | string | - | 分类筛选（可选） |

**响应：**

```json
{
  "success": true,
  "posts": [...],
  "page": 1,
  "page_size": 20
}
```

**缓存：** L1 30秒 / L2 2分钟  
**响应头：** `Cache-Control: max-age=30`、`X-Cache: HIT/MISS`

---

### 随机帖子

```
GET /api/posts/random
```

**响应：**

```json
{
  "success": true,
  "posts": [...]
}
```

---

### 获取帖子详情

```
GET /api/posts/<post_id>
```

**响应：**

```json
{
  "success": true,
  "post": {
    "id": 1,
    "title": "帖子标题",
    "content": "<p>HTML内容</p>",
    "author_id": 123,
    "author_name": "用户名",
    "author_avatar": "https://...",
    "category": "general",
    "views": 100,
    "likes": 10,
    "comments_count": 5,
    "created_at": "2025-01-01T00:00:00"
  },
  "comments": [...],
  "liked": false,
  "favorited": false
}
```

**缓存：** L1 1分钟 / L2 5分钟  
**说明：** 每次访问浏览量 +1

---

### 发布帖子

```
POST /api/posts/create
```

**需要登录：** 是

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| title | string | 是 | 标题（最多100字） |
| content | string | 是 | 内容（HTML格式） |
| category | string | 否 | 分类，默认 `general` |

**响应：**

```json
{
  "success": true,
  "id": 1
}
```

**限流：** 10次 / 分钟 / 用户

---

### 点赞帖子

```
POST /api/posts/<post_id>/like
```

**需要登录：** 是

**说明：** 切换点赞状态。

**响应：**

```json
{
  "success": true,
  "liked": true
}
```

---

### 删除帖子

```
POST /api/posts/<post_id>/delete
```

**需要登录：** 是（仅作者或管理员）

**响应：**

```json
{
  "success": true
}
```

---

### 收藏帖子

```
POST /api/posts/<post_id>/favorite
```

**需要登录：** 是

**说明：** 切换收藏状态。

**响应：**

```json
{
  "success": true,
  "favorited": true
}
```

---

### 举报帖子

```
POST /api/posts/<post_id>/report
```

**需要登录：** 是

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| reason | string | 是 | 举报原因 |
| detail | string | 否 | 详细描述（最多500字） |

**响应：**

```json
{
  "success": true
}
```

---

## 评论相关

### 获取帖子评论

```
GET /api/posts/<post_id>/comments?page=1&page_size=50
```

**查询参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| page | int | 1 | 页码 |
| page_size | int | 50 | 每页条数 |

**响应：**

```json
{
  "success": true,
  "comments": [...],
  "page": 1,
  "page_size": 50
}
```

**缓存：** L1 1分钟 / L2 5分钟

---

### 发表评论

```
POST /api/posts/<post_id>/comments/create
```

**需要登录：** 是

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| content | string | 是 | 评论内容（最多500字） |
| parent_id | int | 否 | 回复的评论 ID |

**响应：**

```json
{
  "success": true,
  "comment": { ... }
}
```

**限流：** 20次 / 分钟 / 用户

---

### 删除评论

```
POST /api/comments/<comment_id>/delete
```

**需要登录：** 是（仅作者或管理员）

**响应：**

```json
{
  "success": true
}
```

---

## 世界频道

### 获取全部消息

```
GET /api/World/ALL
```

**响应：** 消息列表数组

**缓存：** L1 2秒 / L2 10秒  
**响应头：** `Cache-Control: max-age=2`

---

### 发送消息

```
POST /api/World/Send
```

**需要登录：** 是

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| content | string | 是 | 消息内容（最多500字） |
| parent_id | int | 否 | 回复的消息 ID |

**响应：**

```json
{
  "success": true
}
```

**限流：** 5次 / 分钟 / 用户

---

## 搜索

### 搜索帖子和用户

```
GET /api/search?k=关键词&page=1&page_size=20
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| k | string | 是 | 搜索关键词 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |

**响应：**

```json
{
  "success": true,
  "posts": [...],
  "users": [...],
  "keyword": "关键词",
  "page": 1,
  "page_size": 20
}
```

**缓存：** L1 2分钟 / L2 10分钟

---

## 会馆

### 获取会馆列表

```
GET /api/huiguan
```

**响应：**

```json
{
  "success": true,
  "list": [
    {
      "name": "会馆名称",
      "leader": "馆长",
      "qq": "QQ群号",
      "site": "网站地址",
      "description": "简介"
    }
  ]
}
```

---

## 其他

### 彩蛋

```
GET /Easter-Egg
```

**响应：** 随机一条彩蛋数据（JSON）

---

### RSS

```
GET /rss.xml
```

**说明：** 暂未实现，返回空字符串。

---

## 错误码

| HTTP 状态码 | 说明 |
|---|---|
| 200 | 请求成功 |
| 400 | 参数错误 |
| 401 | 未登录 / 无权限 |
| 404 | 资源不存在 |
| 429 | 请求过于频繁（限流） |
| 500 | 服务器内部错误 |

---

## 安全说明

- 密码使用 `werkzeug.security.generate_password_hash` 哈希存储
- Session Cookie 使用 HttpOnly + SameSite=Lax + Secure（生产环境）
- 所有状态变更请求受 CSRF 保护（Origin/Referer 校验）
- 敏感接口均有速率限制
- 用户输入内容经 XSS 净化后存储（移除 script、iframe 等危险标签及 on* 事件）
