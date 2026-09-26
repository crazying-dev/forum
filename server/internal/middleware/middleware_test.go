package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
)

func newRateLimitRouter(key string, maxCount int, window time.Duration) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.POST("/x", RateLimit(key, maxCount, window), func(c *gin.Context) {
		c.Status(http.StatusOK)
	})
	return r
}

func serveN(t *testing.T, r *gin.Engine, n int) int {
	t.Helper()
	code := 0
	for i := 0; i < n; i++ {
		w := httptest.NewRecorder()
		r.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/x", nil))
		code = w.Code
	}
	return code
}

// window=300*time.Second 时：前 10 次放行，第 11 次应 429。
func TestRateLimitWindowSeconds(t *testing.T) {
	r := newRateLimitRouter("test_window_seconds", 10, 300*time.Second)
	if code := serveN(t, r, 10); code != http.StatusOK {
		t.Fatalf("前 10 次请求应为 200，实际 %d", code)
	}
	if code := serveN(t, r, 1); code != http.StatusTooManyRequests {
		t.Fatalf("第 11 次请求应为 429，实际 %d", code)
	}
}

// window 误传裸整数（纳秒）时应回退为 1 分钟防御，第 11 次仍应 429。
func TestRateLimitGuardsSubSecondWindow(t *testing.T) {
	r := newRateLimitRouter("test_window_guard", 10, 300)
	if code := serveN(t, r, 10); code != http.StatusOK {
		t.Fatalf("前 10 次请求应为 200，实际 %d", code)
	}
	if code := serveN(t, r, 1); code != http.StatusTooManyRequests {
		t.Fatalf("第 11 次请求应为 429（窗口已回退为 1 分钟），实际 %d", code)
	}
}
