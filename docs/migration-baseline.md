# 生产库基线审计与迁移决策树

> 本文件是 2026-10-18 ov2 平台升级（0018–0027）的上线前基线检查清单。**生产环境执行前必须逐项核对并备份**；开发库已知为 `schema_migrations=17`、clean、`world` 表不存在。

## 1. 已知开发库基线（2026-10-18）

| 项 | 值 |
|---|---|
| PostgreSQL | 18.6（容器 `ouo-postgres`，库 `yj_forum`） |
| `schema_migrations` | `17`，`dirty=false` |
| `world` | 不存在（已在 `0003_guilds` 删除） |
| `users` / `posts` / `comments` / `guilds` / `media_assets` | 6 / 15 / 20 / 1 / 5 |
| `media_assets` ID 形态 | `MD` + UnixNano（历史）；新代码将改为随机 128-bit |
| MongoDB GridFS | `guild_logos.files` 6、`guild_intro_images.files` 1、`guild_leader_images.files` 1、`guide_images` 0（以实际 dump 为准） |

备份产物（不入 Git）：`.backups/2026-10-18/yj_forum_20261018.dump`、`.backups/2026-10-18/forum_admin_20261018.archive`。

## 2. 生产上线前检查（逐项）

1. `SELECT version, dirty FROM schema_migrations;`
   - 若表不存在 → 记录为「未知基线」，**禁止直接 `migrate up`**。
   - 若 `dirty=true` → 先人工核对失败迁移，再决定前向修复或 `force`。
2. `SELECT table_name, table_type FROM information_schema.tables WHERE table_name='world';`
   - 若为 `BASE TABLE` → 先备份并导入 `world_messages`，再由 0018 的 DO 块 drop 并建视图。
   - 若为 `VIEW` 或不存在 → 0018 直接建/替换视图。
3. 检查 `users`、`posts`、`comments`、`guilds`、`media_assets` 是否存在；与 `0001_init` 的表集合对比。
4. 检查 `guilds.uuid`、`posts.published_at`、`comments.content_format`、`site_configs` 等 0005–0017 列是否存在。
5. 备份：`pg_dump -Fc`、`mongodump`（四个 GridFS bucket + `forum_admin` 集合）、SeaweedFS 数据目录快照。
6. 在克隆库执行 0018–0027，跑 `scripts/verify-migrations.sql`（结构校验 + 计数校验）。
7. 生产只做前向迁移；**不做 down**。回滚以应用版本回滚 + 前向修复为主。

## 3. 决策树

```text
有 schema_migrations?
├─ 否 ──> 未知基线：schema diff → 人工确认 → 用 baseline 脚本 stamp 到与现有结构匹配的版本
│          （禁止直接 migrate up；禁止在未备份时执行）
└─ 是
   ├─ dirty=true ──> 人工核对失败迁移 → 前向修复 / force 到已验证版本
   └─ dirty=false
      ├─ version=17 ──> 直接执行 0018–0027
      ├─ version<17 ──> 先补齐 0002–0017（逐条核对），再执行 0018–0027
      └─ version>17 ──> 代码版本高于库；停止并人工确认
```

## 4. 旧 world 导入保护（0018 内）

```sql
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema='public' AND table_name='world' AND table_type='BASE TABLE') THEN
    INSERT INTO world_messages (sender_id, sender_name, content, content_format, parent_id, created_at)
    SELECT sender_id, sender_name, content, 'markdown', parent_id, created_at FROM world
    ON CONFLICT DO NOTHING;
    DROP TABLE world;
  END IF;
END $$;
CREATE OR REPLACE VIEW world AS
  SELECT id, sender_id, sender_name, content, parent_id, created_at
  FROM world_messages WHERE status = 1;
```

> 实际迁移以 `0018_world_channel.up.sql` 为准；本段只表达顺序与保护逻辑。

## 5. 迁移工程注意事项

- 新表统一 `TIMESTAMPTZ`；admin 的 PG 连接需 `SET TIME ZONE 'UTC'`。
- 不在 golang-migrate 事务内执行 `CREATE INDEX CONCURRENTLY`；大表索引低峰手工建。
- 迁移前设置 `lock_timeout`/`statement_timeout`，避免长时间锁表。
- admin 无 migrations 目录；所有新表/列读取必须带 `pgTableExists`/`pgTableHasColumn` 守卫。
- `media_references` 的活跃引用（帖子/评论/回收站/审批/草稿）不得被 GC；`is_legacy=TRUE` 永不参与孤儿 GC。

## 6. 0027 补充

- `0027_user_password_changed_at` 新增 `users.password_changed_at`，用于 legacy token 接受窗口与改密后旧 token 失效；执行顺序在 0026 之后。
