-- 灵力奖励：规则 + 日用量 + 流水（advisory lock 串行化）
CREATE TABLE IF NOT EXISTS spirit_rules (
  action VARCHAR(16) PRIMARY KEY,
  amount INT NOT NULL,
  daily_cap INT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO spirit_rules (action, amount, daily_cap) VALUES
  ('post', 5, 20),
  ('comment', 3, 15)
ON CONFLICT (action) DO NOTHING;

CREATE TABLE IF NOT EXISTS spirit_daily_usage (
  user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  action VARCHAR(16) NOT NULL,
  day_key DATE NOT NULL,
  awarded INT NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, action, day_key)
);

CREATE TABLE IF NOT EXISTS spirit_awards (
  id BIGSERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  action VARCHAR(16) NOT NULL,
  amount INT NOT NULL,
  day_key DATE NOT NULL,
  source_id VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (action, source_id)
);

CREATE INDEX IF NOT EXISTS idx_spirit_awards_user_day
  ON spirit_awards (user_id, day_key DESC);
