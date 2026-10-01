-- 指南（guide）：树形节点，读取接口见 GET /api/v1/guides(/ :id)
-- 说明：kind 为展示类型（doc/…，默认 doc）；content_format 与帖子/文章一致（html/markdown）。
CREATE TABLE IF NOT EXISTS guide_nodes (
  id VARCHAR(64) PRIMARY KEY,
  parent_id VARCHAR(64) NULL REFERENCES guide_nodes(id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL,
  kind VARCHAR(16) NOT NULL DEFAULT 'doc',
  sort INTEGER NOT NULL DEFAULT 0,
  content TEXT NOT NULL DEFAULT '',
  content_format VARCHAR(16) NOT NULL DEFAULT 'html',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_guide_nodes_parent ON guide_nodes (parent_id, sort);
