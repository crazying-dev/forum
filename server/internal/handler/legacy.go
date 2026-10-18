package handler

import (
	"crypto/rand"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
	"yj-forum/server/internal/legacy"
	"yj-forum/server/internal/middleware"
	"yj-forum/server/internal/models"
)

const (
	legacyUserKey    = "legacyUser"
	legacySessionTTL = 86400 // forum_session 24h，对齐 SessionManager
	maxLegacyAvatar  = 5 << 20
)

var (
	legacyEmailRe = regexp.MustCompile(`^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$`)
	legacyFileRe  = regexp.MustCompile(`^[A-Za-z0-9._-]+$`)
)

// legacyHandler 旧 APP 兼容层 HTTP 处理器。
type legacyHandler struct {
	svc      *legacy.Service
	cfg      *config.Config
	db       *database.DB
	sessions *auth.SessionManager
	mailer   *email.Sender
}

// RegisterLegacyRoutes 注册旧 APP 兼容层路由（/api/* 两代路径 + /Easter-Egg + /avatar/:filename）。
// 由 handler.Register 调用；本函数内部自行创建 r.Group("/api")，不改 router.go。
func RegisterLegacyRoutes(r *gin.Engine, cfg *config.Config, db *database.DB, sessions *auth.SessionManager, mailer *email.Sender) {
	svc := legacy.NewService(db, cfg, sessions)
	h := &legacyHandler{svc: svc, cfg: cfg, db: db, sessions: sessions, mailer: mailer}
	worldH := newLegacyWorldHandler(svc, svc, h.requireUser)

	api := r.Group("/api")
	api.Use(h.legacyHeaders())
	api.Use(h.versionGate())

	// ---- 认证：旧 V1 + forum-new 两代路径 ----
	api.POST("/login", middleware.RateLimit("legacy_login", 10, 5*time.Minute), h.Login)
	api.POST("/register", middleware.RateLimit("legacy_register", 5, 5*time.Minute), h.Register)
	api.POST("/logout", h.Logout)
	api.POST("/user/login", middleware.RateLimit("legacy_login", 10, 5*time.Minute), h.Login)
	api.POST("/user/register", middleware.RateLimit("legacy_register", 5, 5*time.Minute), h.Register)
	api.POST("/user/logout", h.Logout)
	api.GET("/user/info", h.requireUser, h.UserInfo)
	api.PUT("/user/info", h.requireUser, h.UpdateUserInfo)
	api.POST("/user/info", h.requireUser, h.UpdateUserInfo)
	api.POST("/user/avatar/upload", middleware.RateLimit("legacy_avatar", 10, time.Hour), h.requireUser, h.UploadAvatar)

	// ---- 旧 APP 账号/邮箱流程（两代路径）----
	api.POST("/email/send-register-code", middleware.RateLimit("legacy_send_register_code", 5, 10*time.Minute), h.SendRegisterCode)
	api.POST("/send-register-code", middleware.RateLimit("legacy_send_register_code", 5, 10*time.Minute), h.SendRegisterCode)
	api.POST("/email/send-code-reset-password", middleware.RateLimit("legacy_reset_code", 5, 10*time.Minute), h.SendResetPasswordCode)
	api.POST("/send-code-reset-password", middleware.RateLimit("legacy_reset_code", 5, 10*time.Minute), h.SendResetPasswordCode)
	api.POST("/email/reset-password-by-code", middleware.RateLimit("legacy_reset_by_code", 10, 10*time.Minute), h.ResetPasswordByCode)
	api.POST("/reset-password-by-code", middleware.RateLimit("legacy_reset_by_code", 10, 10*time.Minute), h.ResetPasswordByCode)
	api.POST("/email/send-change-password-code", h.requireUser, h.SendChangePasswordCode)
	api.POST("/user/password", h.requireUser, h.ChangePassword)
	api.POST("/email/send-verify-code", h.requireUser, h.SendVerifyEmailCode)
	api.POST("/email/verify-code-email", h.requireUser, h.VerifyCodeEmail)
	api.POST("/email/send-verify-email", h.requireUser, h.SendVerifyEmailLink)
	api.POST("/email/verify-email", h.VerifyEmailToken)
	api.POST("/email/send-change-email-old-code", h.requireUser, h.SendChangeEmailOldCode)
	api.POST("/email/send-change-email-code", h.requireUser, h.SendChangeEmailNewCode)
	api.POST("/user/email", h.requireUser, h.ChangeEmail)
	api.POST("/email/send-delete-account-code", h.requireUser, h.SendDeleteAccountCode)
	api.POST("/user/delete", h.requireUser, h.DeleteAccount)

	// ---- 用户（forum-new 单数 + 旧 V1 复数两代路径）----
	api.GET("/user/:id", h.optionalUser, h.UserProfile)
	api.GET("/user/:id/comments", h.optionalUser, h.UserComments)
	api.GET("/users/:id/comments", h.optionalUser, h.UserComments)
	api.GET("/user/:id/posts", h.optionalUser, h.UserPosts)
	api.GET("/user/:id/favorites", h.optionalUser, h.UserFavorites)
	api.GET("/user/:id/following", h.optionalUser, h.UserFollowing)
	api.GET("/user/:id/followers", h.optionalUser, h.UserFollowers)
	api.POST("/user/:id/follow", h.requireUser, h.ToggleFollow)
	api.GET("/users/:id/info", h.optionalUser, h.UserProfile)
	api.GET("/users/:id/posts", h.optionalUser, h.UserPosts)
	api.GET("/users/:id/favorites", h.optionalUser, h.UserFavorites)
	api.GET("/users/:id/following", h.optionalUser, h.UserFollowing)
	api.GET("/users/:id/followers", h.optionalUser, h.UserFollowers)
	api.POST("/users/:id/follow", h.requireUser, h.ToggleFollow)
	api.GET("/users/me/replies", h.requireUser, h.MyReplies)

	// ---- 帖子 ----
	api.GET("/posts", h.ListPosts)
	api.GET("/posts/random", h.RandomPosts)
	api.GET("/posts/:id", h.optionalUser, h.PostDetail)
	api.POST("/posts/create", h.requireUser, h.CreatePost)
	api.POST("/posts", h.requireUser, h.CreatePost)
	api.POST("/posts/:id/like", h.requireUser, h.LikePost)
	api.POST("/posts/:id/favorite", h.requireUser, h.FavoritePost)
	api.POST("/posts/:id/report", h.requireUser, h.ReportPost)
	api.POST("/posts/:id/delete", h.requireUser, h.DeletePost)

	// ---- 评论 ----
	api.GET("/posts/:id/comments", h.optionalUser, h.ListComments)
	api.POST("/posts/:id/comments/create", h.requireUser, h.CreateComment)
	api.POST("/posts/:id/comments", h.requireUser, h.CreateComment)
	api.POST("/comments/:id/like", h.requireUser, h.LikeComment)
	api.POST("/comments/:id/delete", h.requireUser, h.DeleteComment)

	// ---- 世界频道（两代大小写路径）----
	api.GET("/World/ALL", worldH.All)
	api.POST("/World/Send", worldH.requireUser, worldH.Send)
	api.GET("/world/ALL", worldH.All)
	api.POST("/world/Send", worldH.requireUser, worldH.Send)

	// ---- 搜索 / 反馈 / 静态数据 ----
	api.GET("/search", h.Search)
	api.POST("/report-bug", middleware.RateLimit("legacy_bug", 5, 5*time.Minute), h.optionalUser, h.ReportBug)
	api.GET("/huiguan", h.Huiguan)

	// ---- 旧 APP 发布 / 更新 ----
	api.GET("/app/releases", h.AppReleases)
	api.GET("/app/releases/:platform", h.AppPlatform)
	api.GET("/app/check", h.AppCheck)
	api.GET("/app/download/:platform/:filename", h.AppDownload)
	api.GET("/app/mirror/:platform/:filename", h.AppDownload)
	api.GET("/app/cache", h.AppCache)
	api.GET("/app/windows/forum.exe", h.AppWindowsExe)

	// ---- 根路径 ----
	r.GET("/Easter-Egg", h.EasterEgg)
	r.GET("/avatar/:filename", h.ServeAvatar)
}

