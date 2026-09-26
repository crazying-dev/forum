-- 会馆修复（审计 L-2 / L-3）
-- 说明：入馆申请并发去重与审批备注列；不改动既有表结构与数据

-- 1) 入馆申请去重：同一会馆 + 同一用户至多一条待审（status = 0）申请（部分唯一索引）
CREATE UNIQUE INDEX uq_guild_join_requests_pending
    ON guild_join_requests(guild_id, user_id) WHERE status = 0;

-- 2) 审批备注（管理端处理申请时可填写）
ALTER TABLE guild_join_requests ADD COLUMN handled_note TEXT DEFAULT '';
