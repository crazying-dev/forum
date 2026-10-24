package handler

import (
	"crypto/tls"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
)

// TestWriteMediaHeadersNotModified 验证 If-None-Match 命中时的 304 与缓存头。
func TestWriteMediaHeadersNotModified(t *testing.T) {
	gin.SetMode(gin.TestMode)
	const sha = "deadbeef0123456789abcdef"
	asset := &database.MediaAsset{ID: "MD1", Visibility: "public", Size: 1024, SHA256: sha}

	rec := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(rec)
	c.Request = httptest.NewRequest(http.MethodGet, "/ov2/api/media/MD1", nil)
	c.Request.Header.Set("If-None-Match", `"other", W/"`+sha+`"`)

	if ok := writeMediaHeaders(c, asset, mediaResponseMeta{Size: asset.Size, SHA256: asset.SHA256}); ok {
		t.Fatal("If-None-Match 命中时应返回 false（已写 304）")
	}
	c.Writer.WriteHeaderNow() // 单测直接调用 handler，需手动 flush 头
	if rec.Code != http.StatusNotModified {
		t.Fatalf("status = %d, want 304", rec.Code)
	}
	if got := rec.Header().Get("ETag"); got != `"`+sha+`"` {
		t.Fatalf("ETag = %q", got)
	}
	if got := rec.Header().Get("Cache-Control"); got != "public, max-age=31536000, immutable" {
		t.Fatalf("Cache-Control = %q", got)
	}
	if got := rec.Header().Get("Content-Length"); got != "1024" {
		t.Fatalf("Content-Length = %q", got)
	}
}

// TestWriteMediaHeadersOK 验证未命中时返回 true，且 private/变体头正确。
func TestWriteMediaHeadersOK(t *testing.T) {
	gin.SetMode(gin.TestMode)
	const sha = "cafebabe0123456789abcdef"
	asset := &database.MediaAsset{ID: "MD2", Visibility: "private", Size: 2048, SHA256: sha}

	rec := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(rec)
	c.Request = httptest.NewRequest(http.MethodGet, "/ov2/api/media/MD2?w=480", nil)
	c.Request.Header.Set("If-None-Match", `"stale"`)

	if ok := writeMediaHeaders(c, asset, mediaResponseMeta{Size: 512, SHA256: sha, Variant: "w480"}); !ok {
		t.Fatal("If-None-Match 未命中时应返回 true")
	}
	if got := rec.Header().Get("Cache-Control"); got != "private, max-age=60" {
		t.Fatalf("Cache-Control = %q", got)
	}
	if got := rec.Header().Get("X-Media-Cache"); got != "private" {
		t.Fatalf("X-Media-Cache = %q", got)
	}
	if got := rec.Header().Get("X-Media-Variant"); got != "w480" {
		t.Fatalf("X-Media-Variant = %q", got)
	}
	if got := rec.Header().Get("Content-Length"); got != "512" {
		t.Fatalf("Content-Length = %q", got)
	}
}

// TestETagMatches 验证 If-None-Match 解析（列表/弱校验/通配）。
func TestETagMatches(t *testing.T) {
	const etag = `"abc"`
	cases := []struct {
		header string
		want   bool
	}{
		{"", false},
		{etag, true},
		{`"x", ` + etag, true},
		{`W/"abc"`, true},
		{"*", true},
		{`"abcd"`, false},
	}
	for _, tc := range cases {
		if got := etagMatches(tc.header, etag); got != tc.want {
			t.Fatalf("etagMatches(%q) = %v, want %v", tc.header, got, tc.want)
		}
	}
}

// TestAbsoluteMediaURL 验证媒体 URL 的绝对化规则。
func TestAbsoluteMediaURL(t *testing.T) {
	tests := []struct {
		name   string
		cfg    *config.Config
		target string
		host   string
		proto  string
		tls    bool
		public string
		want   string
	}{
		{
			name: "configured public base",
			cfg:  &config.Config{PublicBaseURL: "https://yjlt.top"},
			host: "internal:8090", public: "/ov2/api/media/MD1",
			want: "https://yjlt.top/ov2/api/media/MD1",
		},
		{
			name: "bare configured host gets https",
			cfg:  &config.Config{PublicBaseURL: "yjlt.top"},
			host: "internal:8090", public: "/ov2/api/media/MD1",
			want: "https://yjlt.top/ov2/api/media/MD1",
		},
		{
			name: "loopback config falls back to request origin",
			cfg:  &config.Config{PublicBaseURL: "http://localhost:3000"},
			host: "localhost:3200", proto: "http", public: "/ov2/api/media/MD1",
			want: "http://localhost:3200/ov2/api/media/MD1",
		},
		{
			name: "no config uses forwarded proto and host",
			cfg:  &config.Config{},
			host: "forum.example", proto: "https, http", public: "/ov2/api/media/MD1",
			want: "https://forum.example/ov2/api/media/MD1",
		},
		{
			name: "no config uses tls",
			cfg:  &config.Config{},
			host: "api.example", tls: true, public: "/ov2/api/media/MD1",
			want: "https://api.example/ov2/api/media/MD1",
		},
		{
			name: "already absolute",
			cfg:  &config.Config{PublicBaseURL: "https://yjlt.top"},
			host: "internal:8090", public: "https://cdn.example/ov2/api/media/MD1",
			want: "https://cdn.example/ov2/api/media/MD1",
		},
		{
			name: "empty path",
			cfg:  &config.Config{PublicBaseURL: "https://yjlt.top"},
			host: "internal:8090", public: "",
			want: "",
		},
		{
			name: "nil config uses request origin",
			cfg:  nil,
			host: "forum.example", proto: "http", public: "/ov2/api/media/MD1",
			want: "http://forum.example/ov2/api/media/MD1",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			target := tc.target
			if target == "" {
				target = "http://" + tc.host + "/upload"
			}
			req := httptest.NewRequest("POST", target, nil)
			req.Host = tc.host
			if tc.proto != "" {
				req.Header.Set("X-Forwarded-Proto", tc.proto)
			}
			if tc.tls {
				req.TLS = &tls.ConnectionState{}
			}
			if got := absoluteMediaURL(tc.cfg, req, tc.public); got != tc.want {
				t.Fatalf("absoluteMediaURL() = %q, want %q", got, tc.want)
			}
		})
	}
}
