package handler

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/database"
)

// embedMaxIDs 引用卡片每类型最多解析的 id 数。
const embedMaxIDs = 30

// EmbedsHandler 引用卡片批量取值（公开）。
type EmbedsHandler struct {
	DB *database.DB
}

// parseIDList 解析逗号分隔 id：去空并截断到上限。
func parseIDList(raw string) []string {
	ids := []string{}
	for _, part := range strings.Split(raw, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		ids = append(ids, part)
		if len(ids) >= embedMaxIDs {
			break
		}
	}
	return ids
}

// ---- GET /api/v1/embeds ----

// List 批量取引用卡片数据（users/posts/articles 均为逗号分隔 id，查不到的 id 省略）。
func (h *EmbedsHandler) List(c *gin.Context) {
	ctx := c.Request.Context()
	users, err := h.DB.GetEmbedUsers(ctx, parseIDList(c.Query("users")))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	posts, err := h.DB.GetEmbedPosts(ctx, parseIDList(c.Query("posts")))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	articles, err := h.DB.GetEmbedArticles(ctx, parseIDList(c.Query("articles")))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "users": users, "posts": posts, "articles": articles})
}
