package handler

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/database"
)

// SiteHandler 站点公开配置。
type SiteHandler struct {
	DB *database.DB
}

// SiteAnnouncement 站点公告（site_configs key=announcement）。
type SiteAnnouncement struct {
	Enabled   bool   `json:"enabled"`
	Text      string `json:"text"`
	Version   int    `json:"version"`
	UpdatedAt string `json:"updated_at"`
}

// defaultSiteAnnouncement 公告缺失/解析失败时的默认值（关闭、空文案）。
func defaultSiteAnnouncement() SiteAnnouncement {
	return SiteAnnouncement{Enabled: false, Text: "", Version: 0, UpdatedAt: ""}
}

func parseSiteAnnouncement(raw []byte) SiteAnnouncement {
	out := defaultSiteAnnouncement()
	if len(raw) == 0 || !json.Valid(raw) {
		return out
	}
	var wire struct {
		Enabled   bool            `json:"enabled"`
		Text      string          `json:"text"`
		Version   json.RawMessage `json:"version"`
		UpdatedAt json.RawMessage `json:"updated_at"`
	}
	if err := json.Unmarshal(raw, &wire); err != nil {
		return out
	}
	out.Enabled = wire.Enabled
	out.Text = wire.Text
	out.Version = parseAnnouncementVersion(wire.Version)
	out.UpdatedAt = parseAnnouncementUpdatedAt(wire.UpdatedAt)
	return out
}

// parseAnnouncementVersion 容忍数字或字符串（管理端写入形态未冻结）。
func parseAnnouncementVersion(raw json.RawMessage) int {
	if len(raw) == 0 {
		return 0
	}
	var n int
	if err := json.Unmarshal(raw, &n); err == nil {
		return n
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		if v, convErr := strconv.Atoi(strings.TrimSpace(s)); convErr == nil {
			return v
		}
	}
	return 0
}

// parseAnnouncementUpdatedAt 容忍字符串（RFC3339）或数字时间戳。
func parseAnnouncementUpdatedAt(raw json.RawMessage) string {
	if len(raw) == 0 || string(raw) == "null" {
		return ""
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		return s
	}
	return strings.TrimSpace(string(raw))
}

// SiteConfig 站点配置（theme/daily_quote/announcement；缺失或解析失败时回默认值）。
func (h *SiteHandler) SiteConfig(c *gin.Context) {
	theme := json.RawMessage(`{"mode":"auto","start":"10-01","end":"10-07"}`)
	if raw, err := h.DB.GetSiteConfig(c.Request.Context(), "theme.festival"); err == nil && json.Valid(raw) {
		theme = json.RawMessage(raw)
	}
	quote := json.RawMessage(`{"enabled":false,"provider":"dlystc"}`)
	if raw, err := h.DB.GetSiteConfig(c.Request.Context(), "daily_quote"); err == nil && json.Valid(raw) {
		quote = json.RawMessage(raw)
	}
	announcement := defaultSiteAnnouncement()
	if raw, err := h.DB.GetSiteConfig(c.Request.Context(), "announcement"); err == nil {
		announcement = parseSiteAnnouncement(raw)
	}
	c.Header("Cache-Control", "public, max-age=60")
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{
		"theme": theme, "daily_quote": quote, "announcement": announcement,
	}})
}
