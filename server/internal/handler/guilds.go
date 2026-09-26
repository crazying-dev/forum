package handler

import (
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/models"
)

// GuildsHandler 会馆/信息流/文章相关端点。
type GuildsHandler struct {
	DB       *database.DB
	Cache    *CacheSet
	Sessions *auth.SessionManager
}

// resolveGuild 按 slug 载入会馆；不存在或出错时已写入响应，返回 ok=false。
func (h *GuildsHandler) resolveGuild(c *gin.Context) (*models.GuildDetail, bool) {
	g, err := h.DB.GetGuildBySlug(c.Request.Context(), c.Param("slug"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return nil, false
	}
	if g == nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "会馆不存在"})
		return nil, false
	}
	return g, true
}

// feedPage 信息流分页（上限 50）。
func feedPage(c *gin.Context) (int, int) {
	page, pageSize := parsePage(c)
	if pageSize > 50 {
		pageSize = 50
	}
	return page, pageSize
}

// ---- GET /api/v1/guilds ----

// List 会馆列表（匿名缓存 30s，键 guilds:list）。
func (h *GuildsHandler) List(c *gin.Context) {
	if v, ok := h.Cache.Guilds.Get("guilds:list"); ok {
		c.Header("X-Cache", "HIT")
		c.JSON(http.StatusOK, v)
		return
	}
	guilds, err := h.DB.ListGuilds(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	resp := gin.H{"success": true, "guilds": guilds}
	h.Cache.Guilds.Set("guilds:list", resp, 30*time.Second)
	c.Header("X-Cache", "MISS")
	c.JSON(http.StatusOK, resp)
}

// ---- GET /api/v1/guilds/:slug ----

// Detail 会馆详情（匿名缓存 30s；登录用户实时附带 my_state）。
func (h *GuildsHandler) Detail(c *gin.Context) {
	slug := c.Param("slug")
	me := currentUserFromCookie(c, h.Sessions)
	key := "guilds:detail:" + slug
	if me == "" {
		if v, ok := h.Cache.Guilds.Get(key); ok {
			c.Header("X-Cache", "HIT")
			c.JSON(http.StatusOK, v)
			return
		}
	}
	g, ok := h.resolveGuild(c)
	if !ok {
		return
	}
	// my_state：未登录为 null，登录返回成员/馆长/待审状态
	var myState any
	if me != "" {
		st := models.GuildMyState{
			IsMember: h.DB.IsGuildMember(c.Request.Context(), g.ID, me),
			IsLeader: g.LeaderUserID != nil && *g.LeaderUserID == me,
		}
		if req, err := h.DB.GetPendingJoinRequest(c.Request.Context(), g.ID, me); err == nil && req != nil {
			st.HasPendingRequest = true
			st.RequestID = req.ID
		}
		myState = st
	}
	resp := gin.H{"success": true, "guild": g, "my_state": myState}
	if me == "" {
		h.Cache.Guilds.Set(key, resp, 30*time.Second)
		c.Header("X-Cache", "MISS")
	} else {
		c.Header("X-Cache", "BYPASS")
	}
	c.JSON(http.StatusOK, resp)
}

// ---- GET /api/v1/guilds/:slug/feed ----

// Feed 会馆信息流（帖子 + 文章）。
func (h *GuildsHandler) Feed(c *gin.Context) {
	g, ok := h.resolveGuild(c)
	if !ok {
		return
	}
	page, pageSize := feedPage(c)
	category := strings.TrimSpace(c.Query("category"))
	items, hasMore, err := h.DB.ListGuildFeed(c.Request.Context(), g.ID, page, pageSize, category)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "items": items, "has_more": hasMore,
		"page": page, "page_size": pageSize,
		"guild": gin.H{"id": g.ID, "slug": g.Slug, "name": g.Name, "theme_color": g.ThemeColor}})
}

// ---- GET /api/v1/guilds/:slug/members ----

// Members 会馆成员列表（公开，无缓存；page_size 默认 24）。
func (h *GuildsHandler) Members(c *gin.Context) {
	g, ok := h.resolveGuild(c)
	if !ok {
		return
	}
	page, pageSize := parsePageWithDefault(c, 24)
	members, hasMore, err := h.DB.ListGuildMembers(c.Request.Context(), g.ID, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "members": members, "page": page, "page_size": pageSize, "has_more": hasMore})
}

// ---- GET /api/v1/guilds/:slug/leader ----

