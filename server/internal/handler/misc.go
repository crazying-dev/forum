package handler

import (
	"crypto/rand"
	"encoding/json"
	"fmt"
	"html"
	"log"
	"math/big"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"yj-forum/server/internal/auth"
	"yj-forum/server/internal/config"
	"yj-forum/server/internal/database"
	"yj-forum/server/internal/email"
	"yj-forum/server/internal/middleware"
)

// MiscHandler 杂项（投票/Bug/彩蛋/验证码邮件）。
type MiscHandler struct {
	DB       *database.DB
	Cfg      *config.Config
	Mailer   *email.Sender
	Sessions *auth.SessionManager
}

func (h *MiscHandler) userFromCookie(c *gin.Context) string {
	if uid := CurrentUser(c); uid != "" {
		return uid
	}
	if token, err := c.Cookie(cookieName); err == nil && token != "" {
		if id, verr := h.Sessions.Validate(c.Request.Context(), token); verr == nil && id != "" {
			return id
		}
	}
	return ""
}

// ---- 验证码邮件 ----

// SendRegisterCode 注册验证码。
func (h *MiscHandler) SendRegisterCode(c *gin.Context) {
	mw := middleware.RateLimit("register_code", 3, 300*time.Second)
	mw(c)
	if c.IsAborted() {
		return
	}
	var req struct {
		Email string `json:"email" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	emailAddr := strings.ToLower(strings.TrimSpace(req.Email))
	if h.DB.UserExistsByEmail(c.Request.Context(), emailAddr) {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "邮箱已被注册"})
		return
	}
	code := genCode(6)
	if err := h.DB.CreateVerifyCode(c.Request.Context(), emailAddr, code, "register", 5); err != nil {
		log.Printf("[CODE] register code insert failed (%s): %v", emailAddr, err)
	}
	h.sendCode(c, "注册验证码", emailAddr, code)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "验证码已发送"})
}

// SendVerifyEmailCode 邮箱验证码（需登录）。
func (h *MiscHandler) SendVerifyEmailCode(c *gin.Context) {
	uid := h.userFromCookie(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	u, err := h.DB.GetUserByID(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	code := genCode(6)
	if err := h.DB.CreateVerifyCode(c.Request.Context(), u.Email, code, "email_verify", 5); err != nil {
		log.Printf("[CODE] email_verify code insert failed (%s): %v", u.Email, err)
	}
	h.sendCode(c, "邮箱验证码", u.Email, code)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "验证码已发送"})
}

// SendResetPasswordCode 重置密码验证码。
func (h *MiscHandler) SendResetPasswordCode(c *gin.Context) {
	var req struct {
		Email string `json:"email" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	emailAddr := strings.ToLower(strings.TrimSpace(req.Email))
	code := genCode(6)
	if err := h.DB.CreateVerifyCode(c.Request.Context(), emailAddr, code, "password_reset", 5); err != nil {
		log.Printf("[CODE] password_reset code insert failed (%s): %v", emailAddr, err)
	}
	h.sendCode(c, "重置密码验证码", emailAddr, code)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "验证码已发送（若邮箱存在）"})
}

func (h *MiscHandler) sendCode(c *gin.Context, label, to, code string) {
	plain := fmt.Sprintf("【妖精论坛】%s：%s，5分钟内有效。", label, code)
	html := email.BuildHTML(label, "你的验证码", []string{"请在 5 分钟内输入以下验证码：", `<div style="font-size:32px;font-weight:700;color:#4f46e5;text-align:center;letter-spacing:8px">` + code + `</div>`}, "", "", "")
	go func() {
		_, _ = h.Mailer.Send("【妖精论坛】"+label, plain, []string{to}, html)
	}()
}

// ---- 验证码校验（注册/邮箱/重置）----

