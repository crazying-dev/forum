-- 回滚会馆系统：删表/列、还原 users(id) 外键、按 0001 重建 world 表

-- 1) 移除帖子归属会馆列
DROP INDEX IF EXISTS idx_posts_guild_created;
ALTER TABLE posts DROP CONSTRAINT IF EXISTS posts_guild_id_fkey;
ALTER TABLE posts DROP COLUMN IF EXISTS guild_id;

-- 2) 删除会馆相关表（依赖倒序；guilds_id_seq 随 guilds 表一起删除）
DROP TABLE IF EXISTS guild_article_participants;
DROP TABLE IF EXISTS guild_articles;
DROP TABLE IF EXISTS guild_announcements;
DROP TABLE IF EXISTS guild_categories;
DROP TABLE IF EXISTS guild_join_requests;
DROP TABLE IF EXISTS guild_members;
DROP TABLE IF EXISTS guilds;

-- 3) 还原 users(id) 外键（去掉 ON UPDATE CASCADE，保持与 0001/0002 一致）
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT c.conname,
               c.conrelid::regclass::text AS tbl,
               c.confdeltype,
               (SELECT string_agg(quote_ident(a.attname), ', ')
                  FROM unnest(c.conkey) AS k(attnum)
                  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum) AS cols
        FROM pg_constraint c
        WHERE c.contype = 'f'
          AND c.confrelid = 'users'::regclass
          AND c.conrelid = ANY (ARRAY['posts','comments','post_likes','post_favorites','user_follows',
                                      'verify_tokens','post_reports','sessions','comment_likes']::regclass[])
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
        EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY (%s) REFERENCES users(id) ON DELETE %s',
                       r.tbl, r.conname, r.cols,
                       CASE r.confdeltype WHEN 'c' THEN 'CASCADE'
                                          WHEN 'n' THEN 'SET NULL'
                                          WHEN 'd' THEN 'SET DEFAULT'
                                          WHEN 'r' THEN 'RESTRICT'
                                          ELSE 'NO ACTION' END);
    END LOOP;
END $$;

-- 4) 重建 world 表与索引（还原 0001_init）
CREATE TABLE world (
    id SERIAL PRIMARY KEY,
    sender_id VARCHAR(255) NOT NULL,
    sender_name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    parent_id INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_world_created_at ON world(created_at DESC);
