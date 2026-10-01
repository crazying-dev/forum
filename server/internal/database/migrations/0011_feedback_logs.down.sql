-- 回滚 0011：移除状态流转日志，并把「已处理(2)」还原为「处理中(1)」
DROP TABLE IF EXISTS bug_report_logs;
UPDATE bug_reports SET status = 1 WHERE status = 2;
