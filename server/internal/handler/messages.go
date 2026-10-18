package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/cache"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/sanitize"
	"yj-forum/server/internal/sse"
)

const (
	maxChatContentBytes = 16 * 1024
	maxChatPlainRunes   = 2000
)

// 消息中心 SSE：进程内 Hub（topic=user:<id>）。
// 单独抽成包级单例，保证 messages.stream 与 posts/comments 的推送使用同一 Hub；
// 需要替换时在启动阶段调用 SetMessageHub（router/main 集成点）。
var (
	messageHubMu sync.RWMutex
	messageHub   = sse.NewHub()
)

// SetMessageHub 替换全局消息中心 Hub。
func SetMessageHub(h *sse.Hub) {
	if h == nil {
		return
	}
	messageHubMu.Lock()
	messageHub = h
	messageHubMu.Unlock()
}

// ActiveMessageHub 返回全局消息中心 Hub。
func ActiveMessageHub() *sse.Hub {
	messageHubMu.RLock()
	defer messageHubMu.RUnlock()
	return messageHub
}

// MessageHandler 消息中心（点赞/评论/系统/管理团队聊天 + SSE）。
type MessageHandler struct {
	DB       *database.DB
	Sessions *auth.SessionManager
	// Hub 可选；设置后仅影响本 handler 的 stream/推送，建议保持 nil 使用全局 ActiveMessageHub。
	Hub *sse.Hub
	// ChatRate 可选；2 秒/用户聊天限流桶。
	ChatRate *cache.Cache
}

var fallbackChatRate = cache.New(10000, 2*time.Second)

func (h *MessageHandler) hub() *sse.Hub {
	if h != nil && h.Hub != nil {
		return h.Hub
	}
	return ActiveMessageHub()
}

func (h *MessageHandler) chatRate() *cache.Cache {
	if h != nil && h.ChatRate != nil {
		return h.ChatRate
	}
	return fallbackChatRate
}

// RegisterMessageRoutes 注册 /messages 路由（由 router.go 集成调用）。
func RegisterMessageRoutes(api *gin.RouterGroup, h *MessageHandler) {
	if api == nil || h == nil {
		return
	}
	g := api.Group("/messages", h.AuthRequired())
	g.GET("/summary", h.Summary)
	g.GET("/likes", h.Likes)
	g.GET("/comments", h.Comments)
	g.GET("/system", h.System)
	g.GET("/chat", h.ChatList)
	g.POST("/chat", h.ChatSend)
	g.POST("/chat/read", h.ChatRead)
	g.POST("/read", h.Read)
	g.GET("/stream", h.Stream)
}

// AuthRequired 会话校验（与现有 handler 的 cookie 认证一致）。
func (h *MessageHandler) AuthRequired() gin.HandlerFunc {
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

// ---- GET /messages/summary ----

func (h *MessageHandler) Summary(c *gin.Context) {
	uid := CurrentUser(c)
	counts, err := h.DB.UnreadCounts(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true, "likes": counts.Likes, "comments": counts.Comments,
		"system": counts.System, "chat": counts.Chat,
	})
}

// ---- GET /messages/likes ----

func (h *MessageHandler) Likes(c *gin.Context) {
	uid := CurrentUser(c)
	items, hasMore, next, err := h.DB.ListLikeMessages(c.Request.Context(), uid, c.Query("cursor"), messageLimit(c))
	if err != nil {
		status := http.StatusInternalServerError
		if strings.Contains(err.Error(), "游标") {
			status = http.StatusBadRequest
		}
		c.JSON(status, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "items": items, "has_more": hasMore, "next_cursor": next})
}

// ---- GET /messages/comments ----

func (h *MessageHandler) Comments(c *gin.Context) {
	uid := CurrentUser(c)
	items, hasMore, next, err := h.DB.ListCommentMessages(c.Request.Context(), uid, c.Query("cursor"), messageLimit(c))
	if err != nil {
		status := http.StatusInternalServerError
		if strings.Contains(err.Error(), "游标") {
			status = http.StatusBadRequest
		}
		c.JSON(status, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "items": items, "has_more": hasMore, "next_cursor": next})
}

// ---- GET /messages/system ----

