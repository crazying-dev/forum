package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/database"
)

// GuidesHandler 指南读取（公开接口）。
type GuidesHandler struct {
	DB *database.DB
}

// ---- GET /api/v1/guides ----

// List 指南节点列表（不含正文；空列表返回 []）。
func (h *GuidesHandler) List(c *gin.Context) {
	nodes, err := h.DB.ListGuideNodes(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"nodes": nodes}})
}

// ---- GET /api/v1/guides/:id ----

// Detail 指南节点详情（含正文）；不存在返回 404。
func (h *GuidesHandler) Detail(c *gin.Context) {
	node, err := h.DB.GetGuideNode(c.Request.Context(), c.Param("id"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if node == nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "指南不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"node": node}})
}