// ---- 中间件 ----

// legacyHeaders 标记兼容层与下线日期。
func (h *legacyHandler) legacyHeaders() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("X-Legacy-Compat", "1")
		if h.cfg != nil && strings.TrimSpace(h.cfg.LegacyAppSunset) != "" {
			c.Header("Sunset", strings.TrimSpace(h.cfg.LegacyAppSunset))
		}
		c.Next()
	}
}

// versionGate 最低版本闸门：/api/app/* 豁免；无法判断客户端时放行（fail-open）。
func (h *legacyHandler) versionGate() gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.Request.Method == http.MethodOptions || strings.HasPrefix(c.Request.URL.Path, "/api/app/") {
			c.Next()
			return
		}
		platform, version := legacy.ResolveClient(c.GetHeader("X-Client-Platform"), c.GetHeader("X-Client-Version"), c.GetHeader("User-Agent"))
		if platform == "" || platform == "web" {
			c.Next()
			return
		}
		minimum := h.svc.Releases.MinVersion(platform)
		if minimum == "" || legacy.CompareVersions(version, minimum) >= 0 {
			c.Next()
			return
		}
		downloadURL := h.appDownloadURL(platform)
		downloadPage := ""
		if h.cfg != nil && strings.TrimSpace(h.cfg.PublicBaseURL) != "" {
			downloadPage = strings.TrimRight(h.cfg.PublicBaseURL, "/") + "/Download"
		}
		c.AbortWithStatusJSON(http.StatusUpgradeRequired, gin.H{
			"success": false, "code": "VERSION_TOO_LOW", "message": "版本过低，请更新",
			"platform": platform, "current": version, "min_version": minimum,
			"download_url": downloadURL, "download_page": downloadPage,
		})
	}
}

func (h *legacyHandler) appDownloadURL(platform string) string {
	// 426 响应必须快速返回：只读缓存/内置清单，不在这里触发 GitHub 拉取。
	pf := legacy.FindPlatform(h.svc.Releases.CachedManifest(), platform)
	if pf == nil {
		return ""
	}
	if latest := legacy.PickLatest(pf); latest != nil {
		return latest.URL
	}
	return ""
}

// ---- 认证辅助 ----

func legacyUserFrom(c *gin.Context) *legacy.LegacyUser {
	v, ok := c.Get(legacyUserKey)
	if !ok {
		return nil
	}
	u, _ := v.(*legacy.LegacyUser)
	return u
}

func legacyViewerID(c *gin.Context) string {
	if u := legacyUserFrom(c); u != nil {
		return u.ID
	}
	v, _ := c.Get("userID")
	s, _ := v.(string)
	return s
}

// resolveUser 依次尝试 forum_session、legacy token+ID；校验通过则写 context 并轮换 forum_session。
func (h *legacyHandler) resolveUser(c *gin.Context) *legacy.LegacyUser {
	if u := legacyUserFrom(c); u != nil {
		return u
	}
	ctx := c.Request.Context()

	// 1) 新会话 Cookie
	if h.sessions != nil {
		if token, _ := c.Cookie(cookieName); token != "" {
			if uid, err := h.sessions.Validate(ctx, token); err == nil && uid != "" {
				if u, err := h.svc.LoadUserForLegacy(ctx, uid); err == nil && u.IsBanned == 0 && u.DeletedAt == nil {
					c.Set(legacyUserKey, u)
					c.Set("userID", u.ID)
					return u
				}
			}
		}
	}

	// 2) legacy token + ID Cookie
	token, _ := c.Cookie("token")
	id, _ := c.Cookie("ID")
	if token == "" || id == "" || h.svc.Verifier == nil {
		return nil
	}
	u, err := h.svc.LoadUserForLegacy(ctx, id)
	if err != nil || u.IsBanned != 0 || u.DeletedAt != nil || u.Password == "" {
		return nil
	}
	if err := h.svc.Verifier.Verify(u.ID, token, u.Password, timeValue(u.PasswordChangedAt), time.Now()); err != nil {
		return nil
	}
	c.Set(legacyUserKey, u)
	c.Set("userID", u.ID)
	h.issueSession(c, u.ID)
	return u
}

func timeValue(t *time.Time) time.Time {
	if t == nil {
		return time.Time{}
	}
	return *t
}

