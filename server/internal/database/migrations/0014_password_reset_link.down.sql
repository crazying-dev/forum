-- 回滚 0014：移除操作限流表与 verify_tokens 新增列
ALTER TABLE verify_tokens DROP COLUMN IF EXISTS used_at;
ALTER TABLE verify_tokens DROP COLUMN IF EXISTS visits;
DROP INDEX IF EXISTS idx_account_action_limits_lookup;
DROP TABLE IF EXISTS account_action_limits;
