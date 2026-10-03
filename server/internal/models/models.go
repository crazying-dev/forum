// Package models 定义 API 数据结构。
package models

import "time"

// User 用户（对外，不含密码）。
type User struct {
	ID            string     `json:"id"`
	Name          string     `json:"name"`
	Avatar        string     `json:"avatar"`
	Email         string     `json:"email,omitempty"`
	Gender        int        `json:"gender"`
	Age           string     `json:"age"`
	Intro         string     `json:"intro"`
	Spirit        int        `json:"spirit"`       // 灵力值（签到累计）
	LastSignIn    string     `json:"last_sign_in"` // 最近签到日期（YYYY-MM-DD，未签到为空）
	Prefix        string     `json:"prefix"`
	IsBanned      int        `json:"is_banned"`
	EmailVerified int        `json:"email_verified"`
	CreatedAt     *time.Time `json:"created_at"`
	LastLogin     *time.Time `json:"last_login"`
	DeletedAt     *time.Time `json:"-"`                 // 注销时间（非空即已注销，不下发）
	Deleted       bool       `json:"deleted,omitempty"` // 已注销标记（仅注销账号返回 true）
}

// UserBrief 列表/关联场景的用户摘要。
type UserBrief struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Avatar      string `json:"avatar"`
	Prefix      string `json:"prefix"`
	Intro       string `json:"intro"`
	IsSelf      bool   `json:"is_self"`
	IsFollowing bool   `json:"is_following"`
	IsMutual    bool   `json:"is_mutual"` // 共同关注：viewer 是否也关注了该用户（仅 following 列表下发；粉丝列表/匿名/本人恒 false）
}

// Post 帖子。
type Post struct {
	ID            string     `json:"id"`
	UserID        string     `json:"user_id"`
	Title         string     `json:"title"`
	Content       string     `json:"content"`
	ContentFormat string     `json:"content_format"` // 正文存储形态：markdown（历史数据）/ html（新富文本）
	Summary       string     `json:"summary,omitempty"`
	Category      string     `json:"category"`
	Likes         int        `json:"likes"`
	Views         int        `json:"views"`
	Status        int        `json:"status"`
	CreatedAt     *time.Time `json:"created_at"`
	UpdatedAt     *time.Time `json:"updated_at"`
	// PublishedAt 定时发布时间（未来=未发布；存量/立即帖为发布时刻，DB 恒非空）
	PublishedAt *time.Time `json:"published_at,omitempty"`
	UserName    string     `json:"user_name"`
	UserAvatar  string     `json:"user_avatar"`
	// 作者所属会馆（无会馆时为 "" / "" / false）
	UserGuildName       string `json:"user_guild_name"`
	UserGuildThemeColor string `json:"user_guild_theme_color"`
	UserIsLeader        bool   `json:"user_is_leader"`
	// 会馆归属（nil 表示公共广场）
	GuildID         *int64 `json:"guild_id,omitempty"`
	GuildName       string `json:"guild_name,omitempty"`
	GuildThemeColor string `json:"guild_theme_color,omitempty"`
}

// Comment 评论。
type Comment struct {
	ID            string     `json:"id"`
	PostID        string     `json:"post_id"`
	UserID        string     `json:"user_id"`
	Content       string     `json:"content"`
	ContentFormat string     `json:"content_format"` // 正文存储形态：markdown（历史数据）/ html（新富文本）
	ParentID      *string    `json:"parent_id"`
	Likes         int        `json:"likes"`
	Status        int        `json:"status"`
	LikedByMe     bool       `json:"liked_by_me"`
	CreatedAt     *time.Time `json:"created_at"`
	UserName      string     `json:"user_name"`
	UserAvatar    string     `json:"user_avatar"`
	// 作者所属会馆（无会馆时为 "" / "" / false）
	UserGuildName       string `json:"user_guild_name"`
	UserGuildThemeColor string `json:"user_guild_theme_color"`
	UserIsLeader        bool   `json:"user_is_leader"`
}

// PostListItem 列表用帖子（含 summary）。
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
	// PublishedAt 发布时间（RFC3339；本人视角下的定时帖为未来时间）
	PublishedAt string `json:"published_at"`
	UserName    string `json:"user_name"`
	UserAvatar  string `json:"user_avatar"`
	// 作者所属会馆（无会馆时为 "" / "" / false）
	UserGuildName       string `json:"user_guild_name"`
	UserGuildThemeColor string `json:"user_guild_theme_color"`
	UserIsLeader        bool   `json:"user_is_leader"`
	// 会馆归属（nil 表示公共广场）
	GuildID         *int64 `json:"guild_id,omitempty"`
	GuildName       string `json:"guild_name,omitempty"`
	GuildThemeColor string `json:"guild_theme_color,omitempty"`
}

