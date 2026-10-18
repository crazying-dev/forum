package database

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"

	"yj-forum/server/internal/models"
)

// 注：gender/age/intro/prefix 可为 NULL（历史数据，如个别账号 prefix 未写），读取时统一 COALESCE 兜底；
// last_sign_in 可空（未签到），扫描后格式化为 YYYY-MM-DD
const userCols = `id, name, avatar, email, COALESCE(gender, 0), COALESCE(age, ''), COALESCE(intro, ''), spirit, last_sign_in, COALESCE(prefix, ''), is_banned, email_verified, created_at, last_login, deleted_at`

func scanUser(row interface{ Scan(...any) error }) (*models.User, error) {
	var u models.User
	var createdAt, lastLogin, lastSignIn *time.Time
	err := row.Scan(&u.ID, &u.Name, &u.Avatar, &u.Email, &u.Gender, &u.Age, &u.Intro, &u.Spirit, &lastSignIn,
		&u.Prefix, &u.IsBanned, &u.EmailVerified, &createdAt, &lastLogin, &u.DeletedAt)
	if err != nil {
		return nil, err
	}
	u.CreatedAt = createdAt
	u.LastLogin = lastLogin
	if lastSignIn != nil {
		u.LastSignIn = lastSignIn.Format("2006-01-02")
	}
	return &u, nil
}

// GetUserByID 按 ID 查用户（不含密码）。
func (d *DB) GetUserByID(ctx context.Context, id string) (*models.User, error) {
	return scanUser(d.QueryRow(ctx, "SELECT "+userCols+" FROM users WHERE id=$1", id))
}

// GetUserByName 按用户名查（含密码哈希，供登录）。
func (d *DB) GetUserByName(ctx context.Context, name string) (*models.User, string, error) {
	var u models.User
	var pwd string
	var createdAt, lastLogin, lastSignIn *time.Time
	err := d.QueryRow(ctx, `SELECT id, name, avatar, email, COALESCE(gender, 0), COALESCE(age, ''), COALESCE(intro, ''), spirit, last_sign_in, COALESCE(prefix, ''), is_banned, email_verified, created_at, last_login, password
		FROM users WHERE name=$1`, name).
		Scan(&u.ID, &u.Name, &u.Avatar, &u.Email, &u.Gender, &u.Age, &u.Intro, &u.Spirit, &lastSignIn,
			&u.Prefix, &u.IsBanned, &u.EmailVerified, &createdAt, &lastLogin, &pwd)
	if err != nil {
		return nil, "", err
	}
	u.CreatedAt = createdAt
	u.LastLogin = lastLogin
	if lastSignIn != nil {
		u.LastSignIn = lastSignIn.Format("2006-01-02")
	}
	return &u, pwd, nil
}

// GetUserByEmail 按邮箱查（含密码）。
func (d *DB) GetUserByEmail(ctx context.Context, email string) (*models.User, string, error) {
	var u models.User
	var pwd string
	var createdAt, lastLogin, lastSignIn *time.Time
	err := d.QueryRow(ctx, `SELECT id, name, avatar, email, COALESCE(gender, 0), COALESCE(age, ''), COALESCE(intro, ''), spirit, last_sign_in, COALESCE(prefix, ''), is_banned, email_verified, created_at, last_login, password
		FROM users WHERE email=$1`, email).
		Scan(&u.ID, &u.Name, &u.Avatar, &u.Email, &u.Gender, &u.Age, &u.Intro, &u.Spirit, &lastSignIn,
			&u.Prefix, &u.IsBanned, &u.EmailVerified, &createdAt, &lastLogin, &pwd)
	if err != nil {
		return nil, "", err
	}
	u.CreatedAt = createdAt
	u.LastLogin = lastLogin
	if lastSignIn != nil {
		u.LastSignIn = lastSignIn.Format("2006-01-02")
	}
	return &u, pwd, nil
}

// NewUser 注册新用户。email/name 冲突返回对应错误。
func (d *DB) NewUser(ctx context.Context, name, email, passwordHash, avatar string) (string, error) {
	id := GenID("RL")
	_, err := d.Exec(ctx, `INSERT INTO users (id, name, avatar, email, password) VALUES ($1,$2,$3,$4,$5)`,
		id, name, avatar, email, passwordHash)
	if err != nil {
		return "", err
	}
	return id, nil
}

