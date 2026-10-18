// Package legacy 实现旧 APP 兼容层的数据服务与 HTML→Markdown 转换。
package legacy

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/models"
)

// 兼容层对外错误（handler 据此映射 HTTP 状态码）。
var (
	ErrUserNotFound    = errors.New("用户不存在")
	ErrPostNotFound    = errors.New("帖子不存在")
	ErrCommentNotFound = errors.New("评论不存在")
	ErrWorldTooFast    = errors.New("发言太快，请稍后再试")
	ErrSearchTooShort  = errors.New("关键词至少2个字符")
)

// Service 旧 APP 兼容层数据服务。
type Service struct {
	DB       *database.DB
	Cfg      *config.Config
	Sessions *auth.SessionManager
	Verifier *TokenVerifier
	Releases *ReleaseProvider

	mu            sync.Mutex
	lastWorldSend map[string]time.Time

	HuiguanPaths   []string
	EasterEggPaths []string
}

// NewService 创建兼容层服务；cfg 可为 nil（仅测试场景）。
func NewService(db *database.DB, cfg *config.Config, sessions *auth.SessionManager) *Service {
	s := &Service{
		DB: db, Cfg: cfg, Sessions: sessions,
		lastWorldSend: map[string]time.Time{},
		HuiguanPaths: []string{
			os.Getenv("HUIGUAN_PATH"),
			"huiguan.json",
			"forum-legacy/huiguan.json",
			"../forum-legacy/huiguan.json",
			"../../forum-legacy/huiguan.json",
		},
	}
	if cfg != nil {
		s.Verifier = NewTokenVerifier(cfg.SecretKey, cfg.LegacyTokenTTL, cfg.LegacyTokenNotBefore)
		s.Releases = NewReleaseProvider(cfg.GitHubToken)
		s.EasterEggPaths = []string{
			cfg.EasterEggPath,
			"EasterEgg/1.json",
			"forum-legacy/EasterEgg/1.json",
			"../forum-legacy/EasterEgg/1.json",
			"../../forum-legacy/EasterEgg/1.json",
		}
	} else {
		s.Verifier = NewTokenVerifier("", 0, time.Time{})
		s.Releases = NewReleaseProvider("")
		s.EasterEggPaths = []string{"EasterEgg/1.json", "forum-legacy/EasterEgg/1.json", "../forum-legacy/EasterEgg/1.json"}
	}
	return s
}

// ---- 用户 ----

// LegacyUser users 表在兼容层需要的完整字段（含密码/封禁/注销/改密时间）。
type LegacyUser struct {
	ID                string
	Name              string
	Avatar            string
	Email             string
	Gender            int
	Age               string
	Intro             string
	Prefix            string
	IsBanned          int
	EmailVerified     int
	CreatedAt         *time.Time
	LastLogin         *time.Time
	Password          string
	DeletedAt         *time.Time
	PasswordChangedAt *time.Time
}

const legacyUserCols = `id, COALESCE(name, ''), COALESCE(avatar, ''), COALESCE(email, ''), COALESCE(gender, 0), COALESCE(age, ''), COALESCE(intro, ''), COALESCE(prefix, ''), is_banned, email_verified, created_at, last_login, COALESCE(password, ''), deleted_at, password_changed_at`

func scanLegacyUser(row interface{ Scan(...any) error }) (*LegacyUser, error) {
	var u LegacyUser
	if err := row.Scan(&u.ID, &u.Name, &u.Avatar, &u.Email, &u.Gender, &u.Age, &u.Intro, &u.Prefix,
		&u.IsBanned, &u.EmailVerified, &u.CreatedAt, &u.LastLogin, &u.Password, &u.DeletedAt, &u.PasswordChangedAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}
	return &u, nil
}

// LoadUserForLegacy 按 ID 加载兼容层用户（不过滤封禁/注销，由调用方判定）。
func (s *Service) LoadUserForLegacy(ctx context.Context, id string) (*LegacyUser, error) {
	if s.DB == nil || strings.TrimSpace(id) == "" {
		return nil, ErrUserNotFound
	}
	return scanLegacyUser(s.DB.QueryRow(ctx, "SELECT "+legacyUserCols+" FROM users WHERE id=$1", strings.TrimSpace(id)))
}

// LoadUserByIdentifier 登录用：按用户名或邮箱查找。
func (s *Service) LoadUserByIdentifier(ctx context.Context, identifier string) (*LegacyUser, error) {
	identifier = strings.TrimSpace(identifier)
	if s.DB == nil || identifier == "" {
		return nil, ErrUserNotFound
	}
	if strings.Contains(identifier, "@") {
		return scanLegacyUser(s.DB.QueryRow(ctx, "SELECT "+legacyUserCols+" FROM users WHERE email=$1", strings.ToLower(identifier)))
	}
	u, err := scanLegacyUser(s.DB.QueryRow(ctx, "SELECT "+legacyUserCols+" FROM users WHERE name=$1", identifier))
	if err == nil {
		return u, nil
	}
	if !errors.Is(err, ErrUserNotFound) {
		return nil, err
	}
	// 旧格式用户名兼容（与 handler/auth.go 保持一致）。
	legacyName := strings.ReplaceAll(identifier, "[TIME]", `<p class="TimeWithUserNameAPI"></p>`)
	if legacyName == identifier {
		return nil, ErrUserNotFound
	}
	return scanLegacyUser(s.DB.QueryRow(ctx, "SELECT "+legacyUserCols+" FROM users WHERE name=$1", legacyName))
}

// PublicMap 兼容层用户 JSON（self 为 true 时包含 email；vip 字段按实际表恒为 "0"）。
func (u *LegacyUser) PublicMap(self bool) map[string]any {
	m := map[string]any{
		"id":             u.ID,
		"name":           u.Name,
		"avatar":         u.Avatar,
		"gender":         u.Gender,
		"age":            u.Age,
		"intro":          u.Intro,
		"vip":            "0",
		"email_verified": u.EmailVerified,
		"created_at":     u.CreatedAt,
		"last_login":     u.LastLogin,
	}
	if self {
		m["email"] = u.Email
	}
	return m
}

