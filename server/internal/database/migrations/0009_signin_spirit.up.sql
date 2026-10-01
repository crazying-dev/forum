-- 灵力值与签到：spirit 累计灵力（每日签到 +10），last_sign_in 记录最近签到日期（未签到为 NULL）
ALTER TABLE users ADD COLUMN IF NOT EXISTS spirit INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_sign_in DATE;