// SignInToday 每日签到：当日未签到则灵力 +10 并刷新签到日期。
// 返回最新灵力与签到日期；当日已签到返回 (0, "", false, nil)。
func (d *DB) SignInToday(ctx context.Context, userID string) (int, string, bool, error) {
	var spirit int
	var lastSignIn *time.Time
	// 签到日界固定为 Asia/Shanghai（东八区）：避免库会话时区（UTC）导致跨零点口径偏差
	err := d.QueryRow(ctx, `UPDATE users SET spirit = spirit + 10, last_sign_in = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
		WHERE id = $1 AND (last_sign_in IS NULL OR last_sign_in < (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date)
		RETURNING spirit, last_sign_in`, userID).Scan(&spirit, &lastSignIn)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, "", false, nil
	}
	if err != nil {
		return 0, "", false, err
	}
	return spirit, lastSignIn.Format("2006-01-02"), true, nil
}

// GetUserPasswordHash 读取用户密码哈希（改密前校验当前密码用）。
func (d *DB) GetUserPasswordHash(ctx context.Context, userID string) (string, error) {
	var hash string
	err := d.QueryRow(ctx, `SELECT password FROM users WHERE id=$1`, userID).Scan(&hash)
	return hash, err
}

// UpdateUserProfile 更新资料（白名单字段）。
func (d *DB) UpdateUserProfile(ctx context.Context, userID string, fields map[string]any) error {
	if len(fields) == 0 {
		return nil
	}
	sqlQ := "UPDATE users SET "
	args := []any{}
	i := 1
	for k, v := range fields {
		sqlQ += k + " = $" + itoa(i) + ", "
		args = append(args, v)
		i++
	}
	sqlQ = sqlQ[:len(sqlQ)-2] + " WHERE id = $" + itoa(i)
	args = append(args, userID)
	_, err := d.Exec(ctx, sqlQ, args...)
	return err
}

// UpdateUserEmailVerified 邮箱验证通过。
func (d *DB) UpdateUserEmailVerified(ctx context.Context, userID string) error {
	_, err := d.Exec(ctx, "UPDATE users SET email_verified = 1 WHERE id = $1", userID)
	return err
}

// UpdateUserLastLogin 更新最后登录时间。
func (d *DB) UpdateUserLastLogin(ctx context.Context, userID string) error {
	_, err := d.Exec(ctx, "UPDATE users SET last_login = NOW() WHERE id = $1", userID)
	return err
}

// GetUserByIDSimple 公开信息（含 is_banned）。
func (d *DB) HasUser(ctx context.Context, id string) (bool, error) {
	var exists bool
	err := d.QueryRow(ctx, "SELECT EXISTS(SELECT 1 FROM users WHERE id=$1)", id).Scan(&exists)
	return exists, err
}

// ---- 点赞 / 收藏 / 关注 ----

// LikePost 切换点赞，返回 (是否点赞, 最新点赞数)。
func (d *DB) LikePost(ctx context.Context, postID, userID string) (bool, int, error) {
	return d.likePostTx(ctx, postID, userID)
}

func (d *DB) likePostTx(ctx context.Context, postID, userID string) (bool, int, error) {
	var count int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM post_likes WHERE post_id=$1 AND user_id=$2", postID, userID).Scan(&count)
	if count > 0 {
		_, _ = d.Exec(ctx, "DELETE FROM post_likes WHERE post_id=$1 AND user_id=$2", postID, userID)
		_, _ = d.Exec(ctx, "UPDATE posts SET likes = GREATEST(likes - 1, 0) WHERE id=$1", postID)
		return false, d.currentLikes(ctx, postID), nil
	}
	_, err := d.Exec(ctx, "INSERT INTO post_likes (post_id, user_id) VALUES ($1,$2)", postID, userID)
	if err != nil {
		return false, 0, err
	}
	_, err = d.Exec(ctx, "UPDATE posts SET likes = likes + 1 WHERE id=$1", postID)
	if err != nil {
		return false, 0, err
	}
	return true, d.currentLikes(ctx, postID), nil
}

func (d *DB) currentLikes(ctx context.Context, postID string) int {
	var likes int
	_ = d.QueryRow(ctx, "SELECT COALESCE(likes,0) FROM posts WHERE id=$1", postID).Scan(&likes)
	return likes
}

