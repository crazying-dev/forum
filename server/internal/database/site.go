package database

import (
	"context"
)

// GetSiteConfig 读取站点配置原始 JSON（key 不存在返回 pgx.ErrNoRows）。
func (d *DB) GetSiteConfig(ctx context.Context, key string) ([]byte, error) {
	var raw []byte
	if err := d.QueryRow(ctx, `SELECT value FROM site_configs WHERE key = $1`, key).Scan(&raw); err != nil {
		return nil, err
	}
	return raw, nil
}