// requireUser 要求已登录（兼容层 401 形状）。
func (h *legacyHandler) requireUser(c *gin.Context) {
	if h.resolveUser(c) == nil {
		c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	c.Next()
}

// optionalUser 可选登录，解析失败也继续。
func (h *legacyHandler) optionalUser(c *gin.Context) {
	h.resolveUser(c)
	c.Next()
}

// issueSession 轮换 forum_session Cookie（同时写非 HttpOnly user_id 供新前端识别）。
func (h *legacyHandler) issueSession(c *gin.Context, userID string) {
	if h.sessions == nil {
		return
	}
	if old, _ := c.Cookie(cookieName); old != "" {
		_ = h.sessions.Delete(c.Request.Context(), old)
	}
	token, err := h.sessions.Create(c.Request.Context(), userID)
	if err != nil {
		log.Printf("[LEGACY] 创建 forum_session 失败: %v", err)
		return
	}
	secure := h.cfg != nil && h.cfg.AppEnv == "prod"
	c.SetSameSite(http.SameSiteLaxMode)
	c.SetCookie(cookieName, token, legacySessionTTL, "/", "", secure, true)
	c.SetCookie("user_id", userID, legacySessionTTL*30, "/", "", secure, false)
}

// setLegacyCookies 写 legacy token + ID Cookie。
func (h *legacyHandler) setLegacyCookies(c *gin.Context, userID, token string) {
	maxAge := 7 * 24 * 3600
	if h.cfg != nil && h.cfg.LegacyTokenTTL > 0 {
		maxAge = int(h.cfg.LegacyTokenTTL / time.Second)
	}
	secure := h.cfg != nil && h.cfg.AppEnv == "prod"
	c.SetSameSite(http.SameSiteLaxMode)
	c.SetCookie("token", token, maxAge, "/", "", secure, true)
	c.SetCookie("ID", userID, maxAge, "/", "", secure, true)
}

func (h *legacyHandler) clearAuthCookies(c *gin.Context) {
	c.SetSameSite(http.SameSiteLaxMode)
	for _, name := range []string{cookieName, "user_id", "token", "ID"} {
		c.SetCookie(name, "", -1, "/", "", false, true)
	}
}

// ---- 登录 / 注册 / 登出 ----

type legacyLoginReq struct {
	Name     string `json:"name"`
	Email    string `json:"email"`
	Username string `json:"username"`
	Account  string `json:"account"`
	User     string `json:"user"`
	Password string `json:"password"`
}

// Login 兼容登录：写 legacy token+ID 与 forum_session。
func (h *legacyHandler) Login(c *gin.Context) {
	var req legacyLoginReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "用户名或密码错误"})
		return
	}
	identifier := strings.TrimSpace(req.Name)
	if identifier == "" {
		identifier = strings.TrimSpace(req.Email)
	}
	if identifier == "" {
		identifier = strings.TrimSpace(req.Username)
	}
	if identifier == "" {
		identifier = strings.TrimSpace(req.Account)
	}
	if identifier == "" {
		identifier = strings.TrimSpace(req.User)
	}
	if identifier == "" || req.Password == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "用户名或密码错误"})
		return
	}
	u, err := h.svc.LoadUserByIdentifier(c.Request.Context(), identifier)
	if err != nil || u.IsBanned != 0 || u.DeletedAt != nil || !auth.CheckPassword(u.Password, req.Password) {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "用户名或密码错误"})
		return
	}
	_ = h.db.UpdateUserLastLogin(c.Request.Context(), u.ID)
	token, err := legacy.GenerateToken(h.secretKey(), u.ID, u.Password, time.Now())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	h.setLegacyCookies(c, u.ID, token)
	h.issueSession(c, u.ID)
	if h.mailer != nil && u.Email != "" {
		go h.sendLoginNotice(u)
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "登录成功", "Token": token, "user": u.PublicMap(true)})
}

// sendLoginNotice 异步登录提醒（失败静默，不影响登录）。
func (h *legacyHandler) sendLoginNotice(u *legacy.LegacyUser) {
	nowStr := time.Now().Format("2006-01-02 15:04:05")
	plain := "尊敬的 " + u.Name + "，您好！\n\n您的账号已于 " + nowStr + " 登录妖精论坛。\n如非本人操作，请立即修改密码。\n\n© 2026 妖精论坛 - 粉丝公益创作"
	htmlBody := email.BuildHTML("登录提醒", "您的账号已登录",
		[]string{"尊敬的 " + u.Name + "，您好！", "您的账号已于 " + nowStr + " 登录妖精论坛。", "如非本人操作，请立即修改密码。"},
		"", "", "")
	_, _ = h.mailer.Send("【妖精论坛】登录提醒", plain, []string{u.Email}, htmlBody)
}

func (h *legacyHandler) secretKey() string {
	if h.cfg == nil {
		return ""
	}
	return h.cfg.SecretKey
}

type legacyRegisterReq struct {
	Name     string `json:"name"`
	Email    string `json:"email"`
	Password string `json:"password"`
	Code     string `json:"code"`
}

// Register 兼容注册：校验字段，可选邮箱验证码；成功后自动登录。
func (h *legacyHandler) Register(c *gin.Context) {
	var req legacyRegisterReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	name := strings.TrimSpace(req.Name)
	email := strings.ToLower(strings.TrimSpace(req.Email))
	password := req.Password
	code := strings.TrimSpace(req.Code)
	cleanName := database.StripEasterEgg(name)
	if n := len([]rune(cleanName)); n < 2 || n > 20 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "用户名需2-20个字符"})
		return
	}
	if strings.HasPrefix(cleanName, "已注销") {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "该用户名为保留名称"})
		return
	}
	if !legacyEmailRe.MatchString(email) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请输入有效的邮箱"})
		return
	}
	if len(password) < 8 || !hasLetterAndDigit(password) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码至少8位且需包含字母和数字"})
		return
	}
	if h.db.UserExistsByName(c.Request.Context(), name) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "用户名已被占用", "error": "name_exists"})
		return
	}
	if h.db.UserExistsByEmail(c.Request.Context(), email) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "邮箱已被注册", "error": "email_exists"})
		return
	}
	// 注册必须有邮箱验证码（旧 APP 也会提交 code）；黑名单与 ALTCHA 补偿控制同时生效
	if code == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请输入邮箱验证码"})
		return
	}
	blocked, blErr := h.db.IsEmailBlacklisted(c.Request.Context(), email)
	if blErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if blocked {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "邮箱异样"})
		return
	}
	ok, err := h.db.GetVerifyCode(c.Request.Context(), email, code, "register")
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码无效或已过期"})
		return
	}
	verified := true
	hash, err := auth.HashPassword(password)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	avatar := h.defaultAvatar()
	uid, err := h.db.NewUser(c.Request.Context(), name, email, hash, avatar)
	if err != nil {
		msg := "注册失败"
		errText := strings.ToLower(err.Error())
		code := ""
		if strings.Contains(errText, "email") {
			msg, code = "邮箱已被注册", "email_exists"
		} else if strings.Contains(errText, "name") {
			msg, code = "用户名已存在", "name_exists"
		}
		payload := gin.H{"success": false, "message": msg}
		if code != "" {
			payload["error"] = code
		}
		c.JSON(http.StatusBadRequest, payload)
		return
	}
	if verified {
		_ = h.db.UpdateUserEmailVerified(c.Request.Context(), uid)
		_ = h.db.MarkVerifyCodeUsed(c.Request.Context(), email, code, "register")
	}
	u, err := h.svc.LoadUserForLegacy(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{"success": true, "message": "注册成功", "id": uid, "avatar": avatar})
		return
	}
	token, err := legacy.GenerateToken(h.secretKey(), u.ID, u.Password, time.Now())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	h.setLegacyCookies(c, u.ID, token)
	h.issueSession(c, u.ID)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "注册成功", "id": uid, "avatar": avatar,
		"Token": token, "user": u.PublicMap(true)})
}

