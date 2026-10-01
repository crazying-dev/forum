-- 帖子/文章定时发布
-- 约定：published_at 在未来即视为「定时未发布」，列表/搜索/信息流等读路径统一过滤 published_at <= NOW()；
--       存量行 published_at 回填为 created_at（均在过去，历史数据视为已发布）；立即帖创建时 publish_notified=TRUE，定时帖 FALSE，
--       由服务端定时任务到点补发粉丝通知并置回 TRUE（见 handler.PostsHandler.ProcessScheduledPublishes）。
-- 说明：沿用项目现有时间列惯例（TIMESTAMP WITHOUT TIME ZONE + CURRENT_TIMESTAMP），不使用 TIMESTAMPTZ。
ALTER TABLE posts ADD COLUMN IF NOT EXISTS published_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS publish_notified BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE guild_articles ADD COLUMN IF NOT EXISTS published_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- 存量行发布时间回填为原创建时间；迁移时不存在定时帖
UPDATE posts SET published_at = created_at;
UPDATE guild_articles SET published_at = created_at;

CREATE INDEX IF NOT EXISTS idx_posts_published_at ON posts (published_at);
CREATE INDEX IF NOT EXISTS idx_guild_articles_published_at ON guild_articles (published_at);
-- 待补发通知的定时帖（部分索引，仅扫未通知行）
CREATE INDEX IF NOT EXISTS idx_posts_pending_publish ON posts (published_at) WHERE publish_notified = FALSE;
