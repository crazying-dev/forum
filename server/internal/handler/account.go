package handler

import (
	"html"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
)

// AccountHandler 账号注销与邮箱换绑。
type AccountHandler struct {
	DB       *database.DB
	Cfg      *config.Config
	Mailer   *email.Sender
	Sessions *auth.SessionManager
	Cache    *CacheSet
}

// ---- POST /api/v1/users/me/delete ----

type deleteAccountReq struct {
	Mode        string `json:"mode"`
	Password    string `json:"password"`
	ConfirmName string `json:"confirmName"`
}

// DeleteAccount 注销账号（purge=彻底删除 / anonymize=匿名化保留内容）。
func (h *AccountHandler) DeleteAccount(c *gin.Context) {
	uid := CurrentUser(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req deleteAccountReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	mode := strings.TrimSpace(req.Mode)
	if mode != "purge" && mode != "anonymize" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	user, err := h.DB.GetUserByIDWithPassword(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	if !auth.CheckPassword(user.Password, req.Password) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "密码错误"})
		return
	}
	if strings.TrimSpace(req.ConfirmName) != user.Name {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "确认信息不匹配"})
		return
	}
	var (
		oldAvatar string
		delErr    error
	)
	if mode == "purge" {
		oldAvatar, delErr = h.DB.PurgeUser(c.Request.Context(), uid)
	} else {
		defaultAvatar := h.Cfg.ImageFatherURL + "/avatars/LuoXiaoHei1.png"
		oldAvatar, delErr = h.DB.AnonymizeUser(c.Request.Context(), uid, defaultAvatar)
	}
	if delErr != nil {
		log.Printf("[ACCOUNT] 注销失败 (uid=%s mode=%s): %v", uid, mode, delErr)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "注销失败"})
		return
	}
	h.removeAvatarFile(oldAvatar)
	h.invalidateAccountCaches()
	if err := h.Sessions.DeleteByUserID(c.Request.Context(), uid); err != nil {
		log.Printf("[ACCOUNT] 注销后会话清理失败 (uid=%s): %v", uid, err)
	}
	c.SetCookie(cookieName, "", -1, "/", "", false, false)
	c.SetCookie("user_id", "", -1, "/", "", false, false)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "账号已注销"})
}

// removeAvatarFile 尽力删除本地头像文件；外部 URL/空值忽略，文件不存在忽略。
func (h *AccountHandler) removeAvatarFile(avatar string) {
	if !strings.HasPrefix(avatar, "/avatar/") {
		return
	}
	filename := strings.TrimPrefix(avatar, "/avatar/")
	if filename == "" || strings.Contains(filename, "..") || strings.Contains(filename, "/") || strings.Contains(filename, "\\") {
		return
	}
	_ = os.Remove(filepath.Join(h.Cfg.AvatarDir, filename))
}

// invalidateAccountCaches 注销后清空与用户内容相关的进程内缓存。
func (h *AccountHandler) invalidateAccountCaches() {
	if h.Cache == nil {
		return
	}
	h.Cache.Posts.DeletePrefix("posts:list:")
	h.Cache.Posts.Delete(randomPoolKey)
	h.Cache.PostDetail.DeletePrefix("post:detail:")
	h.Cache.Comments.DeletePrefix("comments:post:")
	h.Cache.Search.DeletePrefix("search:")
	h.Cache.Guilds.DeletePrefix("guilds:")
}

// ---- 邮箱换绑 ----

type emailCodeReq struct {
	Code string `json:"code"`
}

