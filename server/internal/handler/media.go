package handler

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
)

// maxImageBytes 发帖图片大小上限（5MB）。
const maxImageBytes = 5 << 20

// MediaHandler 用户图片（发帖配图）上传与读取。
type MediaHandler struct {
	DB  *database.DB
	Cfg *config.Config
}

// sniffImageExt 按文件头嗅探图片扩展名（仅 png/jpeg/webp/gif）；非允许类型返回空串。
func sniffImageExt(head []byte) string {
	switch {
	case len(head) >= 8 && bytes.Equal(head[:8], []byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}):
		return ".png"
	case len(head) >= 3 && head[0] == 0xFF && head[1] == 0xD8 && head[2] == 0xFF:
		return ".jpg"
	case len(head) >= 12 && bytes.Equal(head[:4], []byte("RIFF")) && bytes.Equal(head[8:12], []byte("WEBP")):
		return ".webp"
	case len(head) >= 6 && (string(head[:6]) == "GIF87a" || string(head[:6]) == "GIF89a"):
		return ".gif"
	}
	return ""
}

// imageMime 扩展名 -> MIME。
func imageMime(ext string) string {
	switch ext {
	case ".png":
		return "image/png"
	case ".jpg":
		return "image/jpeg"
	case ".webp":
		return "image/webp"
	case ".gif":
		return "image/gif"
	}
	return "application/octet-stream"
}

// truncateRunes 按字符截断（列宽语义），避免切断多字节字符。
func truncateRunes(s string, max int) string {
	r := []rune(s)
	if len(r) > max {
		return string(r[:max])
	}
	return s
}

// ---- POST /api/v1/media/images ----

// UploadImage 上传发帖图片（登录；multipart 字段 file；原样存储不做转码）。
func (h *MediaHandler) UploadImage(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	// 请求体上限 5MB + 1MB（multipart 边界与表单字段余量）
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxImageBytes+(1<<20))
	file, err := c.FormFile("file")
	if err != nil {
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			c.JSON(http.StatusRequestEntityTooLarge, gin.H{"success": false, "message": "图片大小不能超过5MB"})
			return
		}
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请选择图片文件"})
		return
	}
	if file.Size > maxImageBytes {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"success": false, "message": "图片大小不能超过5MB"})
		return
	}
	src, err := file.Open()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "文件读取失败"})
		return
	}
	defer src.Close()

	// 按文件头嗅探类型（仅允许 png/jpeg/webp/gif）
	head := make([]byte, 512)
	n, _ := io.ReadFull(src, head)
	ext := sniffImageExt(head[:n])
	if ext == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "仅支持 PNG/JPG/WebP/GIF 图片"})
		return
	}
	if _, err := src.Seek(0, io.SeekStart); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "文件读取失败"})
		return
	}

	// 随机文件名：16 字节 crypto/rand 的 hex + 嗅探出的扩展名
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "文件名生成失败"})
		return
	}
	fileName := hex.EncodeToString(buf) + ext
	if err := os.MkdirAll(h.Cfg.MediaDir, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "存储目录创建失败"})
		return
	}
	full := filepath.Join(h.Cfg.MediaDir, fileName)
	dst, err := os.Create(full)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "保存失败"})
		return
	}
	written, copyErr := io.Copy(dst, io.LimitReader(src, maxImageBytes+1))
	closeErr := dst.Close()
	if copyErr != nil || closeErr != nil || written > maxImageBytes {
		_ = os.Remove(full)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "保存失败"})
		return
	}

	assetID := database.GenID("MD")
	if err := h.DB.CreateMediaAsset(c.Request.Context(), assetID, fileName,
		truncateRunes(filepath.Base(file.Filename), 255), imageMime(ext), written, uid); err != nil {
		_ = os.Remove(full)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "保存失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "id": assetID, "url": "/api/v1/media/" + assetID})
}

// ---- GET /api/v1/media/:id ----

// ServeImage 读取图片（公开）；不存在或 status≠1 返回 404。
func (h *MediaHandler) ServeImage(c *gin.Context) {
	asset, err := h.DB.GetMediaAsset(c.Request.Context(), c.Param("id"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if asset == nil {
		c.Status(http.StatusNotFound)
		return
	}
	// 路径穿越防护
	if asset.FileName == "" || strings.Contains(asset.FileName, "..") ||
		strings.Contains(asset.FileName, "/") || strings.Contains(asset.FileName, "\\") {
		c.Status(http.StatusNotFound)
		return
	}
	full := filepath.Join(h.Cfg.MediaDir, asset.FileName)
	if _, err := os.Stat(full); err != nil {
		c.Status(http.StatusNotFound)
		return
	}
	if asset.Mime != "" {
		c.Header("Content-Type", asset.Mime)
	}
	c.Header("Cache-Control", "public, max-age=600")
	c.File(full)
}
