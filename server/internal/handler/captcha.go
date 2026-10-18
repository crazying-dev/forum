package handler

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/altcha"
)

// CaptchaHandler ALTCHA v2 公开端点。
type CaptchaHandler struct {
	Altcha *altcha.Service
}

// NewCaptchaHandler 创建 CaptchaHandler。
func NewCaptchaHandler(svc *altcha.Service) *CaptchaHandler {
	return &CaptchaHandler{Altcha: svc}
}

// Config GET /captcha/config。
func (h *CaptchaHandler) Config(c *gin.Context) {
	enabled := h != nil && h.Altcha != nil && h.Altcha.Enabled()
	algorithm, cost := altcha.DefaultAlgorithm, altcha.DefaultCost
	if h != nil && h.Altcha != nil {
		algorithm, cost = h.Altcha.Algorithm(), h.Altcha.Cost()
	}
	c.JSON(http.StatusOK, gin.H{
		"success":   true,
		"enabled":   enabled,
		"algorithm": algorithm,
		"cost":      cost,
	})
}

// Challenge GET /captcha/challenge，直接返回 ALTCHA 官方 Challenge JSON（不包 success）。
func (h *CaptchaHandler) Challenge(c *gin.Context) {
	if !h.captchaEnabled() {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "CAPTCHA_DISABLED"})
		return
	}
	challenge, err := h.Altcha.Challenge(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "message": "CAPTCHA_UNAVAILABLE"})
		return
	}
	c.JSON(http.StatusOK, challenge)
}

// Verify POST /captcha/verify，body {altcha:"<base64 payload>"}，成功返回一次性 grant。
func (h *CaptchaHandler) Verify(c *gin.Context) {
	if !h.captchaEnabled() {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "CAPTCHA_DISABLED"})
		return
	}
	var req struct {
		Altcha string `json:"altcha"`
	}
	if err := c.ShouldBindJSON(&req); err != nil || strings.TrimSpace(req.Altcha) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "CAPTCHA_REQUIRED"})
		return
	}
	ok, err := h.Altcha.Verify(c.Request.Context(), req.Altcha)
	if err != nil || !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "CAPTCHA_REQUIRED"})
		return
	}
	grant, err := h.Altcha.Grant(c.ClientIP())
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "message": "CAPTCHA_UNAVAILABLE"})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success":    true,
		"grant":      grant,
		"expires_in": int(altcha.GrantTTL.Seconds()),
	})
}

// VerifyRequest 校验受保护端点携带的 ALTCHA proof（altcha 或 grant）。
// ALTCHA 未启用（或未注入 service）时返回 true，保持原有行为；启用后任何
// 缺失/无效/校验异常都返回 false（fail-closed）。
func VerifyRequest(c *gin.Context, svc *altcha.Service, altchaPayload, grant string) bool {
	if svc == nil || !svc.Enabled() {
		return true
	}
	if g := strings.TrimSpace(grant); g != "" && svc.VerifyGrant(g, c.ClientIP()) {
		return true
	}
	if p := strings.TrimSpace(altchaPayload); p != "" {
		ok, err := svc.Verify(c.Request.Context(), p)
		return err == nil && ok
	}
	return false
}

// VerifyRequest 方法形式，便于 CaptchaHandler 自身复用。
func (h *CaptchaHandler) VerifyRequest(c *gin.Context, altchaPayload, grant string) bool {
	if h == nil {
		return VerifyRequest(c, nil, altchaPayload, grant)
	}
	return VerifyRequest(c, h.Altcha, altchaPayload, grant)
}

func (h *CaptchaHandler) captchaEnabled() bool {
	return h != nil && h.Altcha != nil && h.Altcha.Enabled()
}

// RegisterCaptchaRoutes 注册 /captcha/* 路由。
func RegisterCaptchaRoutes(api *gin.RouterGroup, h *CaptchaHandler) {
	if h == nil {
		h = &CaptchaHandler{}
	}
	api.GET("/captcha/config", h.Config)
	api.GET("/captcha/challenge", h.Challenge)
	api.POST("/captcha/verify", h.Verify)
}