func (h *legacyHandler) defaultAvatar() string {
	if h.cfg != nil && strings.TrimSpace(h.cfg.ImageFatherURL) != "" {
		return strings.TrimRight(h.cfg.ImageFatherURL, "/") + "/avatars/LuoXiaoHei1.png"
	}
	return "/avatar/default.png"
}

// ---- 旧 APP 账号/邮箱流程 ----

func legacyRandCode() string {
	var b [4]byte
	_, _ = rand.Read(b[:])
	n := binary.BigEndian.Uint32(b[:]) % 1000000
	return fmt.Sprintf("%06d", n)
}

type legacyEmailReq struct {
	Email string `json:"email"`
}

func (h *legacyHandler) sendLegacyCode(c *gin.Context, toEmail, purpose, label string) {
	toEmail = strings.ToLower(strings.TrimSpace(toEmail))
	if toEmail == "" || !legacyEmailRe.MatchString(toEmail) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请输入有效的邮箱"})
		return
	}
	code := legacyRandCode()
	if err := h.db.CreateVerifyCode(c.Request.Context(), toEmail, code, purpose, 10); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	plain := fmt.Sprintf("你的%s验证码是 %s，10 分钟内有效。", label, code)
	htmlBody := email.BuildHTML("妖精论坛", label+"验证码",
		[]string{"验证码：<strong>" + code + "</strong>", "10 分钟内有效"}, "", "", "")
	go func() {
		_, _ = h.mailer.Send("【妖精论坛】"+label+"验证码", plain, []string{toEmail}, htmlBody)
	}()
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "验证码已发送"})
}

// SendRegisterCode 旧 APP 注册验证码。
func (h *legacyHandler) SendRegisterCode(c *gin.Context) {
	var req legacyEmailReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	email := strings.ToLower(strings.TrimSpace(req.Email))
	if h.db.UserExistsByEmail(c.Request.Context(), email) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "邮箱已被注册"})
		return
	}
	if blocked, _ := h.db.IsEmailBlacklisted(c.Request.Context(), email); blocked {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "邮箱异样"})
		return
	}
	h.sendLegacyCode(c, email, "register", "注册")
}

// SendResetPasswordCode 旧 APP 验证码重置密码（发送）。
func (h *legacyHandler) SendResetPasswordCode(c *gin.Context) {
	var req legacyEmailReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	h.sendLegacyCode(c, req.Email, "reset_password", "重置密码")
}

// ResetPasswordByCode 旧 APP 验证码重置密码（提交）。
func (h *legacyHandler) ResetPasswordByCode(c *gin.Context) {
	var req struct {
		Email    string `json:"email"`
		Code     string `json:"code"`
		Password string `json:"password"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	email := strings.ToLower(strings.TrimSpace(req.Email))
	if len(req.Password) < 8 || !hasLetterAndDigit(req.Password) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码至少8位且需包含字母和数字"})
		return
	}
	ok, err := h.db.GetVerifyCode(c.Request.Context(), email, strings.TrimSpace(req.Code), "reset_password")
	if err != nil || !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码无效或已过期"})
		return
	}
	u, err := h.db.GetUserByEmailWithPassword(c.Request.Context(), email)
	if err != nil || u == nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码无效或已过期"})
		return
	}
	hash, err := auth.HashPassword(req.Password)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if err := h.db.UpdateUserProfile(c.Request.Context(), u.ID, map[string]any{"password": hash, "password_changed_at": time.Now()}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "重置失败"})
		return
	}
	_ = h.db.MarkVerifyCodeUsed(c.Request.Context(), email, strings.TrimSpace(req.Code), "reset_password")
	_ = h.sessions.DeleteByUserID(c.Request.Context(), u.ID)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "密码已重置"})
}

// SendChangePasswordCode 旧 APP 修改密码验证码（发到当前邮箱）。
func (h *legacyHandler) SendChangePasswordCode(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	h.sendLegacyCode(c, u.Email, "change_password", "修改密码")
}

// ChangePassword 旧 APP 修改密码（旧密码或邮箱验证码）。
func (h *legacyHandler) ChangePassword(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req struct {
		OldPassword string `json:"old_password"`
		Code        string `json:"code"`
		NewPassword string `json:"new_password"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if len(req.NewPassword) < 8 || !hasLetterAndDigit(req.NewPassword) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码至少8位且需包含字母和数字"})
		return
	}
	if strings.TrimSpace(req.Code) != "" {
		ok, err := h.db.GetVerifyCode(c.Request.Context(), u.Email, strings.TrimSpace(req.Code), "change_password")
		if err != nil || !ok {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码无效或已过期"})
			return
		}
		_ = h.db.MarkVerifyCodeUsed(c.Request.Context(), u.Email, strings.TrimSpace(req.Code), "change_password")
	} else {
		full, err := h.db.GetUserByIDWithPassword(c.Request.Context(), u.ID)
		if err != nil || !auth.CheckPassword(full.Password, req.OldPassword) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "旧密码错误"})
			return
		}
	}
	hash, err := auth.HashPassword(req.NewPassword)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if err := h.db.UpdateUserProfile(c.Request.Context(), u.ID, map[string]any{"password": hash, "password_changed_at": time.Now()}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "修改失败"})
		return
	}
	_ = h.sessions.DeleteByUserID(c.Request.Context(), u.ID)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "密码已修改，请重新登录"})
}

// SendVerifyEmailCode 旧 APP 邮箱验证码。
func (h *legacyHandler) SendVerifyEmailCode(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	h.sendLegacyCode(c, u.Email, "email_verify", "邮箱验证")
}

