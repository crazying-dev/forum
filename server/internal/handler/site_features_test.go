package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
)

func siteTestRouter(method, path string, handler gin.HandlerFunc) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Handle(method, path, handler)
	return r
}

func doJSON(t *testing.T, r *gin.Engine, method, path string) (*httptest.ResponseRecorder, map[string]any) {
	t.Helper()
	w := httptest.NewRecorder()
	req := httptest.NewRequest(method, path, nil)
	r.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("%s %s status = %d, body = %s", method, path, w.Code, w.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("解析响应失败: %v (%s)", err, w.Body.String())
	}
	return w, body
}

func TestRegisterSiteFeatureRoutes(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	RegisterSiteFeatureRoutes(r.Group("/ov2/api"), &SiteFeatureHandlers{})

	want := []string{
		"/ov2/api/changelogs",
		"/ov2/api/changelogs/:id",
		"/ov2/api/downloads/releases",
		"/ov2/api/downloads/latest",
		"/ov2/api/downloads/check",
		"/ov2/api/downloads/mirror/:platform/:filename",
		"/ov2/api/site/daily-quote",
	}
	got := map[string]bool{}
	for _, route := range r.Routes() {
		got[route.Path] = true
	}
	for _, path := range want {
		if !got[path] {
			t.Errorf("missing route %s", path)
		}
	}
}

func TestDailyQuoteSuccess(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Accept") != "application/json" {
			t.Errorf("Accept = %q", r.Header.Get("Accept"))
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"content":"  岁月不居，时节如流  ","author":"孔融","source":"论盛孝章书"}`))
	}))
	defer srv.Close()

	h := &SiteFeatureHandlers{QuoteURL: srv.URL, HTTPClient: srv.Client()}
	r := siteTestRouter(http.MethodGet, "/site/daily-quote", h.DailyQuote)
	_, body := doJSON(t, r, http.MethodGet, "/site/daily-quote")

	if body["success"] != true {
		t.Errorf("success = %v", body["success"])
	}
	if body["text"] != "岁月不居，时节如流" {
		t.Errorf("text = %v", body["text"])
	}
	if body["source"] != "孔融 · 论盛孝章书" {
		t.Errorf("source = %v", body["source"])
	}
}

func TestDailyQuoteFallback(t *testing.T) {
	cases := []struct {
		name   string
		status int
		body   string
	}{
		{"upstream 500", http.StatusInternalServerError, "boom"},
		{"invalid json", http.StatusOK, "{"},
		{"empty content", http.StatusOK, `{"content":"   "}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tc.status)
				_, _ = w.Write([]byte(tc.body))
			}))
			defer srv.Close()

			h := &SiteFeatureHandlers{QuoteURL: srv.URL, HTTPClient: srv.Client()}
			r := siteTestRouter(http.MethodGet, "/site/daily-quote", h.DailyQuote)
			_, body := doJSON(t, r, http.MethodGet, "/site/daily-quote")

			if body["success"] != true {
				t.Errorf("fallback should still success, got %v", body["success"])
			}
			if body["text"] != fallbackQuoteText || body["text"] == "" {
				t.Errorf("text = %v, want fallback %q", body["text"], fallbackQuoteText)
			}
			if body["source"] != fallbackQuoteSource {
				t.Errorf("source = %v", body["source"])
			}
		})
	}
}

func TestDailyQuoteTimeoutFallback(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(200 * time.Millisecond)
		_, _ = w.Write([]byte(`{"content":"太慢了"}`))
	}))
	defer srv.Close()

	h := &SiteFeatureHandlers{QuoteURL: srv.URL, HTTPClient: srv.Client(), QuoteTimeout: 20 * time.Millisecond}
	r := siteTestRouter(http.MethodGet, "/site/daily-quote", h.DailyQuote)
	_, body := doJSON(t, r, http.MethodGet, "/site/daily-quote")
	if body["text"] != fallbackQuoteText {
		t.Fatalf("timeout text = %v", body["text"])
	}
}

func TestDailyQuoteCache60s(t *testing.T) {
	var hits int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&hits, 1)
		_, _ = w.Write([]byte(`{"content":"缓存一言","author":"测试"}`))
	}))
	defer srv.Close()

	h := &SiteFeatureHandlers{QuoteURL: srv.URL, HTTPClient: srv.Client()}
	r := siteTestRouter(http.MethodGet, "/site/daily-quote", h.DailyQuote)
	doJSON(t, r, http.MethodGet, "/site/daily-quote")
	_, body := doJSON(t, r, http.MethodGet, "/site/daily-quote")
	if body["text"] != "缓存一言" {
		t.Fatalf("text = %v", body["text"])
	}
	if got := atomic.LoadInt32(&hits); got != 1 {
		t.Fatalf("upstream hits = %d, want 1 (60s cache)", got)
	}
}
