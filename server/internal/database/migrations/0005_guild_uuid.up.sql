-- 会馆稳定 UUID 标识（对外契约使用 uuid，数字 id 仅服务端排序）
-- 说明：现有行由 volatile 默认值 gen_random_uuid() 自动回填；uuid 唯一

ALTER TABLE guilds ADD COLUMN IF NOT EXISTS uuid UUID NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS guilds_uuid_key ON guilds(uuid);
