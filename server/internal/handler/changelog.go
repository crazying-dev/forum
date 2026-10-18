package handler

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/database"
)

// ChangelogHandler 更新日志（公开读取）。
type ChangelogHandler struct {
	DB *database.DB
}

// ---- GET /changelogs ----

// List 更新日志列表（仅已发布且发布时间已到；page_size 默认 20，上限 100）。
func (h *ChangelogHandler) List(c *gin.Context) {
	page, pageSize := parsePage(c)
	items, total, err := h.DB.ListChangelogs(c.Request.Context(), page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true, "items": items, "total": total,
		"page": page, "page_size": pageSize,
	})
}

// ---- GET /changelogs/:id ----

// Detail 更新日志详情；不存在或未发布返回 404。
func (h *ChangelogHandler) Detail(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	item, err := h.DB.GetChangelog(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if item == nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "更新日志不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "item": item})
}