// HasLikedPost 是否已点赞。
func (d *DB) HasLikedPost(ctx context.Context, postID, userID string) bool {
	var n int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM post_likes WHERE post_id=$1 AND user_id=$2", postID, userID).Scan(&n)
	return n > 0
}

// ToggleFavorite 切换收藏。
func (d *DB) ToggleFavorite(ctx context.Context, postID, userID string) (bool, error) {
	var count int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM post_favorites WHERE post_id=$1 AND user_id=$2", postID, userID).Scan(&count)
	if count > 0 {
		_, err := d.Exec(ctx, "DELETE FROM post_favorites WHERE post_id=$1 AND user_id=$2", postID, userID)
		return false, err
	}
	_, err := d.Exec(ctx, "INSERT INTO post_favorites (post_id, user_id) VALUES ($1,$2)", postID, userID)
	return true, err
}

// HasFavoritedPost 是否已收藏。
func (d *DB) HasFavoritedPost(ctx context.Context, postID, userID string) bool {
	var n int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM post_favorites WHERE post_id=$1 AND user_id=$2", postID, userID).Scan(&n)
	return n > 0
}

// GetUserFavorites 用户收藏帖子列表（仅已发布）。
func (d *DB) GetUserFavorites(ctx context.Context, userID string, page, pageSize int) ([]models.PostListItem, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	return d.queryPostListItems(ctx, `SELECT p.id, p.user_id, p.title, `+postSummaryExpr+`, p.category, p.likes, p.views,
		p.created_at, u.name, u.avatar,
		(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
		p.guild_id, g.name, g.theme_color,
		COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false),
		p.published_at
		FROM post_favorites f JOIN posts p ON f.post_id = p.id JOIN users u ON p.user_id = u.id
		LEFT JOIN guilds g ON g.id = p.guild_id
		LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
		LEFT JOIN guilds ug ON ug.id = ugm.guild_id
		WHERE f.user_id = $1 AND p.status = 1 AND p.published_at <= NOW() ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`,
		userID, pageSize, offset)
}

// ToggleFollow 关注/取消（禁自关）。
func (d *DB) ToggleFollow(ctx context.Context, followerID, followingID string) (bool, error) {
	if followerID == followingID {
		return false, errSelfFollow
	}
	var count int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM user_follows WHERE follower_id=$1 AND following_id=$2", followerID, followingID).Scan(&count)
	if count > 0 {
		_, err := d.Exec(ctx, "DELETE FROM user_follows WHERE follower_id=$1 AND following_id=$2", followerID, followingID)
		return false, err
	}
	_, err := d.Exec(ctx, "INSERT INTO user_follows (follower_id, following_id) VALUES ($1,$2)", followerID, followingID)
	return true, err
}

// IsFollowing 是否已关注。
func (d *DB) IsFollowing(ctx context.Context, followerID, followingID string) bool {
	var n int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM user_follows WHERE follower_id=$1 AND following_id=$2", followerID, followingID).Scan(&n)
	return n > 0
}

// GetFollowStats 关注统计。
func (d *DB) GetFollowStats(ctx context.Context, userID string) (models.FollowStats, error) {
	var fs models.FollowStats
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM user_follows WHERE follower_id=$1", userID).Scan(&fs.FollowingCount)
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM user_follows WHERE following_id=$1", userID).Scan(&fs.FollowerCount)
	return fs, nil
}

// GetFollowingList 关注列表（has_more 用 pageSize+1 探测；is_mutual 为 viewer 是否回关）。
func (d *DB) GetFollowingList(ctx context.Context, userID, viewerID string, page, pageSize int) ([]models.UserBrief, bool, error) {
	return d.followList(ctx, "follower_id", userID, viewerID, page, pageSize)
}

// GetFollowerList 粉丝列表（has_more 用 pageSize+1 探测；is_mutual 恒 false）。
func (d *DB) GetFollowerList(ctx context.Context, userID, viewerID string, page, pageSize int) ([]models.UserBrief, bool, error) {
	return d.followList(ctx, "following_id", userID, viewerID, page, pageSize)
}

