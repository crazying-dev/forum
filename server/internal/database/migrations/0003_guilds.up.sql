-- 会馆系统：会馆、成员、入馆申请、分类、公告、文章（含参与人）与帖子归属
-- 说明：动态会馆替代旧 huiguan.json 静态列表；world 表在本迁移中移除

-- 1) 会馆主表（id 用于人工排序，后期可调整）
CREATE TABLE guilds (
    id INTEGER PRIMARY KEY,
    slug VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL UNIQUE,
    intro TEXT DEFAULT '',
    logo_file_id VARCHAR(64) DEFAULT '',
    logo_version INTEGER DEFAULT 0,
    theme_color VARCHAR(16) DEFAULT '#6A8C89',
    leader_user_id VARCHAR(64) DEFAULT NULL,
    leader_bio TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (leader_user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE SET NULL
);
-- id 不自增（按人工顺序排序）：显式建序列并作为默认值
CREATE SEQUENCE guilds_id_seq OWNED BY guilds.id;
ALTER TABLE guilds ALTER COLUMN id SET DEFAULT nextval('guilds_id_seq');

-- 2) 会馆成员（一个用户同一时间至多属于一个会馆）
CREATE TABLE guild_members (
    user_id VARCHAR(64) PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON UPDATE CASCADE ON DELETE CASCADE
);
CREATE INDEX idx_guild_members_guild_id ON guild_members(guild_id);

-- 3) 入馆申请（status: 0 待审 / 1 通过 / 2 拒绝 / 3 撤回）
CREATE TABLE guild_join_requests (
    id SERIAL PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    status INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    handled_by VARCHAR(64) DEFAULT '',
    handled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE CASCADE
);
CREATE INDEX idx_guild_join_requests_guild_status ON guild_join_requests(guild_id, status);
CREATE INDEX idx_guild_join_requests_user_status ON guild_join_requests(user_id, status);

-- 4) 会馆自定义分类
CREATE TABLE guild_categories (
    id SERIAL PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    name VARCHAR(32) NOT NULL,
    sort INTEGER DEFAULT 0,
    UNIQUE(guild_id, name),
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON UPDATE CASCADE ON DELETE CASCADE
);
CREATE INDEX idx_guild_categories_guild_sort ON guild_categories(guild_id, sort);

-- 5) 会馆公告
CREATE TABLE guild_announcements (
    id SERIAL PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON UPDATE CASCADE ON DELETE CASCADE
);
CREATE INDEX idx_guild_announcements_guild_created ON guild_announcements(guild_id, created_at DESC);

-- 6) 会馆文章
CREATE TABLE guild_articles (
    id VARCHAR(64) PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary VARCHAR(500) DEFAULT '',
    content TEXT NOT NULL,
    author_user_id VARCHAR(64) DEFAULT NULL,
    views INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (guild_id) REFERENCES guilds(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (author_user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE SET NULL
);
CREATE INDEX idx_guild_articles_guild_created ON guild_articles(guild_id, created_at DESC);

-- 7) 文章参与人（user_name 为署名快照，用户改名/注销时兜底展示）
CREATE TABLE guild_article_participants (
    article_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    user_name VARCHAR(64) DEFAULT '',
    PRIMARY KEY (article_id, user_id),
    FOREIGN KEY (article_id) REFERENCES guild_articles(id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE CASCADE
);

-- 8) 帖子归属会馆（NULL 表示公共广场）
ALTER TABLE posts ADD COLUMN guild_id INTEGER DEFAULT NULL;
ALTER TABLE posts ADD CONSTRAINT posts_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES guilds(id) ON UPDATE CASCADE ON DELETE CASCADE;
CREATE INDEX idx_posts_guild_created ON posts(guild_id, created_at DESC);

-- 9) 重建 users(id) 外键：保留原 ON DELETE 语义并统一补上 ON UPDATE CASCADE
--    覆盖 0001/0002 中的全部引用：posts/comments/post_likes/post_favorites/user_follows/
--    verify_tokens/post_reports/sessions/comment_likes
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
        EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY (%s) REFERENCES users(id) ON UPDATE CASCADE ON DELETE %s',
                       r.tbl, r.conname, r.cols,
                       CASE r.confdeltype WHEN 'c' THEN 'CASCADE'
                                          WHEN 'n' THEN 'SET NULL'
                                          WHEN 'd' THEN 'SET DEFAULT'
                                          WHEN 'r' THEN 'RESTRICT'
                                          ELSE 'NO ACTION' END);
    END LOOP;
END $$;

-- 10) 移除世界频道（由会馆/公共广场取代）
DROP TABLE world;
