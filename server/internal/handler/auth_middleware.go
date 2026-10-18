package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
)

// AuthRequired 会话校验中间件，成功后在 context 写入 userID。
func (h *AuthHandler) AuthRequired() gin.HandlerFunc {
	return func(c *gin.Context) {
		token, _ := c.Cookie(cookieName)
		if token == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
			return
		}
		userID, err := h.Sessions.Validate(c.Request.Context(), token)
		if err != nil || userID == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"success": false, "message": "登录已过期，请重新登录"})
			return
		}
		c.Set("userID", userID)
		c.Next()
	}
}

// OptionalAuth 可选登录：有有效 session 时写入 userID，无 session 也继续（用于公开媒体 ACL）。
func (h *AuthHandler) OptionalAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		if token, err := c.Cookie(cookieName); err == nil && token != "" {
			if uid, verr := h.Sessions.Validate(c.Request.Context(), token); verr == nil && uid != "" {
				c.Set("userID", uid)
			}
		}
		c.Next()
	}
}

// CurrentUser 从 context 读取 userID（可为空）。
func CurrentUser(c *gin.Context) string {
	v, _ := c.Get("userID")
	s, _ := v.(string)
	return s
}

// CurrentUserFromCookie 从 cookie 解析登录用户（未登录返回空）。
func (h *AuthHandler) CurrentUserFromCookie(c *gin.Context) string {
	return currentUserFromCookie(c, h.Sessions)
}

// currentUserFromCookie 从 cookie 解析登录用户（未登录返回空）。
func currentUserFromCookie(c *gin.Context, sessions *auth.SessionManager) string {
	if uid := CurrentUser(c); uid != "" {
		return uid
	}
	if token, err := c.Cookie(cookieName); err == nil && token != "" {
		if id, verr := sessions.Validate(c.Request.Context(), token); verr == nil && id != "" {
			return id
		}
	}
	return ""
}
