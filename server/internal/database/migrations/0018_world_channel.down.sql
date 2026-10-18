-- 回滚：恢复旧 world 表（保留已导入消息），删除视图与新表
DROP VIEW IF EXISTS world;

CREATE TABLE IF NOT EXISTS world (
  id SERIAL PRIMARY KEY,
  sender_id VARCHAR(255) NOT NULL,
  sender_name VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  parent_id INTEGER DEFAULT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO world (id, sender_id, sender_name, content, parent_id, created_at)
SELECT id, sender_id, sender_name, content, parent_id, created_at FROM world_messages
ON CONFLICT (id) DO NOTHING;

-- 显式插入 id 后推进序列，避免回滚后旧代码 INSERT 主键冲突
SELECT setval(pg_get_serial_sequence('world','id'), COALESCE((SELECT MAX(id) FROM world), 1), true);

DROP TABLE IF EXISTS world_messages;
