# 世界频道

## 列表（公开）

`GET /ov2/api/world/messages?before_id=&after_id=&limit=50`

- `limit` 默认 50、最大 500；`before_id` 历史页（降序），`after_id` 增量页（升序，优先）。
- 响应：`{success,items,has_more,next_before_id}`。

消息字段：`id,sender_id,sender_name,sender_avatar,content,content_format,parent_id,guild_id,guild_name,is_leader,is_admin,created_at`。

## 发送（登录）

`POST /ov2/api/world/messages`
```json
{ "content_html": "<p>...</p>", "parent_id": null }
```
- 每用户 2 秒一条；纯文本 1–2000 字；最多 9 张图片；禁止引用卡片（`data-embed`）。
- 发送时快照 `sender_name/sender_avatar/guild_id/guild_name/is_leader`。
- 成功 201 `{success,id}`。

## SSE（公开）

`GET /ov2/api/world/stream?last_id=`

- `last_id=0` 首包 `hello` + 最多 200 条 `message`；之后推送新消息。
- 心跳 15s；`Last-Event-ID` 续传最多 500 条，超出走 REST 分页。
- 慢客户端丢弃事件；客户端按 id 去重。

## 保留与清理

- PG `world_messages` 最多 10000 条。
- 每天 03:00 Asia/Shanghai：cutoff = id 降序第 10001 条；分批 500–2000 删除；advisory lock 防并发。
- 旧 `world` 视图只读；旧 APP 走 `/api/World/ALL` 裸数组（见 compat.md）。