// ReplyItem 我收到的回复。
type ReplyItem struct {
	Comment
	PostID    string `json:"post_id"`
	PostTitle string `json:"post_title"`
}

// Guild 会馆基础信息。
type Guild struct {
	ID           int64      `json:"id"`
	Slug         string     `json:"slug"`
	Name         string     `json:"name"`
	Intro        string     `json:"intro"`
	LogoFileID   string     `json:"logo_file_id,omitempty"`
	LogoVersion  int        `json:"logo_version"`
	ThemeColor   string     `json:"theme_color"`
	LeaderUserID *string    `json:"leader_user_id"`
	LeaderBio    string     `json:"leader_bio"`
	CreatedAt    *time.Time `json:"created_at"`
	UpdatedAt    *time.Time `json:"updated_at"`
}

// GuildLeaderInfo 馆长摘要。
type GuildLeaderInfo struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Avatar string `json:"avatar"`
	Intro  string `json:"intro"`
	Bio    string `json:"bio"`
	Title  string `json:"title"`
}

// GuildSummary 会馆概要（馆长页用）。
type GuildSummary struct {
	UUID       string `json:"uuid"`
	Slug       string `json:"slug"`
	Name       string `json:"name"`
	ThemeColor string `json:"theme_color"`
}

// GuildLeaderPage 馆长页数据（会馆概要 + 馆长摘要 + 寄语 + 正文）。
type GuildLeaderPage struct {
	Guild     GuildSummary     `json:"guild"`
	Leader    *GuildLeaderInfo `json:"leader"`
	LeaderBio string           `json:"leader_bio"`
	Content   string           `json:"content"`
}

// GuildIntroSummary 会馆介绍页头（会馆概要 + 统计 + 封面）。
type GuildIntroSummary struct {
	UUID          string     `json:"uuid"`
	Slug          string     `json:"slug"`
	Name          string     `json:"name"`
	Intro         string     `json:"intro"`
	ThemeColor    string     `json:"theme_color"`
	CreatedAt     *time.Time `json:"created_at"`
	MemberCount   int        `json:"member_count"`
	CategoryCount int        `json:"category_count"`
	CoverFileID   string     `json:"cover_file_id"`
}

// GuildIntroPage 会馆介绍页（富文本正文）。
type GuildIntroPage struct {
	Guild   GuildIntroSummary `json:"guild"`
	Content string            `json:"content"`
}

// GuildListItem 会馆列表项。
type GuildListItem struct {
	ID          int64            `json:"id"`
	UUID        string           `json:"uuid"`
	Slug        string           `json:"slug"`
	Name        string           `json:"name"`
	Intro       string           `json:"intro"`
	ThemeColor  string           `json:"theme_color"`
	MemberCount int              `json:"member_count"`
	HasLogo     bool             `json:"has_logo"`
	LogoVersion int              `json:"logo_version"`
	CreatedAt   *time.Time       `json:"created_at"`
	Leader      *GuildLeaderInfo `json:"leader"`
}

// GuildCategory 会馆自定义分类。
type GuildCategory struct {
	ID      int64  `json:"id"`
	GuildID int64  `json:"guild_id"`
	Name    string `json:"name"`
	Sort    int    `json:"sort"`
}

// GuildAnnouncement 会馆公告。
type GuildAnnouncement struct {
	ID        int64      `json:"id"`
	GuildID   int64      `json:"guild_id"`
	Content   string     `json:"content"`
	CreatedAt *time.Time `json:"created_at"`
	UpdatedAt *time.Time `json:"updated_at"`
}

// GuildDetail 会馆详情（含馆长、分类、公告）。
type GuildDetail struct {
	Guild
	// UUID 会馆稳定标识（对外契约）
	UUID string `json:"uuid"`
	// LogoFileID 覆盖内嵌 Guild 的同名字段：管理端文件 ID 仅服务端内部使用，不随详情下发 JSON
	LogoFileID    string              `json:"-"`
	Leader        *GuildLeaderInfo    `json:"leader"`
	MemberCount   int                 `json:"member_count"`
	HasLogo       bool                `json:"has_logo"`
	Categories    []GuildCategory     `json:"categories"`
	Announcements []GuildAnnouncement `json:"announcements"`
}

