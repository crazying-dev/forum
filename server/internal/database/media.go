package database

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
)

// ---- 用户媒体（发帖图片）----

// MediaAsset 媒体资产行（服务端内部使用；上传响应只暴露 id 与 url）。
type MediaAsset struct {
	ID       string
	FileName string
	Mime     string
}

// CreateMediaAsset 记录用户上传图片资产（status=1 正常）。
func (d *DB) CreateMediaAsset(ctx context.Context, id, fileName, originalName, mime string, size int64, uploaderID string) error {
	_, err := d.Exec(ctx, `INSERT INTO media_assets (id, file_name, original_name, mime, size, uploader_user_id, scene, status)
		VALUES ($1,$2,$3,$4,$5,$6,'post_image',1)`, id, fileName, originalName, mime, size, uploaderID)
	return err
}

// GetMediaAsset 读取可用图片资产（status=1）；不存在或已删除返回 (nil, nil)。
func (d *DB) GetMediaAsset(ctx context.Context, id string) (*MediaAsset, error) {
	var m MediaAsset
	err := d.QueryRow(ctx, `SELECT id, file_name, mime FROM media_assets WHERE id = $1 AND status = 1`, id).
		Scan(&m.ID, &m.FileName, &m.Mime)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &m, nil
}

// ListExpiredMediaAssets 待清理的已删除图片（status=0 且 deleted_at 早于 days 天前）；行记录保留。
func (d *DB) ListExpiredMediaAssets(ctx context.Context, days int) ([]MediaAsset, error) {
	if days < 1 {
		days = 7
	}
	rows, err := d.Query(ctx, `SELECT id, file_name, mime FROM media_assets
		WHERE status = 0 AND deleted_at IS NOT NULL AND deleted_at < now() - $1 * INTERVAL '1 day'`, days)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	assets := []MediaAsset{}
	for rows.Next() {
		var m MediaAsset
		if err := rows.Scan(&m.ID, &m.FileName, &m.Mime); err != nil {
			return nil, err
		}
		assets = append(assets, m)
	}
	return assets, rows.Err()
}
