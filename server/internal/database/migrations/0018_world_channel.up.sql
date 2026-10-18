-- 世界频道：新表 world_messages + 旧 world 只读兼容视图
-- 兼容原版 forum-legacy 的 6 列（id/sender_id/sender_name/content/parent_id/created_at）
CREATE TABLE IF NOT EXISTS world_messages (
  id BIGSERIAL PRIMARY KEY,
  sender_id VARCHAR(64) NOT NULL,
  sender_name VARCHAR(255) NOT NULL DEFAULT '',
  sender_avatar VARCHAR(512) NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  content_format VARCHAR(16) NOT NULL DEFAULT 'html',
  parent_id BIGINT NULL,
  guild_id VARCHAR(64) NOT NULL DEFAULT '',
  guild_name VARCHAR(255) NOT NULL DEFAULT '',
  is_leader BOOLEAN NOT NULL DEFAULT FALSE,
  is_admin BOOLEAN NOT NULL DEFAULT FALSE,
  admin_id VARCHAR(64) NOT NULL DEFAULT '',
  status SMALLINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_world_messages_created ON world_messages (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_world_messages_sender ON world_messages (sender_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_world_messages_parent ON world_messages (parent_id);

-- 旧 world 基表存在时先导入（保留原 id/parent_id），再 drop 并建视图
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema='public' AND table_name='world' AND table_type='BASE TABLE') THEN
    INSERT INTO world_messages (id, sender_id, sender_name, content, content_format, parent_id, created_at)
    SELECT id, sender_id, sender_name, content, 'html', parent_id, created_at FROM world
    ON CONFLICT (id) DO NOTHING;
    PERFORM setval(pg_get_serial_sequence('world_messages','id'),
                   COALESCE((SELECT MAX(id) FROM world_messages), 1), true);
    DROP TABLE world;
  END IF;
END $$;

DROP VIEW IF EXISTS world;
CREATE VIEW world AS
  SELECT id, sender_id, sender_name, content, parent_id, created_at
  FROM world_messages
  WHERE status = 1;
