package database

import (
	"context"
	"time"
)

// UserInfo 用户 + 密码（仅登录使用）。
type UserInfo struct {
	ID            string
	Name          string
	Avatar        string
	Email         string
	Gender        int
	Age           string
	Intro         string
	VIP           string
	Prefix        string
	IsBanned      int
	EmailVerified int
	CreatedAt     *time.Time
	LastLogin     *time.Time
	Password      string
}

func scanUserWithPassword(row interface{ Scan(...any) error }) (*UserInfo, error) {
	var u UserInfo
	var createdAt, lastLogin *time.Time
	err := row.Scan(&u.ID, &u.Name, &u.Avatar, &u.Email, &u.Gender, &u.Age, &u.Intro, &u.VIP,
		&u.Prefix, &u.IsBanned, &u.EmailVerified, &createdAt, &lastLogin, &u.Password)
	if err != nil {
		return nil, err
	}
	u.CreatedAt = createdAt
	u.LastLogin = lastLogin
	return &u, nil
}

// GetUserByNameWithPassword 按用户名查（含密码）。
func (d *DB) GetUserByNameWithPassword(ctx context.Context, name string) (*UserInfo, error) {
	return scanUserWithPassword(d.QueryRow(ctx, `SELECT id, name, avatar, email, COALESCE(gender, 0), COALESCE(age, ''), COALESCE(intro, ''), vip, COALESCE(prefix, ''),
		is_banned, email_verified, created_at, last_login, password FROM users WHERE name=$1`, name))
}

// GetUserByEmailWithPassword 按邮箱查（含密码）。
func (d *DB) GetUserByEmailWithPassword(ctx context.Context, email string) (*UserInfo, error) {
	return scanUserWithPassword(d.QueryRow(ctx, `SELECT id, name, avatar, email, COALESCE(gender, 0), COALESCE(age, ''), COALESCE(intro, ''), vip, COALESCE(prefix, ''),
		is_banned, email_verified, created_at, last_login, password FROM users WHERE email=$1`, email))
}

// UserExistsByEmail 邮箱是否已存在。
func (d *DB) UserExistsByEmail(ctx context.Context, email string) bool {
	var n int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM users WHERE email=$1", email).Scan(&n)
	return n > 0
}

// UserExistsByName 用户名是否已存在。
func (d *DB) UserExistsByName(ctx context.Context, name string) bool {
	var n int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM users WHERE name=$1", name).Scan(&n)
	return n > 0
}
