package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/config"
	"yj-forum/server/internal/legacy"
)

type fakeWorldLister struct {
	messages []legacy.WorldMessage
	since    string
	limit    int
}

func (f *fakeWorldLister) WorldList(_ context.Context, since string, limit int) ([]legacy.WorldMessage, error) {
	f.since, f.limit = since, limit
	return f.messages, nil
}

type fakeWorldSender struct{}

func (fakeWorldSender) WorldSend(context.Context, *legacy.LegacyUser, string, *int64) (*legacy.WorldMessage, error) {
	return &legacy.WorldMessage{}, nil
}

// 世界频道 GET 必须是裸 JSON 数组（不是 {success,...} 包装），且带 max-age=2。
func TestLegacyWorldAllBareArray(t *testing.T) {
	gin.SetMode(gin.TestMode)
	parent := int64(7)
	fake := &fakeWorldLister{messages: []legacy.WorldMessage{
		{ID: 2, SenderID: "RL1", SenderName: "小黑", Content: "你好", ParentID: &parent, SenderAvatar: "a.png"},
		{ID: 1, SenderID: "RL2", SenderName: "小白", Content: "世界"},
	}}
	h := newLegacyWorldHandler(fake, fakeWorldSender{}, func(c *gin.Context) { c.Next() })
	r := gin.New()
	r.GET("/api/World/ALL", h.All)
	r.GET("/api/world/ALL", h.All)

	for _, path := range []string{"/api/World/ALL", "/api/world/ALL?since=2026-05-06%2012:00:00"} {
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, path, nil)
		r.ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("%s 状态 %d，body=%s", path, w.Code, w.Body.String())
		}
		if got := w.Header().Get("Cache-Control"); got != "max-age=2" {
			t.Fatalf("%s Cache-Control=%q", path, got)
		}
		body := strings.TrimSpace(w.Body.String())
		if !strings.HasPrefix(body, "[") {
			t.Fatalf("%s 响应不是裸数组：%s", path, body)
		}
		var arr []map[string]any
		if err := json.Unmarshal([]byte(body), &arr); err != nil {
			t.Fatalf("解析数组失败：%v body=%s", err, body)
		}
		if len(arr) != 2 {
			t.Fatalf("消息条数 %d", len(arr))
		}
		for _, key := range []string{"id", "sender_id", "sender_name", "content", "parent_id", "sender_avatar", "created_at"} {
			if _, ok := arr[0][key]; !ok {
				t.Errorf("世界消息缺少字段 %q：%v", key, arr[0])
			}
		}
	}
}

func testReleaseService() *legacy.Service {
	svc := legacy.NewService(nil, nil, nil)
	provider := legacy.NewReleaseProvider("")
	provider.Fetch = func() (*legacy.ReleaseManifest, error) {
		return &legacy.ReleaseManifest{
			Schema: 1, MinVersions: map[string]string{"windows": "1.3.18", "web": "0"},
			Platforms: []legacy.ReleasePlatform{
				{Key: "windows", Name: "Windows", Status: "available", Releases: []legacy.ReleaseAsset{
					{Version: "1.3.18", Channel: "stable", Filename: "forum_setup.exe", URL: "https://example.com/forum_setup.exe"},
				}},
			},
		}, nil
	}
	svc.Releases = provider
	return svc
}

