-- 账号注销：软删除标记与用户名部分唯一索引
-- 说明：deleted_at 非空即视为已注销；用户名唯一约束改为仅对未注销账号生效（注销账号可重名「已注销账户」）。
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_name_key;
CREATE UNIQUE INDEX IF NOT EXISTS users_name_active_key ON users (name) WHERE deleted_at IS NULL;