// VerifyCodeEmail 旧 APP 邮箱验证码确认。
func (h *legacyHandler) VerifyCodeEmail(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req struct {
		Code string `json:"code"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	ok, err := h.db.GetVerifyCode(c.Request.Context(), u.Email, strings.TrimSpace(req.Code), "email_verify")
	if err != nil || !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码无效或已过期"})
		return
	}
	_ = h.db.MarkVerifyCodeUsed(c.Request.Context(), u.Email, strings.TrimSpace(req.Code), "email_verify")
	_ = h.db.UpdateUserEmailVerified(c.Request.Context(), u.ID)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "邮箱已验证"})
}

// SendVerifyEmailLink 旧 APP 邮箱验证链接。
func (h *legacyHandler) SendVerifyEmailLink(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	token, err := h.db.CreateVerifyToken(c.Request.Context(), u.ID, "email_verify", 60)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	base := strings.TrimRight(h.cfg.PublicBaseURL, "/")
	if !strings.HasPrefix(base, "http") {
		base = "https://" + base
	}
	link := base + "/verify-email?token=" + token
	htmlBody := email.BuildHTML("妖精论坛", "邮箱验证", []string{"点击下方按钮完成邮箱验证", "链接 60 分钟内有效"}, "验证邮箱", link, "")
	go func() {
		_, _ = h.mailer.Send("【妖精论坛】邮箱验证", "请打开链接验证邮箱："+link, []string{u.Email}, htmlBody)
	}()
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "验证邮件已发送"})
}

// VerifyEmailToken 旧 APP 邮箱验证链接回调。
func (h *legacyHandler) VerifyEmailToken(c *gin.Context) {
	var req struct {
		Token string `json:"token"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	uid, err := h.db.GetVerifyToken(c.Request.Context(), strings.TrimSpace(req.Token), "email_verify")
	if err != nil || uid == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "链接无效或已过期"})
		return
	}
	_ = h.db.UpdateUserEmailVerified(c.Request.Context(), uid)
	_ = h.db.DeleteVerifyToken(c.Request.Context(), strings.TrimSpace(req.Token))
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "邮箱已验证"})
}

// SendChangeEmailOldCode 换绑第 1 步：旧邮箱验证码。
func (h *legacyHandler) SendChangeEmailOldCode(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	h.sendLegacyCode(c, u.Email, "email_change_old", "更换邮箱（身份确认）")
}

// SendChangeEmailNewCode 换绑第 2 步：新邮箱验证码。
func (h *legacyHandler) SendChangeEmailNewCode(c *gin.Context) {
	var req legacyEmailReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	email := strings.ToLower(strings.TrimSpace(req.Email))
	if h.db.UserExistsByEmail(c.Request.Context(), email) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "邮箱已被注册"})
		return
	}
	h.sendLegacyCode(c, email, "email_change_new", "更换绑定邮箱")
}

// ChangeEmail 换绑邮箱：旧邮箱码 + 新邮箱码。
func (h *legacyHandler) ChangeEmail(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req struct {
		OldCode string `json:"old_code"`
		Email   string `json:"email"`
		Code    string `json:"code"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	email := strings.ToLower(strings.TrimSpace(req.Email))
	ok, err := h.db.GetVerifyCode(c.Request.Context(), u.Email, strings.TrimSpace(req.OldCode), "email_change_old")
	if err != nil || !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "旧邮箱验证码无效"})
		return
	}
	ok, err = h.db.GetVerifyCode(c.Request.Context(), email, strings.TrimSpace(req.Code), "email_change_new")
	if err != nil || !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "新邮箱验证码无效"})
		return
	}
	if err := h.db.UpdateUserProfile(c.Request.Context(), u.ID, map[string]any{"email": email}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "换绑失败"})
		return
	}
	_ = h.db.MarkVerifyCodeUsed(c.Request.Context(), u.Email, strings.TrimSpace(req.OldCode), "email_change_old")
	_ = h.db.MarkVerifyCodeUsed(c.Request.Context(), email, strings.TrimSpace(req.Code), "email_change_new")
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "邮箱已更换"})
}

// UserComments 旧 APP 个人页评论列表。
func (h *legacyHandler) UserComments(c *gin.Context) {
	id := strings.TrimSpace(c.Param("id"))
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "50"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 50
	}
	comments, total, err := h.db.GetUserComments(c.Request.Context(), id, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "comments": comments, "total": total, "page": page, "page_size": pageSize})
}

// SendDeleteAccountCode 旧 APP 注销账号验证码。
func (h *legacyHandler) SendDeleteAccountCode(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	h.sendLegacyCode(c, u.Email, "delete_account", "注销账号")
}

// DeleteAccount 旧 APP 注销账号（purge / anonymize）。
func (h *legacyHandler) DeleteAccount(c *gin.Context) {
	u := legacyUserFrom(c)
	if u == nil {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req struct {
		Mode     string `json:"mode"`
		Confirm  string `json:"confirm"`
		Password string `json:"password"`
		Code     string `json:"code"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	mode := strings.TrimSpace(req.Mode)
	if mode != "purge" && mode != "anonymize" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	confirm := strings.TrimSpace(req.Confirm)
	if confirm != "注销账号" && confirm != u.Name {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "确认信息不匹配"})
		return
	}
	if strings.TrimSpace(req.Code) != "" {
		ok, err := h.db.GetVerifyCode(c.Request.Context(), u.Email, strings.TrimSpace(req.Code), "delete_account")
		if err != nil || !ok {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码无效或已过期"})
			return
		}
		_ = h.db.MarkVerifyCodeUsed(c.Request.Context(), u.Email, strings.TrimSpace(req.Code), "delete_account")
	} else {
		full, err := h.db.GetUserByIDWithPassword(c.Request.Context(), u.ID)
		if err != nil || !auth.CheckPassword(full.Password, req.Password) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码错误"})
			return
		}
	}
	var err error
	if mode == "purge" {
		_, err = h.db.PurgeUser(c.Request.Context(), u.ID)
	} else {
		defaultAvatar := h.cfg.ImageFatherURL + "/avatars/LuoXiaoHei1.png"
		_, err = h.db.AnonymizeUser(c.Request.Context(), u.ID, defaultAvatar)
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "注销失败"})
		return
	}
	_ = h.sessions.DeleteByUserID(c.Request.Context(), u.ID)
	h.clearAuthCookies(c)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "账号已注销", "mode": mode})
}

// Logout 清理两套 Cookie 与会话。
func (h *legacyHandler) Logout(c *gin.Context) {
	if token, _ := c.Cookie(cookieName); token != "" && h.sessions != nil {
		_ = h.sessions.Delete(c.Request.Context(), token)
	}
	h.clearAuthCookies(c)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "已退出登录"})
}

// ---- 用户资料 ----

func legacyStatsMap(res *legacy.ProfileResult) map[string]any {
	return map[string]any{
		"post_count": res.Stats.PostCount, "total_likes": res.Stats.TotalLikes, "total_views": res.Stats.TotalViews,
		"following_count": res.FollowStats.FollowingCount, "follower_count": res.FollowStats.FollowerCount,
	}
}

