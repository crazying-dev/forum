-- 富文本与用户媒体：会馆介绍页、正文格式标记、用户上传图片资产
-- 说明：content_format 标记正文存储形态（markdown=历史数据，html=新富文本，由写入方显式指定）
--       media_assets 记录用户上传图片（status: 1 正常 / 0 已删除；行记录保留，物理文件由定时任务清理）

ALTER TABLE guilds ADD COLUMN IF NOT EXISTS intro_page_content TEXT NOT NULL DEFAULT '';
ALTER TABLE guilds ADD COLUMN IF NOT EXISTS intro_cover_file_id VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE posts ADD COLUMN IF NOT EXISTS content_format VARCHAR(16) NOT NULL DEFAULT 'markdown';
ALTER TABLE guild_articles ADD COLUMN IF NOT EXISTS content_format VARCHAR(16) NOT NULL DEFAULT 'markdown';
CREATE TABLE IF NOT EXISTS media_assets (
  id VARCHAR(64) PRIMARY KEY,
  file_name VARCHAR(128) NOT NULL,
  original_name VARCHAR(255) NOT NULL DEFAULT '',
  mime VARCHAR(64) NOT NULL DEFAULT '',
  size BIGINT NOT NULL DEFAULT 0,
  uploader_user_id VARCHAR(64) NOT NULL,
  scene VARCHAR(32) NOT NULL DEFAULT 'post_image',
  status SMALLINT NOT NULL DEFAULT 1,
  deleted_by_admin_id VARCHAR(64) NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_media_assets_uploader ON media_assets (uploader_user_id);
CREATE INDEX IF NOT EXISTS idx_media_assets_created ON media_assets (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_media_assets_status ON media_assets (status, created_at DESC);
