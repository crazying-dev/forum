package handler

import (
	"encoding/json"
	"net/http"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/database"
)

// SiteHandler 站点公开配置。
type SiteHandler struct {
	DB *database.DB
}

// SiteConfig 站点配置（theme/daily_quote；缺失或解析失败时回默认值）。
func (h *SiteHandler) SiteConfig(c *gin.Context) {
	theme := json.RawMessage(`{"mode":"auto","start":"10-01","end":"10-07"}`)
	if raw, err := h.DB.GetSiteConfig(c.Request.Context(), "theme.festival"); err == nil && json.Valid(raw) {
		theme = json.RawMessage(raw)
	}
	quote := json.RawMessage(`{"enabled":false,"provider":"dlystc"}`)
	if raw, err := h.DB.GetSiteConfig(c.Request.Context(), "daily_quote"); err == nil && json.Valid(raw) {
		quote = json.RawMessage(raw)
	}
	c.Header("Cache-Control", "public, max-age=60")
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"theme": theme, "daily_quote": quote}})
}
