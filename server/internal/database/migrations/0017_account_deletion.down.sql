-- 回滚 0017：移除注销标记并恢复用户名全量唯一约束
-- 注意：若库中已存在重名注销账号（重名「已注销账户」），恢复唯一约束会报错，属预期；
--       需先人工清理重名数据后再执行回滚。
DROP INDEX IF EXISTS users_name_active_key;
ALTER TABLE users ADD CONSTRAINT users_name_key UNIQUE (name);
ALTER TABLE users DROP COLUMN IF EXISTS deleted_at;
