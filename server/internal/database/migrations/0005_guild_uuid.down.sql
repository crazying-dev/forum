-- 回滚 0005：移除会馆 UUID 列与唯一索引
DROP INDEX IF EXISTS guilds_uuid_key;
ALTER TABLE guilds DROP COLUMN IF EXISTS uuid;