// UserInfo 当前登录用户资料 + stats。
func (h *legacyHandler) UserInfo(c *gin.Context) {
	u := legacyUserFrom(c)
	res, err := h.svc.Profile(c.Request.Context(), u.ID, u.ID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	user := res.User.PublicMap(true)
	user["stats"] = legacyStatsMap(res)
	c.JSON(http.StatusOK, gin.H{"success": true, "user": user})
}

type legacyUpdateUserReq struct {
	Avatar *string `json:"avatar"`
	Gender *int    `json:"gender"`
	Age    *string `json:"age"`
	Intro  *string `json:"intro"`
	Name   *string `json:"name"`
}

// UpdateUserInfo 更新资料白名单字段（avatar/gender/age/intro/name）。
func (h *legacyHandler) UpdateUserInfo(c *gin.Context) {
	u := legacyUserFrom(c)
	var req legacyUpdateUserReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	fields := map[string]any{}
	if req.Avatar != nil {
		avatar := strings.TrimSpace(*req.Avatar)
		if avatar != "" && !validAvatarURL(avatar) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "头像地址不合法"})
			return
		}
		fields["avatar"] = avatar
	}
	if req.Gender != nil {
		g := *req.Gender
		if g < 0 || g > 2 {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "性别取值不合法"})
			return
		}
		fields["gender"] = g
	}
	if req.Age != nil {
		age := strings.TrimSpace(*req.Age)
		if len([]rune(age)) > 32 {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "年龄格式不正确"})
			return
		}
		fields["age"] = age
	}
	if req.Intro != nil {
		intro := strings.TrimSpace(*req.Intro)
		if len([]rune(intro)) > 500 {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "简介过长（最多500字）"})
			return
		}
		fields["intro"] = intro
	}
	if req.Name != nil {
		name := strings.TrimSpace(*req.Name)
		clean := database.StripEasterEgg(name)
		if n := len([]rune(clean)); n < 2 || n > 20 {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "用户名需2-20个字符"})
			return
		}
		if clean != u.Name && h.db.UserExistsByName(c.Request.Context(), clean) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "用户名已被占用"})
			return
		}
		fields["name"] = clean
	}
	if len(fields) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "没有可更新的字段"})
		return
	}
	if err := h.db.UpdateUserProfile(c.Request.Context(), u.ID, fields); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "更新失败"})
		return
	}
	res, err := h.svc.Profile(c.Request.Context(), u.ID, u.ID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	user := res.User.PublicMap(true)
	user["stats"] = legacyStatsMap(res)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "资料已更新", "user": user})
}

// UserProfile 公开资料（/api/user/:id 与 /api/users/:id/info）。
func (h *legacyHandler) UserProfile(c *gin.Context) {
	res, err := h.svc.Profile(c.Request.Context(), c.Param("id"), legacyViewerID(c))
	if err != nil || res.User.IsBanned != 0 || res.User.DeletedAt != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	// 公开资料不下发 email（即使看的是自己，email 只由 /api/user/info 提供）。
	user := res.User.PublicMap(false)
	user["stats"] = legacyStatsMap(res)
	user["is_following"] = res.IsFollowing
	user["is_self"] = res.IsSelf
	c.JSON(http.StatusOK, gin.H{"success": true, "user": user})
}

func (h *legacyHandler) loadPublicTarget(c *gin.Context) (*legacy.LegacyUser, bool) {
	u, err := h.svc.LoadUserForLegacy(c.Request.Context(), c.Param("id"))
	if err != nil || u.IsBanned != 0 || u.DeletedAt != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return nil, false
	}
	return u, true
}

// UserPosts 用户帖子列表。
func (h *legacyHandler) UserPosts(c *gin.Context) {
	u, ok := h.loadPublicTarget(c)
	if !ok {
		return
	}
	page, pageSize := parsePage(c)
	posts, err := h.svc.UserPosts(c.Request.Context(), u.ID, legacyViewerID(c), page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts, "page": page, "page_size": pageSize})
}

// UserFavorites 用户收藏（仅本人可见）。
func (h *legacyHandler) UserFavorites(c *gin.Context) {
	u, ok := h.loadPublicTarget(c)
	if !ok {
		return
	}
	if legacyViewerID(c) != u.ID {
		c.JSON(http.StatusForbidden, gin.H{"success": false, "message": "无权查看他人收藏"})
		return
	}
	page, pageSize := parsePage(c)
	posts, err := h.svc.UserFavorites(c.Request.Context(), u.ID, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts, "page": page, "page_size": pageSize})
}

// UserFollowing 关注列表。
func (h *legacyHandler) UserFollowing(c *gin.Context) {
	h.followList(c, true)
}

// UserFollowers 粉丝列表。
func (h *legacyHandler) UserFollowers(c *gin.Context) {
	h.followList(c, false)
}

func (h *legacyHandler) followList(c *gin.Context, following bool) {
	u, ok := h.loadPublicTarget(c)
	if !ok {
		return
	}
	page, pageSize := parsePage(c)
	var (
		users []legacy.FollowUser
		err   error
	)
	if following {
		users, err = h.svc.Following(c.Request.Context(), u.ID, legacyViewerID(c), page, pageSize)
	} else {
		users, err = h.svc.Followers(c.Request.Context(), u.ID, legacyViewerID(c), page, pageSize)
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "users": users, "page": page, "page_size": pageSize})
}

// ToggleFollow 关注/取消关注。
func (h *legacyHandler) ToggleFollow(c *gin.Context) {
	u, ok := h.loadPublicTarget(c)
	if !ok {
		return
	}
	viewer := legacyUserFrom(c)
	following, err := h.svc.ToggleFollow(c.Request.Context(), viewer.ID, u.ID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "following": following})
}

// MyReplies 我收到的回复。
func (h *legacyHandler) MyReplies(c *gin.Context) {
	page, pageSize := parsePageWithDefault(c, 50)
	replies, total, err := h.svc.MyReplies(c.Request.Context(), legacyUserFrom(c).ID, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "replies": replies, "total": total, "page": page, "page_size": pageSize})
}

// ---- 帖子 ----

// ListPosts 帖子列表。
func (h *legacyHandler) ListPosts(c *gin.Context) {
	page, pageSize := parsePage(c)
	posts, err := h.svc.PostList(c.Request.Context(), page, pageSize, c.Query("category"), c.Query("sort"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts, "page": page, "page_size": pageSize})
}

// RandomPosts 随机帖子。
func (h *legacyHandler) RandomPosts(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "200"))
	posts, err := h.svc.RandomPosts(c.Request.Context(), limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "posts": posts})
}

// PostDetail 帖子详情 + 评论 + 点赞/收藏状态。
func (h *legacyHandler) PostDetail(c *gin.Context) {
	post, comments, liked, favorited, err := h.svc.Detail(c.Request.Context(), c.Param("id"), legacyViewerID(c))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "帖子不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "post": post, "comments": comments, "liked": liked, "favorited": favorited})
}

func (h *legacyHandler) visiblePost(c *gin.Context, id, viewer string) (*models.Post, bool) {
	post, err := h.db.GetPost(c.Request.Context(), id)
	if err != nil || post == nil || post.Status != 1 {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "帖子不存在"})
		return nil, false
	}
	if post.PublishedAt != nil && post.PublishedAt.After(time.Now()) && post.UserID != viewer {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "帖子不存在"})
		return nil, false
	}
	return post, true
}

