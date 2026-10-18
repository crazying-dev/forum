// Package legacy 实现旧 APP 兼容层的认证/契约辅助。
package legacy

import (
	"crypto/hmac"
	"crypto/md5"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

var (
	ErrLegacyTokenMalformed = errors.New("legacy token 格式错误")
	ErrLegacyTokenExpired   = errors.New("legacy token 已过期")
	ErrLegacyTokenFuture    = errors.New("legacy token 时间不在有效窗口")
	ErrLegacyTokenInvalid   = errors.New("legacy token 签名无效")
)

// TokenVerifier 校验 forum-legacy 的 token（token---{md5}.{hmac}---{st}）。
//
// 安全边界：legacy token 的 st 不在 HMAC 内，无法从密码学上阻止重放；
// 本实现通过 st 接受窗口、password_changed_at、NotBefore、封禁/注销检查与
// 会话轮换把风险压到最低，并通过 LEGACY_APP_SUNSET 设定下线日期。
type TokenVerifier struct {
	Secret    []byte
	TTL       time.Duration
	NotBefore time.Time
	ClockSkew time.Duration
}

// NewTokenVerifier 创建校验器。secret 为空时所有校验失败（fail-closed）。
func NewTokenVerifier(secret string, ttl time.Duration, notBefore time.Time) *TokenVerifier {
	if ttl <= 0 {
		ttl = 7 * 24 * time.Hour
	}
	return &TokenVerifier{
		Secret:    []byte(secret),
		TTL:       ttl,
		NotBefore: notBefore,
		ClockSkew: 5 * time.Minute,
	}
}

// Verify 校验 token；passwordChangedAt 用于拒绝改密前签发的 token。
func (v *TokenVerifier) Verify(userID, token, passwordHash string, passwordChangedAt, now time.Time) error {
	if v == nil || len(v.Secret) == 0 || userID == "" || token == "" || passwordHash == "" {
		return ErrLegacyTokenInvalid
	}
	parts := strings.Split(token, "---")
	if len(parts) != 3 || parts[0] != "token" {
		return ErrLegacyTokenMalformed
	}
	st, err := strconv.ParseInt(parts[2], 10, 64)
	if err != nil {
		return ErrLegacyTokenMalformed
	}
	sent := time.Unix(st, 0)
	if sent.After(now.Add(v.ClockSkew)) {
		return ErrLegacyTokenFuture
	}
	if now.Sub(sent) > v.TTL {
		return ErrLegacyTokenExpired
	}
	notBefore := v.NotBefore
	if passwordChangedAt.After(notBefore) {
		notBefore = passwordChangedAt
	}
	if !notBefore.IsZero() && sent.Before(notBefore.Truncate(time.Second)) {
		return ErrLegacyTokenExpired
	}
	expected, err := CoreToken(v.Secret, userID, passwordHash)
	if err != nil {
		return err
	}
	if !hmac.Equal([]byte(expected), []byte(parts[1])) {
		return ErrLegacyTokenInvalid
	}
	return nil
}

// GenerateToken 生成 legacy token（兼容层登录/注册写 Cookie 用）。
func GenerateToken(secret, userID, passwordHash string, sent time.Time) (string, error) {
	core, err := CoreToken([]byte(secret), userID, passwordHash)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("token---%s---%d", core, sent.Unix()), nil
}

// CoreToken 复刻 legacy GetToken(user_id, password_hash)：md5(repr(tuple)) + "." + hmac_sha256(repr(tuple))。
func CoreToken(secret []byte, userID, passwordHash string) (string, error) {
	if len(secret) == 0 {
		return "", ErrLegacyTokenInvalid
	}
	raw := pythonReprTuple2(userID, passwordHash)
	digest := md5.Sum([]byte(raw))
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write([]byte(raw))
	return hex.EncodeToString(digest[:]) + "." + hex.EncodeToString(mac.Sum(nil)), nil
}

// pythonReprTuple2 复刻 Python repr((a, b)) 对 ASCII 字符串的输出。
// 旧系统的 user_id/password_hash 只含字母、数字与少数符号，不包含引号/反斜杠。
func pythonReprTuple2(a, b string) string {
	return "(" + pythonReprString(a) + ", " + pythonReprString(b) + ")"
}

func pythonReprString(s string) string {
	// Python 默认单引号；转义反斜杠与单引号。
	var b strings.Builder
	b.WriteByte('\'')
	for _, r := range s {
		switch r {
		case '\\':
			b.WriteString("\\\\")
		case '\'':
			b.WriteString("\\'")
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte('\'')
	return b.String()
}