// 版本过低 → 426 VERSION_TOO_LOW；/api/app/* 豁免；无法判断客户端放行。
func TestLegacyVersionGate426(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &legacyHandler{svc: testReleaseService()}
	r := gin.New()
	r.Use(h.versionGate())
	r.GET("/api/posts", func(c *gin.Context) { c.JSON(http.StatusOK, gin.H{"success": true}) })
	r.GET("/api/app/check", func(c *gin.Context) { c.JSON(http.StatusOK, gin.H{"success": true}) })

	do := func(path, platform, version string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		if platform != "" {
			req.Header.Set("X-Client-Platform", platform)
			req.Header.Set("X-Client-Version", version)
		}
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		return w
	}

	w := do("/api/posts", "windows", "1.0.0")
	if w.Code != http.StatusUpgradeRequired {
		t.Fatalf("期望 426，实际 %d body=%s", w.Code, w.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["code"] != "VERSION_TOO_LOW" || body["min_version"] != "1.3.18" {
		t.Fatalf("426 body 不符：%v", body)
	}

	if w := do("/api/posts", "windows", "1.3.18"); w.Code != http.StatusOK {
		t.Fatalf("达到最低版本应放行，实际 %d", w.Code)
	}
	if w := do("/api/posts", "", ""); w.Code != http.StatusOK {
		t.Fatalf("无法判断客户端应放行，实际 %d", w.Code)
	}
	if w := do("/api/app/check", "windows", "1.0.0"); w.Code != http.StatusOK {
		t.Fatalf("/api/app/* 应豁免闸门，实际 %d", w.Code)
	}
}

// 与现有新 API（/ov2/api、/api/v1）同一 engine 注册不得冲突（Gin 冲突会 panic）。
func TestRegisterLegacyRoutesAlongsideNewAPI(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	Register(r, &config.Config{}, nil, nil, nil, nil, nil)
	// Register 内部已调用 RegisterLegacyRoutes；此处不再重复注册
	var hasV1, hasLegacy bool
	for _, route := range r.Routes() {
		if route.Path == "/api/v1/posts" {
			hasV1 = true
		}
		if route.Path == "/api/posts" && route.Method == http.MethodGet {
			hasLegacy = true
		}
	}
	if !hasV1 || !hasLegacy {
		t.Fatalf("路由未同时注册：v1=%v legacy=%v", hasV1, hasLegacy)
	}
}

// 静态路径必须优先于参数路径（/user/info、/users/me/replies）。
func TestLegacyStaticRoutesBeatParams(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	RegisterLegacyRoutes(r, &config.Config{}, nil, nil, nil)
	cases := []struct {
		path string
		want int
	}{
		{"/api/user/info", http.StatusUnauthorized},
		{"/api/users/me/replies", http.StatusUnauthorized},
		{"/api/user/RLNOTEXIST", http.StatusNotFound},
	}
	for _, tc := range cases {
		w := httptest.NewRecorder()
		r.ServeHTTP(w, httptest.NewRequest(http.MethodGet, tc.path, nil))
		if w.Code != tc.want {
			t.Errorf("%s 状态 %d，期望 %d body=%s", tc.path, w.Code, tc.want, w.Body.String())
		}
	}
}

// 注册不得与静态/参数路由冲突（Gin 冲突会 panic）。
func TestRegisterLegacyRoutesRegistersPaths(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	RegisterLegacyRoutes(r, nil, nil, nil, nil)
	want := map[string]bool{
		"POST /api/login": false, "POST /api/register": false, "POST /api/logout": false,
		"POST /api/user/login": false, "GET /api/user/info": false, "GET /api/user/:id": false,
		"GET /api/users/:id/info": false, "GET /api/users/:id/posts": false,
		"GET /api/users/:id/favorites": false, "GET /api/users/:id/followers": false,
		"GET /api/users/:id/following": false, "POST /api/users/:id/follow": false,
		"GET /api/users/me/replies": false,
		"GET /api/posts":            false, "GET /api/posts/:id": false, "POST /api/posts/create": false,
		"GET /api/posts/:id/comments": false, "POST /api/posts/:id/comments/create": false,
		"POST /api/comments/:id/delete": false,
		"GET /api/World/ALL":            false, "POST /api/World/Send": false,
		"GET /api/world/ALL": false, "POST /api/world/Send": false,
		"GET /api/search": false, "POST /api/report-bug": false, "GET /api/huiguan": false,
		"GET /Easter-Egg": false, "POST /api/user/avatar/upload": false,
		"GET /api/app/releases": false, "GET /api/app/check": false,
		"GET /api/app/download/:platform/:filename": false, "GET /api/app/mirror/:platform/:filename": false,
		"GET /api/app/cache": false,
	}
	for _, route := range r.Routes() {
		key := route.Method + " " + route.Path
		if _, ok := want[key]; ok {
			want[key] = true
		}
	}
	for key, found := range want {
		if !found {
			t.Errorf("缺少路由 %s", key)
		}
	}
}
