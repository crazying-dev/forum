-- 消息中心：per-recipient 通知 + 分类已读 + 全局广播
CREATE TABLE IF NOT EXISTS notifications (
  id BIGSERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type VARCHAR(32) NOT NULL,
  actor_id VARCHAR(64) NOT NULL DEFAULT '',
  target_type VARCHAR(32) NOT NULL DEFAULT '',
  target_id VARCHAR(64) NOT NULL DEFAULT '',
  context_post_id VARCHAR(64) NOT NULL DEFAULT '',
  context_comment_id VARCHAR(64) NOT NULL DEFAULT '',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  dedupe_key VARCHAR(160) NOT NULL DEFAULT '',
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  read_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_dedupe
  ON notifications (dedupe_key) WHERE dedupe_key <> '';
CREATE INDEX IF NOT EXISTS idx_notifications_user_created
  ON notifications (user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
  ON notifications (user_id, is_read) WHERE is_read = FALSE;

CREATE TABLE IF NOT EXISTS message_read_state (
  user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category VARCHAR(32) NOT NULL,
  last_read_at TIMESTAMPTZ NOT NULL DEFAULT 'epoch',
  PRIMARY KEY (user_id, category)
);

CREATE TABLE IF NOT EXISTS broadcast_notices (
  id BIGSERIAL PRIMARY KEY,
  type VARCHAR(32) NOT NULL,
  title VARCHAR(255) NOT NULL DEFAULT '',
  body_html TEXT NOT NULL DEFAULT '',
  link VARCHAR(512) NOT NULL DEFAULT '',
  published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by VARCHAR(64) NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_broadcast_notices_published
  ON broadcast_notices (published_at DESC, id DESC);
