package handler

import (
	"context"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/database"
	"yj-forum/server/internal/releases"
)

const (
	defaultQuoteURL     = "https://dlystc.unknownmp.top/api/v2/sentence"
	defaultQuoteTimeout = 5 * time.Second
	quoteCacheTTL       = 60 * time.Second
	fallbackQuoteText   = "愿你在妖精论坛度过美好的一天。"
	fallbackQuoteSource = "妖精论坛"
)

// SiteFeatureHandlers 站点功能模块依赖集合（更新日志/下载/每日一言）。
//
// DB 与 Releases 由 main/router 注入；QuoteURL/HTTPClient/QuoteTimeout 仅测试需要覆盖。
type SiteFeatureHandlers struct {
	DB       *database.DB
	Releases *releases.Service

	HTTPClient   *http.Client
	QuoteURL     string
	QuoteTimeout time.Duration

	quoteMu     sync.Mutex
	quoteAt     time.Time
	quoteText   string
	quoteSource string
}

// NewSiteFeatureHandlers 创建站点功能处理器。
func NewSiteFeatureHandlers(db *database.DB, releasesSvc *releases.Service) *SiteFeatureHandlers {
	return &SiteFeatureHandlers{DB: db, Releases: releasesSvc}
}

// RegisterSiteFeatureRoutes 注册站点功能路由（由 router 为 /ov2/api 与 /api/v1 各调用一次）。
func RegisterSiteFeatureRoutes(api *gin.RouterGroup, h *SiteFeatureHandlers) {
	if api == nil || h == nil {
		return
	}
	changelogs := &ChangelogHandler{DB: h.DB}
	downloads := &DownloadsHandler{Releases: h.Releases}

	api.GET("/changelogs", changelogs.List)
	api.GET("/changelogs/:id", changelogs.Detail)

	api.GET("/downloads/releases", downloads.List)
	api.GET("/downloads/latest", downloads.Latest)
	api.GET("/downloads/check", downloads.Check)
	api.GET("/downloads/mirror/:platform/:filename", downloads.Mirror)

	api.GET("/site/daily-quote", h.DailyQuote)
}

// quoteResponse dlystc /api/v2/sentence 响应（只取展示字段）。
type quoteResponse struct {
	Content string `json:"content"`
	Author  string `json:"author"`
	Source  string `json:"source"`
}

// ---- GET /site/daily-quote ----

// DailyQuote 每日一言（后端 60s 缓存；第三方失败/超时/空内容时使用本地兜底）。
func (h *SiteFeatureHandlers) DailyQuote(c *gin.Context) {
	h.quoteMu.Lock()
	defer h.quoteMu.Unlock()

	if !h.quoteAt.IsZero() && time.Since(h.quoteAt) < quoteCacheTTL {
		c.JSON(http.StatusOK, gin.H{"success": true, "text": h.quoteText, "source": h.quoteSource})
		return
	}

	text, source := h.fetchQuote(c.Request.Context())
	h.quoteAt = time.Now()
	h.quoteText = text
	h.quoteSource = source
	c.JSON(http.StatusOK, gin.H{"success": true, "text": text, "source": source})
}

// fetchQuote 请求第三方一言；任何异常都回退到本地文案。
func (h *SiteFeatureHandlers) fetchQuote(parent context.Context) (string, string) {
	timeout := h.QuoteTimeout
	if timeout <= 0 {
		timeout = defaultQuoteTimeout
	}
	ctx, cancel := context.WithTimeout(parent, timeout)
	defer cancel()

	url := strings.TrimSpace(h.QuoteURL)
	if url == "" {
		url = defaultQuoteURL
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		log.Printf("[QUOTE] 创建请求失败: %v", err)
		return fallbackQuoteText, fallbackQuoteSource
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "yj-forum-server")

	client := h.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: timeout}
	}
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("[QUOTE] 拉取失败: %v", err)
		return fallbackQuoteText, fallbackQuoteSource
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		log.Printf("[QUOTE] 上游返回 %d", resp.StatusCode)
		return fallbackQuoteText, fallbackQuoteSource
	}

	var raw quoteResponse
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&raw); err != nil {
		log.Printf("[QUOTE] 解析失败: %v", err)
		return fallbackQuoteText, fallbackQuoteSource
	}
	text := strings.TrimSpace(raw.Content)
	if text == "" {
		return fallbackQuoteText, fallbackQuoteSource
	}
	text = truncateRunes(text, 300)

	parts := make([]string, 0, 2)
	if author := strings.TrimSpace(raw.Author); author != "" {
		parts = append(parts, author)
	}
	if src := strings.TrimSpace(raw.Source); src != "" {
		parts = append(parts, src)
	}
	source := truncateRunes(strings.Join(parts, " · "), 100)
	if source == "" {
		source = "dlystc"
	}
	return text, source
}

// truncateRunes 按字符截断并加省略号。
func truncateRunes(s string, max int) string {
	runes := []rune(s)
	if len(runes) <= max {
		return s
	}
	return string(runes[:max]) + "…"
}
