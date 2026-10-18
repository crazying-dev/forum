# 消息中心 / 管理团队 / SSE

## 汇总

`GET /ov2/api/messages/summary` → `{success,likes,comments,system,chat}`

## 赞 / 评论（全部历史）

- `GET /messages/likes?cursor=&limit=20`
- `GET /messages/comments?cursor=&limit=20`

条目示例：
```json
{ "id":"pl_19", "actor":{"id":"RL...","name":"墨白","avatar":"/ov2/api/media/..."}, "target_type":"post", "target_id":"PS...", "post_id":"PS...", "post_title":"...", "comment_id":"", "comment_excerpt":"", "created_at":"..." }
```

## 系统通知

`GET /messages/system?cursor=&limit=20` → 合并 `broadcast_notices` 与 per-user system 通知。

## 已读

`POST /messages/read` body `{category:"likes"|"comments"|"system", last_read_at:"RFC3339"}`；只前进不后退。

## 管理团队聊天

- `GET /messages/chat?cursor=&limit=20` → 共享会话消息（`sender_type=user|admin`，admin 消息带 `sender_name/sender_avatar/admin_id`）。
- `POST /messages/chat` body `{content_html}`；2 秒/用户限流；富文本与图片。
- `POST /messages/chat/read` body `{last_message_id}`。

## SSE

`GET /messages/stream`（登录）

事件：`hello`、`unread`、`notification`、`message`、`heartbeat`、`error`。持久事件带 `id:`；客户端按 id 去重，断线重连后用 `Last-Event-ID` 或重新拉取 summary。
