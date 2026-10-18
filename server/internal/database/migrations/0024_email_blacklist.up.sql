-- 注册邮箱黑名单（admin 维护；精确邮箱 / @domain / *@domain）
CREATE TABLE IF NOT EXISTS email_blacklist (
  id BIGSERIAL PRIMARY KEY,
  pattern VARCHAR(255) NOT NULL UNIQUE,
  note VARCHAR(255) NOT NULL DEFAULT '',
  created_by VARCHAR(64) NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_blacklist_created
  ON email_blacklist (created_at DESC);