// VerifyCodeEmail 邮箱验证（code 通道）。
func (h *MiscHandler) VerifyCodeEmail(c *gin.Context) {
	uid := h.userFromCookie(c)
	if uid == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"success": false, "message": "请先登录"})
		return
	}
	var req struct {
		Code string `json:"code" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	u, err := h.DB.GetUserByID(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "用户不存在"})
		return
	}
	ok, _ := h.DB.GetVerifyCode(c.Request.Context(), u.Email, req.Code, "email_verify")
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码错误或已过期"})
		return
	}
	_ = h.DB.MarkVerifyCodeUsed(c.Request.Context(), u.Email, req.Code, "email_verify")
	_ = h.DB.UpdateUserEmailVerified(c.Request.Context(), uid)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "邮箱验证成功"})
}

// ResetPasswordByCode 验证码重置密码。
func (h *MiscHandler) ResetPasswordByCode(c *gin.Context) {
	var req struct {
		Email    string `json:"email" binding:"required"`
		Code     string `json:"code" binding:"required"`
		Password string `json:"password" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	emailAddr := strings.ToLower(strings.TrimSpace(req.Email))
	ok, _ := h.DB.GetVerifyCode(c.Request.Context(), emailAddr, req.Code, "password_reset")
	if !ok {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码错误或已过期"})
		return
	}
	user, err := h.DB.GetUserByEmailWithPassword(c.Request.Context(), emailAddr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证码错误或已过期"})
		return
	}
	hash, _ := bcryptHash(req.Password)
	_ = h.DB.UpdateUserProfile(c.Request.Context(), user.ID, map[string]any{"password": hash})
	_ = h.DB.MarkVerifyCodeUsed(c.Request.Context(), emailAddr, req.Code, "password_reset")
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "密码重置成功"})
}

// ---- 工具 ----

func genCode(n int) string {
	const digits = "0123456789"
	var sb strings.Builder
	for i := 0; i < n; i++ {
		nb, _ := rand.Int(rand.Reader, big.NewInt(10))
		sb.WriteByte(digits[nb.Int64()])
	}
	return sb.String()
}

func bcryptHash(pwd string) (string, error) {
	return auth.HashPassword(pwd)
}

type voteReq struct {
	Choice string `json:"choice" binding:"required"`
}

// VoteVersion 版本投票。
func (h *MiscHandler) VoteVersion(c *gin.Context) {
	var req voteReq
	if err := c.ShouldBindJSON(&req); err != nil || (req.Choice != "v1" && req.Choice != "v2") {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	uid := h.userFromCookie(c)
	var voterKey string
	if uid != "" {
		voterKey = "u:" + uid
	} else {
		voterKey = "ip:" + c.ClientIP()
	}
	var voterID, voterName string
	if uid != "" {
		if u, err := h.DB.GetUserByID(c.Request.Context(), uid); err == nil {
			voterID, voterName = u.ID, u.Name
		}
	}
	if err := h.DB.VoteVersion(c.Request.Context(), voterKey, req.Choice, voterID, voterName); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "投票失败"})
		return
	}
	stats, _ := h.DB.GetVersionVoteStats(c.Request.Context())
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "投票成功", "stats": stats})
}

// VoteVersionStats 投票统计。
func (h *MiscHandler) VoteVersionStats(c *gin.Context) {
	stats, _ := h.DB.GetVersionVoteStats(c.Request.Context())
	c.JSON(http.StatusOK, gin.H{"success": true, "stats": stats})
}

// ---- Bug 举报 ----

type bugReq struct {
	Title   string `json:"title" binding:"required"`
	Detail  string `json:"detail" binding:"required"`
	Steps   string `json:"steps"`
	Contact string `json:"contact"`
	PageURL string `json:"page_url"`
}

