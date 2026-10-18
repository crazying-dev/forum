DROP TABLE IF EXISTS altcha_used;
-- 保留 site_configs.announcement：回滚不应丢失运营公告
DROP INDEX IF EXISTS idx_world_messages_status_id;
DROP INDEX IF EXISTS idx_chat_members_room_read;
