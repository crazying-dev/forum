-- 管理团队聊天：每个用户一条 team room；成员可含 user/admin
CREATE TABLE IF NOT EXISTS chat_rooms (
  id BIGSERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_members (
  room_id BIGINT NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
  member_type VARCHAR(16) NOT NULL,
  member_id VARCHAR(64) NOT NULL,
  last_read_message_id BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (room_id, member_type, member_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_members_member ON chat_members (member_type, member_id);

CREATE TABLE IF NOT EXISTS chat_messages (
  id BIGSERIAL PRIMARY KEY,
  room_id BIGINT NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
  sender_type VARCHAR(16) NOT NULL,
  admin_id VARCHAR(64) NOT NULL DEFAULT '',
  forum_account_id VARCHAR(64) NOT NULL DEFAULT '',
  forum_account_name VARCHAR(255) NOT NULL DEFAULT '',
  forum_account_avatar VARCHAR(512) NOT NULL DEFAULT '',
  content_html TEXT NOT NULL,
  content_format VARCHAR(16) NOT NULL DEFAULT 'html',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_room_id ON chat_messages (room_id, id DESC);
