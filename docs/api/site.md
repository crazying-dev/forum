# 站点配置 / 公告 / 更新日志 / 每日一言

## 站点配置

`GET /ov2/api/site/config` → `{success,data:{theme,daily_quote,announcement}}`

公告结构：`{enabled,text,version,updated_at}`；仅首页渲染，非富文本，关闭按 version 记忆。

## 更新日志

- `GET /ov2/api/changelogs?page=1&page_size=20` → `{success,items,total,page,page_size}`；只返回已发布且 `published_at<=now()`。
- `GET /ov2/api/changelogs/:id`。

条目：`{id,version,title,content_html,published_at}`。

## 每日一言

`GET /ov2/api/site/daily-quote` → `{success,text,source}`；后端 5s 超时 + 60s 缓存，失败返回本地兜底文案。

## 管理端

admin「论坛配置」→ 公告 / 黑名单 / 更新日志三个 Tab；发布更新日志会写 `broadcast_notices`（type=changelog）。
