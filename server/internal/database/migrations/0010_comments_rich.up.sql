-- 评论富文本化：content_format 标记评论存储形态（markdown=历史数据，html=新富文本）
ALTER TABLE comments ADD COLUMN IF NOT EXISTS content_format VARCHAR(16) NOT NULL DEFAULT 'markdown';
