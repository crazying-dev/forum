-- 密码重置链接化与账号操作限流
-- 说明：verify_tokens 记录重置链接的打开次数（最多 3 次）与核销时间；
--       account_action_limits 记录按「动作 + 邮箱」维度的操作时间（如重置邮件 1 小时 1 次）。
CREATE TABLE IF NOT EXISTS account_action_limits (
    id BIGSERIAL PRIMARY KEY,
    action VARCHAR(40) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_account_action_limits_lookup ON account_action_limits (action, email, created_at);

ALTER TABLE verify_tokens ADD COLUMN IF NOT EXISTS visits INTEGER NOT NULL DEFAULT 0;
ALTER TABLE verify_tokens ADD COLUMN IF NOT EXISTS used_at TIMESTAMP;
