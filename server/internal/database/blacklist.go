package database

import (
	"context"
	"strings"
)

// NormalizeEmail 规范化邮箱：去首尾空白、转小写、去掉本地部分的 +tag。
// 例：" Foo.Bar+Spam@Example.COM " -> "foo.bar@example.com"。
func NormalizeEmail(email string) string {
	s := strings.ToLower(strings.TrimSpace(email))
	at := strings.LastIndexByte(s, '@')
	if at < 0 {
		return s
	}
	local, domain := s[:at], s[at+1:]
	if plus := strings.IndexByte(local, '+'); plus >= 0 {
		local = local[:plus]
	}
	return local + "@" + domain
}

// MatchEmailBlacklist 判断邮箱是否命中黑名单模式（纯函数）。
// 支持三种模式：
//   - 精确邮箱：user@example.com
//   - 域名：@example.com
//   - 域名通配：*@example.com
//
// 邮箱与模式均不区分大小写；邮箱会先经 NormalizeEmail 去掉 +tag。
func MatchEmailBlacklist(email string, patterns []string) bool {
	normalized := NormalizeEmail(email)
	at := strings.LastIndexByte(normalized, '@')
	if at <= 0 || at == len(normalized)-1 {
		return false
	}
	domain := normalized[at+1:]

	for _, raw := range patterns {
		pattern := strings.ToLower(strings.TrimSpace(raw))
		if pattern == "" {
			continue
		}
		switch {
		case strings.HasPrefix(pattern, "*@"):
			if domain == strings.TrimPrefix(pattern, "*@") {
				return true
			}
		case strings.HasPrefix(pattern, "@"):
			if domain == strings.TrimPrefix(pattern, "@") {
				return true
			}
		default:
			if normalized == NormalizeEmail(pattern) {
				return true
			}
		}
	}
	return false
}

// IsEmailBlacklisted 查询 email_blacklist 表并判断邮箱是否命中。
// 数据库错误由调用方决定如何处理（注册流程应拒绝并返回 500）。
func (d *DB) IsEmailBlacklisted(ctx context.Context, email string) (bool, error) {
	rows, err := d.Query(ctx, `SELECT pattern FROM email_blacklist`)
	if err != nil {
		return false, err
	}
	defer rows.Close()

	patterns := make([]string, 0, 16)
	for rows.Next() {
		var pattern string
		if err := rows.Scan(&pattern); err != nil {
			return false, err
		}
		patterns = append(patterns, pattern)
	}
	if err := rows.Err(); err != nil {
		return false, err
	}
	return MatchEmailBlacklist(email, patterns), nil
}
