-- 回滚 0009：移除灵力值与最近签到日期
ALTER TABLE users DROP COLUMN IF EXISTS last_sign_in;
ALTER TABLE users DROP COLUMN IF EXISTS spirit;
