-- 回滚 0006：移除馆长头衔与馆长页正文
ALTER TABLE guilds DROP COLUMN IF EXISTS leader_title;
ALTER TABLE guilds DROP COLUMN IF EXISTS leader_page_content;
