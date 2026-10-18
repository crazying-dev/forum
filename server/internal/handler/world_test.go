package handler

import (
	"bytes"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/database"
)

func TestValidateWorldContent(t *testing.T) {
	imgs := func(n int) string {
		return strings.Repeat(`<img src="/media/a.png" alt="a">`, n)
	}
	cases := []struct {
		name    string
		raw     string
		wantErr error
		wantHas []string
		wantNot []string
	}{
		{
			name:    "普通富文本保留格式",
			raw:     `<p><strong>加粗</strong> 与 <em>斜体</em></p>`,
			wantHas: []string{"<strong>加粗</strong>", "<em>斜体</em>"},
		},
		{
			name:    "script 与事件属性被净化",
			raw:     `<script>alert(1)</script><p onclick="x()">正文<img src="/a.png" onerror="alert(1)"></p>`,
			wantHas: []string{"正文", `<img src="/a.png"`},
			wantNot: []string{"script", "onclick", "onerror"},
		},
		{
			name:    "禁 data-embed",
			raw:     `<p>hi</p><div data-embed="user" data-id="abc"></div>`,
			wantErr: errWorldEmbedForbidden,
		},
		{
			name:    "最多 9 张图",
			raw:     `<p>hi</p>` + imgs(10),
			wantErr: errWorldTooManyImages,
		},
		{
			name:    "9 张图允许",
			raw:     `<p>hi</p>` + imgs(9),
			wantHas: []string{"<p>hi</p>"},
		},
		{
			name:    "空内容",
			raw:     `<p></p><p><br></p>`,
			wantErr: errWorldContentEmpty,
		},
		{
			name:    "nbsp 视为空",
			raw:     `<p>&nbsp;</p>`,
			wantErr: errWorldContentEmpty,
		},
		{
			name:    "2000 字允许",
			raw:     `<p>` + strings.Repeat("字", 2000) + `</p>`,
			wantHas: []string{"字"},
		},
		{
			name:    "2001 字拒绝",
			raw:     `<p>` + strings.Repeat("字", 2001) + `</p>`,
			wantErr: errWorldContentTooLong,
		},
		{
			name:    "原始内容超大拒绝",
			raw:     strings.Repeat("a", worldMaxBodyBytes+1),
			wantErr: errWorldContentTooLong,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := validateWorldContent(tc.raw)
			if tc.wantErr != nil {
				if !errors.Is(err, tc.wantErr) {
					t.Fatalf("err = %v, want %v", err, tc.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected err: %v", err)
			}
			for _, s := range tc.wantHas {
				if !strings.Contains(got, s) {
					t.Fatalf("净化结果缺少 %q: %s", s, got)
				}
			}
			for _, s := range tc.wantNot {
				if strings.Contains(strings.ToLower(got), s) {
					t.Fatalf("净化结果不应包含 %q: %s", s, got)
				}
			}
		})
	}
}

func TestWorldParseID(t *testing.T) {
	cases := []struct {
		in   string
		want int64
	}{
		{"", 0},
		{"   ", 0},
		{"42", 42},
		{" 42 ", 42},
		{"0", 0},
		{"-1", 0},
		{"abc", 0},
		{"9223372036854775808", 0}, // int64 溢出
	}
	for _, tc := range cases {
		if got := worldParseID(tc.in); got != tc.want {
			t.Fatalf("worldParseID(%q) = %d, want %d", tc.in, got, tc.want)
		}
	}
}

func TestWorldParseLimitAndNormalize(t *testing.T) {
	if got := worldParseLimit(""); got != 0 {
		t.Fatalf("worldParseLimit(空) = %d, want 0", got)
	}
	if got := worldParseLimit("abc"); got != 0 {
		t.Fatalf("worldParseLimit(abc) = %d, want 0", got)
	}
	if got := worldParseLimit(" 500 "); got != 500 {
		t.Fatalf("worldParseLimit(500) = %d", got)
	}
	if got := database.NormalizeWorldLimit(worldParseLimit("501")); got != 500 {
		t.Fatalf("limit 501 应截断为 500，got %d", got)
	}
	if got := database.NormalizeWorldLimit(worldParseLimit("")); got != database.WorldDefaultLimit {
		t.Fatalf("空 limit 应回落 %d，got %d", database.WorldDefaultLimit, got)
	}
}

func TestWorldNextBeforeID(t *testing.T) {
	items := []database.WorldMessage{{ID: 10}, {ID: 7}, {ID: 5}}
	if got := worldNextBeforeID(items, true); got != 5 {
		t.Fatalf("next_before_id = %d, want 5", got)
	}
	if got := worldNextBeforeID(items, false); got != 0 {
		t.Fatalf("has_more=false 时 next_before_id = %d, want 0", got)
	}
	if got := worldNextBeforeID(nil, true); got != 0 {
		t.Fatalf("空列表 next_before_id = %d, want 0", got)
	}
}

func TestWorldResumeID(t *testing.T) {
	gin.SetMode(gin.TestMode)
	cases := []struct {
		name   string
		query  string
		header string
		want   int64
	}{
		{"query 优先", "last_id=123", "456", 123},
		{"header 回退", "", "456", 456},
		{"query 非法回退 header", "last_id=abc", "456", 456},
		{"均为空", "", "", 0},
		{"负数忽略", "last_id=-1", "", 0},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(rec)
			c.Request = httptest.NewRequest(http.MethodGet, "/ov2/api/world/stream?"+tc.query, nil)
			if tc.header != "" {
				c.Request.Header.Set("Last-Event-ID", tc.header)
			}
			if got := worldResumeID(c); got != tc.want {
				t.Fatalf("worldResumeID = %d, want %d", got, tc.want)
			}
		})
	}
}

