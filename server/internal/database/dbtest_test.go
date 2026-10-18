package database

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
)

// 测试使用独立 schema（不污染开发库）；未设置 TEST_DATABASE_URL 时回退本地 Docker 测试库。
var (
	testDBConn  *DB
	testDBErr   error
	testSchema  string
	testBaseDSN string
)

func TestMain(m *testing.M) {
	setupTestDatabase()
	code := m.Run()
	teardownTestDatabase()
	os.Exit(code)
}

func baseTestDSN() string {
	if v := os.Getenv("TEST_DATABASE_URL"); v != "" {
		return v
	}
	return "postgresql://postgres:localdev123@127.0.0.1:5432/yj_forum_test"
}

func setupTestDatabase() {
	base := baseTestDSN()
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	cfg, err := pgx.ParseConfig(base)
	if err != nil {
		testDBErr = fmt.Errorf("解析 TEST_DATABASE_URL: %w", err)
		return
	}
	// 确保数据库存在
	adminCfg := *cfg
	adminCfg.Database = "postgres"
	admin, err := pgx.ConnectConfig(ctx, &adminCfg)
	if err != nil {
		testDBErr = fmt.Errorf("PostgreSQL 不可用: %w", err)
		return
	}
	var exists bool
	_ = admin.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = $1)", cfg.Database).Scan(&exists)
	if !exists {
		if _, err := admin.Exec(ctx, "CREATE DATABASE "+pgx.Identifier{cfg.Database}.Sanitize()); err != nil {
			admin.Close(ctx)
			testDBErr = fmt.Errorf("创建测试库: %w", err)
			return
		}
	}
	admin.Close(ctx)

	// 在目标库创建唯一 schema，避免与开发数据/并行测试互相影响
	target, err := pgx.ConnectConfig(ctx, cfg)
	if err != nil {
		testDBErr = fmt.Errorf("连接测试库: %w", err)
		return
	}
	testSchema = fmt.Sprintf("test_%d", time.Now().UnixNano())
	if _, err := target.Exec(ctx, "CREATE SCHEMA "+pgx.Identifier{testSchema}.Sanitize()); err != nil {
		target.Close(ctx)
		testDBErr = fmt.Errorf("创建测试 schema: %w", err)
		return
	}
	target.Close(ctx)

	dsn, err := dsnWithSearchPath(base, testSchema)
	if err != nil {
		testDBErr = err
		return
	}
	if err := Migrate(dsn); err != nil {
		testDBErr = fmt.Errorf("测试库迁移失败: %w", err)
		return
	}
	db, err := New(ctx, dsn)
	if err != nil {
		testDBErr = fmt.Errorf("打开测试库: %w", err)
		return
	}
	testDBConn = db
	testBaseDSN = base
}

func dsnWithSearchPath(base, schema string) (string, error) {
	u, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	q := u.Query()
	q.Set("options", "-csearch_path="+schema)
	u.RawQuery = q.Encode()
	return u.String(), nil
}

func teardownTestDatabase() {
	if testDBConn != nil {
		testDBConn.Close()
	}
	if testSchema == "" || testBaseDSN == "" {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	cfg, err := pgx.ParseConfig(testBaseDSN)
	if err != nil {
		return
	}
	conn, err := pgx.ConnectConfig(ctx, cfg)
	if err != nil {
		return
	}
	_, _ = conn.Exec(ctx, "DROP SCHEMA IF EXISTS "+pgx.Identifier{testSchema}.Sanitize()+" CASCADE")
	conn.Close(ctx)
}

func testDB(t *testing.T) *DB {
	t.Helper()
	if testDBErr != nil {
		t.Skipf("PostgreSQL 测试库不可用: %v", testDBErr)
	}
	if testDBConn == nil {
		t.Skip("PostgreSQL 测试库未初始化")
	}
	return testDBConn
}

// newTestUser 插入一个已验证邮箱的测试用户，测试结束级联清理。
func newTestUser(t *testing.T, db *DB) string {
	t.Helper()
	id := GenID("TU")
	_, err := db.Exec(context.Background(), `INSERT INTO users (id, name, avatar, email, password, email_verified)
		VALUES ($1, $2, '', $3, 'x', 1)`, id, id, id+"@example.test")
	if err != nil {
		t.Fatalf("insert test user: %v", err)
	}
	t.Cleanup(func() {
		_, _ = db.Exec(context.Background(), "DELETE FROM users WHERE id = $1", id)
	})
	return id
}