func (h *MessageHandler) System(c *gin.Context) {
	uid := CurrentUser(c)
	items, hasMore, next, err := h.DB.ListSystem(c.Request.Context(), uid, c.Query("cursor"), messageLimit(c))
	if err != nil {
		status := http.StatusInternalServerError
		if strings.Contains(err.Error(), "游标") {
			status = http.StatusBadRequest
		}
		c.JSON(status, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "items": items, "has_more": hasMore, "next_cursor": next})
}

// ---- POST /messages/read ----

type markReadReq struct {
	Category   string `json:"category"`
	LastReadAt string `json:"last_read_at"`
}

func (h *MessageHandler) Read(c *gin.Context) {
	uid := CurrentUser(c)
	var req markReadReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if req.Category != "likes" && req.Category != "comments" && req.Category != "system" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "category 需为 likes/comments/system"})
		return
	}
	lastRead := time.Now().UTC()
	if raw := strings.TrimSpace(req.LastReadAt); raw != "" {
		t, err := time.Parse(time.RFC3339Nano, raw)
		if err != nil {
			t, err = time.Parse(time.RFC3339, raw)
		}
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "last_read_at 需为 RFC3339"})
			return
		}
		lastRead = t.UTC()
	}
	if err := h.DB.MarkCategoryRead(c.Request.Context(), uid, req.Category, lastRead); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "保存失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ---- GET/POST /messages/chat ----

func (h *MessageHandler) ChatList(c *gin.Context) {
	uid := CurrentUser(c)
	items, hasMore, err := h.DB.GetChatMessages(c.Request.Context(), uid, c.Query("cursor"), messageLimit(c))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	next := ""
	if hasMore && len(items) > 0 {
		next = database.CursorID(items[len(items)-1].ID)
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "items": items, "has_more": hasMore, "next_cursor": next})
}

type sendChatReq struct {
	ContentHTML string `json:"content_html" binding:"required"`
}

func (h *MessageHandler) ChatSend(c *gin.Context) {
	uid := CurrentUser(c)
	if !h.chatRate().SetIfAbsent("chat:"+uid, time.Now()) {
		c.JSON(http.StatusTooManyRequests, gin.H{"success": false, "message": "发送太快，请 2 秒后再试"})
		return
	}
	var req sendChatReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if len(req.ContentHTML) > maxChatContentBytes {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "内容过长"})
		return
	}
	content := sanitize.SanitizeRichContent(strings.TrimSpace(req.ContentHTML))
	plain := sanitize.StripTagsAndTrim(content)
	hasRichMedia := strings.Contains(content, "<img") || strings.Contains(content, "data-embed")
	if len([]rune(plain)) > maxChatPlainRunes || (plain == "" && !hasRichMedia) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "内容需 1-2000 字符"})
		return
	}
	msg, err := h.DB.CreateChatMessage(c.Request.Context(), uid, content)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "发送失败"})
		return
	}
	h.pushChatMessage(uid, msg)
	c.JSON(http.StatusOK, gin.H{"success": true, "id": msg.ID})
}

type chatReadReq struct {
	LastMessageID int64 `json:"last_message_id"`
}