// ProfileResult 用户资料聚合。
type ProfileResult struct {
	User        *LegacyUser
	Stats       models.Stats
	FollowStats models.FollowStats
	IsFollowing bool
	IsSelf      bool
}

// Profile 公开资料 + 统计（viewerID 为空表示匿名）。
func (s *Service) Profile(ctx context.Context, id, viewerID string) (*ProfileResult, error) {
	u, err := s.LoadUserForLegacy(ctx, id)
	if err != nil {
		return nil, err
	}
	stats, _ := s.DB.GetUserStats(ctx, id)
	followStats, _ := s.DB.GetFollowStats(ctx, id)
	isSelf := viewerID != "" && viewerID == id
	isFollowing := false
	if viewerID != "" && !isSelf {
		isFollowing = s.DB.IsFollowing(ctx, viewerID, id)
	}
	return &ProfileResult{User: u, Stats: stats, FollowStats: followStats, IsFollowing: isFollowing, IsSelf: isSelf}, nil
}

// ---- 帖子 ----

// PostListItem 旧 APP 帖子列表项。
type PostListItem struct {
	ID           string     `json:"id"`
	UserID       string     `json:"user_id"`
	Title        string     `json:"title"`
	Summary      string     `json:"summary"`
	Category     string     `json:"category"`
	Likes        int        `json:"likes"`
	Views        int        `json:"views"`
	CommentCount int        `json:"comment_count"`
	CreatedAt    *time.Time `json:"created_at"`
	UserName     string     `json:"user_name"`
	UserAvatar   string     `json:"user_avatar"`
}

// PostDetail 旧 APP 帖子详情。
type PostDetail struct {
	ID           string     `json:"id"`
	UserID       string     `json:"user_id"`
	Title        string     `json:"title"`
	Content      string     `json:"content"`
	Category     string     `json:"category"`
	Likes        int        `json:"likes"`
	Views        int        `json:"views"`
	CommentCount int        `json:"comment_count"`
	Status       int        `json:"status"`
	CreatedAt    *time.Time `json:"created_at"`
	UpdatedAt    *time.Time `json:"updated_at"`
	UserName     string     `json:"user_name"`
	UserAvatar   string     `json:"user_avatar"`
}

// Comment 旧 APP 评论。
type Comment struct {
	ID         string     `json:"id"`
	UserID     string     `json:"user_id"`
	Content    string     `json:"content"`
	ParentID   *string    `json:"parent_id"`
	Likes      int        `json:"likes"`
	Liked      bool       `json:"liked"`
	CreatedAt  *time.Time `json:"created_at"`
	UserName   string     `json:"user_name"`
	UserAvatar string     `json:"user_avatar"`
}

const legacyPostSelect = `SELECT p.id, p.user_id, p.title, p.content, p.content_format, p.category, p.likes, p.views,
	p.created_at, COALESCE(u.name, ''), COALESCE(u.avatar, ''),
	(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.status = 1)
	FROM posts p JOIN users u ON u.id = p.user_id`

type scannedPost struct {
	PostListItem
	content       string
	contentFormat string
}

func scanPostListItem(row interface{ Scan(...any) error }) (scannedPost, error) {
	var p scannedPost
	err := row.Scan(&p.ID, &p.UserID, &p.Title, &p.content, &p.contentFormat, &p.Category, &p.Likes, &p.Views,
		&p.CreatedAt, &p.UserName, &p.UserAvatar, &p.CommentCount)
	return p, err
}

func (p scannedPost) legacyItem() PostListItem {
	summary := p.content
	if p.contentFormat == "html" {
		summary = HTMLToMarkdown(p.content)
	}
	item := p.PostListItem
	item.Summary = truncateRunes(strings.TrimSpace(summary), 200)
	return item
}

func normalizePage(page, pageSize, defaultSize, maxSize int) (int, int) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > maxSize {
		pageSize = defaultSize
	}
	return page, pageSize
}

// PostList 帖子列表（page/page_size/category/sort）。
func (s *Service) PostList(ctx context.Context, page, pageSize int, category, sort string) ([]PostListItem, error) {
	page, pageSize = normalizePage(page, pageSize, 20, 100)
	order := "ORDER BY p.created_at DESC"
	switch sort {
	case "comprehensive":
		order = "ORDER BY (p.likes * 3 + p.views) DESC, p.created_at DESC"
	case "random":
		order = "ORDER BY RANDOM()"
	}
	where := "WHERE p.status = 1 AND p.published_at <= NOW()"
	args := []any{}
	if category = strings.TrimSpace(category); category != "" {
		args = append(args, category)
		where += fmt.Sprintf(" AND p.category = $%d", len(args))
	}
	args = append(args, pageSize, (page-1)*pageSize)
	sqlQ := legacyPostSelect + " " + where + " " + order + fmt.Sprintf(" LIMIT $%d OFFSET $%d", len(args)-1, len(args))
	return s.queryPosts(ctx, sqlQ, args...)
}

// RandomPosts 随机帖子（最多 200）。
func (s *Service) RandomPosts(ctx context.Context, limit int) ([]PostListItem, error) {
	if limit < 1 || limit > 200 {
		limit = 200
	}
	return s.queryPosts(ctx, legacyPostSelect+" WHERE p.status = 1 AND p.published_at <= NOW() ORDER BY RANDOM() LIMIT $1", limit)
}

// UserPosts 指定用户的帖子（viewer 为作者时可见定时未发布帖）。
func (s *Service) UserPosts(ctx context.Context, userID, viewerID string, page, pageSize int) ([]PostListItem, error) {
	page, pageSize = normalizePage(page, pageSize, 20, 100)
	where := "WHERE p.user_id = $1 AND p.status = 1"
	if viewerID != userID {
		where += " AND p.published_at <= NOW()"
	}
	return s.queryPosts(ctx, legacyPostSelect+" "+where+fmt.Sprintf(" ORDER BY p.created_at DESC LIMIT $2 OFFSET $3"), userID, pageSize, (page-1)*pageSize)
}

