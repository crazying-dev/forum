-- 回滚 0012：移除定时发布相关索引与列（回滚后全部帖子/文章均视为已发布）
DROP INDEX IF EXISTS idx_posts_pending_publish;
DROP INDEX IF EXISTS idx_guild_articles_published_at;
DROP INDEX IF EXISTS idx_posts_published_at;

ALTER TABLE guild_articles DROP COLUMN IF EXISTS published_at;
ALTER TABLE posts DROP COLUMN IF EXISTS publish_notified;
ALTER TABLE posts DROP COLUMN IF EXISTS published_at;
