-- 会馆馆长页：馆长头衔与馆长页正文
-- 说明：leader_title 为馆长署名（如「初代馆长」）；leader_page_content 为馆长页正文，均允许空串

ALTER TABLE guilds ADD COLUMN IF NOT EXISTS leader_title VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE guilds ADD COLUMN IF NOT EXISTS leader_page_content TEXT NOT NULL DEFAULT '';