// GuildMembership 用户与会馆的关系（资料页用）。
type GuildMembership struct {
	ID         int64  `json:"id"`
	UUID       string `json:"uuid"`
	Slug       string `json:"slug"`
	Name       string `json:"name"`
	ThemeColor string `json:"theme_color"`
	IsLeader   bool   `json:"is_leader"`
}

// GuildMember 会馆成员（列表用）。
type GuildMember struct {
	ID       string     `json:"id"`
	Name     string     `json:"name"`
	Avatar   string     `json:"avatar"`
	Prefix   string     `json:"prefix"`
	Intro    string     `json:"intro"`
	IsLeader bool       `json:"is_leader"`
	JoinedAt *time.Time `json:"joined_at"`
}

// GuildJoinRequest 入馆申请。
type GuildJoinRequest struct {
	ID        int64      `json:"id"`
	GuildID   int64      `json:"guild_id"`
	UserID    string     `json:"user_id"`
	Status    int        `json:"status"`
	Reason    string     `json:"reason"`
	HandledBy string     `json:"handled_by"`
	HandledAt *time.Time `json:"handled_at"`
	CreatedAt *time.Time `json:"created_at"`
}

// GuildArticleAuthor 文章作者摘要。
type GuildArticleAuthor struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Avatar string `json:"avatar"`
}

// GuildArticleParticipant 文章参与人（name 优先取实时用户名，回退署名快照）。
type GuildArticleParticipant struct {
	UserID   string `json:"user_id"`
	UserName string `json:"user_name"`
	Avatar   string `json:"avatar"`
}

// GuildArticle 会馆文章。
type GuildArticle struct {
	ID              string                    `json:"id"`
	GuildID         int64                     `json:"guild_id"`
	Title           string                    `json:"title"`
	Summary         string                    `json:"summary"`
	Content         string                    `json:"content,omitempty"`
	ContentFormat   string                    `json:"content_format"` // 正文存储形态：markdown（历史数据）/ html（富文本）
	AuthorUserID    *string                   `json:"author_user_id,omitempty"`
	Views           int                       `json:"views"`
	CreatedAt       *time.Time                `json:"created_at"`
	UpdatedAt       *time.Time                `json:"updated_at"`
	Author          *GuildArticleAuthor       `json:"author"`
	Participants    []GuildArticleParticipant `json:"participants"`
	GuildSlug       string                    `json:"guild_slug,omitempty"`
	GuildName       string                    `json:"guild_name,omitempty"`
	GuildThemeColor string                    `json:"guild_theme_color,omitempty"`
}

// ArticleSearchItem 文章搜索结果项。
type ArticleSearchItem struct {
	ID        string     `json:"id"`
	Title     string     `json:"title"`
	GuildName string     `json:"guild_name"`
	CreatedAt *time.Time `json:"created_at"`
}

// ---- 引用卡片（embeds）----

// EmbedGuild 引用卡片中用户所属会馆的摘要。
type EmbedGuild struct {
	Name       string `json:"name"`
	Slug       string `json:"slug"`
	ThemeColor string `json:"theme_color"`
}

// EmbedUser 引用卡片用户（无会馆时 guild 为 null）。
type EmbedUser struct {
	ID     string      `json:"id"`
	Name   string      `json:"name"`
	Avatar string      `json:"avatar"`
	Prefix string      `json:"prefix"`
	Intro  string      `json:"intro"`
	Guild  *EmbedGuild `json:"guild"`
}

// EmbedPost 引用卡片帖子。
type EmbedPost struct {
	ID         string     `json:"id"`
	Title      string     `json:"title"`
	UserID     string     `json:"user_id"`
	UserName   string     `json:"user_name"`
	UserAvatar string     `json:"user_avatar"`
	Category   string     `json:"category"`
	CreatedAt  *time.Time `json:"created_at"`
	GuildName  string     `json:"guild_name"`
}

// EmbedArticle 引用卡片文章。
type EmbedArticle struct {
	ID           string     `json:"id"`
	Title        string     `json:"title"`
	AuthorID     string     `json:"author_id"`
	AuthorName   string     `json:"author_name"`
	AuthorAvatar string     `json:"author_avatar"`
	CreatedAt    *time.Time `json:"created_at"`
	GuildName    string     `json:"guild_name"`
}