// CreatePost 发帖（markdown 原样入库）。
func (h *legacyHandler) CreatePost(c *gin.Context) {
	var req struct {
		Title    string `json:"title"`
		Content  string `json:"content"`
		Category string `json:"category"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	title := strings.TrimSpace(req.Title)
	content := strings.TrimSpace(req.Content)
	if title == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "标题不能为空"})
		return
	}
	if len([]rune(title)) > 100 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "标题过长（最多100字）"})
		return
	}
	if content == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "内容不能为空"})
		return
	}
	if len(content) > 256*1024 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "正文过长"})
		return
	}
	id, err := h.svc.CreatePost(c.Request.Context(), legacyUserFrom(c).ID, title, content, req.Category)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "发布失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "id": id})
}

// LikePost 点赞切换。
func (h *legacyHandler) LikePost(c *gin.Context) {
	if _, ok := h.visiblePost(c, c.Param("id"), legacyUserFrom(c).ID); !ok {
		return
	}
	liked, likes, err := h.db.LikePost(c.Request.Context(), c.Param("id"), legacyUserFrom(c).ID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "操作失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "liked": liked, "likes": likes})
}

// FavoritePost 收藏切换。
func (h *legacyHandler) FavoritePost(c *gin.Context) {
	if _, ok := h.visiblePost(c, c.Param("id"), legacyUserFrom(c).ID); !ok {
		return
	}
	favorited, err := h.db.ToggleFavorite(c.Request.Context(), c.Param("id"), legacyUserFrom(c).ID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "操作失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "favorited": favorited})
}

// ReportPost 举报帖子。
func (h *legacyHandler) ReportPost(c *gin.Context) {
	if _, ok := h.visiblePost(c, c.Param("id"), legacyUserFrom(c).ID); !ok {
		return
	}
	var req struct {
		Reason string `json:"reason"`
		Detail string `json:"detail"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if strings.TrimSpace(req.Reason) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请选择举报原因"})
		return
	}
	if len([]rune(req.Detail)) > 500 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "描述过长（最多500字）"})
		return
	}
	if err := h.db.ReportPost(c.Request.Context(), c.Param("id"), legacyUserFrom(c).ID, req.Reason, req.Detail); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "举报失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// DeletePost 删除帖子（仅作者）。
func (h *legacyHandler) DeletePost(c *gin.Context) {
	post, err := h.db.GetPost(c.Request.Context(), c.Param("id"))
	if err != nil || post == nil || post.Status != 1 {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "帖子不存在"})
		return
	}
	if post.UserID != legacyUserFrom(c).ID {
		c.JSON(http.StatusForbidden, gin.H{"success": false, "message": "无权删除此帖子"})
		return
	}
	if _, err := h.db.DeletePost(c.Request.Context(), post.ID, legacyUserFrom(c).ID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "删除失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ---- 评论 ----

// ListComments 评论列表。
func (h *legacyHandler) ListComments(c *gin.Context) {
	if _, ok := h.visiblePost(c, c.Param("id"), legacyViewerID(c)); !ok {
		return
	}
	page, pageSize := parsePageWithDefault(c, 50)
	comments, err := h.svc.CommentList(c.Request.Context(), c.Param("id"), page, pageSize, legacyViewerID(c))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "comments": comments, "page": page, "page_size": pageSize})
}

// CreateComment 发表评论（markdown 原样入库）。
func (h *legacyHandler) CreateComment(c *gin.Context) {
	if _, ok := h.visiblePost(c, c.Param("id"), legacyUserFrom(c).ID); !ok {
		return
	}
	var req struct {
		Content  string  `json:"content"`
		ParentID *string `json:"parent_id"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	content := strings.TrimSpace(req.Content)
	if content == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "评论内容不能为空"})
		return
	}
	if len([]rune(content)) > 500 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "评论过长（最多500字）"})
		return
	}
	comment, err := h.svc.CreateComment(c.Request.Context(), c.Param("id"), legacyUserFrom(c).ID, content, req.ParentID)
	if err != nil {
		if errors.Is(err, legacy.ErrCommentNotFound) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "回复的评论不存在或已删除"})
			return
		}
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "评论失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "comment": comment})
}

// LikeComment 评论点赞切换。
func (h *legacyHandler) LikeComment(c *gin.Context) {
	liked, likes, err := h.db.LikeComment(c.Request.Context(), c.Param("id"), legacyUserFrom(c).ID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "评论不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "liked": liked, "likes": likes})
}

// DeleteComment 删除评论（仅作者）。
func (h *legacyHandler) DeleteComment(c *gin.Context) {
	comment, err := h.db.GetComment(c.Request.Context(), c.Param("id"))
	if err != nil || comment == nil || comment.Status != 1 {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "评论不存在"})
		return
	}
	if comment.UserID != legacyUserFrom(c).ID {
		c.JSON(http.StatusForbidden, gin.H{"success": false, "message": "无权删除此评论"})
		return
	}
	if _, err := h.db.DeleteComment(c.Request.Context(), comment.ID, legacyUserFrom(c).ID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "删除失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// ---- 搜索 / 反馈 / 静态数据 ----

// Search 搜索帖子 / 用户。
func (h *legacyHandler) Search(c *gin.Context) {
	keyword := strings.TrimSpace(c.Query("k"))
	if len([]rune(keyword)) < 2 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "关键词至少2个字符"})
		return
	}
	page, pageSize := parsePage(c)
	res, err := h.svc.Search(c.Request.Context(), keyword, c.Query("type"), page, pageSize)
	if err != nil {
		if errors.Is(err, legacy.ErrSearchTooShort) {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": err.Error()})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "搜索失败"})
		return
	}
	payload := gin.H{"success": true, "keyword": keyword, "page": page, "page_size": pageSize}
	if res.Posts != nil {
		payload["posts"] = res.Posts
		payload["posts_total"] = res.PostsTotal
		payload["posts_has_more"] = res.PostsHasMore
	}
	if res.Users != nil {
		payload["users"] = res.Users
		payload["users_total"] = res.UsersTotal
		payload["users_has_more"] = res.UsersHasMore
	}
	c.JSON(http.StatusOK, payload)
}

// ReportBug Bug 反馈（游客可提交，登录自动记录身份）。
func (h *legacyHandler) ReportBug(c *gin.Context) {
	var req struct {
		Title   string `json:"title"`
		Detail  string `json:"detail"`
		Steps   string `json:"steps"`
		Contact string `json:"contact"`
		PageURL string `json:"page_url"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	title := strings.TrimSpace(req.Title)
	detail := strings.TrimSpace(req.Detail)
	if title == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请填写 Bug 标题"})
		return
	}
	if len([]rune(title)) > 200 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "标题过长（最多200字）"})
		return
	}
	if detail == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请填写 Bug 详细描述"})
		return
	}
	if len([]rune(detail)) > 5000 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "详细描述过长（最多5000字）"})
		return
	}
	if len([]rune(req.Steps)) > 3000 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "复现步骤过长（最多3000字）"})
		return
	}
	if len([]rune(req.Contact)) > 200 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "联系方式过长（最多200字）"})
		return
	}
	reporterID, reporterName := "", ""
	if u := legacyUserFrom(c); u != nil {
		reporterID, reporterName = u.ID, u.Name
	}
	id, err := h.db.ReportBug(c.Request.Context(), title, detail, strings.TrimSpace(req.Steps), strings.TrimSpace(req.Contact),
		reporterID, reporterName, c.GetHeader("User-Agent"), strings.TrimSpace(req.PageURL))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "提交失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "Bug 已提交，感谢反馈", "id": id})
}

