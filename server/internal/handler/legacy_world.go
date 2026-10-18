package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/legacy"
)

// legacyWorldLister 世界频道读取能力（*legacy.Service 实现；测试可注入 fake）。
type legacyWorldLister interface {
	WorldList(ctx context.Context, since string, limit int) ([]legacy.WorldMessage, error)
}

// legacyWorldSender 世界频道发送能力。
type legacyWorldSender interface {
	WorldSend(ctx context.Context, user *legacy.LegacyUser, content string, parentID *int64) (*legacy.WorldMessage, error)
}

// legacyWorldHandler 世界频道兼容 handler（裸数组响应）。
type legacyWorldHandler struct {
	lister      legacyWorldLister
	sender      legacyWorldSender
	requireUser gin.HandlerFunc
}

func newLegacyWorldHandler(lister legacyWorldLister, sender legacyWorldSender, requireUser gin.HandlerFunc) *legacyWorldHandler {
	return &legacyWorldHandler{lister: lister, sender: sender, requireUser: requireUser}
}

// All GET /api/World/ALL 与 /api/world/ALL：裸 JSON 数组（最多 100，支持 since）。
func (h *legacyWorldHandler) All(c *gin.Context) {
	limit := 100
	if raw := strings.TrimSpace(c.Query("limit")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 && n <= 100 {
			limit = n
		}
	}
	messages, err := h.lister.WorldList(c.Request.Context(), c.Query("since"), limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	// 契约：世界频道 GET 为裸数组，Cache-Control max-age=2。
	c.Header("Cache-Control", "max-age=2")
	c.JSON(http.StatusOK, messages)
}

// Send POST /api/World/Send 与 /api/world/Send：纯文本 500 字/2 秒。
func (h *legacyWorldHandler) Send(c *gin.Context) {
	user := legacyUserFrom(c)
	if user == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req struct {
		Content  string          `json:"content"`
		ParentID json.RawMessage `json:"parent_id"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	content := strings.TrimSpace(req.Content)
	if content == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "内容不能为空"})
		return
	}
	if len([]rune(content)) > 500 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "内容过长（最多500字）"})
		return
	}
	parentID := parseLegacyParentID(req.ParentID)
	msg, err := h.sender.WorldSend(c.Request.Context(), user, content, parentID)
	if err != nil {
		if errors.Is(err, legacy.ErrWorldTooFast) {
			c.JSON(http.StatusTooManyRequests, gin.H{"success": false, "message": err.Error()})
			return
		}
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "发送失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "发送成功", "msg": msg})
}

// parseLegacyParentID 兼容旧客户端的数字或字符串 parent_id；非法值忽略。
func parseLegacyParentID(raw json.RawMessage) *int64 {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var num int64
	if err := json.Unmarshal(raw, &num); err == nil && num > 0 {
		return &num
	}
	var text string
	if err := json.Unmarshal(raw, &text); err == nil {
		if n, err := strconv.ParseInt(strings.TrimSpace(text), 10, 64); err == nil && n > 0 {
			return &n
		}
	}
	return nil
}
