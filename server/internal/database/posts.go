package database

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"

	"yj-forum/server/internal/models"
	"yj-forum/server/internal/sanitize"
)

// guildCols 归一化 LEFT JOIN guilds 得到的可空列。
func guildCols(id *int64, name, theme *string) (*int64, string, string) {
	return id, strVal(name), strVal(theme)
}

// formatPublishedAt 发布时间格式化为 RFC3339（空值返回空串）。
func formatPublishedAt(t *time.Time) string {
	if t == nil {
		return ""
	}
	return t.Format(time.RFC3339)
}

// scanPostListItem 扫描一行列表用帖子；列顺序与各查询 SELECT 末尾追加的 published_at 对应。
func scanPostListItem(row interface{ Scan(...any) error }) (models.PostListItem, error) {
	var p models.PostListItem
	var createdAt, publishedAt *time.Time
	var guildID *int64
	var guildName, guildTheme *string
	if err := row.Scan(&p.ID, &p.UserID, &p.Title, &p.Summary, &p.Category, &p.Likes, &p.Views, &createdAt, &p.UserName, &p.UserAvatar, &p.CommentCount,
		&guildID, &guildName, &guildTheme,
		&p.UserGuildName, &p.UserGuildThemeColor, &p.UserIsLeader,
		&publishedAt); err != nil {
		return p, err
	}
	p.CreatedAt = createdAt
	p.PublishedAt = formatPublishedAt(publishedAt)
	p.GuildID, p.GuildName, p.GuildThemeColor = guildCols(guildID, guildName, guildTheme)
	return p, nil
}

// postSummaryExpr 帖子摘要投影：html 正文先剥离标签再截断，历史 markdown 保持原样。
const postSummaryExpr = `CASE WHEN p.content_format = 'html' THEN LEFT(regexp_replace(p.content, '<[^>]+>', '', 'g'), 200) ELSE LEFT(p.content, 200) END`

// GetPostList 分页帖子列表（对齐 legacy get_post_list）。
func (d *DB) GetPostList(ctx context.Context, page, pageSize int, category string) ([]models.PostListItem, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	base := `SELECT p.id, p.user_id, p.title, ` + postSummaryExpr + `, p.category, p.likes, p.views,
	       p.created_at, u.name, u.avatar,
	       (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
	       p.guild_id, g.name, g.theme_color,
	       COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false),
	       p.published_at
	FROM posts p JOIN users u ON p.user_id = u.id LEFT JOIN guilds g ON g.id = p.guild_id
	LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
	LEFT JOIN guilds ug ON ug.id = ugm.guild_id
	WHERE p.status = 1 AND p.published_at <= NOW()`
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
		p, err := scanPostListItem(rows)
		if err != nil {
			return nil, err
		}
		posts = append(posts, p)
	}
	return posts, rows.Err()
}

// ---- 引用选择器默认项 ----

// pickerPostCols 引用选择器帖子投影（与列表一致的 PostListItem 字段顺序）。
const pickerPostCols = `SELECT p.id, p.user_id, p.title, ` + postSummaryExpr + `, p.category, p.likes, p.views,
	p.created_at, u.name, u.avatar,
	(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
	p.guild_id, g.name, g.theme_color,
	COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false),
	p.published_at
	FROM posts p JOIN users u ON p.user_id = u.id
	LEFT JOIN guilds g ON g.id = p.guild_id
	LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
	LEFT JOIN guilds ug ON ug.id = ugm.guild_id`

