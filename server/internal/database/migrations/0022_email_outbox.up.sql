-- 邮件 outbox + 粉丝 fanout job（一行一收件人，避免 To: 泄露）
CREATE TABLE IF NOT EXISTS email_outbox (
  id BIGSERIAL PRIMARY KEY,
  to_email VARCHAR(255) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  plain_body TEXT NOT NULL DEFAULT '',
  html_body TEXT NOT NULL DEFAULT '',
  dedupe_key VARCHAR(160) NOT NULL DEFAULT '',
  status SMALLINT NOT NULL DEFAULT 0,
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_email_outbox_dedupe
  ON email_outbox (dedupe_key) WHERE dedupe_key <> '';
CREATE INDEX IF NOT EXISTS idx_email_outbox_pending
  ON email_outbox (status, scheduled_at);

CREATE TABLE IF NOT EXISTS email_fanout_jobs (
  id BIGSERIAL PRIMARY KEY,
  kind VARCHAR(32) NOT NULL,
  ref_id VARCHAR(64) NOT NULL,
  actor_id VARCHAR(64) NOT NULL,
  status SMALLINT NOT NULL DEFAULT 0,
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ NULL,
  UNIQUE (kind, ref_id)
);

CREATE INDEX IF NOT EXISTS idx_email_fanout_pending
  ON email_fanout_jobs (status, created_at);
