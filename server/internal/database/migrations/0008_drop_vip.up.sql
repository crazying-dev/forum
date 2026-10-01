-- 移除历史 vip 字段：论坛不再使用 VIP，对外结构与读写同步清理
ALTER TABLE users DROP COLUMN IF EXISTS vip;
