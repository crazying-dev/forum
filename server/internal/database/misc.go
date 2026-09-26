package database

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"time"

	"yj-forum/server/internal/models"
)

// ---- 验证 token（邮箱验证/密码重置，30 分钟）----

// CreateVerifyToken 创建验证 token。
func (d *DB) CreateVerifyToken(ctx context.Context, userID, tokenType string, expiresMinutes int) (string, error) {
	if expiresMinutes <= 0 {
		expiresMinutes = 30
	}
	token := randomToken(48)
	_, err := d.Exec(ctx, `INSERT INTO verify_tokens (user_id, token, token_type, expires_at)
		VALUES ($1,$2,$3, NOW() + $4 * INTERVAL '1 minute')`, userID, token, tokenType, expiresMinutes)
	if err != nil {
		return "", err
	}
	return token, nil
}

// GetVerifyToken 校验 token（返回 user_id）。
func (d *DB) GetVerifyToken(ctx context.Context, token, tokenType string) (string, error) {
	var userID string
	err := d.QueryRow(ctx, `SELECT user_id FROM verify_tokens
		WHERE token = $1 AND token_type = $2 AND expires_at > NOW()`, token, tokenType).Scan(&userID)
	if err != nil {
		return "", err
	}
	return userID, nil
}

// DeleteVerifyToken 删除 token。
func (d *DB) DeleteVerifyToken(ctx context.Context, token string) error {
	_, err := d.Exec(ctx, `DELETE FROM verify_tokens WHERE token = $1`, token)
	return err
}

// ---- 验证码（6 位，5 分钟）----

// CreateVerifyCode 创建验证码。
func (d *DB) CreateVerifyCode(ctx context.Context, email, code, purpose string, expiresMinutes int) error {
	if expiresMinutes <= 0 {
		expiresMinutes = 5
	}
	_, err := d.Exec(ctx, `INSERT INTO verify_codes (email, code, purpose, expires_at)
		VALUES ($1,$2,$3, NOW() + $4 * INTERVAL '1 minute')`, email, code, purpose, expiresMinutes)
	return err
}

// GetVerifyCode 校验验证码（返回 id 行存在性）。
func (d *DB) GetVerifyCode(ctx context.Context, email, code, purpose string) (bool, error) {
	var n int
	err := d.QueryRow(ctx, `SELECT COUNT(*) FROM verify_codes
		WHERE email=$1 AND code=$2 AND purpose=$3 AND used=0 AND expires_at > NOW()`, email, code, purpose).Scan(&n)
	return n > 0, err
}

// MarkVerifyCodeUsed 标记验证码已使用。
func (d *DB) MarkVerifyCodeUsed(ctx context.Context, email, code, purpose string) error {
	_, err := d.Exec(ctx, `UPDATE verify_codes SET used=1 WHERE email=$1 AND code=$2 AND purpose=$3`, email, code, purpose)
	return err
}

// IncrementVerifyCodeAttempts 失败次数 +1。
func (d *DB) IncrementVerifyCodeAttempts(ctx context.Context, email, purpose string) error {
	_, err := d.Exec(ctx, `UPDATE verify_codes SET attempts = attempts + 1 WHERE email=$1 AND purpose=$2`, email, purpose)
	return err
}

// CleanExpiredVerifyCodes 清理过期验证码。
func (d *DB) CleanExpiredVerifyCodes(ctx context.Context) error {
	_, err := d.Exec(ctx, `DELETE FROM verify_codes WHERE expires_at < NOW() OR used=1`)
	return err
}

// ---- 投票 ----

// VoteVersion 投票（upsert by voter_key）。
func (d *DB) VoteVersion(ctx context.Context, voterKey, choice, voterID, voterName string) error {
	_, err := d.Exec(ctx, `INSERT INTO version_votes (voter_key, voter_id, voter_name, choice)
		VALUES ($1,$2,$3,$4)
		ON CONFLICT (voter_key) DO UPDATE SET choice = EXCLUDED.choice, voter_id = EXCLUDED.voter_id,
			voter_name = EXCLUDED.voter_name, updated_at = NOW()`, voterKey, voterID, voterName, choice)
	return err
}

// GetVersionVoteStats 投票统计。
func (d *DB) GetVersionVoteStats(ctx context.Context) (models.VersionVoteStats, error) {
	var s models.VersionVoteStats
	_ = d.QueryRow(ctx, `SELECT COUNT(*) FILTER (WHERE choice='v1'), COUNT(*) FILTER (WHERE choice='v2') FROM version_votes`).Scan(&s.V1, &s.V2)
	return s, nil
}

// ---- 举报 ----

// ReportPost 举报帖子。
func (d *DB) ReportPost(ctx context.Context, postID, reporterID, reason, detail string) error {
	_, err := d.Exec(ctx, `INSERT INTO post_reports (post_id, reporter_id, reason, detail) VALUES ($1,$2,$3,$4)`,
		postID, reporterID, reason, detail)
	return err
}

