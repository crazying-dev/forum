package database

import (
	"context"
	"time"

	"yj-forum/server/internal/models"
)

// guildCols 归一化 LEFT JOIN guilds 得到的可空列。
func guildCols(id *int64, name, theme *string) (*int64, string, string) {
	return id, strVal(name), strVal(theme)
}

// GetPostList 分页帖子列表（对齐 legacy get_post_list）。
func (d *DB) GetPostList(ctx context.Context, page, pageSize int, category string) ([]models.PostListItem, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	base := `SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views,
	       p.created_at, u.name, u.avatar,
	       (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
	       p.guild_id, g.name, g.theme_color,
	       COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false)
	FROM posts p JOIN users u ON p.user_id = u.id LEFT JOIN guilds g ON g.id = p.guild_id
	LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
	LEFT JOIN guilds ug ON ug.id = ugm.guild_id
	WHERE p.status = 1`
	args := []any{}
	if category != "" {
		base += " AND p.category = $1"
		args = append(args, category)
	}
	base += " ORDER BY p.created_at DESC LIMIT $" + itoa(len(args)+1) + " OFFSET $" + itoa(len(args)+2)
	args = append(args, pageSize, offset)

	rows, err := d.Query(ctx, base, args...)
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
			&guildID, &guildName, &guildTheme,
			&p.UserGuildName, &p.UserGuildThemeColor, &p.UserIsLeader); err != nil {
			return nil, err
		}
		p.CreatedAt = createdAt
		p.GuildID, p.GuildName, p.GuildThemeColor = guildCols(guildID, guildName, guildTheme)
		posts = append(posts, p)
	}
	return posts, rows.Err()
}

// GetRandomPosts 随机最多 200 条（对齐 legacy get_random_posts）。
func (d *DB) GetRandomPosts(ctx context.Context, limit int) ([]models.PostListItem, error) {
	if limit < 1 || limit > 200 {
		limit = 200
	}
	rows, err := d.Query(ctx, `SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views,
		p.created_at, u.name, u.avatar,
		(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
		p.guild_id, g.name, g.theme_color,
		COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false)
		FROM posts p JOIN users u ON p.user_id = u.id LEFT JOIN guilds g ON g.id = p.guild_id
		LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
		LEFT JOIN guilds ug ON ug.id = ugm.guild_id
		WHERE p.status = 1 ORDER BY RANDOM() LIMIT $1`, limit)
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
			&guildID, &guildName, &guildTheme,
			&p.UserGuildName, &p.UserGuildThemeColor, &p.UserIsLeader); err != nil {
			return nil, err
		}
		p.CreatedAt = createdAt
		p.GuildID, p.GuildName, p.GuildThemeColor = guildCols(guildID, guildName, guildTheme)
		posts = append(posts, p)
	}
	return posts, rows.Err()
}

// GetPost 帖子详情（JOIN 用户与所属会馆）。
func (d *DB) GetPost(ctx context.Context, postID string) (*models.Post, error) {
	row := d.QueryRow(ctx, `SELECT p.id, p.user_id, p.title, p.content, p.category, p.likes, p.views, p.status,
		p.created_at, p.updated_at, u.name, u.avatar, p.guild_id, g.name, g.theme_color,
		COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false)
		FROM posts p JOIN users u ON p.user_id = u.id LEFT JOIN guilds g ON g.id = p.guild_id
		LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
		LEFT JOIN guilds ug ON ug.id = ugm.guild_id
		WHERE p.id = $1`, postID)
	var p models.Post
	var createdAt, updatedAt *time.Time
	var guildID *int64
	var guildName, guildTheme *string
	err := row.Scan(&p.ID, &p.UserID, &p.Title, &p.Content, &p.Category, &p.Likes, &p.Views, &p.Status,
		&createdAt, &updatedAt, &p.UserName, &p.UserAvatar, &guildID, &guildName, &guildTheme,
		&p.UserGuildName, &p.UserGuildThemeColor, &p.UserIsLeader)
	if err != nil {
		return nil, err
	}
	p.CreatedAt = createdAt
	p.UpdatedAt = updatedAt
	p.GuildID, p.GuildName, p.GuildThemeColor = guildCols(guildID, guildName, guildTheme)
	return &p, nil
}

// SendPost 发帖（guildID 非空时归属该会馆）。
func (d *DB) SendPost(ctx context.Context, userID, title, content, category string, guildID *int64) (string, error) {
	if category == "" {
		category = "general"
	}
	postID := GenID("PS")
	_, err := d.Exec(ctx, `INSERT INTO posts (id, user_id, title, content, category, guild_id) VALUES ($1,$2,$3,$4,$5,$6)`,
		postID, userID, title, SafeHTML(content), category, guildID)
	if err != nil {
		return "", err
	}
	return postID, nil
}

// GetUserPosts 用户帖子列表。
func (d *DB) GetUserPosts(ctx context.Context, userID string, page, pageSize int) ([]models.PostListItem, error) {
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
		p.guild_id, g.name, g.theme_color,
		COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false)
		FROM posts p JOIN users u ON p.user_id = u.id LEFT JOIN guilds g ON g.id = p.guild_id
		LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
		LEFT JOIN guilds ug ON ug.id = ugm.guild_id
		WHERE p.user_id = $1 AND p.status = 1 ORDER BY p.created_at DESC LIMIT $2 OFFSET $3`,
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
			&guildID, &guildName, &guildTheme,
			&p.UserGuildName, &p.UserGuildThemeColor, &p.UserIsLeader); err != nil {
			return nil, err
		}
		p.CreatedAt = createdAt
		p.GuildID, p.GuildName, p.GuildThemeColor = guildCols(guildID, guildName, guildTheme)
		posts = append(posts, p)
	}
	return posts, rows.Err()
}

// GetUserStats 用户统计。
func (d *DB) GetUserStats(ctx context.Context, userID string) (models.Stats, error) {
	var s models.Stats
	err := d.QueryRow(ctx, `SELECT COUNT(*), COALESCE(SUM(likes),0), COALESCE(SUM(views),0)
		FROM posts WHERE user_id = $1 AND status = 1`, userID).Scan(&s.PostCount, &s.TotalLikes, &s.TotalViews)
	return s, err
}

// IncrementPostViews 浏览 +1。
func (d *DB) IncrementPostViews(ctx context.Context, postID string) error {
	_, err := d.Exec(ctx, `UPDATE posts SET views = views + 1 WHERE id = $1`, postID)
	return err
}

// DeletePost 删除（仅作者，软删 status=0）。
func (d *DB) DeletePost(ctx context.Context, postID, userID string) (bool, error) {
	tag, err := d.Exec(ctx, `UPDATE posts SET status = 0 WHERE id = $1 AND user_id = $2`, postID, userID)
	return tag > 0, err
}

// itoa 简易 int -> string。
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
