package database

import (
	"context"
	"time"

	"yj-forum/server/internal/models"
)

const userCols = `id, name, avatar, email, gender, age, intro, vip, prefix, is_banned, email_verified, created_at, last_login`

func scanUser(row interface{ Scan(...any) error }) (*models.User, error) {
	var u models.User
	var createdAt, lastLogin *time.Time
	err := row.Scan(&u.ID, &u.Name, &u.Avatar, &u.Email, &u.Gender, &u.Age, &u.Intro, &u.VIP,
		&u.Prefix, &u.IsBanned, &u.EmailVerified, &createdAt, &lastLogin)
	if err != nil {
		return nil, err
	}
	u.CreatedAt = createdAt
	u.LastLogin = lastLogin
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
	var createdAt, lastLogin *time.Time
	err := d.QueryRow(ctx, `SELECT id, name, avatar, email, gender, age, intro, vip, prefix, is_banned, email_verified, created_at, last_login, password
		FROM users WHERE name=$1`, name).
		Scan(&u.ID, &u.Name, &u.Avatar, &u.Email, &u.Gender, &u.Age, &u.Intro, &u.VIP,
			&u.Prefix, &u.IsBanned, &u.EmailVerified, &createdAt, &lastLogin, &pwd)
	if err != nil {
		return nil, "", err
	}
	u.CreatedAt = createdAt
	u.LastLogin = lastLogin
	return &u, pwd, nil
}

// GetUserByEmail 按邮箱查（含密码）。
func (d *DB) GetUserByEmail(ctx context.Context, email string) (*models.User, string, error) {
	var u models.User
	var pwd string
	var createdAt, lastLogin *time.Time
	err := d.QueryRow(ctx, `SELECT id, name, avatar, email, gender, age, intro, vip, prefix, is_banned, email_verified, created_at, last_login, password
		FROM users WHERE email=$1`, email).
		Scan(&u.ID, &u.Name, &u.Avatar, &u.Email, &u.Gender, &u.Age, &u.Intro, &u.VIP,
			&u.Prefix, &u.IsBanned, &u.EmailVerified, &createdAt, &lastLogin, &pwd)
	if err != nil {
		return nil, "", err
	}
	u.CreatedAt = createdAt
	u.LastLogin = lastLogin
	return &u, pwd, nil
}

// NewUser 注册新用户。email/name 冲突返回对应错误。
func (d *DB) NewUser(ctx context.Context, name, email, passwordHash, avatar string) (string, error) {
	id := GenID("RL")
	_, err := d.Exec(ctx, `INSERT INTO users (id, name, avatar, email, password, vip) VALUES ($1,$2,$3,$4,$5,'0')`,
		id, name, avatar, email, passwordHash)
	if err != nil {
		return "", err
	}
	return id, nil
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

// GetUserFavorites 用户收藏帖子列表。
func (d *DB) GetUserFavorites(ctx context.Context, userID string, page, pageSize int) ([]models.PostListItem, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	rows, err := d.Query(ctx, `SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views,
		p.created_at, u.name, u.avatar,
		(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
		p.guild_id, g.name, g.theme_color
		FROM post_favorites f JOIN posts p ON f.post_id = p.id JOIN users u ON p.user_id = u.id
		LEFT JOIN guilds g ON g.id = p.guild_id
		WHERE f.user_id = $1 AND p.status = 1 ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`,
		userID, pageSize, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var posts []models.PostListItem
	for rows.Next() {
		var p models.PostListItem
		var createdAt *time.Time
		var guildID *int64
		var guildName, guildTheme *string
		if err := rows.Scan(&p.ID, &p.UserID, &p.Title, &p.Summary, &p.Category, &p.Likes, &p.Views, &createdAt, &p.UserName, &p.UserAvatar, &p.CommentCount,
			&guildID, &guildName, &guildTheme); err != nil {
			return nil, err
		}
		p.CreatedAt = createdAt
		p.GuildID, p.GuildName, p.GuildThemeColor = guildCols(guildID, guildName, guildTheme)
		posts = append(posts, p)
	}
	return posts, rows.Err()
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

// GetFollowingList 关注列表。
func (d *DB) GetFollowingList(ctx context.Context, userID, viewerID string, page, pageSize int) ([]models.UserBrief, error) {
	return d.followList(ctx, "follower_id", userID, viewerID, page, pageSize)
}

// GetFollowerList 粉丝列表。
func (d *DB) GetFollowerList(ctx context.Context, userID, viewerID string, page, pageSize int) ([]models.UserBrief, error) {
	return d.followList(ctx, "following_id", userID, viewerID, page, pageSize)
}

func (d *DB) followList(ctx context.Context, side, userID, viewerID string, page, pageSize int) ([]models.UserBrief, error) {
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
	rows, err := d.Query(ctx, `SELECT u.id, u.name, u.avatar, u.vip, u.prefix, u.intro,
		(u.id = $4) AS is_self,
		EXISTS(SELECT 1 FROM user_follows f2 WHERE f2.follower_id = $4 AND f2.following_id = u.id) AS is_following
		FROM user_follows f JOIN users u ON u.id = f.`+col+`
		WHERE f.`+side+` = $1 ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`,
		userID, pageSize, offset, viewerID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var users []models.UserBrief
	for rows.Next() {
		var u models.UserBrief
		if err := rows.Scan(&u.ID, &u.Name, &u.Avatar, &u.VIP, &u.Prefix, &u.Intro, &u.IsSelf, &u.IsFollowing); err != nil {
			return nil, err
		}
		users = append(users, u)
	}
	return users, rows.Err()
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
