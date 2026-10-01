-- 反馈四态化与状态流转日志
-- 说明：status 0=未处理 / 1=处理中 / 2=已处理 / 3=关闭；
--       旧「处理中(1)」的历史数据统一迁移为「已处理(2)」，状态流转日志由管理端写入
UPDATE bug_reports SET status = 2 WHERE status = 1;

CREATE TABLE IF NOT EXISTS bug_report_logs (
  id BIGSERIAL PRIMARY KEY,
  report_id INTEGER NOT NULL,
  from_status INTEGER,
  to_status INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bug_report_logs_report ON bug_report_logs (report_id, created_at);