func TestWorldWriteSSE(t *testing.T) {
	var buf bytes.Buffer
	msg := database.WorldMessage{ID: 7, SenderName: "甲", Content: "第一行\n第二行"}
	if err := worldWriteSSE(&buf, "7", "message", msg); err != nil {
		t.Fatalf("worldWriteSSE err: %v", err)
	}
	out := buf.String()
	if !strings.HasPrefix(out, "id: 7\nevent: message\ndata: ") {
		t.Fatalf("SSE 帧头不正确: %q", out)
	}
	if !strings.HasSuffix(out, "\n\n") {
		t.Fatalf("SSE 帧应以空行结束: %q", out)
	}
	// JSON 序列化后内容中的换行必须是转义的，不能在 data 行产生裸换行。
	for _, line := range strings.Split(strings.TrimSuffix(out, "\n\n"), "\n") {
		if strings.HasPrefix(line, "data: ") && strings.ContainsAny(strings.TrimPrefix(line, "data: "), "\r\n") {
			t.Fatalf("data 行包含裸换行: %q", line)
		}
	}
}

func TestRegisterWorldRoutes(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	api := r.Group("/ov2/api")
	RegisterWorldRoutes(api, &WorldHandler{})

	paths := map[string]bool{}
	for _, rt := range r.Routes() {
		paths[rt.Method+" "+rt.Path] = true
	}
	for _, want := range []string{
		"GET /ov2/api/world/messages",
		"POST /ov2/api/world/messages",
		"GET /ov2/api/world/stream",
	} {
		if !paths[want] {
			t.Fatalf("缺少路由 %s，实际: %v", want, paths)
		}
	}

	// 未登录 POST 应 401（Sessions 为 nil 时安全拒绝）
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/ov2/api/world/messages", strings.NewReader(`{"content_html":"hi"}`))
	r.ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("未登录 POST 状态码 = %d, want 401", rec.Code)
	}

	// nil 参数安全
	RegisterWorldRoutes(nil, &WorldHandler{})
	RegisterWorldRoutes(api, nil)
}
