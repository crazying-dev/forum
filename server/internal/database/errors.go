package database

import (
	"errors"

	"github.com/jackc/pgx/v5/pgconn"
)

var errSelfFollow = errors.New("不能关注自己")

var errCommentUnavailable = errors.New("评论不存在")

// IsUniqueViolation 判断错误是否为 PostgreSQL 唯一约束冲突（SQLSTATE 23505）。
func IsUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}
