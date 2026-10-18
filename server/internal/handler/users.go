package handler

import (
	"context"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/models"
)

// guildProfile 用户会馆概要（未入馆返回 nil 与 false）。
func (h *AuthHandler) guildProfile(ctx context.Context, userID string) (*models.GuildMembership, bool) {
	ms, err := h.DB.GetUserGuildMembership(ctx, userID)
	if err != nil || ms == nil {
		return nil, false
	}
	return ms, ms.IsLeader
}

// isDeletedUser 用户是否已注销（不存在返回 false）。
func (h *AuthHandler) isDeletedUser(ctx context.Context, id string) bool {
	u, err := h.DB.GetUserByID(ctx, id)
	return err == nil && u.DeletedAt != nil
}

// ---- /api/v1/users/me ----

// Me 当前登录用户。
func (h *AuthHandler) Me(c *gin.Context) {
	uid := h.CurrentUserFromCookie(c)
	if uid == "" {
		c.JSON(http.StatusOK, gin.H{"success": false, "message": "未登录"})
		return
	}
	u, err := h.DB.GetUserByID(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	guild, isLeader := h.guildProfile(c.Request.Context(), uid)
	c.JSON(http.StatusOK, gin.H{"success": true, "user": u, "guild": guild, "is_leader": isLeader})
}

// ---- GET /api/v1/users/:id ----

// UserProfile 用户主页。
func (h *AuthHandler) UserProfile(c *gin.Context) {
	id := c.Param("id")
	u, err := h.DB.GetUserByID(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	if u.DeletedAt != nil {
		// 已注销账号：仅下发最小档案（沿用原 user 结构并附加 deleted 标志）
		profile := *u
		profile.Email = ""
		profile.Deleted = true
		c.JSON(http.StatusOK, gin.H{"success": true, "user": profile, "stats": models.Stats{}, "follow_stats": models.FollowStats{},
			"is_following": false, "is_self": false, "guild": nil, "is_leader": false})
		return
	}
	stats, _ := h.DB.GetUserStats(c.Request.Context(), id)
	followStats, _ := h.DB.GetFollowStats(c.Request.Context(), id)
	me := h.CurrentUserFromCookie(c)
	isSelf := me != "" && me == id
	isFollowing := false
	if me != "" && !isSelf {
		isFollowing = h.DB.IsFollowing(c.Request.Context(), me, id)
	}
	// 公开信息脱敏（email 仅本人可见）
	profile := models.UserProfile{
		User:        *u,
		Stats:       stats,
		FollowStats: followStats,
		IsFollowing: isFollowing,
		IsSelf:      isSelf,
	}
	if !isSelf {
		profile.User.Email = ""
	}
	guild, isLeader := h.guildProfile(c.Request.Context(), id)
	c.JSON(http.StatusOK, gin.H{"success": true, "user": profile.User, "stats": stats, "follow_stats": followStats, "is_following": isFollowing, "is_self": isSelf,
		"guild": guild, "is_leader": isLeader})
}

// ---- GET /api/v1/users/:id/posts ----

// UserPosts 用户帖子。
func (h *AuthHandler) UserPosts(c *gin.Context) {
	id := c.Param("id")
	page, pageSize := parsePage(c)
	if h.isDeletedUser(c.Request.Context(), id) {
		c.JSON(http.StatusOK, gin.H{"success": true, "posts": []models.PostListItem{}, "page": page, "page_size": pageSize})
		return
	}
	viewer := h.CurrentUserFromCookie(c)
	posts, err := h.DB.GetUserPosts(c.Request.Context(), id, viewer, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts, "page": page, "page_size": pageSize})
}

// ---- PATCH /api/v1/users/me ----

type updateProfileReq struct {
	Name            *string `json:"Name"`
	Gender          *int    `json:"gender"`
	Age             *string `json:"age"`
	Intro           *string `json:"intro"`
	Avatar          *string `json:"avatar"`
	Password        *string `json:"password"`
	CurrentPassword *string `json:"current_password"`
}

// UpdateMe 修改资料（白名单字段，灵力值 spirit / 签到日期 last_sign_in 不可由客户端修改）。
func (h *AuthHandler) UpdateMe(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req updateProfileReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	fields := map[string]any{}
	if req.Name != nil {
		clean := database.StripEasterEgg(*req.Name)
		if len([]rune(clean)) < 2 || len([]rune(clean)) > 20 {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "用户名需2-20个字符"})
			return
		}
		if strings.HasPrefix(strings.TrimSpace(clean), "已注销") {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "该用户名为保留名称"})
			return
		}
		fields["name"] = *req.Name
	}
	if req.Gender != nil {
		fields["gender"] = *req.Gender
	}
	if req.Age != nil {
		fields["age"] = *req.Age
	}
	if req.Intro != nil {
		fields["intro"] = *req.Intro
	}
	if req.Avatar != nil && *req.Avatar != "" {
		avatar := strings.TrimSpace(*req.Avatar)
		if !validAvatarURL(avatar) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "头像地址不合法"})
			return
		}
		fields["avatar"] = avatar
	}
	passwordChanged := false
	if req.Password != nil && *req.Password != "" {
		// 改密必须提供当前密码：防止会话被劫持后直接接管账号
		if req.CurrentPassword == nil || strings.TrimSpace(*req.CurrentPassword) == "" {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请输入当前密码"})
			return
		}
		if len(*req.Password) < 8 {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码至少8位"})
			return
		}
		if !hasLetterAndDigit(*req.Password) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码需包含字母和数字"})
			return
		}
		currentHash, err := h.DB.GetUserPasswordHash(c.Request.Context(), uid)
		if err != nil || !auth.CheckPassword(currentHash, *req.CurrentPassword) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "当前密码错误"})
			return
		}
		hash, err := auth.HashPassword(*req.Password)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
			return
		}
		fields["password"] = hash
		fields["password_changed_at"] = time.Now()
		passwordChanged = true
	}
	if err := h.DB.UpdateUserProfile(c.Request.Context(), uid, fields); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "更新失败"})
		return
	}
	if passwordChanged {
		// 改密后吊销全部旧会话，并为当前浏览器签发新会话（阻止其他设备继续使用旧会话）
		_ = h.Sessions.DeleteByUserID(c.Request.Context(), uid)
		h.issueSession(c, uid)
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// validAvatarURL 校验头像地址：允许站内相对路径或 http/https；拒绝 data/javascript/svg 等危险形态。
func validAvatarURL(raw string) bool {
	raw = strings.TrimSpace(raw)
	if raw == "" || len(raw) > 2048 {
		return false
	}
	lower := strings.ToLower(raw)
	if strings.HasPrefix(lower, "data:") || strings.HasPrefix(lower, "javascript:") || strings.HasPrefix(lower, "vbscript:") {
		return false
	}
	if strings.HasPrefix(raw, "/") {
		return strings.HasPrefix(raw, "/avatar/") || strings.HasPrefix(raw, "/static/img/avatars/") ||
			strings.HasPrefix(raw, "/ov2/api/media/") || strings.HasPrefix(raw, "/api/v1/media/")
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" || u.User != nil {
		return false
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return false
	}
	if strings.HasSuffix(strings.ToLower(u.Path), ".svg") {
		return false
	}
	return true
}

// ---- POST /api/v1/users/me/sign-in ----

// SignIn 每日签到（当日未签到则灵力 +10；重复签到 409）。
func (h *AuthHandler) SignIn(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	spirit, lastSignIn, signed, err := h.DB.SignInToday(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "签到失败"})
		return
	}
	if !signed {
		c.JSON(http.StatusConflict, gin.H{"success": false, "message": "今日已签到"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"spirit": spirit, "last_sign_in": lastSignIn}})
}