// FeedItem 动态流条目（帖子或文章）：公共广场与会馆信息流统一结构。
type FeedItem struct {
	Type         string     `json:"type"` // post | article
	ID           string     `json:"id"`
	Title        string     `json:"title"`
	Summary      string     `json:"summary"`
	Category     string     `json:"category"`
	Likes        int        `json:"likes"`
	Views        int        `json:"views"`
	CommentCount int        `json:"comment_count"`
	CreatedAt    *time.Time `json:"created_at"`
	UpdatedAt    *time.Time `json:"updated_at"`
	UserID       string     `json:"user_id"`
	UserName     string     `json:"user_name"`
	UserAvatar   string     `json:"user_avatar"`
	// 作者所属会馆（无会馆时为 "" / "" / false）
	UserGuildName       string              `json:"user_guild_name"`
	UserGuildThemeColor string              `json:"user_guild_theme_color"`
	UserIsLeader        bool                `json:"user_is_leader"`
	GuildID             *int64              `json:"guild_id"`
	GuildName           *string             `json:"guild_name"`
	GuildThemeColor     *string             `json:"guild_theme_color"`
	Author              *GuildArticleAuthor `json:"author"`
	ParticipantsCount   int                 `json:"participants_count"`
}

// GuildMyState 当前用户与会馆的关系（详情页用）。
type GuildMyState struct {
	IsMember          bool  `json:"is_member"`
	IsLeader          bool  `json:"is_leader"`
	HasPendingRequest bool  `json:"has_pending_request"`
	RequestID         int64 `json:"request_id,omitempty"`
}

// Stats 用户统计。
type Stats struct {
	PostCount  int `json:"post_count"`
	TotalLikes int `json:"total_likes"`
	TotalViews int `json:"total_views"`
}

// FollowStats 关注统计。
type FollowStats struct {
	FollowingCount int `json:"following_count"`
	FollowerCount  int `json:"follower_count"`
}

// UserProfile 用户主页。
type UserProfile struct {
	User        User        `json:"user"`
	Stats       Stats       `json:"stats"`
	FollowStats FollowStats `json:"follow_stats"`
	IsFollowing bool        `json:"is_following"`
	IsSelf      bool        `json:"is_self"`
}

// VersionVoteStats 投票统计。
type VersionVoteStats struct {
	V1 int `json:"v1"`
	V2 int `json:"v2"`
}

// ---- Bug 反馈（公开读取，均不含提交人信息）----

// BugReportListItem 反馈列表项（不含 steps）。
type BugReportListItem struct {
	ID        int64      `json:"id"`
	Title     string     `json:"title"`
	Detail    string     `json:"detail"`
	Status    int        `json:"status"`
	CreatedAt *time.Time `json:"created_at"`
}

// BugReport 反馈详情（不含提交人信息）。
type BugReport struct {
	ID        int64      `json:"id"`
	Title     string     `json:"title"`
	Detail    string     `json:"detail"`
	Steps     string     `json:"steps"`
	Status    int        `json:"status"`
	CreatedAt *time.Time `json:"created_at"`
}

// BugReportLog 反馈状态流转日志（from_status 可为空）。
type BugReportLog struct {
	FromStatus *int       `json:"from_status"`
	ToStatus   int        `json:"to_status"`
	Note       string     `json:"note"`
	CreatedAt  *time.Time `json:"created_at"`
}

// ---- 指南（guides）----

// GuideNodeListItem 指南节点列表项（不含正文）。
type GuideNodeListItem struct {
	ID        string     `json:"id"`
	ParentID  *string    `json:"parent_id"`
	Title     string     `json:"title"`
	Kind      string     `json:"kind"`
	Sort      int        `json:"sort"`
	UpdatedAt *time.Time `json:"updated_at"`
}

// GuideNode 指南节点详情（含正文）。
type GuideNode struct {
	ID            string     `json:"id"`
	ParentID      *string    `json:"parent_id"`
	Title         string     `json:"title"`
	Kind          string     `json:"kind"`
	Sort          int        `json:"sort"`
	Content       string     `json:"content"`
	ContentFormat string     `json:"content_format"`
	UpdatedAt     *time.Time `json:"updated_at"`
}

// BugReportStat 反馈状态统计项（status: 0 未处理 / 1 处理中 / 2 已处理 / 3 关闭）。
type BugReportStat struct {
	Status int `json:"status"`
	Count  int `json:"count"`
}
