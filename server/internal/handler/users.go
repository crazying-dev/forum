package handler

import (
	"context"
	"net/http"
	"strconv"
	"strings"

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
	posts, err := h.DB.GetUserPosts(c.Request.Context(), id, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts, "page": page, "page_size": pageSize})
}

// ---- PATCH /api/v1/users/me ----

type updateProfileReq struct {
	Name     *string `json:"Name"`
	Gender   *int    `json:"gender"`
	Age      *string `json:"age"`
	Intro    *string `json:"intro"`
	Avatar   *string `json:"avatar"`
	Password *string `json:"password"`
}

// UpdateMe 修改资料。
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
		fields["avatar"] = *req.Avatar
	}
	if req.Password != nil && *req.Password != "" {
		hash, err := auth.HashPassword(*req.Password)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
			return
		}
		fields["password"] = hash
	}
	if err := h.DB.UpdateUserProfile(c.Request.Context(), uid, fields); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "更新失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
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
		users []models.UserBrief
		err   error
	)
	viewer := h.CurrentUserFromCookie(c)
	if kind == "following" {
		users, err = h.DB.GetFollowingList(c.Request.Context(), id, viewer, page, pageSize)
	} else {
		users, err = h.DB.GetFollowerList(c.Request.Context(), id, viewer, page, pageSize)
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "users": users, "page": page, "page_size": pageSize})
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
	posts, err := h.DB.GetUserFavorites(c.Request.Context(), id, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts, "page": page, "page_size": pageSize})
}

// parsePage 解析 page/page_size。
func parsePage(c *gin.Context) (int, int) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
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
