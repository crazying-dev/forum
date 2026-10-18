package handler

import (
	"testing"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/database"
)

func TestRegisterMessageRoutes(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	h := &MessageHandler{DB: &database.DB{}, Sessions: &auth.SessionManager{}}
	RegisterMessageRoutes(r.Group("/ov2/api"), h)

	want := []string{
		"GET /ov2/api/messages/summary",
		"GET /ov2/api/messages/likes",
		"GET /ov2/api/messages/comments",
		"GET /ov2/api/messages/system",
		"POST /ov2/api/messages/read",
		"GET /ov2/api/messages/chat",
		"POST /ov2/api/messages/chat",
		"POST /ov2/api/messages/chat/read",
		"GET /ov2/api/messages/stream",
	}
	got := map[string]bool{}
	for _, route := range r.Routes() {
		got[route.Method+" "+route.Path] = true
	}
	for _, w := range want {
		if !got[w] {
			t.Fatalf("路由未注册: %s（已注册: %v）", w, got)
		}
	}
}
