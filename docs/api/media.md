# 媒体（S3 / 本地 / 旧 GridFS 兼容）

## 上传

`POST /ov2/api/media/images`（登录，multipart）

| 字段 | 说明 |
|---|---|
| `file` | png/jpeg/webp/gif，≤5MB |
| `scene` | `post_image` / `comment_image` / `world_message` / `chat_message` |
| `owner_id` | 可选：帖子/评论/聊天室/世界消息 ID |
| `guild_uuid` | 可选：会馆 UUID |

成功：
```json
{ "success": true, "id": "MD...", "url": "https://yjlt.top/ov2/api/media/MD..." }
```

`url` 为可对外使用的完整地址（优先 `PUBLIC_BASE_URL`；配置缺失或为本机回环地址时按请求 `Host` / `X-Forwarded-Proto` 生成）。数据库 `media_assets.public_url` 仍保存相对路径 `/ov2/api/media/<id>`，便于更换域名；前端会把该完整地址直接写入富文本正文。

## 读取与 ACL

`GET /ov2/api/media/:id`

| visibility | 谁能读 |
|---|---|
| public | 所有人（头像/已发布帖子/评论/世界/会馆/指南/更新日志） |
| private | 本人、聊天室成员、定时帖作者、管理员（admin 经后台 raw 代理） |

私密媒体未授权统一 404（不泄露存在性）。响应带 `X-Content-Type-Options: nosniff`、`Content-Disposition: inline`；public 缓存 600s，private 60s。

## 存储

- 新上传：`storage_provider=s3`（SeaweedFS）或 `local`（S3 未启用时回退 `MEDIA_DIR`）。
- 旧资源：`is_legacy=TRUE`，永不参与孤儿 GC；`/avatar/*`、`/api/v1/media/*`、`/static/*` 继续可用；新 MD 媒体走 `/ov2/api/media/<id>`；`/guild-img/*`、`/guide-img/*` 作为**旧 GridFS 兼容代理**保留（论坛 → 管理端），历史富文本中的 24 位 ObjectID 仍可加载。
- 删除：`status=0 + deleted_at`；7 天后 GC；`media_references` 有活跃引用时不删。

## 头像

- 上传：`POST /users/me/avatar`（≤10MB），返回 `/ov2/api/media/<id>` 并写 `users.avatar`。
- 旧头像：`GET /avatar/:filename` 继续读 `AVATAR_DIR`。
