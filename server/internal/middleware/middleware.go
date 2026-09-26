// Package middleware 提供 Gin 中间件（CORS/CSRF/限流/安全头/压缩/日志）。
package middleware

import (
	"compress/gzip"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

// ---- 限流 ----

type rateEntry struct {
	times []time.Time
}

var (
	rateMu      sync.Mutex
	rateStore   = map[string]*rateEntry{}
	lastCleanup = time.Now()
)

// RateLimit 简易速率限制（key 维度 + 客户端 IP）。
// 返回 true 表示超限（应返回 429）。
// window 必须传 time.Duration（如 300*time.Second）；小于 1 秒的窗口一律视为误传裸整数，回退为 1 分钟防御。
func RateLimit(key string, maxCount int, window time.Duration) gin.HandlerFunc {
	if window < time.Second {
		window = time.Minute
	}
	return func(c *gin.Context) {
		ip := c.ClientIP()
		rk := key + ":" + ip
		rateMu.Lock()
		now := time.Now()
		ent, ok := rateStore[rk]
		if !ok {
			ent = &rateEntry{}
			rateStore[rk] = ent
		}
		// 过滤窗口外
		cutoff := now.Add(-window)
		kept := ent.times[:0]
		for _, t := range ent.times {
			if t.After(cutoff) {
				kept = append(kept, t)
			}
		}
		ent.times = kept
		if len(ent.times) >= maxCount {
			rateMu.Unlock()
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{"success": false, "message": "请求过于频繁，请稍后再试"})
			return
		}
		ent.times = append(ent.times, now)
		// 定期清理
		if len(rateStore) > 5000 || now.Sub(lastCleanup) > 10*time.Minute {
			lastCleanup = now
			for k, item := range rateStore {
				stale := time.Now().Add(-2 * window)
				hasFresh := false
				for _, t := range item.times {
					if t.After(stale) {
						hasFresh = true
						break
					}
				}
				if !hasFresh {
					delete(rateStore, k)
				}
			}
		}
		rateMu.Unlock()
		c.Next()
	}
}

// ---- CSRF ----

// CSRF 校验 Origin/Referer（对齐 legacy main.py csrf_protect）。
func CSRF(allowedOrigins []string) gin.HandlerFunc {
	return func(c *gin.Context) {
		method := c.Request.Method
		if method == http.MethodGet || method == http.MethodHead || method == http.MethodOptions {
			c.Next()
			return
		}
		origin := c.GetHeader("Origin")
		referer := c.GetHeader("Referer")
		if isAllowed(origin, allowedOrigins, c) || isAllowed(referer, allowedOrigins, c) {
			c.Next()
			return
		}
		c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"success": false, "message": "跨站请求已被拦截"})
	}
}

func isAllowed(url string, allowedOrigins []string, c *gin.Context) bool {
	if url == "" {
		return false
	}
	// 同源：Origin 的 host 与请求 Host（或 X-Forwarded-Host，Next 代理时）比对
	host := c.Request.Host
	if fwd := c.GetHeader("X-Forwarded-Host"); fwd != "" {
		host = fwd
	}
	if strings.HasPrefix(url, "http://"+host) || strings.HasPrefix(url, "https://"+host) {
		return true
	}
	for _, ao := range allowedOrigins {
		if ao != "" && strings.HasPrefix(url, strings.TrimRight(ao, "/")) {
			return true
		}
	}
	return false
}

// ---- CORS ----

// CORS 白名单 CORS（默认镜像 legacy：origins 为空时允许全部）。
func CORS(allowedOrigins []string) gin.HandlerFunc {
	allowAll := len(allowedOrigins) == 0
	originSet := map[string]bool{}
	for _, o := range allowedOrigins {
		originSet[o] = true
	}
	return func(c *gin.Context) {
		origin := c.GetHeader("Origin")
		if origin != "" && (allowAll || originSet[origin]) {
			c.Header("Access-Control-Allow-Origin", origin)
			c.Header("Access-Control-Allow-Credentials", "true")
			c.Header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
			c.Header("Access-Control-Allow-Headers", "Content-Type, Authorization")
			c.Header("Access-Control-Max-Age", "86400")
		}
		if c.Request.Method == http.MethodOptions {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	}
}

// ---- 安全响应头 + gzip ----

// SecurityHeaders 安全头（对齐 legacy performance_optimize 安全部分）。
func SecurityHeaders() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Writer.Header().Set("X-Content-Type-Options", "nosniff")
		c.Writer.Header().Set("X-Frame-Options", "SAMEORIGIN")
		c.Writer.Header().Set("Referrer-Policy", "strict-origin-when-cross-origin")
		c.Writer.Header().Set("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()")
		c.Writer.Header().Set("X-XSS-Protection", "1; mode=block")
		if c.Request.TLS != nil || c.GetHeader("X-Forwarded-Proto") == "https" {
			c.Writer.Header().Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		}
		c.Next()
	}
}

func shouldGzip(c *gin.Context) bool {
	ct := c.Writer.Header().Get("Content-Type")
	return strings.Contains(ct, "text/") || strings.Contains(ct, "application/json") ||
		strings.Contains(ct, "application/javascript") || strings.Contains(ct, "image/svg+xml")
}

// gzipWriter 包装 ResponseWriter 做 gzip 压缩。
type gzipWriter struct {
	gin.ResponseWriter
	writer *gzip.Writer
}

func (g *gzipWriter) Write(data []byte) (int, error) {
	return g.writer.Write(data)
}

// Gzip 压缩中间件。
func Gzip() gin.HandlerFunc {
	return func(c *gin.Context) {
		ct := c.Writer.Header().Get("Content-Type")
		if strings.Contains(c.GetHeader("Accept-Encoding"), "gzip") &&
			(strings.Contains(ct, "text/") || strings.Contains(ct, "application/json") || strings.Contains(ct, "application/javascript") || strings.Contains(ct, "image/svg+xml")) {
			gz := gzip.NewWriter(c.Writer)
			gw := &gzipWriter{ResponseWriter: c.Writer, writer: gz}
			c.Writer.Header().Set("Content-Encoding", "gzip")
			c.Writer.Header().Add("Vary", "Accept-Encoding")
			c.Writer = gw
			c.Next()
			gz.Close()
			return
		}
		c.Next()
	}
}

// ---- 日志 ----

// Logger 请求日志。
func Logger() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		c.Next()
		dur := time.Since(start)
		if dur > 200*time.Millisecond {
			log.Printf("[HTTP] %s %s %d %s", c.Request.Method, c.Request.URL.Path, c.Writer.Status(), dur)
		}
	}
}
