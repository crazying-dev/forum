package handler

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"html"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/sanitize"
	"yj-forum/server/internal/sse"
)

const (
	// worldSnapshotLimit SSE 首包消息数。
	worldSnapshotLimit = 200
	// worldReplayLimit Last-Event-ID 补发上限。
	worldReplayLimit = 500
	// worldHeartbeatInterval SSE 心跳间隔。
	worldHeartbeatInterval = 15 * time.Second
	// worldClientBuffer SSE 订阅缓冲（慢客户端丢弃由 Hub 处理）。
	worldClientBuffer = 256
	// worldMaxContentRunes 纯文本长度上限。
	worldMaxContentRunes = 2000
	// worldMaxImages 单条消息图片上限。
	worldMaxImages = 9
	// worldMaxBodyBytes 请求体上限（防超大 DOM 拖垮净化）。
	worldMaxBodyBytes = 256 << 10
)

var (
	errWorldContentEmpty   = errors.New("内容不能为空")
	errWorldContentTooLong = errors.New("内容过长（最多2000字）")
	errWorldEmbedForbidden = errors.New("世界频道不支持引用卡片")
	errWorldTooManyImages  = errors.New("图片最多 9 张")
)

// WorldHandler 世界频道（/world/messages 列表与发布、/world/stream SSE）。
// Hub 由进程内 SSE Hub 注入；poller 向 topic "world" 广播，handler 只订阅。
type WorldHandler struct {
	DB       *database.DB
	Cfg      *config.Config
	Hub      *sse.Hub
	Sessions *auth.SessionManager
}

// RegisterWorldRoutes 注册世界频道路由（由 router.go 在 /ov2/api 与 /api/v1 两个 group 各调用一次）。
//
//	GET  /world/messages  公开列表（before_id / after_id / limit）
//	POST /world/messages  登录发布（content_html / parent_id?）
//	GET  /world/stream    公开 SSE（last_id 或 Last-Event-ID）
func RegisterWorldRoutes(api *gin.RouterGroup, h *WorldHandler) {
	if api == nil || h == nil {
		return
	}
	api.GET("/world/messages", h.ListMessages)
	api.POST("/world/messages", h.authRequired(), h.CreateMessage)
	api.GET("/world/stream", h.Stream)
}

// authRequired 与会话中间件语义一致（复用 AuthHandler.AuthRequired，避免两份校验逻辑）。
func (h *WorldHandler) authRequired() gin.HandlerFunc {
	if h.Sessions == nil {
		return func(c *gin.Context) {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		}
	}
	return (&AuthHandler{Sessions: h.Sessions}).AuthRequired()
}

// ---- GET /world/messages ----

// ListMessages 公开消息列表：after_id 增量（升序） / before_id 历史（降序） / 缺省最新一页（降序）。
func (h *WorldHandler) ListMessages(c *gin.Context) {
	if h.DB == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务不可用"})
		return
	}
	beforeID := worldParseID(c.Query("before_id"))
	afterID := worldParseID(c.Query("after_id"))
	limit := database.NormalizeWorldLimit(worldParseLimit(c.Query("limit")))

	items, hasMore, err := h.DB.ListWorldMessages(c.Request.Context(), beforeID, afterID, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success":        true,
		"items":          items,
		"has_more":       hasMore,
		"next_before_id": worldNextBeforeID(items, hasMore),
	})
}

// ---- POST /world/messages ----

type worldCreateReq struct {
	ContentHTML string `json:"content_html"`
	ParentID    *int64 `json:"parent_id"`
}

// CreateMessage 发布消息：富文本净化、禁 data-embed、纯文本 1-2000 字、最多 9 张图。
// 广播由 poller 统一完成（避免 handler/poller 双写导致重复推送）。
func (h *WorldHandler) CreateMessage(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	if h.DB == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务不可用"})
		return
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, worldMaxBodyBytes)
	var req worldCreateReq
	if err := c.ShouldBindJSON(&req); err != nil {
		var tooLarge *http.MaxBytesError
		if errors.As(err, &tooLarge) {
			c.JSON(http.StatusRequestEntityTooLarge, gin.H{"success": false, "message": "内容过长"})
			return
		}
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}

	content, err := validateWorldContent(req.ContentHTML)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": err.Error()})
		return
	}
	var parentID *int64
	if req.ParentID != nil && *req.ParentID > 0 {
		parentID = req.ParentID
	}

	id, err := h.DB.CreateWorldMessage(c.Request.Context(), uid, content, "html", parentID)
	switch {
	case errors.Is(err, database.ErrWorldRateLimited):
		c.JSON(http.StatusTooManyRequests, gin.H{"success": false, "message": "发言太快，请稍后再试"})
		return
	case errors.Is(err, database.ErrWorldUserNotFound):
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	case err != nil:
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "发送失败"})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"success": true, "id": id})
}

// validateWorldContent 净化并校验消息正文，返回可入库的 HTML。
// 规则：禁 data-embed；最多 9 张 <img>；纯文本（去标签/反转义后）1-2000 字。
func validateWorldContent(raw string) (string, error) {
	if len(raw) > worldMaxBodyBytes {
		return "", errWorldContentTooLong
	}
	sanitized := sanitize.SanitizeRichContent(raw)
	lower := strings.ToLower(sanitized)
	if strings.Contains(lower, "data-embed") {
		return "", errWorldEmbedForbidden
	}
	if strings.Count(lower, "<img") > worldMaxImages {
		return "", errWorldTooManyImages
	}
	plain := strings.TrimSpace(html.UnescapeString(sanitize.StripTagsAndTrim(sanitized)))
	n := utf8.RuneCountInString(plain)
	if n == 0 {
		return "", errWorldContentEmpty
	}
	if n > worldMaxContentRunes {
		return "", errWorldContentTooLong
	}
	return sanitized, nil
}

