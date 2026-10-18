-- 更新日志（富文本，PG）+ admin 直写 PG 的缓存失效表
CREATE TABLE IF NOT EXISTS changelogs (
  id BIGSERIAL PRIMARY KEY,
  version VARCHAR(64) NOT NULL DEFAULT '',
  title VARCHAR(255) NOT NULL,
  content_html TEXT NOT NULL DEFAULT '',
  published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_published BOOLEAN NOT NULL DEFAULT TRUE,
  created_by VARCHAR(64) NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_changelogs_published
  ON changelogs (is_published, published_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS cache_invalidations (
  id BIGSERIAL PRIMARY KEY,
  scope VARCHAR(64) NOT NULL,
  key VARCHAR(255) NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_invalidations_pending
  ON cache_invalidations (processed_at, created_at);
