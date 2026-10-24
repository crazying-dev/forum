-- 媒体变体：上传时预生成的等比缩放图（w480 / w1280，JPEG）
-- 说明：变体随资产删除级联清理；object_key/bucket 指向 S3/SeaweedFS 对象。
CREATE TABLE IF NOT EXISTS media_variants (
  media_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
  variant TEXT NOT NULL,
  object_key TEXT NOT NULL DEFAULT '',
  bucket TEXT NOT NULL DEFAULT '',
  mime TEXT NOT NULL DEFAULT '',
  width INT NOT NULL DEFAULT 0,
  height INT NOT NULL DEFAULT 0,
  size BIGINT NOT NULL DEFAULT 0,
  sha256 TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (media_id, variant)
);
