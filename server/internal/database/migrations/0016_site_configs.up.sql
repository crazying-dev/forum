-- 站点配置（key-value JSONB）
-- 说明：theme.festival 控制节日主题，daily_quote 控制每日一句；公开读取见 GET /api/v1/site/config。
CREATE TABLE IF NOT EXISTS site_configs (
    key VARCHAR(64) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO site_configs (key, value) VALUES
    ('theme.festival', '{"mode":"auto","start":"10-01","end":"10-07"}'::jsonb),
    ('daily_quote', '{"enabled":false,"provider":"dlystc"}'::jsonb)
ON CONFLICT (key) DO NOTHING;