// followList side=follower_id 为「关注列表」，side=following_id 为「粉丝列表」。
// is_mutual 仅关注列表有意义：viewer 非空且非本人时，表示 viewer 也关注了该行用户。
func (d *DB) followList(ctx context.Context, side, userID, viewerID string, page, pageSize int) ([]models.UserBrief, bool, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	col := "following_id"
	if side == "following_id" {
		col = "follower_id"
	}
	// 粉丝列表无互关语义，恒 false
	mutual := "FALSE"
	if side == "follower_id" {
		mutual = `(COALESCE($4, '') <> '' AND $4 <> $1 AND EXISTS(
			SELECT 1 FROM user_follows f3 WHERE f3.follower_id = $4 AND f3.following_id = u.id))`
	}
	// 历史数据中 name/avatar/prefix/intro 可能为 NULL（如个别账号 prefix 未写），统一 COALESCE 兜底
	rows, err := d.Query(ctx, `SELECT u.id, COALESCE(u.name, ''), COALESCE(u.avatar, ''), COALESCE(u.prefix, ''), COALESCE(u.intro, ''),
		(u.id = $4) AS is_self,
		EXISTS(SELECT 1 FROM user_follows f2 WHERE f2.follower_id = $4 AND f2.following_id = u.id) AS is_following,
		`+mutual+` AS is_mutual
		FROM user_follows f JOIN users u ON u.id = f.`+col+`
		WHERE f.`+side+` = $1 ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`,
		userID, pageSize+1, offset, viewerID)
	if err != nil {
		return nil, false, err
	}
	defer rows.Close()
	users := []models.UserBrief{}
	for rows.Next() {
		var u models.UserBrief
		if err := rows.Scan(&u.ID, &u.Name, &u.Avatar, &u.Prefix, &u.Intro, &u.IsSelf, &u.IsFollowing, &u.IsMutual); err != nil {
			return nil, false, err
		}
		users = append(users, u)
	}
	if err := rows.Err(); err != nil {
		return nil, false, err
	}
	hasMore := len(users) > pageSize
	if hasMore {
		users = users[:pageSize]
	}
	return users, hasMore, nil
}

// GetMutualList 共同关注：user 与 viewer 都关注的用户（按 user 的关注时间倒序）；has_more 用 pageSize+1 探测。
func (d *DB) GetMutualList(ctx context.Context, userID, viewerID string, page, pageSize int) ([]models.UserBrief, bool, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	// 同 followList：nullable 列统一 COALESCE 兜底
	rows, err := d.Query(ctx, `SELECT u.id, COALESCE(u.name, ''), COALESCE(u.avatar, ''), COALESCE(u.prefix, ''), COALESCE(u.intro, ''),
		(u.id = $4) AS is_self, TRUE AS is_following, TRUE AS is_mutual
		FROM user_follows a JOIN user_follows b ON b.following_id = a.following_id
		JOIN users u ON u.id = a.following_id
		WHERE a.follower_id = $4 AND b.follower_id = $1
		ORDER BY b.created_at DESC LIMIT $2 OFFSET $3`,
		userID, pageSize+1, offset, viewerID)
	if err != nil {
		return nil, false, err
	}
	defer rows.Close()
	users := []models.UserBrief{}
	for rows.Next() {
		var u models.UserBrief
		if err := rows.Scan(&u.ID, &u.Name, &u.Avatar, &u.Prefix, &u.Intro, &u.IsSelf, &u.IsFollowing, &u.IsMutual); err != nil {
			return nil, false, err
		}
		users = append(users, u)
	}
	if err := rows.Err(); err != nil {
		return nil, false, err
	}
	hasMore := len(users) > pageSize
	if hasMore {
		users = users[:pageSize]
	}
	return users, hasMore, nil
}

// GetFollowerEmails 粉丝邮箱（发帖通知）。
func (d *DB) GetFollowerEmails(ctx context.Context, userID string, limit int) ([]string, error) {
	if limit < 1 || limit > 5000 {
		limit = 5000
	}
	rows, err := d.Query(ctx, `SELECT u.email FROM user_follows f JOIN users u ON u.id = f.follower_id
		WHERE f.following_id = $1 LIMIT $2`, userID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var emails []string
	for rows.Next() {
		var e string
		if err := rows.Scan(&e); err != nil {
			return nil, err
		}
		emails = append(emails, e)
	}
	return emails, rows.Err()
}
