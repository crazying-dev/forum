package database

import (
	"context"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
)

// CacheInvalidation 待处理的缓存失效记录。
type CacheInvalidation struct {
	ID       int64
	Scope    string
	Key      string
	Attempts int
}

// EnqueueCacheInvalidationTx 在事务内写入一条缓存失效任务（同 scope+key 未处理时去重）。
func (d *DB) EnqueueCacheInvalidationTx(ctx context.Context, tx pgx.Tx, scope, key string) error {
	scope = strings.TrimSpace(scope)
	key = strings.TrimSpace(key)
	if scope == "" || key == "" {
		return fmt.Errorf("cache_invalidation: scope/key 不能为空")
	}
	_, err := tx.Exec(ctx, `INSERT INTO cache_invalidations (scope, key)
		SELECT $1::varchar, $2::varchar
		WHERE NOT EXISTS (
			SELECT 1 FROM cache_invalidations WHERE scope = $1 AND key = $2 AND processed_at IS NULL
		)`, scope, key)
	return err
}

// EnqueueCacheInvalidation 非事务便捷入口。
func (d *DB) EnqueueCacheInvalidation(ctx context.Context, scope, key string) error {
	return d.Tx(ctx, func(tx pgx.Tx) error {
		return d.EnqueueCacheInvalidationTx(ctx, tx, scope, key)
	})
}

// ClaimCacheInvalidations 原子认领未处理任务（SKIP LOCKED），attempts+1；attempts>=5 的记录不再认领。
func (d *DB) ClaimCacheInvalidations(ctx context.Context, limit int) ([]CacheInvalidation, error) {
	limit = normalizeLimit(limit, 50, 200)
	rows, err := d.Query(ctx, `
		WITH claimed AS (
			SELECT id FROM cache_invalidations
			WHERE processed_at IS NULL AND attempts < 5
			ORDER BY created_at, id
			LIMIT $1
			FOR UPDATE SKIP LOCKED
		)
		UPDATE cache_invalidations c
		SET attempts = c.attempts + 1
		FROM claimed
		WHERE c.id = claimed.id
		RETURNING c.id, c.scope, c.key, c.attempts`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []CacheInvalidation{}
	for rows.Next() {
		var item CacheInvalidation
		if err := rows.Scan(&item.ID, &item.Scope, &item.Key, &item.Attempts); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

// MarkCacheInvalidation 标记处理结果：lastError 为空视为成功；非空且 attempts>=5 视为死信（processed_at 置位停止重试）。
func (d *DB) MarkCacheInvalidation(ctx context.Context, id int64, lastError string) error {
	lastError = truncateText(lastError, 2000)
	_, err := d.Exec(ctx, `UPDATE cache_invalidations
		SET last_error = $2,
			processed_at = CASE WHEN $2 = '' OR attempts >= 5 THEN NOW() ELSE NULL END
		WHERE id = $1`, id, lastError)
	return err
}
