package database

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"yj-forum/server/internal/models"
)

// strVal 解引用可空字符串（nil 视为空串）。
func strVal(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

// ---- 会馆基础 ----

// ListGuilds 会馆列表（id 升序，含成员数与馆长摘要）。
func (d *DB) ListGuilds(ctx context.Context) ([]models.GuildListItem, error) {
	rows, err := d.Query(ctx, `SELECT g.id, g.uuid::text, g.slug, g.name, g.intro, g.theme_color, g.logo_version,
		(COALESCE(g.logo_file_id, '') <> '') AS has_logo,
		(SELECT COUNT(*) FROM guild_members m WHERE m.guild_id = g.id) AS member_count,
		g.created_at,
		u.id, u.name, u.avatar, u.intro
		FROM guilds g LEFT JOIN users u ON u.id = g.leader_user_id
		ORDER BY g.id ASC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	guilds := []models.GuildListItem{}
	for rows.Next() {
		var it models.GuildListItem
		var createdAt *time.Time
		var leaderID, leaderName, leaderAvatar, leaderIntro *string
		if err := rows.Scan(&it.ID, &it.UUID, &it.Slug, &it.Name, &it.Intro, &it.ThemeColor, &it.LogoVersion, &it.HasLogo,
			&it.MemberCount, &createdAt, &leaderID, &leaderName, &leaderAvatar, &leaderIntro); err != nil {
			return nil, err
		}
		it.CreatedAt = createdAt
		if leaderID != nil {
			it.Leader = &models.GuildLeaderInfo{ID: *leaderID, Name: strVal(leaderName),
				Avatar: strVal(leaderAvatar), Intro: strVal(leaderIntro)}
		}
		guilds = append(guilds, it)
	}
	return guilds, rows.Err()
}

// GetGuildBySlug 按 slug 取会馆详情（含馆长、分类、公告）；不存在返回 (nil, nil)。
func (d *DB) GetGuildBySlug(ctx context.Context, slug string) (*models.GuildDetail, error) {
	var det models.GuildDetail
	var leaderID, leaderName, leaderAvatar, leaderIntro *string
	var createdAt, updatedAt *time.Time
	err := d.QueryRow(ctx, `SELECT g.id, g.uuid::text, g.slug, g.name, g.intro, g.logo_file_id, g.logo_version, g.theme_color,
		g.leader_user_id, g.leader_bio, g.created_at, g.updated_at,
		(COALESCE(g.logo_file_id, '') <> '') AS has_logo,
		(SELECT COUNT(*) FROM guild_members m WHERE m.guild_id = g.id) AS member_count,
		u.id, u.name, u.avatar, u.intro
		FROM guilds g LEFT JOIN users u ON u.id = g.leader_user_id
		WHERE g.slug = $1`, slug).
		Scan(&det.ID, &det.UUID, &det.Slug, &det.Name, &det.Intro, &det.LogoFileID, &det.LogoVersion, &det.ThemeColor,
			&det.LeaderUserID, &det.LeaderBio, &createdAt, &updatedAt, &det.HasLogo, &det.MemberCount,
			&leaderID, &leaderName, &leaderAvatar, &leaderIntro)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	det.CreatedAt = createdAt
	det.UpdatedAt = updatedAt
	if leaderID != nil {
		det.Leader = &models.GuildLeaderInfo{ID: *leaderID, Name: strVal(leaderName),
			Avatar: strVal(leaderAvatar), Intro: strVal(leaderIntro), Bio: det.LeaderBio}
	}
	det.Categories, _ = d.ListCategories(ctx, det.ID)
	det.Announcements, _ = d.ListAnnouncements(ctx, det.ID)
	return &det, nil
}

// GetGuildIDByUUID 按会馆 UUID 查数字 id（发帖 guild_uuid 契约用）；不存在返回 (nil, nil)。
func (d *DB) GetGuildIDByUUID(ctx context.Context, uuid string) (*int64, error) {
	var id int64
	err := d.QueryRow(ctx, "SELECT id FROM guilds WHERE uuid = $1", uuid).Scan(&id)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	// 非法 UUID 文本（SQLSTATE 22P02）视同不存在，避免外部输入触发 500
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "22P02" {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &id, nil
}

// ListCategories 会馆分类（sort 升序）。
func (d *DB) ListCategories(ctx context.Context, guildID int64) ([]models.GuildCategory, error) {
	rows, err := d.Query(ctx, `SELECT id, guild_id, name, sort FROM guild_categories
		WHERE guild_id = $1 ORDER BY sort ASC, id ASC`, guildID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	cats := []models.GuildCategory{}
	for rows.Next() {
		var c models.GuildCategory
		if err := rows.Scan(&c.ID, &c.GuildID, &c.Name, &c.Sort); err != nil {
			return nil, err
		}
		cats = append(cats, c)
	}
	return cats, rows.Err()
}

// ListAnnouncements 会馆公告（新→旧）。
func (d *DB) ListAnnouncements(ctx context.Context, guildID int64) ([]models.GuildAnnouncement, error) {
	rows, err := d.Query(ctx, `SELECT id, guild_id, content, created_at, updated_at FROM guild_announcements
		WHERE guild_id = $1 ORDER BY created_at DESC, id DESC`, guildID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	list := []models.GuildAnnouncement{}
	for rows.Next() {
		var a models.GuildAnnouncement
		var createdAt, updatedAt *time.Time
		if err := rows.Scan(&a.ID, &a.GuildID, &a.Content, &createdAt, &updatedAt); err != nil {
			return nil, err
		}
		a.CreatedAt = createdAt
		a.UpdatedAt = updatedAt
		list = append(list, a)
	}
	return list, rows.Err()
}

// ResolveGuildCategory 将会馆自定义分类归一：未配置时用「综合」，不在列表内取第一项。
func (d *DB) ResolveGuildCategory(ctx context.Context, guildID int64, want string) string {
	cats, err := d.ListCategories(ctx, guildID)
	if err != nil || len(cats) == 0 {
		return "综合"
	}
	for _, c := range cats {
		if c.Name == want {
			return want
		}
	}
	return cats[0].Name
}

// ---- 成员关系 ----

// GetUserGuildMembership 用户所在会馆概要（含是否馆长）；未入馆返回 (nil, nil)。
func (d *DB) GetUserGuildMembership(ctx context.Context, userID string) (*models.GuildMembership, error) {
	var m models.GuildMembership
	err := d.QueryRow(ctx, `SELECT g.id, g.uuid::text, g.slug, g.name, g.theme_color,
		(COALESCE(g.leader_user_id, '') = $1) AS is_leader
		FROM guild_members gm JOIN guilds g ON g.id = gm.guild_id
		WHERE gm.user_id = $1`, userID).
		Scan(&m.ID, &m.UUID, &m.Slug, &m.Name, &m.ThemeColor, &m.IsLeader)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &m, nil
}

// GetUserGuildInfo 用户所在会馆完整信息（含是否馆长）；未入馆返回 (nil, false, nil)。
func (d *DB) GetUserGuildInfo(ctx context.Context, userID string) (*models.Guild, bool, error) {
	var g models.Guild
	var isLeader bool
	var createdAt, updatedAt *time.Time
	err := d.QueryRow(ctx, `SELECT g.id, g.slug, g.name, g.intro, g.logo_file_id, g.logo_version, g.theme_color,
		g.leader_user_id, g.leader_bio, g.created_at, g.updated_at,
		(COALESCE(g.leader_user_id, '') = $1) AS is_leader
		FROM guild_members gm JOIN guilds g ON g.id = gm.guild_id
		WHERE gm.user_id = $1`, userID).
		Scan(&g.ID, &g.Slug, &g.Name, &g.Intro, &g.LogoFileID, &g.LogoVersion, &g.ThemeColor,
			&g.LeaderUserID, &g.LeaderBio, &createdAt, &updatedAt, &isLeader)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	g.CreatedAt = createdAt
	g.UpdatedAt = updatedAt
	return &g, isLeader, nil
}

// IsGuildMember 是否为该会馆成员。
func (d *DB) IsGuildMember(ctx context.Context, guildID int64, userID string) bool {
	var n int
	_ = d.QueryRow(ctx, "SELECT COUNT(*) FROM guild_members WHERE guild_id = $1 AND user_id = $2",
		guildID, userID).Scan(&n)
	return n > 0
}

// LeaveGuild 退出会馆，返回是否确为成员。
func (d *DB) LeaveGuild(ctx context.Context, userID string) (bool, error) {
	n, err := d.Exec(ctx, "DELETE FROM guild_members WHERE user_id = $1", userID)
	return n > 0, err
}

// ---- 入馆申请 ----

// GetPendingJoinRequest 该用户对该会馆的待审申请（无则 nil）。
func (d *DB) GetPendingJoinRequest(ctx context.Context, guildID int64, userID string) (*models.GuildJoinRequest, error) {
	var req models.GuildJoinRequest
	var handledAt, createdAt *time.Time
	err := d.QueryRow(ctx, `SELECT id, guild_id, user_id, status, reason, handled_by, handled_at, created_at
		FROM guild_join_requests WHERE guild_id = $1 AND user_id = $2 AND status = 0
		ORDER BY id DESC LIMIT 1`, guildID, userID).
		Scan(&req.ID, &req.GuildID, &req.UserID, &req.Status, &req.Reason, &req.HandledBy, &handledAt, &createdAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	req.HandledAt = handledAt
	req.CreatedAt = createdAt
	return &req, nil
}

// CreateJoinRequest 创建入馆申请（status=0 待审），返回申请 ID。
func (d *DB) CreateJoinRequest(ctx context.Context, guildID int64, userID, reason string) (int64, error) {
	var id int64
	err := d.QueryRow(ctx, `INSERT INTO guild_join_requests (guild_id, user_id, reason) VALUES ($1,$2,$3)
		RETURNING id`, guildID, userID, reason).Scan(&id)
	return id, err
}

// CancelJoinRequest 撤回待审申请（status=3），返回是否撤回成功。
func (d *DB) CancelJoinRequest(ctx context.Context, guildID int64, userID string) (bool, error) {
	n, err := d.Exec(ctx, `UPDATE guild_join_requests SET status = 3
		WHERE guild_id = $1 AND user_id = $2 AND status = 0`, guildID, userID)
	return n > 0, err
}

// ---- 文章 ----

// IncrementArticleViews 文章浏览 +1。
func (d *DB) IncrementArticleViews(ctx context.Context, articleID string) error {
	_, err := d.Exec(ctx, `UPDATE guild_articles SET views = views + 1 WHERE id = $1`, articleID)
	return err
}

// GetArticle 文章详情（含作者、参与人、所属会馆）；不存在返回 (nil, nil)。
func (d *DB) GetArticle(ctx context.Context, articleID string) (*models.GuildArticle, error) {
	var a models.GuildArticle
	var authorID, authorName, authorAvatar *string
	var guildSlug, guildName, guildTheme *string
	var createdAt, updatedAt *time.Time
	err := d.QueryRow(ctx, `SELECT a.id, a.guild_id, a.title, a.summary, a.content, a.author_user_id, a.views,
		a.created_at, a.updated_at,
		author.id, author.name, author.avatar,
		g.slug, g.name, g.theme_color
		FROM guild_articles a
		LEFT JOIN users author ON author.id = a.author_user_id
		LEFT JOIN guilds g ON g.id = a.guild_id
		WHERE a.id = $1`, articleID).
		Scan(&a.ID, &a.GuildID, &a.Title, &a.Summary, &a.Content, &a.AuthorUserID, &a.Views,
			&createdAt, &updatedAt, &authorID, &authorName, &authorAvatar, &guildSlug, &guildName, &guildTheme)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	a.CreatedAt = createdAt
	a.UpdatedAt = updatedAt
	if authorID != nil {
		a.Author = &models.GuildArticleAuthor{ID: *authorID, Name: strVal(authorName), Avatar: strVal(authorAvatar)}
	}
	a.GuildSlug = strVal(guildSlug)
	a.GuildName = strVal(guildName)
	a.GuildThemeColor = strVal(guildTheme)

	rows, err := d.Query(ctx, `SELECT gp.user_id, COALESCE(NULLIF(u.name, ''), gp.user_name), COALESCE(u.avatar, '')
		FROM guild_article_participants gp
		LEFT JOIN users u ON u.id = gp.user_id
		WHERE gp.article_id = $1 ORDER BY gp.user_id ASC`, articleID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	a.Participants = []models.GuildArticleParticipant{}
	for rows.Next() {
		var p models.GuildArticleParticipant
		if err := rows.Scan(&p.UserID, &p.UserName, &p.Avatar); err != nil {
			return nil, err
		}
		a.Participants = append(a.Participants, p)
	}
	return &a, rows.Err()
}

// ---- 信息流 ----

// feedPostSelect 帖子信息流投影（与 feedArticleSelect 列一一对应）。
const feedPostSelect = `SELECT 'post' AS type, p.id, p.title, LEFT(p.content, 200) AS summary, p.category,
	p.likes, p.views, p.created_at, p.updated_at,
	p.user_id, u.name, u.avatar,
	p.guild_id, g.name, g.theme_color,
	COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = p.user_id, false),
	NULL::varchar AS author_id, NULL::varchar AS author_name, NULL::varchar AS author_avatar,
	(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1) AS comment_count,
	0::bigint AS participants_count
	FROM posts p JOIN users u ON u.id = p.user_id LEFT JOIN guilds g ON g.id = p.guild_id
	LEFT JOIN guild_members ugm ON ugm.user_id = p.user_id
	LEFT JOIN guilds ug ON ug.id = ugm.guild_id`

// feedArticleSelect 文章信息流投影（author 为作者摘要，user_id/user_name 兼容帖子字段）。
const feedArticleSelect = `SELECT 'article' AS type, a.id, a.title, a.summary, '' AS category,
	0 AS likes, a.views, a.created_at, a.updated_at,
	COALESCE(a.author_user_id, ''), COALESCE(au.name, ''), COALESCE(au.avatar, ''),
	a.guild_id, g.name, g.theme_color,
	COALESCE(ug.name, ''), COALESCE(ug.theme_color, ''), COALESCE(ug.leader_user_id = a.author_user_id, false),
	COALESCE(au.id, ''), COALESCE(au.name, ''), COALESCE(au.avatar, ''),
	0 AS comment_count,
	(SELECT COUNT(*) FROM guild_article_participants gp WHERE gp.article_id = a.id) AS participants_count
	FROM guild_articles a LEFT JOIN users au ON au.id = a.author_user_id LEFT JOIN guilds g ON g.id = a.guild_id
	LEFT JOIN guild_members ugm ON ugm.user_id = a.author_user_id
	LEFT JOIN guilds ug ON ug.id = ugm.guild_id`

// queryFeed 执行信息流查询：postWhere 为帖子过滤条件，articleWhere 为空串时不含文章。
// 两个分支各自按 created_at 倒序截断 page*pageSize+1 条（+1 用于探测 has_more）后再 UNION ALL，
// 避免对全表排序；外层按 created_at/id 倒序取当页，返回字段与 has_more 语义保持不变。
func (d *DB) queryFeed(ctx context.Context, postWhere string, args []any, articleWhere string, page, pageSize int) ([]models.FeedItem, bool, error) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}
	offset := (page - 1) * pageSize
	branchLimit := offset + pageSize + 1 // 每个分支取到「当页末条的下一条」，保证合并结果精确
	args = append(args, branchLimit, pageSize+1, offset)
	branchLimitParam := "$" + itoa(len(args)-2)
	sqlText := "SELECT * FROM ((" + feedPostSelect + " WHERE " + postWhere +
		" ORDER BY p.created_at DESC, p.id DESC LIMIT " + branchLimitParam + ")"
	if articleWhere != "" {
		sqlText += " UNION ALL (" + feedArticleSelect + " WHERE " + articleWhere +
			" ORDER BY a.created_at DESC, a.id DESC LIMIT " + branchLimitParam + ")"
	}
	sqlText += ") t ORDER BY t.created_at DESC, t.id DESC LIMIT $" + itoa(len(args)-1) + " OFFSET $" + itoa(len(args))

	rows, err := d.Query(ctx, sqlText, args...)
	if err != nil {
		return nil, false, err
	}
	defer rows.Close()
	items := []models.FeedItem{}
	for rows.Next() {
		var it models.FeedItem
		var createdAt, updatedAt *time.Time
		var authorID, authorName, authorAvatar *string
		if err := rows.Scan(&it.Type, &it.ID, &it.Title, &it.Summary, &it.Category, &it.Likes, &it.Views,
			&createdAt, &updatedAt, &it.UserID, &it.UserName, &it.UserAvatar,
			&it.GuildID, &it.GuildName, &it.GuildThemeColor,
			&it.UserGuildName, &it.UserGuildThemeColor, &it.UserIsLeader,
			&authorID, &authorName, &authorAvatar, &it.CommentCount, &it.ParticipantsCount); err != nil {
			return nil, false, err
		}
		it.CreatedAt = createdAt
		it.UpdatedAt = updatedAt
		if authorID != nil {
			it.Author = &models.GuildArticleAuthor{ID: *authorID, Name: strVal(authorName), Avatar: strVal(authorAvatar)}
		}
		items = append(items, it)
	}
	if err := rows.Err(); err != nil {
		return nil, false, err
	}
	hasMore := len(items) > pageSize
	if hasMore {
		items = items[:pageSize]
	}
	return items, hasMore, nil
}

// ListGuildFeed 会馆信息流：帖子 + 文章按时间倒序；category 非空时仅帖子。
func (d *DB) ListGuildFeed(ctx context.Context, guildID int64, page, pageSize int, category string) ([]models.FeedItem, bool, error) {
	postWhere := "p.status = 1 AND p.guild_id = $1"
	args := []any{guildID}
	articleWhere := "a.guild_id = $1"
	if category != "" {
		args = append(args, category)
		postWhere += " AND p.category = $" + itoa(len(args))
		articleWhere = "" // 分类过滤时仅帖子
	}
	return d.queryFeed(ctx, postWhere, args, articleWhere, page, pageSize)
}

// ListGlobalFeed 全站信息流：space=all/public/guild；文章只在 all 或指定会馆时出现。
func (d *DB) ListGlobalFeed(ctx context.Context, space string, guildID int64, category string, page, pageSize int) ([]models.FeedItem, bool, error) {
	postWhere := "p.status = 1"
	articleWhere := ""
	args := []any{}
	switch space {
	case "public":
		postWhere += " AND p.guild_id IS NULL"
	case "guild":
		if guildID > 0 {
			args = append(args, guildID)
			postWhere += " AND p.guild_id = $1"
			articleWhere = "a.guild_id = $1"
		} else {
			// 未指定会馆：列出全部会馆帖子，不含文章
			postWhere += " AND p.guild_id IS NOT NULL"
		}
	default: // all：公共 + 会馆帖子 + 文章
		articleWhere = "TRUE"
	}
	if category != "" {
		args = append(args, category)
		postWhere += " AND p.category = $" + itoa(len(args))
		articleWhere = "" // 分类过滤时仅帖子
	}
	return d.queryFeed(ctx, postWhere, args, articleWhere, page, pageSize)
}