// ---- POST /api/v1/users/:id/follow ----

// ToggleFollow 关注/取消。
func (h *AuthHandler) ToggleFollow(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	target := c.Param("id")
	if h.isDeletedUser(c.Request.Context(), target) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "该账号已注销"})
		return
	}
	following, err := h.DB.ToggleFollow(c.Request.Context(), uid, target)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "操作失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "following": following})
}

// ---- GET /api/v1/users/:id/following / followers ----

func (h *AuthHandler) Following(c *gin.Context) {
	h.followList(c, "following")
}

func (h *AuthHandler) Followers(c *gin.Context) {
	h.followList(c, "followers")
}

func (h *AuthHandler) followList(c *gin.Context, kind string) {
	id := c.Param("id")
	page, pageSize := parsePage(c)
	var (
		users   []models.UserBrief
		hasMore bool
		err     error
	)
	viewer := h.CurrentUserFromCookie(c)
	if kind == "following" {
		users, hasMore, err = h.DB.GetFollowingList(c.Request.Context(), id, viewer, page, pageSize)
	} else {
		users, hasMore, err = h.DB.GetFollowerList(c.Request.Context(), id, viewer, page, pageSize)
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "users": users, "page": page, "page_size": pageSize, "has_more": hasMore})
}

// ---- GET /api/v1/users/:id/mutual ----