func (h *MessageHandler) ChatRead(c *gin.Context) {
	uid := CurrentUser(c)
	var req chatReadReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if err := h.DB.MarkChatRead(c.Request.Context(), uid, req.LastMessageID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "保存失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ---- GET /messages/stream ----

func (h *MessageHandler) Stream(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	hub := h.hub()
	topic := "user:" + uid
	client := hub.Subscribe(topic, 64)
	defer hub.Unsubscribe(topic, client)

	c.Header("Content-Type", "text/event-stream; charset=utf-8")
	c.Header("Cache-Control", "no-cache, no-transform")
	c.Header("Connection", "keep-alive")
	c.Header("X-Accel-Buffering", "no")
	c.Status(http.StatusOK)
	c.Writer.Flush()

	writeSSE(c, "", "hello", gin.H{"success": true, "user_id": uid, "server_time": time.Now().UTC()})
	if counts, err := h.DB.UnreadCounts(c.Request.Context(), uid); err == nil {
		writeSSE(c, "", "unread", unreadData(counts))
	}
	c.Writer.Flush()

	heartbeat := time.NewTicker(15 * time.Second)
	defer heartbeat.Stop()
	// admin 进程写入的聊天消息无法通过本进程 Hub 直接推送；这里做轻量轮询兜底，
	// 保证用户在消息中心打开时能看到管理团队回复（5s 一次，仅活动连接）。
	chatTicker := time.NewTicker(5 * time.Second)
	defer chatTicker.Stop()
	lastChatID, _ := h.DB.LatestChatMessageID(c.Request.Context(), uid)

	for {
		select {
		case <-c.Request.Context().Done():
			return
		case <-heartbeat.C:
			writeSSE(c, "", "heartbeat", gin.H{"success": true, "ts": time.Now().UTC()})
			c.Writer.Flush()
		case <-chatTicker.C:
			items, err := h.DB.GetChatMessagesAfter(c.Request.Context(), uid, lastChatID, 50)
			if err == nil && len(items) > 0 {
				for i := range items {
					msg := &items[i]
					writeSSE(c, strconv.FormatInt(msg.ID, 10), "message", gin.H{"success": true, "item": msg})
					if msg.ID > lastChatID {
						lastChatID = msg.ID
					}
				}
				if counts, err := h.DB.UnreadCounts(c.Request.Context(), uid); err == nil {
					writeSSE(c, "", "unread", unreadData(counts))
				}
				c.Writer.Flush()
			}
		case ev, ok := <-client.Ch:
			if !ok {
				return
			}
			writeSSE(c, ev.ID, ev.Type, ev.Data)
			c.Writer.Flush()
		}
	}
}

// writeSSE 输出一条 SSE 事件（data 统一 JSON 编码；多行自动加 data: 前缀）。
func writeSSE(c *gin.Context, id, event string, data any) {
	payload, err := json.Marshal(data)
	if err != nil {
		payload = []byte(`{"success":false,"message":"encode error"}`)
	}
	if id != "" {
		_, _ = fmt.Fprintf(c.Writer, "id: %s\n", id)
	}
	_, _ = fmt.Fprintf(c.Writer, "event: %s\n", event)
	for _, line := range strings.Split(string(payload), "\n") {
		_, _ = fmt.Fprintf(c.Writer, "data: %s\n", line)
	}
	_, _ = fmt.Fprint(c.Writer, "\n")
}

func messageLimit(c *gin.Context) int {
	n, err := strconv.Atoi(strings.TrimSpace(c.Query("limit")))
	if err != nil || n <= 0 {
		return 20
	}
	if n > 50 {
		return 50
	}
	return n
}

func unreadData(counts database.UnreadCounts) gin.H {
	return gin.H{"success": true, "likes": counts.Likes, "comments": counts.Comments, "system": counts.System, "chat": counts.Chat}
}

// ---- SSE 推送（posts/comments 复用） ----

// PushNotificationEvent 向用户推送持久 notification 事件（带 id，供 EventSource Last-Event-ID 语义）。
func PushNotificationEvent(userID string, id int64, item any) {
	pushUserEvent(userID, sse.Event{ID: strconv.FormatInt(id, 10), Type: "notification", Data: gin.H{"success": true, "item": item}})
}

// PushUnreadEvent 推送最新四类未读数（仅当该用户有活跃 SSE 连接时查询）。
func PushUnreadEvent(ctx context.Context, db *database.DB, userID string) {
	if db == nil || userID == "" {
		return
	}
	if ActiveMessageHub().Count("user:"+userID) == 0 {
		return
	}
	counts, err := db.UnreadCounts(ctx, userID)
	if err != nil {
		return
	}
	pushUserEvent(userID, sse.Event{Type: "unread", Data: unreadData(counts)})
}

func (h *MessageHandler) pushChatMessage(userID string, msg *database.ChatMessage) {
	pushUserEvent(userID, sse.Event{ID: strconv.FormatInt(msg.ID, 10), Type: "message", Data: gin.H{"success": true, "item": msg}})
	PushUnreadEvent(context.Background(), h.DB, userID)
}

func pushUserEvent(userID string, ev sse.Event) {
	if userID == "" {
		return
	}
	hub := ActiveMessageHub()
	if hub.Count("user:"+userID) == 0 {
		return
	}
	hub.Broadcast("user:"+userID, ev)
}
