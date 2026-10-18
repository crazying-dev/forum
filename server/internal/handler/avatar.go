package handler

import (
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/media"
)

const maxAvatarBytes = 10 << 20

// ServeAvatar 提供旧本地头像文件（/avatar/:filename）。
// 新头像写 S3 并返回 /ov2/api/media/<id>，本路由只负责旧资源兼容。
func (h *PostsHandler) ServeAvatar(c *gin.Context) {
	filename := c.Param("filename")
	if strings.Contains(filename, "..") || strings.Contains(filename, "/") || strings.Contains(filename, "\\") {
		c.Status(http.StatusBadRequest)
		return
	}
	full := filepath.Join(h.Cfg.AvatarDir, filename)
	if _, err := os.Stat(full); err != nil {
		c.Status(http.StatusNotFound)
		return
	}
	c.Header("X-Content-Type-Options", "nosniff")
	c.File(full)
}

// UploadAvatar 上传头像：统一走媒体服务（S3 或本地回退），写 users.avatar 为新媒体代理 URL。
func (h *PostsHandler) UploadAvatar(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	file, err := c.FormFile("avatar")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请选择图片文件"})
		return
	}
	if file.Size > maxAvatarBytes {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"success": false, "message": "头像不能超过10MB"})
		return
	}
	src, err := file.Open()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "文件读取失败"})
		return
	}
	defer src.Close()
	data, err := io.ReadAll(io.LimitReader(src, maxAvatarBytes+1))
	if err != nil || len(data) > maxAvatarBytes {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"success": false, "message": "头像不能超过10MB"})
		return
	}
	if h.Media == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "媒体服务未初始化"})
		return
	}
	asset, err := h.Media.Save(c.Request.Context(), media.SaveInput{
		Data: data, OriginalName: file.Filename, Scene: "avatar",
		OwnerType: "avatar", OwnerID: uid, UploaderUserID: uid,
		Visibility: "public", MaxBytes: maxAvatarBytes,
	})
	if err != nil {
		msg := err.Error()
		status := http.StatusInternalServerError
		if strings.Contains(msg, "图片") || strings.Contains(msg, "文件") || strings.Contains(msg, "仅支持") || strings.Contains(msg, "超过") {
			status = http.StatusBadRequest
		}
		c.JSON(status, gin.H{"success": false, "message": msg})
		return
	}
	if err := h.DB.UpdateUserProfile(c.Request.Context(), uid, map[string]any{"avatar": asset.PublicURL}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "头像保存失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "avatar": asset.PublicURL})
}