// UserFavorites 用户收藏（仅已发布）。
func (s *Service) UserFavorites(ctx context.Context, userID string, page, pageSize int) ([]PostListItem, error) {
	page, pageSize = normalizePage(page, pageSize, 20, 100)
	return s.queryPosts(ctx, legacyPostSelect+` JOIN post_favorites f ON f.post_id = p.id
		WHERE f.user_id = $1 AND p.status = 1 AND p.published_at <= NOW()
		ORDER BY f.created_at DESC LIMIT $2 OFFSET $3`, userID, pageSize, (page-1)*pageSize)
}

func (s *Service) queryPosts(ctx context.Context, sqlQ string, args ...any) ([]PostListItem, error) {
	rows, err := s.DB.Query(ctx, sqlQ, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []PostListItem{}
	for rows.Next() {
		p, err := scanPostListItem(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, p.legacyItem())
	}
	return items, rows.Err()
}

// Detail 帖子详情 + 前 50 条评论 + liked/favorited 状态。
func (s *Service) Detail(ctx context.Context, postID, viewerID string) (*PostDetail, []Comment, bool, bool, error) {
	post, err := s.DB.GetPost(ctx, postID)
	if err != nil || post == nil || post.Status != 1 {
		return nil, nil, false, false, ErrPostNotFound
	}
	if post.PublishedAt != nil && post.PublishedAt.After(time.Now()) && post.UserID != viewerID {
		return nil, nil, false, false, ErrPostNotFound
	}
	content := post.Content
	if post.ContentFormat == "html" {
		content = HTMLToMarkdown(post.Content)
	}
	var commentCount int
	_ = s.DB.QueryRow(ctx, "SELECT COUNT(*) FROM comments WHERE post_id=$1 AND status=1", postID).Scan(&commentCount)
	if viewerID != "" {
		if err := s.DB.IncrementPostViews(ctx, postID); err == nil {
			post.Views++
		}
	}
	comments, err := s.CommentList(ctx, postID, 1, 50, viewerID)
	if err != nil {
		return nil, nil, false, false, err
	}
	liked, favorited := false, false
	if viewerID != "" {
		liked = s.DB.HasLikedPost(ctx, postID, viewerID)
		favorited = s.DB.HasFavoritedPost(ctx, postID, viewerID)
	}
	detail := &PostDetail{
		ID: post.ID, UserID: post.UserID, Title: post.Title, Content: content,
		Category: post.Category, Likes: post.Likes, Views: post.Views, CommentCount: commentCount,
		Status: post.Status, CreatedAt: post.CreatedAt, UpdatedAt: post.UpdatedAt,
		UserName: post.UserName, UserAvatar: post.UserAvatar,
	}
	return detail, comments, liked, favorited, nil
}

// CreatePost 旧 APP 发帖：正文按 markdown 原样入库，不做 HTML 净化/包裹。
func (s *Service) CreatePost(ctx context.Context, userID, title, content, category string) (string, error) {
	title = strings.TrimSpace(title)
	content = strings.TrimSpace(content)
	category = strings.TrimSpace(category)
	allowed := map[string]bool{"general": true, "talk": true, "question": true, "share": true, "creative": true}
	if !allowed[category] {
		category = "general"
	}
	id := database.GenID("PS")
	_, err := s.DB.Exec(ctx, `INSERT INTO posts (id, user_id, title, content, content_format, category, published_at, publish_notified)
		VALUES ($1,$2,$3,$4,'markdown',$5,NOW(),TRUE)`, id, userID, title, content, category)
	return id, err
}

// ---- 评论 ----

// CommentList 帖子评论（时间倒序，最多 100/页）。
func (s *Service) CommentList(ctx context.Context, postID string, page, pageSize int, viewerID string) ([]Comment, error) {
	page, pageSize = normalizePage(page, pageSize, 50, 100)
	rows, err := s.DB.Query(ctx, `SELECT c.id, c.user_id, c.content, c.content_format, c.parent_id, c.likes, c.created_at,
		COALESCE(u.name, ''), COALESCE(u.avatar, '')
		FROM comments c JOIN users u ON u.id = c.user_id
		WHERE c.post_id = $1 AND c.status = 1 ORDER BY c.created_at DESC LIMIT $2 OFFSET $3`,
		postID, pageSize, (page-1)*pageSize)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []Comment{}
	for rows.Next() {
		var c Comment
		var content, format string
		if err := rows.Scan(&c.ID, &c.UserID, &content, &format, &c.ParentID, &c.Likes, &c.CreatedAt, &c.UserName, &c.UserAvatar); err != nil {
			return nil, err
		}
		if format == "html" {
			content = HTMLToMarkdown(content)
		}
		c.Content = content
		items = append(items, c)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if viewerID != "" && len(items) > 0 {
		ids := make([]string, len(items))
		for i := range items {
			ids[i] = items[i].ID
		}
		if liked, err := s.DB.GetLikedCommentIDs(ctx, viewerID, ids); err == nil {
			for i := range items {
				items[i].Liked = liked[items[i].ID]
			}
		}
	}
	return items, nil
}

// CreateComment 旧 APP 发评论：正文按 markdown 原样入库。
func (s *Service) CreateComment(ctx context.Context, postID, userID, content string, parentID *string) (*Comment, error) {
	content = strings.TrimSpace(content)
	if parentID != nil && strings.TrimSpace(*parentID) == "" {
		parentID = nil
	}
	if parentID != nil {
		parentPostID, parentStatus, err := s.DB.GetCommentPostAndStatus(ctx, *parentID)
		if err != nil || parentPostID != postID || parentStatus != 1 {
			return nil, ErrCommentNotFound
		}
	}
	created, err := s.DB.AddComment(ctx, postID, userID, content, "markdown", parentID)
	if err != nil {
		return nil, err
	}
	return &Comment{
		ID: created.ID, UserID: created.UserID, Content: created.Content, ParentID: created.ParentID,
		Likes: created.Likes, CreatedAt: created.CreatedAt, UserName: created.UserName, UserAvatar: created.UserAvatar,
	}, nil
}

// ---- 用户社交 ----

// FollowUser 关注列表项。
type FollowUser struct {
	ID          string     `json:"id"`
	Name        string     `json:"name"`
	Avatar      string     `json:"avatar"`
	VIP         string     `json:"vip"`
	Intro       string     `json:"intro"`
	FollowedAt  *time.Time `json:"followed_at"`
	IsFollowing bool       `json:"is_following"`
	IsSelf      bool       `json:"is_self"`
}

// Following 用户关注列表。
func (s *Service) Following(ctx context.Context, userID, viewerID string, page, pageSize int) ([]FollowUser, error) {
	return s.followList(ctx, "follower_id", userID, viewerID, page, pageSize)
}

// Followers 用户粉丝列表。
func (s *Service) Followers(ctx context.Context, userID, viewerID string, page, pageSize int) ([]FollowUser, error) {
	return s.followList(ctx, "following_id", userID, viewerID, page, pageSize)
}

func (s *Service) followList(ctx context.Context, side, userID, viewerID string, page, pageSize int) ([]FollowUser, error) {
	page, pageSize = normalizePage(page, pageSize, 20, 100)
	col := "following_id"
	if side == "following_id" {
		col = "follower_id"
	}
	rows, err := s.DB.Query(ctx, `SELECT u.id, COALESCE(u.name,''), COALESCE(u.avatar,''), COALESCE(u.intro,''), uf.created_at
		FROM user_follows uf JOIN users u ON u.id = uf.`+col+`
		WHERE uf.`+side+` = $1 AND u.deleted_at IS NULL ORDER BY uf.created_at DESC LIMIT $2 OFFSET $3`,
		userID, pageSize, (page-1)*pageSize)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	users := []FollowUser{}
	for rows.Next() {
		var u FollowUser
		var followedAt *time.Time
		if err := rows.Scan(&u.ID, &u.Name, &u.Avatar, &u.Intro, &followedAt); err != nil {
			return nil, err
		}
		u.VIP = "0"
		u.FollowedAt = followedAt
		u.IsSelf = viewerID != "" && viewerID == u.ID
		if viewerID != "" && !u.IsSelf {
			u.IsFollowing = s.DB.IsFollowing(ctx, viewerID, u.ID)
		}
		users = append(users, u)
	}
	return users, rows.Err()
}

// ToggleFollow 关注/取消关注。
func (s *Service) ToggleFollow(ctx context.Context, followerID, targetID string) (bool, error) {
	if followerID == targetID {
		return false, errors.New("不能关注自己")
	}
	return s.DB.ToggleFollow(ctx, followerID, targetID)
}

// ReplyItem 用户收到的回复（旧 APP /api/users/me/replies 形状）。
type ReplyItem struct {
	CommentID        string     `json:"comment_id"`
	CommentContent   string     `json:"comment_content"`
	ParentID         *string    `json:"parent_id"`
	CommentCreatedAt *time.Time `json:"comment_created_at"`
	ReplierID        string     `json:"replier_id"`
	ReplyContent     string     `json:"reply_content"`
	ReplyCreatedAt   *time.Time `json:"reply_created_at"`
	ReplierName      string     `json:"replier_name"`
	ReplierAvatar    string     `json:"replier_avatar"`
	PostID           string     `json:"post_id"`
	PostTitle        string     `json:"post_title"`
}

// MyReplies 回复了我的评论的回复列表（含原评论内容与帖子标题）。
func (s *Service) MyReplies(ctx context.Context, userID string, page, pageSize int) ([]ReplyItem, int, error) {
	page, pageSize = normalizePage(page, pageSize, 50, 100)
	var total int
	_ = s.DB.QueryRow(ctx, `SELECT COUNT(*) FROM comments c JOIN comments r ON r.parent_id = c.id AND r.status = 1
		WHERE c.user_id = $1 AND c.status = 1`, userID).Scan(&total)
	rows, err := s.DB.Query(ctx, `SELECT c.id, c.content, c.parent_id, c.created_at,
		r.user_id, r.content, r.created_at, COALESCE(u.name, ''), COALESCE(u.avatar, ''),
		p.id, p.title
		FROM comments c
		JOIN comments r ON r.parent_id = c.id AND r.status = 1
		JOIN users u ON r.user_id = u.id
		JOIN posts p ON c.post_id = p.id
		WHERE c.user_id = $1 AND c.status = 1 AND p.status = 1
		ORDER BY r.created_at DESC LIMIT $2 OFFSET $3`, userID, pageSize, (page-1)*pageSize)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	items := []ReplyItem{}
	for rows.Next() {
		var r ReplyItem
		var commentContent, replyContent string
		if err := rows.Scan(&r.CommentID, &commentContent, &r.ParentID, &r.CommentCreatedAt,
			&r.ReplierID, &replyContent, &r.ReplyCreatedAt, &r.ReplierName, &r.ReplierAvatar,
			&r.PostID, &r.PostTitle); err != nil {
			return nil, 0, err
		}
		r.CommentContent = commentContent
		r.ReplyContent = replyContent
		items = append(items, r)
	}
	return items, total, rows.Err()
}

// ---- 世界频道 ----

// WorldMessage 旧 APP 世界消息（裸数组元素）。
type WorldMessage struct {
	ID           int64     `json:"id"`
	SenderID     string    `json:"sender_id"`
	SenderName   string    `json:"sender_name"`
	Content      string    `json:"content"`
	ParentID     *int64    `json:"parent_id"`
	SenderAvatar string    `json:"sender_avatar"`
	CreatedAt    time.Time `json:"created_at"`
}

var sinceRe = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(?:Z|[+-]\d{2}:?\d{2})?$`)

// ParseSince 校验 since 参数；空/格式或日期非法返回空串（回落全量）。
func ParseSince(raw string) string {
	s := strings.TrimSpace(raw)
	if s == "" || !sinceRe.MatchString(s) {
		return ""
	}
	layouts := []string{
		time.RFC3339Nano,
		"2006-01-02",
		"2006-01-02 15:04",
		"2006-01-02 15:04:05",
		"2006-01-02 15:04:05.999999999",
		"2006-01-02 15:04Z07:00",
		"2006-01-02 15:04:05Z07:00",
		"2006-01-02 15:04:05.999999999Z07:00",
		"2006-01-02T15:04",
		"2006-01-02T15:04:05",
		"2006-01-02T15:04:05.999999999",
	}
	for _, layout := range layouts {
		if _, err := time.Parse(layout, s); err == nil {
			return s
		}
	}
	return ""
}

// WorldList 世界消息裸数组（最多 100 条，支持 since 增量）。
func (s *Service) WorldList(ctx context.Context, since string, limit int) ([]WorldMessage, error) {
	if limit < 1 || limit > 100 {
		limit = 100
	}
	sqlQ := `SELECT w.id, w.sender_id, w.sender_name, COALESCE(NULLIF(w.sender_avatar, ''), u.avatar, '') AS sender_avatar,
		w.content, w.content_format, w.parent_id, w.created_at
		FROM world_messages w LEFT JOIN users u ON u.id = w.sender_id WHERE w.status = 1`
	args := []any{}
	if v := ParseSince(since); v != "" {
		args = append(args, v)
		sqlQ += fmt.Sprintf(" AND w.created_at > $%d::timestamptz", len(args))
	}
	args = append(args, limit)
	sqlQ += fmt.Sprintf(" ORDER BY w.created_at DESC, w.id DESC LIMIT $%d", len(args))
	rows, err := s.DB.Query(ctx, sqlQ, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	messages := []WorldMessage{}
	for rows.Next() {
		var m WorldMessage
		var content, format string
		if err := rows.Scan(&m.ID, &m.SenderID, &m.SenderName, &m.SenderAvatar, &content, &format, &m.ParentID, &m.CreatedAt); err != nil {
			return nil, err
		}
		if format == "html" {
			content = HTMLToMarkdown(content)
		}
		m.Content = content
		messages = append(messages, m)
	}
	return messages, rows.Err()
}

// WorldSend 发送世界消息：纯文本 ≤500 字、每用户 2 秒一条、content_format='markdown'。
func (s *Service) WorldSend(ctx context.Context, user *LegacyUser, content string, parentID *int64) (*WorldMessage, error) {
	content = strings.TrimSpace(content)
	s.mu.Lock()
	last, ok := s.lastWorldSend[user.ID]
	now := time.Now()
	if ok && now.Sub(last) < 2*time.Second {
		s.mu.Unlock()
		return nil, ErrWorldTooFast
	}
	s.mu.Unlock()

	var id int64
	var createdAt time.Time
	err := s.DB.QueryRow(ctx, `INSERT INTO world_messages (sender_id, sender_name, sender_avatar, content, content_format, parent_id)
		VALUES ($1,$2,$3,$4,'markdown',$5) RETURNING id, created_at`,
		user.ID, user.Name, user.Avatar, content, parentID).Scan(&id, &createdAt)
	if err != nil {
		return nil, err
	}
	s.mu.Lock()
	s.lastWorldSend[user.ID] = now
	s.mu.Unlock()
	return &WorldMessage{ID: id, SenderID: user.ID, SenderName: user.Name, Content: content,
		ParentID: parentID, SenderAvatar: user.Avatar, CreatedAt: createdAt}, nil
}

// ---- 搜索 ----

// SearchResult 搜索响应键集合。
type SearchResult struct {
	Posts        []PostListItem
	PostsTotal   int
	PostsHasMore bool
	Users        []SearchUser
	UsersTotal   int
	UsersHasMore bool
}

// SearchUser 用户搜索结果。
type SearchUser struct {
	ID        string     `json:"id"`
	Name      string     `json:"name"`
	Avatar    string     `json:"avatar"`
	VIP       string     `json:"vip"`
	CreatedAt *time.Time `json:"created_at"`
}

// Search 帖子/用户搜索。
func (s *Service) Search(ctx context.Context, keyword, typ string, page, pageSize int) (*SearchResult, error) {
	keyword = strings.TrimSpace(keyword)
	if len([]rune(keyword)) < 2 {
		return nil, ErrSearchTooShort
	}
	page, pageSize = normalizePage(page, pageSize, 20, 100)
	if typ != "posts" && typ != "users" && typ != "both" {
		typ = "both"
	}
	res := &SearchResult{}
	if typ == "posts" || typ == "both" {
		posts, total, hasMore, err := s.DB.SearchPosts(ctx, keyword, page, pageSize)
		if err != nil {
			return nil, err
		}
		res.Posts = make([]PostListItem, 0, len(posts))
		for _, p := range posts {
			res.Posts = append(res.Posts, PostListItem{
				ID: p.ID, UserID: p.UserID, Title: p.Title, Summary: truncateRunes(p.Summary, 200),
				Category: p.Category, Likes: p.Likes, Views: p.Views, CommentCount: p.CommentCount,
				CreatedAt: p.CreatedAt, UserName: p.UserName, UserAvatar: p.UserAvatar,
			})
		}
		res.PostsTotal = total
		res.PostsHasMore = hasMore
	}
	if typ == "users" || typ == "both" {
		users, total, hasMore, err := s.DB.SearchUsers(ctx, keyword, page, pageSize)
		if err != nil {
			return nil, err
		}
		res.Users = make([]SearchUser, 0, len(users))
		for _, u := range users {
			var createdAt *time.Time
			var isBanned int
			_ = s.DB.QueryRow(ctx, "SELECT created_at, is_banned FROM users WHERE id=$1", u.ID).Scan(&createdAt, &isBanned)
			if isBanned != 0 {
				continue
			}
			res.Users = append(res.Users, SearchUser{ID: u.ID, Name: u.Name, Avatar: u.Avatar, VIP: "0", CreatedAt: createdAt})
		}
		res.UsersTotal = total
		res.UsersHasMore = hasMore
	}
	return res, nil
}

// ---- 静态数据 ----

// HuiguanList 读取 huiguan.json（旧 APP 静态会馆列表）。
func (s *Service) HuiguanList() ([]any, error) {
	for _, path := range s.HuiguanPaths {
		if strings.TrimSpace(path) == "" {
			continue
		}
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var list []any
		if err := json.Unmarshal(data, &list); err != nil {
			return nil, err
		}
		return list, nil
	}
	return nil, os.ErrNotExist
}

// RandomEasterEgg 从彩蛋 JSON 数组随机取一条。
func (s *Service) RandomEasterEgg() (map[string]any, error) {
	for _, path := range s.EasterEggPaths {
		if strings.TrimSpace(path) == "" {
			continue
		}
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var list []map[string]any
		if err := json.Unmarshal(data, &list); err != nil || len(list) == 0 {
			continue
		}
		n, err := rand.Int(rand.Reader, big.NewInt(int64(len(list))))
		if err != nil {
			return list[0], nil
		}
		return list[n.Int64()], nil
	}
	return nil, os.ErrNotExist
}

func truncateRunes(s string, max int) string {
	r := []rune(s)
	if len(r) <= max {
		return s
	}
	return string(r[:max])
}

// ---- 应用发布 / 最低版本闸门 ----

const defaultGitHubRepo = "crazying-dev/forum"

// ReleaseAsset 与 legacy app_releases.json 的 release 结构一致。
type ReleaseAsset struct {
	Version   string   `json:"version"`
	Channel   string   `json:"channel"`
	Date      string   `json:"date"`
	Size      int64    `json:"size"`
	URL       string   `json:"url"`
	Filename  string   `json:"filename"`
	SHA256    string   `json:"sha256"`
	Notes     []string `json:"notes"`
	Mandatory bool     `json:"mandatory"`
}

// ReleasePlatform 平台发布信息。
type ReleasePlatform struct {
	Key         string         `json:"key"`
	Name        string         `json:"name"`
	Icon        string         `json:"icon"`
	Status      string         `json:"status"`
	Requirement string         `json:"requirement"`
	Releases    []ReleaseAsset `json:"releases"`
}

// ReleaseManifest 完整发布清单。
type ReleaseManifest struct {
	Schema      int               `json:"schema"`
	UpdatedAt   string            `json:"updated_at"`
	MinVersions map[string]string `json:"min_versions"`
	Platforms   []ReleasePlatform `json:"platforms"`
}

// ReleaseProvider 从 GitHub Releases 拉取并缓存发布清单；失败时回退内置清单。
type ReleaseProvider struct {
	mu        sync.Mutex
	cached    *ReleaseManifest
	fetchedAt time.Time
	TTL       time.Duration
	Repo      string
	Token     string
	Client    *http.Client
	// Fetch 可注入（测试用）；为空时走 GitHub API。
	Fetch    func() (*ReleaseManifest, error)
	hits     int
	misses   int
	fetching bool
}

// NewReleaseProvider 创建发布清单提供者。
func NewReleaseProvider(token string) *ReleaseProvider {
	return &ReleaseProvider{
		TTL: 10 * time.Minute, Repo: defaultGitHubRepo, Token: token,
		Client: &http.Client{Timeout: 8 * time.Second},
	}
}

// Manifest 返回缓存或新拉取的清单（永不返回 nil）。
func (p *ReleaseProvider) Manifest() *ReleaseManifest {
	p.mu.Lock()
	defer p.mu.Unlock()
	now := time.Now()
	if p.cached != nil && now.Sub(p.fetchedAt) < p.TTL {
		p.hits++
		return p.cached
	}
	p.misses++
	p.fetching = true
	defer func() { p.fetching = false }()
	var (
		m   *ReleaseManifest
		err error
	)
	if p.Fetch != nil {
		m, err = p.Fetch()
	} else {
		m, err = fetchGitHubManifest(p.Client, p.Token, p.Repo)
	}
	if err != nil || m == nil || len(m.Platforms) == 0 || !hasAnyRelease(m) {
		m = fallbackManifest()
	}
	p.cached = m
	p.fetchedAt = now
	return m
}

func hasAnyRelease(m *ReleaseManifest) bool {
	for i := range m.Platforms {
		if len(m.Platforms[i].Releases) > 0 {
			return true
		}
	}
	return false
}

// CachedManifest 返回已缓存的清单；未预热时返回内置清单（不触发网络）。
func (p *ReleaseProvider) CachedManifest() *ReleaseManifest {
	p.mu.Lock()
	m := p.cached
	p.mu.Unlock()
	if m == nil {
		return fallbackManifest()
	}
	return m
}

// MinVersion 平台最低版本；未知/无发布返回空串（不拦截）。
//
// 版本闸门在每个 /api/* 请求上执行，不能因 GitHub 慢而阻塞：未预热时先用内置
// 清单立即返回，同时异步拉取最新清单，后续请求即使用缓存（/api/app/* 也会预热）。
func (p *ReleaseProvider) MinVersion(platform string) string {
	platform = strings.ToLower(strings.TrimSpace(platform))
	if platform == "" || platform == "web" {
		return ""
	}
	p.mu.Lock()
	m := p.cached
	if m == nil && !p.fetching {
		p.fetching = true
		go p.Manifest()
	}
	p.mu.Unlock()
	if m == nil {
		m = fallbackManifest()
	}
	if v, ok := m.MinVersions[platform]; ok {
		return strings.TrimSpace(v)
	}
	return ""
}

// FindRelease 按平台 + 文件名查找可下载 release。
func (p *ReleaseProvider) FindRelease(platform, filename string) (*ReleaseAsset, bool) {
	m := p.Manifest()
	pf := findPlatform(m, platform)
	if pf == nil {
		return nil, false
	}
	for i := range pf.Releases {
		if pf.Releases[i].Filename == filename {
			return &pf.Releases[i], true
		}
	}
	return nil, false
}

// CacheInfo 反代/清单缓存诊断信息。
func (p *ReleaseProvider) CacheInfo() map[string]any {
	p.mu.Lock()
	defer p.mu.Unlock()
	entries := 0
	if p.cached != nil {
		entries = len(p.cached.Platforms)
	}
	return map[string]any{
		"entries": entries, "bytes": 0, "ttl": int(p.TTL.Seconds()),
		"max_bytes": 0, "max_file": 0, "hit": p.hits, "miss": p.misses,
	}
}

// FindPlatform 按 key 或 name 查找平台（大小写不敏感）。
func FindPlatform(m *ReleaseManifest, key string) *ReleasePlatform {
	return findPlatform(m, key)
}

func findPlatform(m *ReleaseManifest, key string) *ReleasePlatform {
	if m == nil {
		return nil
	}
	target := strings.ToLower(strings.TrimSpace(key))
	if target == "" {
		return nil
	}
	for i := range m.Platforms {
		pf := &m.Platforms[i]
		if strings.ToLower(pf.Key) == target || strings.ToLower(pf.Name) == target {
			return pf
		}
	}
	return nil
}

// PickLatest 取平台最新 stable release（无 stable 时取任意最新）。
func PickLatest(pf *ReleasePlatform) *ReleaseAsset {
	if pf == nil || len(pf.Releases) == 0 {
		return nil
	}
	var bestStable, bestAny *ReleaseAsset
	for i := range pf.Releases {
		r := &pf.Releases[i]
		if bestAny == nil || CompareVersions(r.Version, bestAny.Version) > 0 {
			bestAny = r
		}
		if r.Channel == "stable" && (bestStable == nil || CompareVersions(r.Version, bestStable.Version) > 0) {
			bestStable = r
		}
	}
	if bestStable != nil {
		return bestStable
	}
	return bestAny
}

// ParseVersion 解析 "v1.2.3" / "Windows-V1.2.3" 为数字段。
func ParseVersion(text string) []int {
	text = strings.TrimSpace(text)
	if text == "" {
		return nil
	}
	// 取第一个版本号形态的子串（tag 可能带平台前缀）。
	re := regexp.MustCompile(`(?i)v?(\d+(?:\.\d+)*)`)
	m := re.FindStringSubmatch(text)
	if len(m) < 2 {
		return nil
	}
	parts := strings.Split(m[1], ".")
	out := make([]int, 0, len(parts))
	for _, part := range parts {
		n := 0
		for _, ch := range part {
			if ch < '0' || ch > '9' {
				break
			}
			n = n*10 + int(ch-'0')
		}
		out = append(out, n)
	}
	return out
}

// CompareVersions a<b 返回 -1，相等 0，a>b 返回 1（长度差按 0 补齐）。
func CompareVersions(a, b string) int {
	va, vb := ParseVersion(a), ParseVersion(b)
	size := len(va)
	if len(vb) > size {
		size = len(vb)
	}
	for i := 0; i < size; i++ {
		x, y := 0, 0
		if i < len(va) {
			x = va[i]
		}
		if i < len(vb) {
			y = vb[i]
		}
		if x < y {
			return -1
		}
		if x > y {
			return 1
		}
	}
	return 0
}

// ResolveClient 从 X-Client-Platform/X-Client-Version 或 UA（CrForum-Windows/1.3.18）解析客户端。
func ResolveClient(platform, version, userAgent string) (string, string) {
	platform = strings.ToLower(strings.TrimSpace(platform))
	version = strings.TrimSpace(version)
	if platform == "" {
		if m := clientUARe.FindStringSubmatch(userAgent); len(m) == 3 {
			platform = strings.ToLower(m[1])
			if version == "" {
				version = m[2]
			}
		}
	}
	return platform, version
}

var clientUARe = regexp.MustCompile(`(?i)CrForum-([A-Za-z0-9_.-]+)/([0-9][0-9A-Za-z._-]*)`)

// CheckRelease 生成 /api/app/check 响应体；平台未知时返回 nil。
func CheckRelease(m *ReleaseManifest, platform, current string) map[string]any {
	pf := findPlatform(m, platform)
	if pf == nil {
		return nil
	}
	if strings.TrimSpace(current) == "" {
		current = "0.0.0"
	}
	minimum := ""
	if m.MinVersions != nil {
		minimum = strings.TrimSpace(m.MinVersions[strings.ToLower(pf.Key)])
	}
	payload := map[string]any{
		"success": true, "platform": pf.Key, "current": current,
		"latest": nil, "available": false, "mandatory": false, "release": nil,
		"min_version": minimum, "too_low": minimum != "" && CompareVersions(current, minimum) < 0,
		"message": "当前已是最新版本",
	}
	if pf.Status != "available" || len(pf.Releases) == 0 {
		payload["message"] = "该平台暂未发布"
		return payload
	}
	latest := PickLatest(pf)
	if latest == nil {
		payload["message"] = "该平台暂未发布"
		return payload
	}
	payload["latest"] = latest.Version
	if CompareVersions(latest.Version, current) > 0 {
		payload["available"] = true
		payload["mandatory"] = latest.Mandatory
		payload["release"] = latest
		payload["message"] = "发现新版本 " + latest.Version
	}
	return payload
}

// githubRelease GitHub API 的 release 子集。
type githubRelease struct {
	TagName     string `json:"tag_name"`
	Name        string `json:"name"`
	Body        string `json:"body"`
	PublishedAt string `json:"published_at"`
	Prerelease  bool   `json:"prerelease"`
	Draft       bool   `json:"draft"`
	Assets      []struct {
		Name               string `json:"name"`
		Size               int64  `json:"size"`
		BrowserDownloadURL string `json:"browser_download_url"`
	} `json:"assets"`
}

func fetchGitHubManifest(client *http.Client, token, repo string) (*ReleaseManifest, error) {
	if client == nil {
		client = &http.Client{Timeout: 8 * time.Second}
	}
	if repo == "" {
		repo = defaultGitHubRepo
	}
	req, err := http.NewRequest(http.MethodGet, "https://api.github.com/repos/"+repo+"/releases?per_page=30", nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", "yj-forum-legacy-compat")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("github releases: HTTP %d", resp.StatusCode)
	}
	var releases []githubRelease
	if err := json.NewDecoder(resp.Body).Decode(&releases); err != nil {
		return nil, err
	}
	platforms := defaultPlatforms()
	byKey := map[string]*ReleasePlatform{}
	for i := range platforms {
		byKey[platforms[i].Key] = &platforms[i]
	}
	for _, rel := range releases {
		if rel.Draft || rel.Prerelease {
			continue
		}
		key := platformFromTag(rel.TagName)
		if key == "" {
			key = platformFromAssets(rel.Assets)
		}
		if key == "" {
			continue
		}
		pf := byKey[key]
		if pf == nil {
			continue
		}
		asset := pickAsset(rel.Assets, key)
		if asset == nil {
			continue
		}
		notes := splitNotes(rel.Body)
		pf.Releases = append(pf.Releases, ReleaseAsset{
			Version: parseTagVersion(rel.TagName), Channel: "stable",
			Date: firstN(rel.PublishedAt, 10), Size: asset.Size, URL: asset.BrowserDownloadURL,
			Filename: asset.Name, Notes: notes, Mandatory: strings.Contains(strings.ToLower(rel.Body), "mandatory"),
		})
	}
	minVersions := map[string]string{}
	manifest := &ReleaseManifest{Schema: 1, UpdatedAt: time.Now().Format(time.RFC3339), MinVersions: minVersions, Platforms: platforms}
	for i := range manifest.Platforms {
		pf := &manifest.Platforms[i]
		sortReleases(pf)
		if len(pf.Releases) == 0 {
			pf.Status = "coming_soon"
			continue
		}
		pf.Status = "available"
		if latest := PickLatest(pf); latest != nil {
			minVersions[pf.Key] = latest.Version
		}
	}
	minVersions["web"] = "0"
	return manifest, nil
}

func defaultPlatforms() []ReleasePlatform {
	return []ReleasePlatform{
		{Key: "windows", Name: "Windows", Icon: "fa-windows", Status: "coming_soon", Requirement: "Windows 10 / 11（64 位）", Releases: []ReleaseAsset{}},
		{Key: "android", Name: "Android", Icon: "fa-android", Status: "coming_soon", Requirement: "Android 7.0 及以上", Releases: []ReleaseAsset{}},
		{Key: "linux", Name: "Linux", Icon: "fa-linux", Status: "coming_soon", Requirement: "x86_64 桌面发行版", Releases: []ReleaseAsset{}},
		{Key: "macos", Name: "macOS", Icon: "fa-apple", Status: "coming_soon", Requirement: "macOS 11 及以上（Intel / Apple Silicon）", Releases: []ReleaseAsset{}},
	}
}

func platformFromTag(tag string) string {
	lower := strings.ToLower(tag)
	for _, key := range []string{"windows", "android", "linux", "macos"} {
		if strings.Contains(lower, key) {
			return key
		}
	}
	return ""
}

func platformFromAssets(assets []struct {
	Name               string `json:"name"`
	Size               int64  `json:"size"`
	BrowserDownloadURL string `json:"browser_download_url"`
}) string {
	for _, a := range assets {
		name := strings.ToLower(a.Name)
		switch {
		case strings.HasSuffix(name, ".exe") || strings.HasSuffix(name, ".msi"):
			return "windows"
		case strings.HasSuffix(name, ".apk"):
			return "android"
		case strings.HasSuffix(name, ".dmg"):
			return "macos"
		case strings.HasSuffix(name, ".appimage") || strings.HasSuffix(name, ".deb"):
			return "linux"
		}
	}
	return ""
}

func pickAsset(assets []struct {
	Name               string `json:"name"`
	Size               int64  `json:"size"`
	BrowserDownloadURL string `json:"browser_download_url"`
}, key string) *struct {
	Name               string `json:"name"`
	Size               int64  `json:"size"`
	BrowserDownloadURL string `json:"browser_download_url"`
} {
	if len(assets) == 0 {
		return nil
	}
	for i := range assets {
		a := &assets[i]
		name := strings.ToLower(a.Name)
		matched := false
		switch key {
		case "windows":
			matched = strings.HasSuffix(name, ".exe") || strings.HasSuffix(name, ".msi")
		case "android":
			matched = strings.HasSuffix(name, ".apk")
		case "macos":
			matched = strings.HasSuffix(name, ".dmg")
		case "linux":
			matched = strings.HasSuffix(name, ".appimage") || strings.HasSuffix(name, ".deb")
		}
		if matched {
			return a
		}
	}
	// 只有一个附件时允许兜底；多附件但无平台匹配时宁可跳过，避免把校验文件当安装包。
	if len(assets) == 1 {
		return &assets[0]
	}
	return nil
}

func parseTagVersion(tag string) string {
	re := regexp.MustCompile(`(?i)v?(\d+(?:\.\d+)*)`)
	if m := re.FindStringSubmatch(tag); len(m) > 1 {
		return m[1]
	}
	return strings.TrimSpace(tag)
}

func splitNotes(body string) []string {
	notes := []string{}
	for _, line := range strings.Split(body, "\n") {
		line = strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(line), "-"))
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		notes = append(notes, line)
	}
	return notes
}

func sortReleases(pf *ReleasePlatform) {
	// 简单插入排序，避免额外依赖；版本数通常个位数。
	for i := 1; i < len(pf.Releases); i++ {
		for j := i; j > 0 && CompareVersions(pf.Releases[j].Version, pf.Releases[j-1].Version) > 0; j-- {
			pf.Releases[j], pf.Releases[j-1] = pf.Releases[j-1], pf.Releases[j]
		}
	}
}

func firstN(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

// fallbackManifest 内置回退清单（GitHub 不可达时保证旧客户端能更新）。
func fallbackManifest() *ReleaseManifest {
	return &ReleaseManifest{
		Schema: 1, UpdatedAt: "2026-10-17T19:35:00+08:00",
		MinVersions: map[string]string{"windows": "1.3.18", "android": "1.0.16", "web": "0"},
		Platforms: []ReleasePlatform{
			{Key: "windows", Name: "Windows", Icon: "fa-windows", Status: "available", Requirement: "Windows 10 / 11（64 位）", Releases: []ReleaseAsset{{
				Version: "1.3.18", Channel: "stable", Date: "2026-10-10", Size: 158186366,
				URL:      "https://github.com/crazying-dev/forum/releases/download/Windows-V1.3.18/forum_setup.exe",
				Filename: "forum_setup.exe", Notes: []string{},
			}}},
			{Key: "android", Name: "Android", Icon: "fa-android", Status: "available", Requirement: "Android 7.0 及以上", Releases: []ReleaseAsset{{
				Version: "1.0.16", Channel: "stable", Date: "2026-10-10", Size: 8152504,
				URL:      "https://github.com/crazying-dev/forum/releases/download/Android-V1.0.16/forum-android-1.0.16.apk",
				Filename: "forum-android-1.0.16.apk", Notes: []string{},
			}}},
			{Key: "linux", Name: "Linux", Icon: "fa-linux", Status: "coming_soon", Requirement: "x86_64 桌面发行版", Releases: []ReleaseAsset{}},
			{Key: "macos", Name: "macOS", Icon: "fa-apple", Status: "coming_soon", Requirement: "macOS 11 及以上（Intel / Apple Silicon）", Releases: []ReleaseAsset{}},
		},
	}
}
