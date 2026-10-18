package handler

import (
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/altcha"
	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
	"yj-forum/server/internal/middleware"
)

// AuthHandler 认证相关端点。
type AuthHandler struct {
	DB       *database.DB
	Cfg      *config.Config
	Sessions *auth.SessionManager
	Mailer   *email.Sender
	Altcha   *altcha.Service // nil 安全：未注入时跳过 ALTCHA 校验
}

// cookieName 会话 cookie。
const cookieName = "forum_session"

// ---- /api/v1/auth/register ----

type registerReq struct {
	Name     string `json:"name" binding:"required"`
	Email    string `json:"email" binding:"required"`
	Password string `json:"password" binding:"required"`
	Code     string `json:"code" binding:"required"`
	Altcha   string `json:"altcha"`
	Grant    string `json:"grant"`
}

// Register 注册 + 自动登录。
func (h *AuthHandler) Register(c *gin.Context) {
	middleware.RateLimit("register", 5, 300*time.Second)(c)
	if c.IsAborted() {
		return
	}
	var req registerReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if !VerifyRequest(c, h.Altcha, req.Altcha, req.Grant) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "CAPTCHA_REQUIRED"})
		return
	}
	name := strings.TrimSpace(req.Name)
	emailAddr := strings.ToLower(strings.TrimSpace(req.Email))
	password := req.Password
	code := strings.TrimSpace(req.Code)

	// 校验
	cleanName := database.StripEasterEgg(name)
	if len([]rune(cleanName)) < 2 || len([]rune(cleanName)) > 20 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "用户名需2-20个字符"})
		return
	}
	if strings.HasPrefix(strings.TrimSpace(cleanName), "已注销") {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "该用户名为保留名称"})
		return
	}
	if len(password) < 8 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码至少8位"})
		return
	}
	if !hasLetterAndDigit(password) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码需包含字母和数字"})
		return
	}
	// 邮箱黑名单（精确 / @domain / *@domain）
	blocked, err := h.DB.IsEmailBlacklisted(c.Request.Context(), database.NormalizeEmail(emailAddr))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if blocked {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "邮箱异样"})
		return
	}
	// 验证码校验（含失败次数限制）
	ok, err := verifyCodeWithLimit(c.Request.Context(), h.DB, emailAddr, code, "register")
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码错误或已过期"})
		return
	}

	avatar := h.Cfg.ImageFatherURL + "/avatars/LuoXiaoHei1.png"
	hash, err := auth.HashPassword(password)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	uid, err := h.DB.NewUser(c.Request.Context(), name, emailAddr, hash, avatar)
	if err != nil {
		msg := "注册失败"
		if strings.Contains(strings.ToLower(err.Error()), "email") {
			msg = "邮箱已被注册"
		} else if strings.Contains(strings.ToLower(err.Error()), "name") {
			msg = "用户名已存在"
		}
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": msg})
		return
	}
	// 注册已通过邮箱验证码验证（证明邮箱归属；验证码已由校验流程核销），直接标记已认证
	_ = h.DB.UpdateUserEmailVerified(c.Request.Context(), uid)

	// 自动登录
	h.issueSession(c, uid)
	c.JSON(http.StatusCreated, gin.H{"success": true, "id": uid})
}

// ---- /api/v1/auth/login ----

type loginReq struct {
	Name     string `json:"name" binding:"required"`
	Password string `json:"password" binding:"required"`
	Remember bool   `json:"remember"`
	Altcha   string `json:"altcha"`
	Grant    string `json:"grant"`
}

