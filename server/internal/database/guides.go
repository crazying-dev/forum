package database

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"

	"yj-forum/server/internal/models"
)

// ---- 指南（guides）----

// ListGuideNodes 指南节点列表（不含正文；按 sort,id 升序）。
func (d *DB) ListGuideNodes(ctx context.Context) ([]models.GuideNodeListItem, error) {
	rows, err := d.Query(ctx, `SELECT id, parent_id, title, kind, sort, updated_at
		FROM guide_nodes ORDER BY sort ASC, id ASC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	nodes := []models.GuideNodeListItem{}
	for rows.Next() {
		var n models.GuideNodeListItem
		var updatedAt *time.Time
		if err := rows.Scan(&n.ID, &n.ParentID, &n.Title, &n.Kind, &n.Sort, &updatedAt); err != nil {
			return nil, err
		}
		n.UpdatedAt = updatedAt
		nodes = append(nodes, n)
	}
	return nodes, rows.Err()
}

// GetGuideNode 指南节点详情（含正文）；不存在返回 (nil, nil)。
func (d *DB) GetGuideNode(ctx context.Context, id string) (*models.GuideNode, error) {
	var n models.GuideNode
	var updatedAt *time.Time
	err := d.QueryRow(ctx, `SELECT id, parent_id, title, kind, sort, content, content_format, updated_at
		FROM guide_nodes WHERE id = $1`, id).
		Scan(&n.ID, &n.ParentID, &n.Title, &n.Kind, &n.Sort, &n.Content, &n.ContentFormat, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	n.UpdatedAt = updatedAt
	return &n, nil
}