// queryPostListItems 执行 PostListItem 列表查询并扫描。
func (d *DB) queryPostListItems(ctx context.Context, sqlQ string, args ...any) ([]models.PostListItem, error) {
	rows, err := d.Query(ctx, sqlQ, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	posts := []models.PostListItem{}
	for rows.Next() {
		p, err := scanPostListItem(rows)
		if err != nil {
			return nil, err
		}
		posts = append(posts, p)
	}
	return posts, rows.Err()
}

// GetPickerDefaultPosts 引用选择器默认项：我关注的帖子与我收藏的帖子（各至多 20 条）。
// 该数据依赖 viewer（userID），不得使用不含 viewer 的共享缓存。
func (d *DB) GetPickerDefaultPosts(ctx context.Context, userID string) ([]models.PostListItem, []models.PostListItem, error) {
	following, err := d.queryPostListItems(ctx, pickerPostCols+`
		WHERE p.status = 1 AND u.is_banned = 0 AND p.published_at <= NOW()
		AND p.user_id IN (SELECT following_id FROM user_follows WHERE follower_id = $1)
		ORDER BY p.created_at DESC LIMIT 20`, userID)
	if err != nil {
		return nil, nil, err
	}
	favorites, err := d.queryPostListItems(ctx, pickerPostCols+`
		JOIN post_favorites f ON f.post_id = p.id
		WHERE f.user_id = $1 AND p.status = 1 AND u.is_banned = 0 AND p.published_at <= NOW()
		ORDER BY f.created_at DESC LIMIT 20`, userID)
	if err != nil {
		return nil, nil, err
	}
	return following, favorites, nil
}

// GetRandomPosts 随机最多 200 条（对齐 legacy get_random_posts）。
func (d *DB) GetRandomPosts(ctx context.Context, limit int) ([]models.PostListItem, error) {
	if limit < 1 || limit > 200 {
		limit = 200
	}
	rows, err := d.Query(ctx, `SELECT p.id, p.user_id, p.title, `+postSummaryExpr+`, p.category, p.likes, p.views,
		p.created_at, u.name, u.avatar,
		(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
		p.guild_id, g.name, g.theme_color,
		COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false),
		p.published_at
		FROM posts p JOIN users u ON p.user_id = u.id LEFT JOIN guilds g ON g.id = p.guild_id
		LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
		LEFT JOIN guilds ug ON ug.id = ugm.guild_id
		WHERE p.status = 1 AND p.published_at <= NOW() ORDER BY RANDOM() LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var posts []models.PostListItem
	for rows.Next() {
		p, err := scanPostListItem(rows)
		if err != nil {
			return nil, err
		}
		posts = append(posts, p)
	}
	return posts, rows.Err()
}

// GetPost 帖子详情（JOIN 用户与所属会馆）。
func (d *DB) GetPost(ctx context.Context, postID string) (*models.Post, error) {
	row := d.QueryRow(ctx, `SELECT p.id, p.user_id, p.title, p.content, p.content_format, p.category, p.likes, p.views, p.status,
		p.created_at, p.updated_at, u.name, u.avatar, p.guild_id, g.name, g.theme_color,
		COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false),
		p.published_at
		FROM posts p JOIN users u ON p.user_id = u.id LEFT JOIN guilds g ON g.id = p.guild_id
		LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
		LEFT JOIN guilds ug ON ug.id = ugm.guild_id
		WHERE p.id = $1`, postID)
	var p models.Post
	var createdAt, updatedAt, publishedAt *time.Time
	var guildID *int64
	var guildName, guildTheme *string
	err := row.Scan(&p.ID, &p.UserID, &p.Title, &p.Content, &p.ContentFormat, &p.Category, &p.Likes, &p.Views, &p.Status,
		&createdAt, &updatedAt, &p.UserName, &p.UserAvatar, &guildID, &guildName, &guildTheme,
		&p.UserGuildName, &p.UserGuildThemeColor, &p.UserIsLeader,
		&publishedAt)
	if err != nil {
		return nil, err
	}
	p.CreatedAt = createdAt
	p.UpdatedAt = updatedAt
	p.PublishedAt = publishedAt
	p.GuildID, p.GuildName, p.GuildThemeColor = guildCols(guildID, guildName, guildTheme)
	return &p, nil
}

// GetPostPublishInfo 帖子发布状态（作者 + 发布时间 + 状态）；不存在时 exists 为 false。
// 供点赞/收藏/举报/评论等路径判断「软删/定时未发布」可见性（与 Detail 行为一致）。
func (d *DB) GetPostPublishInfo(ctx context.Context, postID string) (authorID string, publishedAt time.Time, status int, exists bool, err error) {
	err = d.QueryRow(ctx, `SELECT user_id, published_at, status FROM posts WHERE id = $1`, postID).Scan(&authorID, &publishedAt, &status)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", time.Time{}, 0, false, nil
	}
	if err != nil {
		return "", time.Time{}, 0, false, err
	}
	return authorID, publishedAt, status, true, nil
}

// PendingPublishPost 待补发通知的定时帖（id/作者/标题）。
type PendingPublishPost struct {
	ID     string
	UserID string
	Title  string
}

// ClaimPendingPublishPosts 原子认领到点未通知的定时帖（每次至多 50 条）并置 publish_notified=TRUE，
// 返回认领行供调用方补发粉丝通知；重复调用不会重复认领。
func (d *DB) ClaimPendingPublishPosts(ctx context.Context) ([]PendingPublishPost, error) {
	rows, err := d.Query(ctx, `UPDATE posts SET publish_notified = TRUE WHERE id IN (
		SELECT id FROM posts WHERE status = 1 AND publish_notified = FALSE AND published_at <= NOW()
		ORDER BY published_at LIMIT 50
	) RETURNING id, user_id, title`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	pending := []PendingPublishPost{}
	for rows.Next() {
		var p PendingPublishPost
		if err := rows.Scan(&p.ID, &p.UserID, &p.Title); err != nil {
			return nil, err
		}
		pending = append(pending, p)
	}
	return pending, rows.Err()
}

// SendPost 发帖（guildID 非空时归属该会馆）；新帖正文一律按富文本（html）存储。
// publishedAt 为 nil 表示立即发布（published_at=NOW() 且 publish_notified=TRUE）；
// 非 nil 为定时发布时间，写入后 publish_notified=FALSE，由定时任务到点补发粉丝通知。
func (d *DB) SendPost(ctx context.Context, userID, title, content, category string, guildID *int64, publishedAt *time.Time) (string, error) {
	if category == "" {
		category = "general"
	}
	postID := GenID("PS")
	notified := publishedAt == nil // 立即帖创建即视为已通知；定时帖待补偿任务置 TRUE
	_, err := d.Exec(ctx, `INSERT INTO posts (id, user_id, title, content, content_format, category, guild_id, published_at, publish_notified)
		VALUES ($1,$2,$3,$4,'html',$5,$6,COALESCE($7, NOW()),$8)`,
		postID, userID, title, sanitize.SanitizeRichContent(content), category, guildID, publishedAt, notified)
	if err != nil {
		return "", err
	}
	return postID, nil
}

// GetUserPosts 用户帖子列表（viewer 为本人时不过滤未来定时帖；其他视角仅见已发布）。
func (d *DB) GetUserPosts(ctx context.Context, userID, viewer string, page, pageSize int) ([]models.PostListItem, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	where := "WHERE p.user_id = $1 AND p.status = 1"
	if viewer != userID {
		where += " AND p.published_at <= NOW()"
	}
	return d.queryPostListItems(ctx, `SELECT p.id, p.user_id, p.title, `+postSummaryExpr+`, p.category, p.likes, p.views,
		p.created_at, u.name, u.avatar,
		(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
		p.guild_id, g.name, g.theme_color,
		COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false),
		p.published_at
		FROM posts p JOIN users u ON u.id = p.user_id LEFT JOIN guilds g ON g.id = p.guild_id
		LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
		LEFT JOIN guilds ug ON ug.id = ugm.guild_id
		`+where+` ORDER BY p.created_at DESC LIMIT $2 OFFSET $3`,
		userID, pageSize, offset)
}

// GetUserStats 用户统计（不含未到发布时间的定时帖）。
func (d *DB) GetUserStats(ctx context.Context, userID string) (models.Stats, error) {
	var s models.Stats
	err := d.QueryRow(ctx, `SELECT COUNT(*), COALESCE(SUM(likes),0), COALESCE(SUM(views),0)
		FROM posts WHERE user_id = $1 AND status = 1 AND published_at <= NOW()`, userID).Scan(&s.PostCount, &s.TotalLikes, &s.TotalViews)
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
