-- 回滚 0010：移除评论正文格式标记
ALTER TABLE comments DROP COLUMN IF EXISTS content_format;