// Huiguan 静态会馆列表。
func (h *legacyHandler) Huiguan(c *gin.Context) {
	list, err := h.svc.HuiguanList()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "会馆数据加载失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "list": list})
}

// EasterEgg 随机彩蛋（GET /Easter-Egg，直接返回一条对象）。
func (h *legacyHandler) EasterEgg(c *gin.Context) {
	item, err := h.svc.RandomEasterEgg()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "彩蛋数据加载失败"})
		return
	}
	c.JSON(http.StatusOK, item)
}

// ---- 头像 ----

// ServeAvatar 旧本地头像文件。
func (h *legacyHandler) ServeAvatar(c *gin.Context) {
	filename := c.Param("filename")
	if !legacyFileRe.MatchString(filename) || filename == "." || filename == ".." {
		c.Status(http.StatusBadRequest)
		return
	}
	if h.cfg == nil || strings.TrimSpace(h.cfg.AvatarDir) == "" {
		c.Status(http.StatusNotFound)
		return
	}
	full := filepath.Join(h.cfg.AvatarDir, filename)
	if _, err := os.Stat(full); err != nil {
		c.Status(http.StatusNotFound)
		return
	}
	c.Header("X-Content-Type-Options", "nosniff")
	c.File(full)
}

// UploadAvatar 旧 APP 头像上传（multipart 字段 avatar/file，≤5MB，落本地 AVATAR_DIR）。
func (h *legacyHandler) UploadAvatar(c *gin.Context) {
	file, err := c.FormFile("avatar")
	if err != nil {
		file, err = c.FormFile("file")
	}
	if err != nil || file == nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请选择图片"})
		return
	}
	if file.Size > maxLegacyAvatar {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "图片过大（最大5MB）"})
		return
	}
	src, err := file.Open()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "文件读取失败"})
		return
	}
	defer src.Close()
	data, err := io.ReadAll(io.LimitReader(src, maxLegacyAvatar+1))
	if err != nil || len(data) > maxLegacyAvatar {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "图片过大（最大5MB）"})
		return
	}
	ext, ok := avatarExtension(http.DetectContentType(data))
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请上传有效图片"})
		return
	}
	if h.cfg == nil || strings.TrimSpace(h.cfg.AvatarDir) == "" {
		c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "message": "头像存储未配置"})
		return
	}
	if err := os.MkdirAll(h.cfg.AvatarDir, 0o755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "头像保存失败"})
		return
	}
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "头像保存失败"})
		return
	}
	filename := hex.EncodeToString(buf) + ext
	if err := os.WriteFile(filepath.Join(h.cfg.AvatarDir, filename), data, 0o644); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "头像保存失败"})
		return
	}
	url := "/avatar/" + filename
	if err := h.db.UpdateUserProfile(c.Request.Context(), legacyUserFrom(c).ID, map[string]any{"avatar": url}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "头像保存失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "avatar": url})
}

func avatarExtension(contentType string) (string, bool) {
	switch contentType {
	case "image/jpeg":
		return ".jpg", true
	case "image/png":
		return ".png", true
	case "image/webp":
		return ".webp", true
	case "image/gif":
		return ".gif", true
	}
	return "", false
}

// ---- /api/app/* ----

// AppReleases 完整发布清单（legacy 形状）。
func (h *legacyHandler) AppReleases(c *gin.Context) {
	m := h.svc.Releases.Manifest()
	c.JSON(http.StatusOK, gin.H{"success": true, "schema": m.Schema, "updated_at": m.UpdatedAt,
		"min_versions": m.MinVersions, "platforms": m.Platforms})
}

// AppPlatform 单平台清单。
func (h *legacyHandler) AppPlatform(c *gin.Context) {
	pf := legacy.FindPlatform(h.svc.Releases.Manifest(), c.Param("platform"))
	if pf == nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "未知平台"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "platform": pf})
}

// AppCheck 版本检查。
func (h *legacyHandler) AppCheck(c *gin.Context) {
	platform := strings.TrimSpace(c.DefaultQuery("platform", "windows"))
	version := strings.TrimSpace(c.DefaultQuery("version", "0.0.0"))
	payload := legacy.CheckRelease(h.svc.Releases.Manifest(), platform, version)
	if payload == nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "未知平台"})
		return
	}
	c.JSON(http.StatusOK, payload)
}

// AppDownload / AppMirror 下载分发：校验平台 + 文件名后 302 到 GitHub Release 资产。
func (h *legacyHandler) AppDownload(c *gin.Context) {
	platform := strings.ToLower(strings.TrimSpace(c.Param("platform")))
	filename := strings.TrimSpace(c.Param("filename"))
	if !legacyFileRe.MatchString(filename) {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "暂无可反代的安装包"})
		return
	}
	asset, ok := h.svc.Releases.FindRelease(platform, filename)
	if !ok || asset.URL == "" {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "暂无可反代的安装包"})
		return
	}
	c.Redirect(http.StatusFound, asset.URL)
}

// AppWindowsExe Windows 客户端直链（UPDATE_EXE_URL 兼容）。
func (h *legacyHandler) AppWindowsExe(c *gin.Context) {
	pf := legacy.FindPlatform(h.svc.Releases.Manifest(), "windows")
	if pf == nil || len(pf.Releases) == 0 {
		c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "message": "安装包暂未上传到服务器"})
		return
	}
	latest := legacy.PickLatest(pf)
	if latest == nil || latest.URL == "" {
		c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "message": "安装包暂未上传到服务器"})
		return
	}
	c.Redirect(http.StatusFound, latest.URL)
}

// AppCache 反代缓存诊断（只读）。
func (h *legacyHandler) AppCache(c *gin.Context) {
	payload := gin.H{"success": true}
	for k, v := range h.svc.Releases.CacheInfo() {
		payload[k] = v
	}
	c.JSON(http.StatusOK, payload)
}
