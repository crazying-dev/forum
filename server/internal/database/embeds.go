package database

import (
	"context"
	"time"

	"yj-forum/server/internal/models"
)

// ---- 引用卡片（embeds）----

// GetEmbedUsers 引用卡片用户（仅未封禁；附所属会馆，无馆时 guild 为 null）。
func (d *DB) GetEmbedUsers(ctx context.Context, ids []string) ([]models.EmbedUser, error) {
	users := []models.EmbedUser{}
	if len(ids) == 0 {
		return users, nil
	}
	rows, err := d.Query(ctx, `SELECT u.id, u.name, COALESCE(u.avatar, ''), COALESCE(u.prefix, ''),
		COALESCE(u.intro, ''), g.name, g.slug, COALESCE(g.theme_color, '')
		FROM users u
		LEFT JOIN guild_members gm ON gm.user_id = u.id
		LEFT JOIN guilds g ON g.id = gm.guild_id
		WHERE u.id = ANY($1::text[]) AND u.is_banned = 0`, ids)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var u models.EmbedUser
		var guildName, guildSlug, guildTheme *string
		if err := rows.Scan(&u.ID, &u.Name, &u.Avatar, &u.Prefix, &u.Intro,
			&guildName, &guildSlug, &guildTheme); err != nil {
			return nil, err
		}
		if guildName != nil {
			u.Guild = &models.EmbedGuild{Name: *guildName, Slug: strVal(guildSlug), ThemeColor: strVal(guildTheme)}
		}
		users = append(users, u)
	}
	return users, rows.Err()
}

// GetEmbedPosts 引用卡片帖子（仅已发布、status=1 且作者未封禁）。
func (d *DB) GetEmbedPosts(ctx context.Context, ids []string) ([]models.EmbedPost, error) {
	posts := []models.EmbedPost{}
	if len(ids) == 0 {
		return posts, nil
	}
	rows, err := d.Query(ctx, `SELECT p.id, p.title, p.user_id, u.name, COALESCE(u.avatar, ''),
		COALESCE(p.category, ''), p.created_at, COALESCE(g.name, '')
		FROM posts p JOIN users u ON u.id = p.user_id
		LEFT JOIN guilds g ON g.id = p.guild_id
		WHERE p.id = ANY($1::text[]) AND p.status = 1 AND p.published_at <= NOW() AND u.is_banned = 0`, ids)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var p models.EmbedPost
		var createdAt *time.Time
		if err := rows.Scan(&p.ID, &p.Title, &p.UserID, &p.UserName, &p.UserAvatar,
			&p.Category, &createdAt, &p.GuildName); err != nil {
			return nil, err
		}
		p.CreatedAt = createdAt
		posts = append(posts, p)
	}
	return posts, rows.Err()
}

// GetEmbedArticles 引用卡片文章（联会馆取 guild_name；不存在的 id 自然省略）。
func (d *DB) GetEmbedArticles(ctx context.Context, ids []string) ([]models.EmbedArticle, error) {
	articles := []models.EmbedArticle{}
	if len(ids) == 0 {
		return articles, nil
	}
	rows, err := d.Query(ctx, `SELECT a.id, a.title, COALESCE(a.author_user_id, ''), COALESCE(au.name, ''),
		COALESCE(au.avatar, ''), a.created_at, COALESCE(g.name, '')
		FROM guild_articles a
		LEFT JOIN users au ON au.id = a.author_user_id
		LEFT JOIN guilds g ON g.id = a.guild_id
		WHERE a.id = ANY($1::text[]) AND a.published_at <= NOW()`, ids)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var a models.EmbedArticle
		var createdAt *time.Time
		if err := rows.Scan(&a.ID, &a.Title, &a.AuthorID, &a.AuthorName, &a.AuthorAvatar,
			&createdAt, &a.GuildName); err != nil {
			return nil, err
		}
		a.CreatedAt = createdAt
		articles = append(articles, a)
	}
	return articles, rows.Err()
}
