package database

import (
	"embed"
	"errors"
	"strings"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/pgx/v5"
	"github.com/golang-migrate/migrate/v4/source/iofs"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

// Migrate 执行数据库迁移。迁移文件已嵌入二进制，不依赖工作目录。
// 迁移失败返回错误，由启动流程终止服务（fail-fast，不再仅告警后继续启动）。
func Migrate(dsn string) error {
	// golang-migrate pgx v5 driver 注册名为 pgx5，需将 postgresql:// 改写为 pgx5://
	pgDSN := dsn
	if i := strings.Index(pgDSN, "://"); i > 0 {
		pgDSN = "pgx5" + pgDSN[i:]
	}

	src, err := iofs.New(migrationsFS, "migrations")
	if err != nil {
		return err
	}
	m, err := migrate.NewWithSourceInstance("iofs", src, pgDSN)
	if err != nil {
		return err
	}
	defer m.Close()
	if err := m.Up(); err != nil && !errors.Is(err, migrate.ErrNoChange) {
		return err
	}
	return nil
}
