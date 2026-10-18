package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/releases"
)

const downloadsFixture = `[
  {
    "tag_name": "Windows-V1.3.18",
    "body": "- 修复 A",
    "draft": false,
    "prerelease": false,
    "published_at": "2026-10-10T08:00:00Z",
    "assets": [{
      "name": "forum_setup.exe",
      "size": 158186366,
      "browser_download_url": "https://github.com/crazying-dev/forum/releases/download/Windows-V1.3.18/forum_setup.exe",
      "digest": "sha256:1a78cd3930a7ebe7f3f28bb48689131a33e4762a7a304a159b67af2710e6e672"
    }]
  },
  {
    "tag_name": "Android-V1.0.16",
    "body": "- 修复 B",
    "draft": false,
    "prerelease": false,
    "published_at": "2026-10-09T08:00:00Z",
    "assets": [{
      "name": "forum-android-1.0.16.apk",
      "size": 8152504,
      "browser_download_url": "https://github.com/crazying-dev/forum/releases/download/Android-V1.0.16/forum-android-1.0.16.apk",
      "digest": "sha256:1bedfc7f3e29a616d217762a9907f846f2d17cf1eb843cf90fd041010b2cdd61"
    }]
  }
]`

func downloadsTestService(t *testing.T) *releases.Service {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(downloadsFixture))
	}))
	t.Cleanup(srv.Close)
	return releases.NewService("", releases.WithAPIBase(srv.URL), releases.WithHTTPClient(srv.Client()))
}

func TestDownloadsCheckFields(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &DownloadsHandler{Releases: downloadsTestService(t)}
	r := gin.New()
	r.GET("/downloads/check", h.Check)

	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/downloads/check?platform=windows&version=1.3.0", nil)
	r.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", w.Code, w.Body.String())
	}

	var body struct {
		Success     bool              `json:"success"`
		Available   bool              `json:"available"`
		Mandatory   bool              `json:"mandatory"`
		Current     string            `json:"current"`
		Latest      string            `json:"latest"`
		MinVersion  string            `json:"min_version"`
		Release     *releases.Release `json:"release"`
		DownloadURL string            `json:"download_url"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if !body.Success || !body.Available || !body.Mandatory {
		t.Errorf("success/available/mandatory = %v/%v/%v", body.Success, body.Available, body.Mandatory)
	}
	if body.Current != "1.3.0" || body.Latest != "1.3.18" || body.MinVersion != "1.3.18" {
		t.Errorf("current/latest/min = %q/%q/%q", body.Current, body.Latest, body.MinVersion)
	}
	if body.Release == nil || body.Release.Filename != "forum_setup.exe" {
		t.Errorf("release = %#v", body.Release)
	}
	if body.DownloadURL == "" {
		t.Errorf("download_url should not be empty")
	}
}

func TestDownloadsCheckUnknownPlatform(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &DownloadsHandler{Releases: downloadsTestService(t)}
	r := gin.New()
	r.GET("/downloads/check", h.Check)

	w := httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/downloads/check?platform=solaris&version=1.0.0", nil))
	if w.Code != http.StatusNotFound {
		t.Fatalf("status = %d, body = %s", w.Code, w.Body.String())
	}
}

func TestMirrorUnknownAsset(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &DownloadsHandler{Releases: downloadsTestService(t)}
	r := gin.New()
	r.GET("/downloads/mirror/:platform/:filename", h.Mirror)

	w := httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/downloads/mirror/windows/nope.exe", nil))
	if w.Code != http.StatusNotFound {
		t.Fatalf("status = %d, body = %s", w.Code, w.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil || body["success"] != false {
		t.Fatalf("body = %s", w.Body.String())
	}
}

func TestMirrorHostWhitelist(t *testing.T) {
	allowed := []string{
		"https://github.com/crazying-dev/forum/releases/download/Windows-V1.3.18/forum_setup.exe",
		"https://release-assets.githubusercontent.com/github-production-release-asset/1/a.exe",
		"https://objects.githubusercontent.com/foo",
		"https://githubassets.com/foo",
	}
	for _, raw := range allowed {
		if !isAllowedMirrorURL(raw) {
			t.Errorf("%s should be allowed", raw)
		}
	}

	blocked := []string{
		"http://github.com/a.exe",
		"https://evil.com/github.com/a.exe",
		"https://github.com.evil.com/a.exe",
		"https://githubusercontent.com.evil.com/a.exe",
		"https://127.0.0.1/a.exe",
		"file:///etc/passwd",
		"not a url",
	}
	for _, raw := range blocked {
		if isAllowedMirrorURL(raw) {
			t.Errorf("%s should be blocked", raw)
		}
	}
}
