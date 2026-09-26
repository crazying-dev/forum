package handler

import (
	"context"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
)

// PostsHandler 帖子/评论/收藏相关（含缓存）。
type PostsHandler struct {
	DB       *database.DB
	Cfg      *config.Config
	Cache    *CacheSet
	Mailer   *email.Sender
	Sessions *auth.SessionManager
}

// ---- GET /api/v1/posts ----

// List 帖子列表（缓存 posts:list:page:size:cat）。
func (h *PostsHandler) List(c *gin.Context) {
	page, pageSize := parsePage(c)
	if pageSize > 50 {
		pageSize = 50
	}
	category := c.Query("category")
	key := "posts:list:" + itoa(page) + ":" + itoa(pageSize) + ":" + category
	if v, ok := h.Cache.Posts.Get(key); ok {
		c.Header("X-Cache", "HIT")
		c.JSON(http.StatusOK, v)
		return
	}
	posts, err := h.DB.GetPostList(c.Request.Context(), page, pageSize, category)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	resp := gin.H{"success": true, "posts": posts, "page": page, "page_size": pageSize}
	h.Cache.Posts.Set(key, resp, 30*time.Second)
	c.Header("X-Cache", "MISS")
	c.JSON(http.StatusOK, resp)
}

// ---- GET /api/v1/posts/random ----

// Random 随机 200 条。
func (h *PostsHandler) Random(c *gin.Context) {
	posts, err := h.DB.GetRandomPosts(c.Request.Context(), 200)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts})
}

// ---- POST /api/v1/posts ----

type createPostReq struct {
	Title    string `json:"title" binding:"required"`
	Content  string `json:"content" binding:"required"`
	Category string `json:"category"`
	GuildID  *int64 `json:"guild_id"`
	// GuildUUID 会馆稳定标识（优先于 guild_id）
	GuildUUID string `json:"guild_uuid"`
}

// Create 发帖（可选 guild_uuid/guild_id：需为会馆成员，分类取自该馆配置）。
func (h *PostsHandler) Create(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req createPostReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	title := strings.TrimSpace(req.Title)
	if title == "" || len([]rune(title)) > 100 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "标题需1-100字符"})
		return
	}
	var (
		cat     string
		guildID *int64
	)
	if gu := strings.TrimSpace(req.GuildUUID); gu != "" {
		// guild_uuid 优先：按稳定标识反查数字 id
		id, err := h.DB.GetGuildIDByUUID(c.Request.Context(), gu)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
			return
		}
		if id == nil {
			c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "会馆不存在"})
			return
		}
		guildID = id
	} else if req.GuildID != nil && *req.GuildID > 0 {
		guildID = req.GuildID
	}
	if guildID != nil {
		// 会馆帖：仅成员可发，分类自会馆配置取值
		if !h.DB.IsGuildMember(c.Request.Context(), *guildID, uid) {
			c.JSON(http.StatusForbidden, gin.H{"success": false, "message": "你还不是该会馆成员，无法发帖"})
			return
		}
		cat = h.DB.ResolveGuildCategory(c.Request.Context(), *guildID, strings.TrimSpace(req.Category))
	} else {
		cat = normalizeCategory(req.Category)
	}
	postID, err := h.DB.SendPost(c.Request.Context(), uid, title, req.Content, cat, guildID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "发布失败"})
		return
	}
	// 粉丝通知（异步）
	go h.notifyFollowers(uid, postID, title)
	h.Cache.Posts.DeletePrefix("posts:list:")
	c.JSON(http.StatusCreated, gin.H{"success": true, "id": postID})
}

func (h *PostsHandler) notifyFollowers(userID, postID, title string) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	emails, err := h.DB.GetFollowerEmails(ctx, userID, 5000)
	if err != nil || len(emails) == 0 {
		return
	}
	plain := "你的关注者 " + userID + " 发布了新帖《" + title + "》\n" + "https://" + h.Cfg.PublicBaseURL + "/post/" + postID
	html := email.BuildHTML("新帖通知", "关注的人发布了新帖",
		[]string{"你的关注者发布了新帖", "<strong>" + title + "</strong>", "点击查看详情"},
		"查看帖子", "https://"+h.Cfg.PublicBaseURL+"/post/"+postID, "")
	// 分批 100 封
	for start := 0; start < len(emails); start += 100 {
		end := start + 100
		if end > len(emails) {
			end = len(emails)
		}
		_, _ = h.Mailer.Send("【妖精论坛】你的关注者发布了新帖", plain, emails[start:end], html)
	}
	log.Printf("[POST] 发帖通知已发送 %d 位粉丝", len(emails))
}