// Login 登录。
func (h *AuthHandler) Login(c *gin.Context) {
	middleware.RateLimit("login", 10, 300*time.Second)(c)
	if c.IsAborted() {
		return
	}
	var req loginReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请输入账号和密码"})
		return
	}
	if !VerifyRequest(c, h.Altcha, req.Altcha, req.Grant) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "CAPTCHA_REQUIRED"})
		return
	}
	nameOrEmail := strings.TrimSpace(req.Name)
	password := req.Password

	var user *database.UserInfo
	var err error
	if strings.Contains(nameOrEmail, "@") && strings.Contains(nameOrEmail, ".") {
		user, err = h.DB.GetUserByEmailWithPassword(c.Request.Context(), strings.ToLower(nameOrEmail))
	} else {
		user, err = h.DB.GetUserByNameWithPassword(c.Request.Context(), nameOrEmail)
		if err != nil {
			// 旧格式兼容
			legacy := strings.ReplaceAll(nameOrEmail, "[TIME]", `<p class="TimeWithUserNameAPI"></p>`)
			user, err = h.DB.GetUserByNameWithPassword(c.Request.Context(), legacy)
		}
	}
	if err != nil || user == nil || !auth.CheckPassword(user.Password, password) {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "账号或密码错误"})
		return
	}
	if user.IsBanned == 1 {
		c.JSON(http.StatusForbidden, gin.H{"success": false, "message": "该账号已被封禁"})
		return
	}
	_ = h.DB.UpdateUserLastLogin(c.Request.Context(), user.ID)

	// 异步登录提醒邮件（不阻塞）
	if user.Email != "" {
		go func() {
			nowStr := time.Now().Format("2006-01-02 15:04:05")
			plain := "尊敬的 " + user.Name + "，您好！\n\n您的账号已于 " + nowStr + " 登录妖精论坛。\n如非本人操作，请立即修改密码。\n\n© 2026 妖精论坛 - 粉丝公益创作"
			html := email.BuildHTML("登录提醒", "您的账号已登录",
				[]string{"尊敬的 " + user.Name + "，您好！", "您的账号已于 " + nowStr + " 登录妖精论坛。", "如非本人操作，请立即修改密码。"},
				"", "", "")
			_, _ = h.Mailer.Send("【妖精论坛】登录提醒", plain, []string{user.Email}, html)
		}()
	}

	h.issueSession(c, user.ID)
	c.JSON(http.StatusOK, gin.H{"success": true, "id": user.ID})
}

// ---- /api/v1/auth/logout ----

// Logout 登出。
func (h *AuthHandler) Logout(c *gin.Context) {
	token, _ := c.Cookie(cookieName)
	if token != "" {
		_ = h.Sessions.Delete(c.Request.Context(), token)
	}
	c.SetCookie(cookieName, "", -1, "/", "", false, false)
	c.SetCookie("user_id", "", -1, "/", "", false, false)
	c.JSON(http.StatusOK, gin.H{"success": true})
}

// issueSession 创建会话并写 cookie（HttpOnly session + 非 HttpOnly user_id）。
func (h *AuthHandler) issueSession(c *gin.Context, userID string) {
	token, err := h.Sessions.Create(c.Request.Context(), userID)
	if err != nil {
		log.Printf("[AUTH] 创建会话失败: %v", err)
		return
	}
	secure := h.Cfg.AppEnv == "prod"
	c.SetSameSite(http.SameSiteLaxMode)
	c.SetCookie(cookieName, token, 86400, "/", "", secure, true) // HttpOnly
	c.SetCookie("user_id", userID, 86400*30, "/", "", secure, false)
}

func hasLetterAndDigit(s string) bool {
	hasLetter, hasDigit := false, false
	for _, ch := range s {
		if (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') {
			hasLetter = true
		}
		if ch >= '0' && ch <= '9' {
			hasDigit = true
		}
	}
	return hasLetter && hasDigit
}

// ---- /api/v1/auth/oauth/callback（兼容 TheDoorOfBings，简化 JSON 返回）----

// HandleOAuth 第三方登录回调（完整 UI 在 Next.js /oauth 页）。
func (h *AuthHandler) HandleOAuth(c *gin.Context) {
	appID := c.Query("app_id")
	if appID != "TheDoorOfBings" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "未知应用"})
		return
	}
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "未登录"})
		return
	}
	u, err := h.DB.GetUserByID(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "user": map[string]string{"id": u.ID, "name": u.Name, "avatar": u.Avatar}})
}
