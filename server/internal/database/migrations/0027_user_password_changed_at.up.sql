-- 改密时间：legacy token 接受窗口与“改密后旧 token 失效”
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ NULL;