// ---- GET /api/v1/posts/:id ----

// Detail 帖子详情（匿名缓存 post:detail:ID；登录用户实时返回含个人状态）。
func (h *PostsHandler) Detail(c *gin.Context) {
	id := c.Param("id")
	me := currentUserFromCookie(c, h.Sessions)
	key := "post:detail:" + id
	if me == "" {
		if v, ok := h.Cache.PostDetail.Get(key); ok {
			c.Header("X-Cache", "HIT")
			c.JSON(http.StatusOK, v)
			return
		}
	}
	post, err := h.DB.GetPost(c.Request.Context(), id)
	if err != nil || post == nil || post.Status != 1 {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "帖子不存在"})
		return
	}
	_ = h.DB.IncrementPostViews(c.Request.Context(), id)
	post.Views++

	liked, favorited := false, false
	if me != "" {
		liked = h.DB.HasLikedPost(c.Request.Context(), id, me)
		favorited = h.DB.HasFavoritedPost(c.Request.Context(), id, me)
	}
	// 评论（附带，取前 50）
	comments, _ := h.DB.GetPostComments(c.Request.Context(), id, 1, 50)
	if me != "" {
		markCommentLikedByMe(h.DB, c.Request.Context(), me, comments)
	}
	resp := gin.H{"success": true, "post": post, "comments": comments, "liked": liked, "favorited": favorited}
	if me == "" {
		h.Cache.PostDetail.Set(key, resp, 60*time.Second)
		c.Header("X-Cache", "MISS")
	} else {
		// 含个人点赞/收藏状态，不走共享缓存
		c.Header("X-Cache", "BYPASS")
	}
	c.JSON(http.StatusOK, resp)
}

// ---- POST /api/v1/posts/:id/like ----

// Like 点赞切换。
func (h *PostsHandler) Like(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	id := c.Param("id")
	liked, likes, err := h.DB.LikePost(c.Request.Context(), id, uid)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "操作失败"})
		return
	}
	h.Cache.PostDetail.Delete("post:detail:" + id)
	h.Cache.Posts.DeletePrefix("posts:list:")
	c.JSON(http.StatusOK, gin.H{"success": true, "liked": liked, "likes": likes})
}

// ---- POST /api/v1/posts/:id/favorite ----

// Favorite 收藏切换。
func (h *PostsHandler) Favorite(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	id := c.Param("id")
	favorited, err := h.DB.ToggleFavorite(c.Request.Context(), id, uid)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "操作失败"})
		return
	}
	h.Cache.PostDetail.Delete("post:detail:" + id)
	c.JSON(http.StatusOK, gin.H{"success": true, "favorited": favorited})
}

// ---- POST /api/v1/posts/:id/delete ----

// Delete 删除帖子（仅作者）。
func (h *PostsHandler) Delete(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	id := c.Param("id")
	ok, err := h.DB.DeletePost(c.Request.Context(), id, uid)
	if err != nil || !ok {
		c.JSON(http.StatusForbidden, gin.H{"success": false, "message": "无权限删除该帖子"})
		return
	}
	h.Cache.PostDetail.Delete("post:detail:" + id)
	h.Cache.Posts.DeletePrefix("posts:list:")
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ---- POST /api/v1/posts/:id/report ----

type reportPostReq struct {
	Reason string `json:"reason" binding:"required"`
	Detail string `json:"detail"`
}

// Report 举报帖子。
func (h *PostsHandler) Report(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	id := c.Param("id")
	var req reportPostReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if len([]rune(req.Detail)) > 500 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "详情不能超过500字"})
		return
	}
	if err := h.DB.ReportPost(c.Request.Context(), id, uid, req.Reason, req.Detail); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "举报失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// AuthRequired 会话校验。
func (h *PostsHandler) AuthRequired() gin.HandlerFunc {
	return func(c *gin.Context) {
		token, _ := c.Cookie(cookieName)
		if token == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
			return
		}
		userID, err := h.Sessions.Validate(c.Request.Context(), token)
		if err != nil || userID == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"success": false, "message": "登录已过期，请重新登录"})
			return
		}
		c.Set("userID", userID)
		c.Next()
	}
}
