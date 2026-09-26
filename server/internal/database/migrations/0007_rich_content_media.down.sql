-- 回滚 0007：移除正文格式标记、会馆介绍页列与用户媒体表
DROP TABLE IF EXISTS media_assets;
ALTER TABLE posts DROP COLUMN IF EXISTS content_format;
ALTER TABLE guild_articles DROP COLUMN IF EXISTS content_format;
ALTER TABLE guilds DROP COLUMN IF EXISTS intro_page_content;
ALTER TABLE guilds DROP COLUMN IF EXISTS intro_cover_file_id;
