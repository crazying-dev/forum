package handler

import (
	"context"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

// ---- GET /api/v1/search ----

// Search 搜索帖子/用户（缓存 120s）。
func (h *PostsHandler) Search(c *gin.Context) {
	k := strings.TrimSpace(c.Query("k"))
	if len([]rune(k)) < 1 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "关键词至少1个字符"})
		return
	}
	typ := c.DefaultQuery("type", "both")
	if typ != "posts" && typ != "users" && typ != "both" {
		typ = "both"
	}
	page, pageSize := parsePage(c)
	key := "search:" + k + ":" + typ + ":" + itoa(page) + ":" + itoa(pageSize)
	if v, ok := h.Cache.Search.Get(key); ok {
		c.Header("X-Cache", "HIT")
		c.JSON(http.StatusOK, v)
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp := gin.H{"success": true, "keyword": k, "page": page, "page_size": pageSize}
	if typ == "posts" || typ == "both" {
		posts, total, hasMore, err := h.DB.SearchPosts(ctx, k, page, pageSize)
		if err == nil {
			resp["posts"] = posts
			resp["posts_total"] = total
			resp["posts_has_more"] = hasMore
		}
	}
	if typ == "users" || typ == "both" {
		users, total, hasMore, err := h.DB.SearchUsers(ctx, k, page, pageSize)
		if err == nil {
			resp["users"] = users
			resp["users_total"] = total
			resp["users_has_more"] = hasMore
		}
	}
	h.Cache.Search.Set(key, resp, 120*time.Second)
	c.Header("X-Cache", "MISS")
	c.JSON(http.StatusOK, resp)
}
