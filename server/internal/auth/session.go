// Package auth 管理登录会话（Session Cookie）。
package auth

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"time"

	"yj-forum/server/internal/database"
)

// SessionManager 会话管理。
type SessionManager struct {
	DB *database.DB
}

const sessionTTL = 24 * time.Hour // 对齐 legacy PERMANENT_SESSION_LIFETIME=86400

// Create 创建会话，返回 token。
func (m *SessionManager) Create(ctx context.Context, userID string) (string, error) {
	token := make([]byte, 32)
	if _, err := rand.Read(token); err != nil {
		return "", err
	}
	t := hex.EncodeToString(token)
	_, err := m.DB.Exec(ctx, `INSERT INTO sessions (token, user_id, expires_at)
		VALUES ($1,$2, NOW() + INTERVAL '24 hours')`, t, userID)
	if err != nil {
		return "", err
	}
	return t, nil
}

// Validate 验证会话，返回 user_id（不存在或过期则空串）。
func (m *SessionManager) Validate(ctx context.Context, token string) (string, error) {
	if token == "" {
		return "", nil
	}
	var userID string
	// 同一条查询内校验封禁/注销：封禁或注销后旧 session 立即失效（即使未删除行）
	err := m.DB.QueryRow(ctx, `SELECT s.user_id FROM sessions s
		JOIN users u ON u.id = s.user_id
		WHERE s.token=$1 AND s.expires_at > NOW()
		  AND COALESCE(u.is_banned, 0) = 0 AND u.deleted_at IS NULL`, token).Scan(&userID)
	if err != nil {
		return "", nil
	}
	return userID, nil
}

// Delete 删除会话。
func (m *SessionManager) Delete(ctx context.Context, token string) error {
	_, err := m.DB.Exec(ctx, `DELETE FROM sessions WHERE token=$1`, token)
	return err
}

// DeleteByUserID 删除某用户全部会话（重置密码/注销后强制下线）。
func (m *SessionManager) DeleteByUserID(ctx context.Context, userID string) error {
	_, err := m.DB.Exec(ctx, `DELETE FROM sessions WHERE user_id=$1`, userID)
	return err
}

// Cleanup 清理过期会话（由后台 goroutine 定期执行）。
func (m *SessionManager) Cleanup(ctx context.Context) {
	_, _ = m.DB.Exec(ctx, `DELETE FROM sessions WHERE expires_at < NOW()`)
}
