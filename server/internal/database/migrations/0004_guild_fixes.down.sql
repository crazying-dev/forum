-- 回滚 0004：移除审批备注列与待审申请部分唯一索引
ALTER TABLE guild_join_requests DROP COLUMN handled_note;
DROP INDEX uq_guild_join_requests_pending;