// ReportBug 提交 Bug（游客也可）。
func (h *MiscHandler) ReportBug(c *gin.Context) {
	var req bugReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
		return
	}
	if len([]rune(req.Title)) > 200 || len([]rune(req.Detail)) > 5000 || len([]rune(req.Steps)) > 3000 || len([]rune(req.Contact)) > 200 {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "内容超长"})
		return
	}
	uid := h.userFromCookie(c)
	var reporterName string
	if uid != "" {
		if u, err := h.DB.GetUserByID(c.Request.Context(), uid); err == nil {
			reporterName = u.Name
		}
	}
	id, err := h.DB.ReportBug(c.Request.Context(), req.Title, req.Detail, req.Steps, req.Contact, uid, reporterName, c.GetHeader("User-Agent"), req.PageURL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "提交失败"})
		return
	}
	// 通知管理员（HTML 邮件中对用户可控片段转义，防注入）
	go func() {
		plain := "Bug 报告 #" + fmt.Sprintf("%d", id) + "\n标题: " + req.Title + "\n详情: " + req.Detail
		htmlBody := email.BuildHTML("Bug 报告", "收到新的 Bug 报告", []string{"标题: " + html.EscapeString(req.Title), "详情: " + html.EscapeString(req.Detail), "提交人: " + reporterName}, "", "", "")
		_, _ = h.Mailer.Send("【妖精论坛】Bug 报告 #"+fmt.Sprintf("%d", id), plain, []string{h.Cfg.ReceiverAll}, htmlBody)
	}()
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "Bug 提交成功", "id": id})
}

// ---- Bug 反馈公开读取（脱敏）----

// ListBugReports 反馈列表（公开；status 可选过滤；不含提交人信息）。
func (h *MiscHandler) ListBugReports(c *gin.Context) {
	var status *int
	if s := strings.TrimSpace(c.Query("status")); s != "" {
		n, err := strconv.Atoi(s)
		if err != nil || n < 0 || n > 3 {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "参数错误"})
			return
		}
		status = &n
	}
	page, pageSize := parsePageWithDefault(c, 10)
	if pageSize > 50 {
		pageSize = 10
	}
	items, total, hasMore, err := h.DB.ListBugReports(c.Request.Context(), status, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{
		"items": items, "total": total, "page": page, "page_size": pageSize, "has_more": hasMore,
	}})
}

// BugReportStats 反馈状态统计（公开；0/1/2/3 四态均返回）。
func (h *MiscHandler) BugReportStats(c *gin.Context) {
	stats, err := h.DB.GetBugReportStats(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"stats": stats}})
}

// BugReportDetail 反馈详情与状态日志（公开；不存在 404）。
func (h *MiscHandler) BugReportDetail(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "反馈不存在"})
		return
	}
	report, logs, err := h.DB.GetBugReportDetail(c.Request.Context(), id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "message": "查询失败"})
		return
	}
	if report == nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "反馈不存在"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"report": report, "logs": logs}})
}

// ---- 彩蛋 ----

// EasterEgg 随机彩蛋。
func (h *MiscHandler) EasterEgg(c *gin.Context) {
	data, err := os.ReadFile(h.Cfg.EasterEggPath)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "彩蛋不存在"})
		return
	}
	var list []struct {
		ID   string `json:"ID"`
		Name string `json:"Name"`
		Text string `json:"Text"`
	}
	if err := json.Unmarshal(data, &list); err != nil || len(list) == 0 {
		c.JSON(http.StatusNotFound, gin.H{"success": false, "message": "彩蛋不存在"})
		return
	}
	n, _ := rand.Int(rand.Reader, big.NewInt(int64(len(list))))
	c.JSON(http.StatusOK, list[n.Int64()])
}

// VerifyToken 邮箱验证 token 消费（verify-email 页）。
func (h *MiscHandler) VerifyToken(c *gin.Context) {
	token := c.Query("token")
	tokenType := c.DefaultQuery("type", "email_verify")
	if token == "" {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "缺少 token"})
		return
	}
	userID, err := h.DB.GetVerifyToken(c.Request.Context(), token, tokenType)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "message": "验证链接无效或已过期"})
		return
	}
	_ = h.DB.DeleteVerifyToken(c.Request.Context(), token)
	_ = h.DB.UpdateUserEmailVerified(c.Request.Context(), userID)
	c.JSON(http.StatusOK, gin.H{"success": true, "message": "邮箱验证成功"})
}
