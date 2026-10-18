package database

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

// Changelog 更新日志（已发布，公开读取）。
type Changelog struct {
	ID          int64     `json:"id"`
	Version     string    `json:"version"`
	Title       string    `json:"title"`
	ContentHTML string    `json:"content_html"`
	PublishedAt time.Time `json:"published_at"`
}

// ListChangelogs 公开更新日志分页（仅 is_published=true 且 published_at<=now）。
func (d *DB) ListChangelogs(ctx context.Context, page, pageSize int) ([]Changelog, int, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 {
		pageSize = 20
	}
	if pageSize > 100 {
		pageSize = 100
	}

	var total int
	if err := d.QueryRow(ctx, `SELECT COUNT(*) FROM changelogs
		WHERE is_published = TRUE AND published_at <= now()`).Scan(&total); err != nil {
		return nil, 0, err
	}

	rows, err := d.Query(ctx, `SELECT id, version, title, content_html, published_at
		FROM changelogs
		WHERE is_published = TRUE AND published_at <= now()
		ORDER BY published_at DESC, id DESC
		LIMIT $1 OFFSET $2`, pageSize, (page-1)*pageSize)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	items := make([]Changelog, 0, pageSize)
	for rows.Next() {
		var item Changelog
		if err := rows.Scan(&item.ID, &item.Version, &item.Title, &item.ContentHTML, &item.PublishedAt); err != nil {
			return nil, 0, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, err
	}
	return items, total, nil
}

// GetChangelog 公开更新日志详情；不存在或未发布返回 (nil, nil)。
func (d *DB) GetChangelog(ctx context.Context, id int64) (*Changelog, error) {
	var item Changelog
	err := d.QueryRow(ctx, `SELECT id, version, title, content_html, published_at
		FROM changelogs
		WHERE id = $1 AND is_published = TRUE AND published_at <= now()`, id).
		Scan(&item.ID, &item.Version, &item.Title, &item.ContentHTML, &item.PublishedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &item, nil
}
