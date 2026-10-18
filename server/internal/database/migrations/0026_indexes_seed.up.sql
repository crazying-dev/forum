-- ALTCHA 一次性消费表 + 站点公告默认配置 + 补充索引
CREATE TABLE IF NOT EXISTS altcha_used (
  challenge_id VARCHAR(128) PRIMARY KEY,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_altcha_used_expires
  ON altcha_used (expires_at);

INSERT INTO site_configs (key, value)
VALUES ('announcement', '{"enabled":false,"text":"","version":"","updated_at":""}'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- 世界频道按 id 裁剪的辅助索引（id 主键已足够，这里补 sender/status 组合）
CREATE INDEX IF NOT EXISTS idx_world_messages_status_id
  ON world_messages (status, id DESC);

-- 聊天成员按 room + 已读游标查询
CREATE INDEX IF NOT EXISTS idx_chat_members_room_read
  ON chat_members (room_id, last_read_message_id);
