// Package database 封装 PostgreSQL 访问（pgxpool）与业务查询。
package database

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// DB 数据库访问对象。
type DB struct {
	Pool *pgxpool.Pool
}

// New 创建连接池（数据库迁移由启动流程在连接建立后单独执行，失败即退出）。
func New(ctx context.Context, dsn string) (*DB, error) {
	poolCfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("解析 DATABASE_URL 失败: %w", err)
	}
	poolCfg.MaxConns = 10
	poolCfg.MinConns = 1
	poolCfg.MaxConnLifetime = 30 * time.Minute
	// 每新建连接固定 UTC：保证 NOW()/CURRENT_DATE 恒为 UTC 墙钟，与库内 TIMESTAMP 列（无时区）惯例一致
	poolCfg.AfterConnect = func(ctx context.Context, conn *pgx.Conn) error {
		_, err := conn.Exec(ctx, "SET TIME ZONE 'UTC'")
		return err
	}
	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		return nil, fmt.Errorf("创建连接池失败: %w", err)
	}
	// 探测连接
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("数据库连接失败: %w", err)
	}
	return &DB{Pool: pool}, nil
}

func (d *DB) Close() { d.Pool.Close() }

// 事务辅助
func (d *DB) Tx(ctx context.Context, fn func(tx pgx.Tx) error) error {
	tx, err := d.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// Query 返回多行。
func (d *DB) Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error) {
	return d.Pool.Query(ctx, sql, args...)
}

// QueryRow 单行。
func (d *DB) QueryRow(ctx context.Context, sql string, args ...any) pgx.Row {
	return d.Pool.QueryRow(ctx, sql, args...)
}

// Exec 执行。
func (d *DB) Exec(ctx context.Context, sql string, args ...any) (int64, error) {
	tag, err := d.Pool.Exec(ctx, sql, args...)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

// ---- ID 生成 ----

var idMu sync.Mutex
var idLastNano int64
var idCounter int64

// GenMediaID 生成不可枚举的媒体 ID（MD + 16 字节 crypto/rand hex）。
// 媒体 ID 会出现在公开 URL 中，不能用时间戳（可枚举/可遍历）。
func GenMediaID() (string, error) {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return "MD" + hex.EncodeToString(buf), nil
}

// GenID 生成带前缀唯一 ID（时间戳纳秒 + 计数器，防同纳秒碰撞）。
// 对齐 legacy: 前缀 + int(time.time() * 1e10)（纳秒 10 位），此处扩展 11 位。
func GenID(prefix string) string {
	idMu.Lock()
	defer idMu.Unlock()
	now := time.Now().UnixNano()
	if now <= idLastNano {
		idCounter++
		now = idLastNano + idCounter
	} else {
		idLastNano = now
		idCounter = 0
	}
	return fmt.Sprintf("%s%d", prefix, now)
}

// StripEasterEgg 去除用户名彩蛋标记（|[TIME] 与 <p...> 旧格式）。
func StripEasterEgg(name string) string {
	name = strings.ReplaceAll(name, "|[TIME]", "")
	rePOpen := regexp.MustCompile(`(?is)<p[^>]*>`)
	rePClose := regexp.MustCompile(`(?is)</p>`)
	name = rePOpen.ReplaceAllString(name, "")
	name = rePClose.ReplaceAllString(name, "")
	return name
}

// logQueryError
func logQueryError(op string, err error, extra ...string) {
	if len(extra) > 0 {
		log.Printf("[DB] %s 失败: %v (%s)", op, err, extra[0])
	} else {
		log.Printf("[DB] %s 失败: %v", op, err)
	}
}
