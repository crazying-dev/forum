-- 邮箱换绑请求
-- 说明：每用户至多一条进行中的换绑请求（idx_email_change_requests_user 唯一）；
--       stage 1=待验证当前邮箱 / 2=当前邮箱已确认、待验证新邮箱；old_email 为发起时快照。
CREATE TABLE IF NOT EXISTS email_change_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    old_email VARCHAR(255) NOT NULL,
    new_email VARCHAR(255) NOT NULL DEFAULT '',
    stage SMALLINT NOT NULL DEFAULT 1,
    old_verified_at TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_change_requests_user ON email_change_requests (user_id);
