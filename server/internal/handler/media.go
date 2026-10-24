package handler

import (
	"context"
	"errors"
	"io"
	"log"
	"net/http"
	"net/url"
	"strconv"
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
// 支持 ?w=480/1280 读取上传时预生成的变体；命中变体时回 X-Media-Variant。
func (h *MediaHandler) ServeImage(c *gin.Context) {
	start := time.Now()
	ctx := c.Request.Context()
	id := c.Param("id")

	asset, err := h.DB.GetMediaAsset(ctx, id)
	if err != nil {
		// 存储/数据库侧异常不应伪装成 404（便于监控发现）。
		c.Header("Cache-Control", "no-store")
		log.Printf("[MEDIA] 资产查询失败 media_id=%s scene=%s provider=%s duration=%s err=%v",
			id, "", "", time.Since(start).Round(time.Millisecond), err)
		c.Status(http.StatusBadGateway)
		return
	}
	if asset == nil {
		c.Status(http.StatusNotFound)
		return
	}
	if !h.canView(c, asset) {
		c.Status(http.StatusNotFound)
		return
	}

	// 变体：仅接受 w=480/1280（需开启变体且媒体为 S3 对象）；未命中则回落原图。
	var variant *database.MediaVariant
	if w := strings.TrimSpace(c.Query("w")); w == "480" || w == "1280" {
		if h.Media != nil && h.Media.VariantsEnabled && h.Media.S3 != nil {
			v, verr := h.DB.GetMediaVariant(ctx, asset.ID, "w"+w)
			if verr != nil {
				log.Printf("[MEDIA] 变体查询失败 media_id=%s variant=w%s err=%v", asset.ID, w, verr)
			} else {
				variant = v
			}
		}
	}

	body, mime, meta, err := h.openMedia(ctx, asset, variant)
	if errors.Is(err, media.ErrMediaNotFound) {
		c.Status(http.StatusNotFound)
		return
	}
	if err != nil {
		// 存储侧错误：不缓存错误响应，并保留可排查的结构化日志。
		c.Header("Cache-Control", "no-store")
		log.Printf("[MEDIA] 读取失败 media_id=%s scene=%s provider=%s duration=%s err=%v",
			asset.ID, asset.Scene, asset.StorageProvider, time.Since(start).Round(time.Millisecond), err)
		c.Status(http.StatusBadGateway)
		return
	}
	defer body.Close()

	if mime != "" {
		c.Header("Content-Type", mime)
	}
	c.Header("X-Content-Type-Options", "nosniff")
	c.Header("Content-Disposition", "inline")
	if !writeMediaHeaders(c, asset, meta) {
		return // If-None-Match 命中：已写 304
	}
	c.Status(http.StatusOK)
	if c.Request.Method == http.MethodHead {
		return // HEAD：只回头部，不传输字节
	}
	_, _ = io.Copy(c.Writer, body)
}

// mediaResponseMeta 响应元数据（原图或变体）。
type mediaResponseMeta struct {
	Size    int64
	SHA256  string
	Variant string // 非空表示命中变体（w480 / w1280）
}

// openMedia 打开原图或变体字节，返回实际服务的对象元数据；变体对象缺失时回落原图。
func (h *MediaHandler) openMedia(ctx context.Context, asset *database.MediaAsset, variant *database.MediaVariant) (io.ReadCloser, string, mediaResponseMeta, error) {
	if variant != nil {
		body, mime, err := h.Media.OpenVariant(ctx, variant)
		if err == nil {
			return body, mime, mediaResponseMeta{Size: variant.Size, SHA256: variant.SHA256, Variant: variant.Variant}, nil
		}
		if !errors.Is(err, media.ErrMediaNotFound) {
			return nil, "", mediaResponseMeta{}, err
		}
		// 变体对象已丢：回落原图
	}
	body, mime, err := h.Media.Open(ctx, asset)
	if err != nil {
		return nil, "", mediaResponseMeta{}, err
	}
	return body, mime, mediaResponseMeta{Size: asset.Size, SHA256: asset.SHA256}, nil
}

// writeMediaHeaders 写入 Content-Length/ETag/Accept-Ranges/Cache-Control 等响应头；
// 命中 If-None-Match 时写 304 并返回 false（调用方不再输出正文）。
func writeMediaHeaders(c *gin.Context, asset *database.MediaAsset, m mediaResponseMeta) bool {
	if m.Variant != "" {
		c.Header("X-Media-Variant", m.Variant)
	}
	if m.Size > 0 {
		c.Header("Content-Length", strconv.FormatInt(m.Size, 10))
	}
	etag := ""
	if m.SHA256 != "" {
		etag = `"` + m.SHA256 + `"`
		c.Header("ETag", etag)
	}
	if asset.Visibility == "public" {
		c.Header("Cache-Control", "public, max-age=31536000, immutable")
	} else {
		c.Header("Cache-Control", "private, max-age=60")
		c.Header("X-Media-Cache", "private")
	}
	if etag != "" && etagMatches(c.GetHeader("If-None-Match"), etag) {
		c.Status(http.StatusNotModified)
		return false
	}
	return true
}

// etagMatches 判断 If-None-Match 是否命中（支持 *、W/ 弱校验前缀与逗号分隔列表）。
func etagMatches(header, etag string) bool {
	for _, raw := range strings.Split(header, ",") {
		candidate := strings.TrimSpace(raw)
		if candidate == "" {
			continue
		}
		if candidate == "*" {
			return true
		}
		candidate = strings.TrimPrefix(candidate, "W/")
		if candidate == etag {
			return true
		}
	}
	return false
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
