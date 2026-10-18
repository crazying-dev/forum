package handler

import (
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/releases"
)

// DownloadsHandler 下载页与客户端更新（数据源 GitHub Releases）。
type DownloadsHandler struct {
	Releases *releases.Service
	Client   *http.Client // 可选：mirror 上游客户端（测试注入）
}

// mirrorHosts 允许反代的 GitHub 域名（含子域）。
var mirrorHosts = []string{"github.com", "githubusercontent.com", "githubassets.com"}

// defaultMirrorClient 流式反代客户端：不设整体超时（大文件），只限制响应头等待时间。
var defaultMirrorClient = &http.Client{
	Transport: &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		ResponseHeaderTimeout: 30 * time.Second,
		IdleConnTimeout:       90 * time.Second,
	},
	CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 10 {
			return errors.New("重定向次数过多")
		}
		if !isAllowedMirrorURL(req.URL.String()) {
			return fmt.Errorf("重定向到非白名单域名: %s", req.URL.Host)
		}
		return nil
	},
}

// platformOrDefault 平台参数，缺省 windows（与旧 APP 客户端一致）。
func platformOrDefault(c *gin.Context) string {
	p := strings.TrimSpace(c.Query("platform"))
	if p == "" {
		return releases.PlatformWindows
	}
	return p
}

func (h *DownloadsHandler) available(c *gin.Context) bool {
	if h.Releases != nil {
		return true
	}
	c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "message": "下载服务未配置"})
	return false
}

// writeReleasesError 统一错误映射：未知平台/无版本/附件不存在 404，其余（GitHub 读取失败）502。
func writeReleasesError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, releases.ErrUnknownPlatform):
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "未知平台"})
	case errors.Is(err, releases.ErrNoRelease):
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "该平台暂未发布"})
	case errors.Is(err, releases.ErrAssetNotFound):
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "安装包不存在"})
	default:
		log.Printf("[DOWNLOAD] 读取 GitHub Releases 失败: %v", err)
		c.JSON(http.StatusBadGateway, gin.H{"success": false, "message": "获取发布信息失败"})
	}
}

// ---- GET /downloads/releases ----

// List 发布列表（可按 platform 过滤；page_size 默认 20）。
func (h *DownloadsHandler) List(c *gin.Context) {
	if !h.available(c) {
		return
	}
	page, pageSize := parsePage(c)
	result, err := h.Releases.List(page, pageSize, c.Query("platform"))
	if err != nil {
		writeReleasesError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true, "items": result.Items, "total": result.Total,
		"page": result.Page, "page_size": result.PageSize,
	})
}

// ---- GET /downloads/latest ----

// Latest 平台最新版本（优先 stable）。
func (h *DownloadsHandler) Latest(c *gin.Context) {
	if !h.available(c) {
		return
	}
	item, err := h.Releases.Latest(platformOrDefault(c))
	if err != nil {
		writeReleasesError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "item": item})
}

// ---- GET /downloads/check ----

// Check 版本检查：available（有更新）/ mandatory（current<min_version）等 426 判定字段。
func (h *DownloadsHandler) Check(c *gin.Context) {
	if !h.available(c) {
		return
	}
	platform := platformOrDefault(c)
	version := strings.TrimSpace(c.DefaultQuery("version", "0.0.0"))
	result, err := h.Releases.Check(platform, version)
	if err != nil {
		writeReleasesError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success":      true,
		"available":    result.Available,
		"mandatory":    result.Mandatory,
		"current":      result.Current,
		"latest":       result.Latest,
		"min_version":  result.MinVersion,
		"release":      result.Release,
		"download_url": result.DownloadURL,
	})
}

// ---- GET /downloads/mirror/:platform/:filename ----

// Mirror 流式反代 GitHub 资产（透传 Range，支持断点续传）。
func (h *DownloadsHandler) Mirror(c *gin.Context) {
	if !h.available(c) {
		return
	}
	platform := c.Param("platform")
	filename := c.Param("filename")
	asset, err := h.Releases.FindAsset(platform, filename)
	if err != nil {
		writeReleasesError(c, err)
		return
	}
	if !isAllowedMirrorURL(asset.URL) {
		c.JSON(http.StatusBadGateway, gin.H{"success": false, "message": "上游地址不受信任"})
		return
	}

	req, err := http.NewRequestWithContext(c.Request.Context(), http.MethodGet, asset.URL, nil)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"success": false, "message": "上游请求创建失败"})
		return
	}
	req.Header.Set("User-Agent", "yj-forum-mirror")
	req.Header.Set("Accept", "*/*")
	req.Header.Set("Accept-Encoding", "identity")
	if rng := strings.TrimSpace(c.GetHeader("Range")); rng != "" {
		req.Header.Set("Range", rng)
	}

	client := h.Client
	if client == nil {
		client = defaultMirrorClient
	}
	resp, err := client.Do(req)
	if err != nil {
		log.Printf("[DOWNLOAD] 反代拉取失败 (%s): %v", asset.URL, err)
		c.JSON(http.StatusBadGateway, gin.H{"success": false, "message": "上游拉取失败"})
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusRequestedRangeNotSatisfiable {
		if cr := resp.Header.Get("Content-Range"); cr != "" {
			c.Header("Content-Range", cr)
		}
		c.Header("Accept-Ranges", "bytes")
		c.Status(resp.StatusCode)
		return
	}
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		log.Printf("[DOWNLOAD] 上游返回 %d (%s)", resp.StatusCode, asset.URL)
		c.JSON(http.StatusBadGateway, gin.H{"success": false, "message": fmt.Sprintf("上游返回 %d", resp.StatusCode)})
		return
	}

	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	c.Header("Content-Type", contentType)
	c.Header("Accept-Ranges", "bytes")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=\"%s\"", asset.Filename))
	c.Header("Cache-Control", "public, max-age=3600")
	for _, key := range []string{"Content-Length", "Content-Range", "ETag", "Last-Modified"} {
		if v := resp.Header.Get(key); v != "" {
			c.Header(key, v)
		}
	}

	c.Writer.WriteHeader(resp.StatusCode)
	if _, err := io.CopyBuffer(c.Writer, resp.Body, make([]byte, 64*1024)); err != nil {
		log.Printf("[DOWNLOAD] 反代传输中断 (%s): %v", asset.URL, err)
	}
}

// isAllowedMirrorURL 仅允许 https + GitHub 域名白名单（防 SSRF）。
func isAllowedMirrorURL(raw string) bool {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || !strings.EqualFold(u.Scheme, "https") {
		return false
	}
	host := strings.ToLower(u.Hostname())
	if host == "" {
		return false
	}
	for _, allowed := range mirrorHosts {
		if host == allowed || strings.HasSuffix(host, "."+allowed) {
			return true
		}
	}
	return false
}