// Mutual 共同关注（viewer 来自 cookie；匿名或看自己时返回空列表）。
func (h *AuthHandler) Mutual(c *gin.Context) {
	id := c.Param("id")
	page, pageSize := parsePage(c)
	users := []models.UserBrief{}
	hasMore := false
	if viewer := h.CurrentUserFromCookie(c); viewer != "" && viewer != id {
		var err error
		users, hasMore, err = h.DB.GetMutualList(c.Request.Context(), id, viewer, page, pageSize)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
			return
		}
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "users": users, "page": page, "page_size": pageSize, "has_more": hasMore})
}

// ---- GET /api/v1/users/me/replies ----

// MyReplies 我收到的回复。
func (h *AuthHandler) MyReplies(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	page, pageSize := parsePage(c)
	replies, total, err := h.DB.GetRepliesToMyComments(c.Request.Context(), uid, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "replies": replies, "total": total})
}

// ---- GET /api/v1/users/:id/comments ----

// UserComments 用户发表的评论。
func (h *AuthHandler) UserComments(c *gin.Context) {
	id := c.Param("id")
	page, pageSize := parsePage(c)
	if h.isDeletedUser(c.Request.Context(), id) {
		c.JSON(http.StatusOK, gin.H{"success": true, "comments": []models.ReplyItem{}, "total": 0, "page": page, "page_size": pageSize})
		return
	}
	comments, total, err := h.DB.GetUserComments(c.Request.Context(), id, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "comments": comments, "total": total, "page": page, "page_size": pageSize})
}

// ---- GET /api/v1/users/:id/favorites ----

// UserFavorites 用户收藏。
func (h *AuthHandler) UserFavorites(c *gin.Context) {
	id := c.Param("id")
	page, pageSize := parsePage(c)
	if h.isDeletedUser(c.Request.Context(), id) {
		c.JSON(http.StatusOK, gin.H{"success": true, "posts": []models.PostListItem{}, "page": page, "page_size": pageSize})
		return
	}
	posts, err := h.DB.GetUserFavorites(c.Request.Context(), id, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts, "page": page, "page_size": pageSize})
}

// parsePage 解析 page/page_size（默认每页 20，上限 100）。
func parsePage(c *gin.Context) (int, int) {
	return parsePageWithDefault(c, 20)
}

// parsePageWithDefault 解析 page/page_size（默认值可定制，上限 100）。
func parsePageWithDefault(c *gin.Context, defaultSize int) (int, int) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", strconv.Itoa(defaultSize)))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = defaultSize
	}
	return page, pageSize
}

// normalizeCategory 分类白名单（公共广场：英文 + 旧中文）。
func normalizeCategory(s string) string {
	s = strings.TrimSpace(s)
	allowed := map[string]bool{
		"general": true, "talk": true, "question": true, "share": true, "creative": true,
		"求助": true, "创意": true,
	}
	if s == "" {
		return "general"
	}
	if !allowed[s] {
		return "general"
	}
	return s
}