// ReportBug 提交 Bug。
func (d *DB) ReportBug(ctx context.Context, title, detail, steps, contact, reporterID, reporterName, userAgent, pageURL string) (int64, error) {
	var id int64
	err := d.QueryRow(ctx, `INSERT INTO bug_reports (title, detail, steps, contact, reporter_id, reporter_name, user_agent, page_url)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id`,
		title, detail, steps, contact, nullIfEmpty(reporterID), reporterName, userAgent, pageURL).Scan(&id)
	return id, err
}

// ---- 搜索 ----

// SearchPosts 帖子搜索（ILIKE 多词 AND + 相关性）。
func (d *DB) SearchPosts(ctx context.Context, keyword string, page, pageSize int) ([]models.PostListItem, int, bool, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	terms := splitTerms(keyword)
	var total int
	// count
	if len(terms) == 0 {
		return []models.PostListItem{}, 0, false, nil
	}
	// 组装 WHERE
	where := "WHERE p.status = 1"
	args := []any{}
	for _, t := range terms {
		args = append(args, "%"+t+"%")
		where += " AND (p.title ILIKE $" + itoa(len(args)) + " OR p.content ILIKE $" + itoa(len(args)) + ")"
	}
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM posts p "+where, args...).Scan(&total)
	// 相关性: title 100, content 50, 简化: 标题命中优先
	rows, err := d.Query(ctx, `SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views,
		p.created_at, u.name, u.avatar,
		(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
		p.guild_id, g.name, g.theme_color,
		COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false)
		FROM posts p JOIN users u ON p.user_id = u.id LEFT JOIN guilds g ON g.id = p.guild_id
		LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
		LEFT JOIN guilds ug ON ug.id = ugm.guild_id `+where+` ORDER BY p.created_at DESC LIMIT $`+itoa(len(args)+1)+` OFFSET $`+itoa(len(args)+2),
		append(args, pageSize, offset)...)
	if err != nil {
		return nil, 0, false, err
	}
	defer rows.Close()
	var posts []models.PostListItem
	for rows.Next() {
		var p models.PostListItem
		var createdAt *time.Time
		var guildID *int64
		var guildName, guildTheme *string
		if err := rows.Scan(&p.ID, &p.UserID, &p.Title, &p.Summary, &p.Category, &p.Likes, &p.Views, &createdAt, &p.UserName, &p.UserAvatar, &p.CommentCount,
			&guildID, &guildName, &guildTheme,
			&p.UserGuildName, &p.UserGuildThemeColor, &p.UserIsLeader); err != nil {
			return nil, 0, false, err
		}
		p.CreatedAt = createdAt
		p.GuildID, p.GuildName, p.GuildThemeColor = guildCols(guildID, guildName, guildTheme)
		posts = append(posts, p)
	}
	hasMore := offset+len(posts) < total
	return posts, total, hasMore, rows.Err()
}

// SearchUsers 用户搜索。
func (d *DB) SearchUsers(ctx context.Context, keyword string, page, pageSize int) ([]models.UserBrief, int, bool, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	terms := splitTerms(keyword)
	if len(terms) == 0 {
		return []models.UserBrief{}, 0, false, nil
	}
	where := "WHERE 1=1"
	args := []any{}
	for _, t := range terms {
		args = append(args, "%"+t+"%")
		where += " AND (name ILIKE $" + itoa(len(args)) + " OR prefix ILIKE $" + itoa(len(args)) + " OR intro ILIKE $" + itoa(len(args)) + ")"
	}
	var total int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM users "+where, args...).Scan(&total)
	// 相关性排序简化为 created_at（保持与 legacy 近似行为）
	rows, err := d.Query(ctx, `SELECT id, name, avatar, vip, prefix, intro FROM users `+where+` ORDER BY created_at DESC LIMIT $`+itoa(len(args)+1)+` OFFSET $`+itoa(len(args)+2),
		append(args, pageSize, offset)...)
	if err != nil {
		return nil, 0, false, err
	}
	defer rows.Close()
	var users []models.UserBrief
	for rows.Next() {
		var u models.UserBrief
		if err := rows.Scan(&u.ID, &u.Name, &u.Avatar, &u.VIP, &u.Prefix, &u.Intro); err != nil {
			return nil, 0, false, err
		}
		users = append(users, u)
	}
	hasMore := offset+len(users) < total
	return users, total, hasMore, rows.Err()
}

// ---- 工具 ----

func randomToken(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return time.Now().Format("20060102150405.000000000")
	}
	return hex.EncodeToString(b)
}

func splitTerms(s string) []string {
	var terms []string
	cur := ""
	for _, ch := range s {
		if ch == ' ' || ch == '\t' || ch == '\n' {
			if cur != "" {
				terms = append(terms, cur)
				cur = ""
			}
		} else {
			cur += string(ch)
		}
	}
	if cur != "" {
		terms = append(terms, cur)
	}
	if len(terms) > 5 {
		terms = terms[:5]
	}
	return terms
}

func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}
