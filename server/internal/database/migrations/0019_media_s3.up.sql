-- S3 媒体中台：扩展 media_assets + 引用表
ALTER TABLE media_assets
  ADD COLUMN IF NOT EXISTS storage_provider VARCHAR(16) NOT NULL DEFAULT 'local',
  ADD COLUMN IF NOT EXISTS bucket VARCHAR(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS object_key VARCHAR(512) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS public_url VARCHAR(1024) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS owner_type VARCHAR(32) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS owner_id VARCHAR(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS guild_uuid VARCHAR(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS width INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS height INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS visibility VARCHAR(16) NOT NULL DEFAULT 'private',
  ADD COLUMN IF NOT EXISTS is_legacy BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS gc_state SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS uploader_admin_id VARCHAR(64) NOT NULL DEFAULT '';

ALTER TABLE media_assets ALTER COLUMN uploader_user_id DROP NOT NULL;
ALTER TABLE media_assets ALTER COLUMN file_name DROP NOT NULL;

-- 旧本地媒体永久标记为 legacy：不参与孤儿 GC，保持 public 读
UPDATE media_assets
   SET is_legacy = TRUE,
       visibility = 'public',
       storage_provider = COALESCE(NULLIF(storage_provider, ''), 'local')
 WHERE is_legacy = FALSE;

CREATE TABLE IF NOT EXISTS media_references (
  media_id VARCHAR(64) NOT NULL,
  owner_type VARCHAR(32) NOT NULL,
  owner_id VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (media_id, owner_type, owner_id)
);

CREATE INDEX IF NOT EXISTS idx_media_references_owner ON media_references (owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_media_assets_owner ON media_assets (owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_media_assets_visibility ON media_assets (visibility, status);
CREATE INDEX IF NOT EXISTS idx_media_assets_legacy ON media_assets (is_legacy, status);