// SendEmailChangeOldCode 向当前邮箱发送换绑验证码（1 小时 1 次）。
func (h *AccountHandler) SendEmailChangeOldCode(c *gin.Context) {
	uid := CurrentUser(c)
	u, err := h.DB.GetUserByID(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	allowed, err := h.DB.TryAcquireActionLimit(c.Request.Context(), "email_change", u.Email, 3600)
	if err != nil {
		log.Printf("[EMAIL_CHANGE] 操作限流检查失败 (%s): %v", u.Email, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if !allowed {
		c.JSON(http.StatusTooManyRequests, gin.H{"success": false, "message": "请求过于频繁，请 1 小时后再试"})
		return
	}
	if err := h.DB.UpsertEmailChangeRequest(c.Request.Context(), uid, u.Email, 30); err != nil {
		log.Printf("[EMAIL_CHANGE] 换绑请求写入失败 (%s): %v", uid, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	code := genCode(6)
	if err := h.DB.CreateVerifyCode(c.Request.Context(), u.Email, code, "email_change_old", 5); err != nil {
		log.Printf("[CODE] email_change_old code insert failed (%s): %v", u.Email, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	sendCodeMail(h.Mailer, "邮箱换绑验证码", u.Email, code)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "验证码已发送"})
}

// VerifyEmailChangeOld 校验当前邮箱验证码，通过后进入新邮箱验证阶段。
func (h *AccountHandler) VerifyEmailChangeOld(c *gin.Context) {
	uid := CurrentUser(c)
	var req emailCodeReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	code := strings.TrimSpace(req.Code)
	reqRow, err := h.DB.GetEmailChangeRequest(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if reqRow == nil || !reqRow.ExpiresAt.After(time.Now()) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请先发送验证码"})
		return
	}
	u, err := h.DB.GetUserByID(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	ok, err := verifyCodeWithLimit(c.Request.Context(), h.DB, u.Email, code, "email_change_old")
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码错误或已过期"})
		return
	}
	if err := h.DB.MarkOldEmailVerified(c.Request.Context(), uid); err != nil {
		log.Printf("[EMAIL_CHANGE] 阶段推进失败 (%s): %v", uid, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "邮箱所有权验证通过"})
}

// SendEmailChangeNewCode 向新邮箱发送验证码（10 分钟至多 3 次、间隔至少 60 秒）。
func (h *AccountHandler) SendEmailChangeNewCode(c *gin.Context) {
	uid := CurrentUser(c)
	var req struct {
		NewEmail string `json:"newEmail" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	newEmail := strings.ToLower(strings.TrimSpace(req.NewEmail))
	reqRow, err := h.DB.GetEmailChangeRequest(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if reqRow == nil || reqRow.Stage < 2 || !reqRow.ExpiresAt.After(time.Now()) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请先完成当前邮箱验证"})
		return
	}
	u, err := h.DB.GetUserByID(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	if newEmail == u.Email {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "新邮箱与当前邮箱相同"})
		return
	}
	if h.DB.UserExistsByEmail(c.Request.Context(), newEmail) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "该邮箱已被使用"})
		return
	}
	allowed, err := h.DB.CheckActionLimit(c.Request.Context(), "email_change_new", newEmail, 3, 600, 60)
	if err != nil {
		log.Printf("[EMAIL_CHANGE] 新邮箱频控检查失败 (%s): %v", newEmail, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if !allowed {
		c.JSON(http.StatusTooManyRequests, gin.H{"success": false, "message": "发送过于频繁，请稍后再试"})
		return
	}
	// 记录本次发送（同时原子保证距上次至少 60 秒）
	acquired, err := h.DB.TryAcquireActionLimit(c.Request.Context(), "email_change_new", newEmail, 60)
	if err != nil {
		log.Printf("[EMAIL_CHANGE] 新邮箱频控记录失败 (%s): %v", newEmail, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if !acquired {
		c.JSON(http.StatusTooManyRequests, gin.H{"success": false, "message": "发送过于频繁，请稍后再试"})
		return
	}
	if err := h.DB.SetNewEmail(c.Request.Context(), uid, newEmail); err != nil {
		log.Printf("[EMAIL_CHANGE] 新邮箱写入失败 (%s): %v", uid, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	code := genCode(6)
	if err := h.DB.CreateVerifyCode(c.Request.Context(), newEmail, code, "email_change_new", 5); err != nil {
		log.Printf("[CODE] email_change_new code insert failed (%s): %v", newEmail, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	sendCodeMail(h.Mailer, "邮箱换绑验证码", newEmail, code)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "验证码已发送"})
}

// ConfirmEmailChange 校验新邮箱验证码并完成换绑，同时通知旧邮箱。
func (h *AccountHandler) ConfirmEmailChange(c *gin.Context) {
	uid := CurrentUser(c)
	var req emailCodeReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	code := strings.TrimSpace(req.Code)
	reqRow, err := h.DB.GetEmailChangeRequest(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if reqRow == nil || reqRow.Stage < 2 || !reqRow.ExpiresAt.After(time.Now()) || reqRow.NewEmail == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "请先完成新邮箱验证"})
		return
	}
	u, err := h.DB.GetUserByID(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	if u.Email != reqRow.OldEmail {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "邮箱状态已变化，请重新发起"})
		return
	}
	ok, err := verifyCodeWithLimit(c.Request.Context(), h.DB, reqRow.NewEmail, code, "email_change_new")
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "服务器错误"})
		return
	}
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码错误或已过期"})
		return
	}
	if h.DB.UserExistsByEmail(c.Request.Context(), reqRow.NewEmail) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "该邮箱已被使用，请重新发起"})
		return
	}
	if err := h.DB.UpdateUserProfile(c.Request.Context(), uid, map[string]any{"email": reqRow.NewEmail, "email_verified": 1}); err != nil {
		log.Printf("[EMAIL_CHANGE] 邮箱更新失败 (%s): %v", uid, err)
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "邮箱换绑失败"})
		return
	}
	if err := h.DB.DeleteEmailChangeRequest(c.Request.Context(), uid); err != nil {
		log.Printf("[EMAIL_CHANGE] 换绑请求清理失败 (%s): %v", uid, err)
	}
	oldEmail, newEmail := reqRow.OldEmail, reqRow.NewEmail
	go func() {
		plain := "你的论坛账号邮箱已更换为 " + newEmail + "，如非本人操作请立即联系管理组。"
		htmlBody := email.BuildHTML("邮箱换绑通知", "账号邮箱已更换",
			[]string{"你的论坛账号邮箱已更换为 " + html.EscapeString(newEmail) + "。", "如非本人操作请立即联系管理组。"}, "", "", "")
		_, _ = h.Mailer.Send("【妖精论坛】邮箱换绑通知", plain, []string{oldEmail}, htmlBody)
	}()
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "邮箱换绑成功"})
}