// ---- GET /world/stream ----

// Stream SSE：首包 hello + 历史消息（无游标 200 条 / Last-Event-ID 补发最多 500 条），
// 之后转发 poller 广播的 message，每 15 秒心跳。
func (h *WorldHandler) Stream(c *gin.Context) {
	if h.DB == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务不可用"})
		return
	}
	ctx := c.Request.Context()
	resumeID := worldResumeID(c)
	resumed := resumeID > 0

	var (
		msgs []database.WorldMessage
		err  error
	)
	if resumed {
		msgs, err = h.DB.ListWorldAfterID(ctx, resumeID, worldReplayLimit)
	} else {
		msgs, _, err = h.DB.ListWorldMessages(ctx, 0, 0, worldSnapshotLimit)
		// 列表为降序；SSE 按时间正序推送，客户端可顺序追加。
		for i, j := 0, len(msgs)-1; i < j; i, j = i+1, j-1 {
			msgs[i], msgs[j] = msgs[j], msgs[i]
		}
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}

	c.Header("Content-Type", "text/event-stream; charset=utf-8")
	c.Header("Cache-Control", "no-cache, no-transform")
	c.Header("Connection", "keep-alive")
	c.Header("X-Accel-Buffering", "no")
	c.Status(http.StatusOK)

	var (
		client *sse.Client
		events <-chan sse.Event
		done   <-chan struct{}
	)
	if h.Hub != nil {
		client = h.Hub.Subscribe("world", worldClientBuffer)
		events = client.Ch
		done = client.Done()
		defer h.Hub.Unsubscribe("world", client)
	}

	write := func(id, event string, data any) error {
		if err := worldWriteSSE(c.Writer, id, event, data); err != nil {
			return err
		}
		c.Writer.Flush()
		return nil
	}

	// 断线重连提示（生产稍长，降低重连风暴）。
	retryMS := 2000
	if h.Cfg != nil && h.Cfg.AppEnv == "prod" {
		retryMS = 3000
	}
	if _, err := fmt.Fprintf(c.Writer, "retry: %d\n\n", retryMS); err != nil {
		return
	}
	c.Writer.Flush()

	hello := gin.H{
		"server_time":       time.Now().UTC().Format(time.RFC3339),
		"heartbeat_seconds": int(worldHeartbeatInterval / time.Second),
		"resumed":           resumed,
		"count":             len(msgs),
	}
	if resumed && len(msgs) == worldReplayLimit {
		// 补发达到上限：提示客户端可能仍有缺口，可整页重载。
		hello["truncated"] = true
	}
	if err := write("", "hello", hello); err != nil {
		return
	}
	for _, m := range msgs {
		if err := write(strconv.FormatInt(m.ID, 10), "message", m); err != nil {
			return
		}
	}

	ticker := time.NewTicker(worldHeartbeatInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-done:
			return
		case ev := <-events:
			if err := write(ev.ID, ev.Type, ev.Data); err != nil {
				return
			}
		case t := <-ticker.C:
			if err := write("", "heartbeat", gin.H{"time": t.UTC().Format(time.RFC3339)}); err != nil {
				return
			}
		}
	}
}

// worldWriteSSE 按 SSE 帧格式写入一个事件。data 为 JSON（不含裸换行）。
func worldWriteSSE(w io.Writer, id, event string, data any) error {
	payload, err := json.Marshal(data)
	if err != nil {
		return err
	}
	var buf bytes.Buffer
	if id != "" {
		buf.WriteString("id: ")
		buf.WriteString(id)
		buf.WriteByte('\n')
	}
	if event != "" {
		buf.WriteString("event: ")
		buf.WriteString(event)
		buf.WriteByte('\n')
	}
	buf.WriteString("data: ")
	buf.Write(payload)
	buf.WriteString("\n\n")
	_, err = w.Write(buf.Bytes())
	return err
}

// worldResumeID 优先取 ?last_id=，否则取 Last-Event-ID 头；非法值按 0（整页快照）处理。
func worldResumeID(c *gin.Context) int64 {
	if id := worldParseID(c.Query("last_id")); id > 0 {
		return id
	}
	return worldParseID(c.GetHeader("Last-Event-ID"))
}

// worldParseID 解析非负 int64；空/非法/负数返回 0。
func worldParseID(raw string) int64 {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return 0
	}
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id < 0 {
		return 0
	}
	return id
}

// worldParseLimit 解析 limit；非法返回 0（由 NormalizeWorldLimit 回落默认值）。
func worldParseLimit(raw string) int {
	n, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil {
		return 0
	}
	return n
}

// worldNextBeforeID 返回本页最小 id（继续向上翻页的 before_id）；没有更多时返回 0。
func worldNextBeforeID(items []database.WorldMessage, hasMore bool) int64 {
	if !hasMore || len(items) == 0 {
		return 0
	}
	min := items[0].ID
	for _, it := range items[1:] {
		if it.ID < min {
			min = it.ID
		}
	}
	return min
}