// LeaderPage 馆长页（公开，无缓存；无馆长时 leader 为 null）。
func (h *GuildsHandler) LeaderPage(c *gin.Context) {
	pg, err := h.DB.GetGuildLeaderPage(c.Request.Context(), c.Param("slug"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if pg == nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "会馆不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "guild": pg.Guild, "leader": pg.Leader,
		"leader_bio": pg.LeaderBio, "content": pg.Content})
}

// ---- GET /api/v1/feed ----

// GlobalFeed 全站信息流：space=all/public/guild。
func (h *GuildsHandler) GlobalFeed(c *gin.Context) {
	space := c.DefaultQuery("space", "all")
	if space != "all" && space != "public" && space != "guild" {
		space = "all"
	}
	guildID, _ := strconv.ParseInt(c.Query("guild_id"), 10, 64)
	category := strings.TrimSpace(c.Query("category"))
	page, pageSize := feedPage(c)
	items, hasMore, err := h.DB.ListGlobalFeed(c.Request.Context(), space, guildID, category, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "items": items, "has_more": hasMore,
		"page": page, "page_size": pageSize, "space": space})
}

// ---- GET /api/v1/articles/:id ----

// Article 文章详情（先查存在性，不存在返回 404 且不自增浏览量；存在时浏览量 +1 并返回自增后的值）。
func (h *GuildsHandler) Article(c *gin.Context) {
	id := c.Param("id")
	a, err := h.DB.GetArticle(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if a == nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "文章不存在"})
		return
	}
	_ = h.DB.IncrementArticleViews(c.Request.Context(), id)
	a.Views++
	c.JSON(http.StatusOK, gin.H{"success": true, "article": a})
}

// ---- POST /api/v1/guilds/:slug/join ----

type guildJoinReq struct {
	Reason string `json:"reason"`
}

// Join 提交入馆申请。
func (h *GuildsHandler) Join(c *gin.Context) {
	uid := CurrentUser(c)
	g, ok := h.resolveGuild(c)
	if !ok {
		return
	}
	var req guildJoinReq
	_ = c.ShouldBindJSON(&req)
	reason := strings.TrimSpace(req.Reason)
	if len([]rune(reason)) > 500 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "申请理由不能超过500字"})
		return
	}
	// 已在任意会馆（含本馆）不可再申请
	if ms, err := h.DB.GetUserGuildMembership(c.Request.Context(), uid); err == nil && ms != nil {
		if ms.ID == g.ID {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "你已是该会馆成员"})
		} else {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "你已加入会馆「" + ms.Name + "」，请先退出"})
		}
		return
	}
	if pending, err := h.DB.GetPendingJoinRequest(c.Request.Context(), g.ID, uid); err == nil && pending != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "你已提交申请，请等待馆长审核"})
		return
	}
	id, err := h.DB.CreateJoinRequest(c.Request.Context(), g.ID, uid, reason)
	if err != nil {
		// 并发提交时命中部分唯一索引（每馆每人仅一条待审）：等同已有待审申请
		if database.IsUniqueViolation(err) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "你已提交申请，请等待馆长审核"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "申请提交失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "request_id": id, "message": "申请已提交，等待馆长审核"})
}

// ---- POST /api/v1/guilds/:slug/join/cancel ----

// CancelJoin 撤回待审申请。
func (h *GuildsHandler) CancelJoin(c *gin.Context) {
	uid := CurrentUser(c)
	g, ok := h.resolveGuild(c)
	if !ok {
		return
	}
	cancelled, err := h.DB.CancelJoinRequest(c.Request.Context(), g.ID, uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "操作失败"})
		return
	}
	if !cancelled {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "没有可撤回的申请"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "申请已撤回"})
}

// ---- POST /api/v1/guilds/:slug/leave ----

// Leave 退出会馆（馆长需先卸任）。
func (h *GuildsHandler) Leave(c *gin.Context) {
	uid := CurrentUser(c)
	g, ok := h.resolveGuild(c)
	if !ok {
		return
	}
	if !h.DB.IsGuildMember(c.Request.Context(), g.ID, uid) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "你还不是该会馆成员"})
		return
	}
	if g.LeaderUserID != nil && *g.LeaderUserID == uid {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "馆长需先卸任才能退出会馆"})
		return
	}
	left, err := h.DB.LeaveGuild(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "退出失败"})
		return
	}
	if !left {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "你还不是该会馆成员"})
		return
	}
	h.Cache.Guilds.DeletePrefix("guilds:")
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "已退出会馆"})
}
