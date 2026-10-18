package handler

import (
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/media"
)

// MediaHandler 媒体上传与读取（S3/本地统一；按 visibility 做 ACL）。
type MediaHandler struct {
	DB       *database.DB
	Cfg      *config.Config
	Media    *media.Service
	Sessions *auth.SessionManager
}

var allowedMediaScenes = map[string]struct{}{
	"post_image":    {},
	"comment_image": {},
	"world_message": {},
	"chat_message":  {},
}

// sceneMeta 返回 owner_type 与默认 visibility。
func sceneMeta(scene string) (string, string) {
	switch scene {
	case "comment_image":
		return "comment", "public"
	case "world_message":
		return "world", "public"
	case "chat_message":
		return "chat", "private"
	default:
		return "post", "public"
	}
}

// UploadImage 上传图片（登录；multipart file；scene 决定用途与 ACL）。
func (h *MediaHandler) UploadImage(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, media.MaxInputBytes+(1<<20))
	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请选择图片文件"})
		return
	}
	if file.Size > media.MaxInputBytes {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"success": false, "message": "图片大小不能超过5MB"})
		return
	}
	src, err := file.Open()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "文件读取失败"})
		return
	}
	defer src.Close()
	data, err := io.ReadAll(io.LimitReader(src, media.MaxInputBytes+1))
	if err != nil || len(data) > media.MaxInputBytes {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"success": false, "message": "图片大小不能超过5MB"})
		return
	}

	scene := strings.TrimSpace(c.PostForm("scene"))
	if scene == "" {
		scene = strings.TrimSpace(c.Query("scene"))
	}
	if _, ok := allowedMediaScenes[scene]; !ok {
		scene = "post_image"
	}
	ownerType, visibility := sceneMeta(scene)
	ownerID := strings.TrimSpace(c.PostForm("owner_id"))
	if ownerID == "" {
		ownerID = strings.TrimSpace(c.Query("owner_id"))
	}
	guildUUID := strings.TrimSpace(c.PostForm("guild_uuid"))
	if guildUUID == "" {
		guildUUID = strings.TrimSpace(c.Query("guild_uuid"))
	}

	asset, err := h.Media.Save(c.Request.Context(), media.SaveInput{
		Data: data, OriginalName: file.Filename, Scene: scene,
		OwnerType: ownerType, OwnerID: ownerID, GuildUUID: guildUUID,
		UploaderUserID: uid, Visibility: visibility,
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
	c.JSON(http.StatusOK, gin.H{"success": true, "id": asset.ID, "url": absoluteMediaURL(h.Cfg, c.Request, asset.PublicURL)})
}

// absoluteMediaURL 把媒体相对路径（数据库仍存相对路径）补成绝对地址：
// 优先 PUBLIC_BASE_URL（normalizeBaseURL），为空时按请求 scheme/host 兜底。
func absoluteMediaURL(cfg *config.Config, r *http.Request, publicURL string) string {
	path := strings.TrimSpace(publicURL)
	if path == "" {
		return ""
	}
	if strings.HasPrefix(path, "http://") || strings.HasPrefix(path, "https://") {
		return path
	}
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}

	base := ""
	if cfg != nil {
		base = normalizeBaseURL(cfg.PublicBaseURL)
	}
	// 配置为本机地址时不可靠（开发默认 localhost:3000、实际端口可能不同），
	// 回退到请求自身 origin，避免把 localhost 写进用户正文。
	if base != "" && !isLoopbackURL(base) {
		return strings.TrimRight(base, "/") + path
	}
	if r == nil {
		return path
	}

	scheme := "http"
	if proto := requestProto(r); proto != "" {
		scheme = proto
	} else if r.TLS != nil {
		scheme = "https"
	}
	host := strings.TrimSpace(r.Host)
	if host == "" {
		return path
	}
	return scheme + "://" + host + path
}

// isLoopbackURL 判断配置地址是否为本机回环 host。
func isLoopbackURL(raw string) bool {
	u, err := url.Parse(raw)
	if err != nil {
		return false
	}
	host := strings.ToLower(u.Hostname())
	return host == "localhost" || host == "::1" || host == "127.0.0.1" || strings.HasPrefix(host, "127.")
}

// requestProto 读取反向代理的 X-Forwarded-Proto（取第一个值），仅接受 http/https。
func requestProto(r *http.Request) string {
	raw := strings.TrimSpace(r.Header.Get("X-Forwarded-Proto"))
	if i := strings.IndexByte(raw, ','); i >= 0 {
		raw = strings.TrimSpace(raw[:i])
	}
	proto := strings.ToLower(raw)
	if proto == "http" || proto == "https" {
		return proto
	}
	return ""
}

// ServeImage 读取图片；public 直接读，private 校验本人/聊天成员/定时帖作者。
func (h *MediaHandler) ServeImage(c *gin.Context) {
	asset, err := h.DB.GetMediaAsset(c.Request.Context(), c.Param("id"))
	if err != nil || asset == nil {
		c.Status(http.StatusNotFound)
		return
	}
	if !h.canView(c, asset) {
		c.Status(http.StatusNotFound)
		return
	}
	body, mime, err := h.Media.Open(c.Request.Context(), asset)
	if err != nil {
		c.Status(http.StatusNotFound)
		return
	}
	defer body.Close()
	if mime != "" {
		c.Header("Content-Type", mime)
	}
	c.Header("X-Content-Type-Options", "nosniff")
	c.Header("Content-Disposition", "inline")
	if asset.Visibility == "public" {
		c.Header("Cache-Control", "public, max-age=600")
	} else {
		c.Header("Cache-Control", "private, max-age=60")
	}
	c.Status(http.StatusOK)
	_, _ = io.Copy(c.Writer, body)
}

func (h *MediaHandler) canView(c *gin.Context, asset *database.MediaAsset) bool {
	if asset.Visibility == "public" {
		return true
	}
	uid := CurrentUser(c)
	if uid == "" {
		return false
	}
	if asset.UploaderUserID != "" && asset.UploaderUserID == uid {
		return true
	}
	ctx := c.Request.Context()
	switch asset.OwnerType {
	case "chat":
		if asset.OwnerID == "" {
			return false
		}
		ok, err := h.DB.IsChatRoomMember(ctx, asset.OwnerID, uid)
		return err == nil && ok
	case "post":
		if asset.OwnerID == "" {
			return false
		}
		owner, published, err := h.DB.GetPostOwnerAndPublished(ctx, asset.OwnerID)
		if err != nil || owner == "" {
			return false
		}
		if owner == uid {
			return true
		}
		return published != nil && !published.After(time.Now())
	case "comment":
		if asset.OwnerID == "" {
			return false
		}
		owner, err := h.DB.GetCommentOwner(ctx, asset.OwnerID)
		return err == nil && owner == uid
	case "feedback":
		// 反馈附件仅 admin 后台可读；ouo 前台不提供
		return false
	default:
		return false
	}
}
