// Package email 实现 SMTP 邮件发送（对齐 legacy Email.py）。
package email

import (
	"crypto/tls"
	"encoding/base64"
	"fmt"
	"log"
	"net"
	"net/smtp"
	"strings"
	"sync"
	"time"
)

// Sender SMTP 发件器。
type Sender struct {
	Enabled     bool
	Host        string
	Port        int
	User        string
	Password    string
	FromName    string
	ReceiverAll string

	mu         sync.Mutex
	lastSentAt map[string]time.Time // 同一收件人 1 秒去重
}

// New 创建发件器。
func New(enabled bool, host string, port int, user, pwd, fromName, receiverAll string) *Sender {
	return &Sender{
		Enabled: enabled, Host: host, Port: port, User: user, Password: pwd,
		FromName: fromName, ReceiverAll: receiverAll,
		lastSentAt: map[string]time.Time{},
	}
}

// Send 发送邮件。返回 (success, error)。
func (s *Sender) Send(subject, body string, receivers []string, htmlContent string) (bool, error) {
	if !s.Enabled {
		log.Println("[EMAIL] SMTP 未启用，跳过发送")
		return false, nil
	}
	if s.User == "" || s.Password == "" {
		return false, fmt.Errorf("SMTP 凭据未配置")
	}
	// 收件人去重 + 1s 节流
	s.mu.Lock()
	now := time.Now()
	unique := make([]string, 0, len(receivers))
	for _, r := range receivers {
		r = strings.TrimSpace(r)
		if r == "" {
			continue
		}
		if last, ok := s.lastSentAt[r]; ok && now.Sub(last) < time.Second {
			continue // 去重
		}
		s.lastSentAt[r] = now
		unique = append(unique, r)
	}
	s.mu.Unlock()
	if len(unique) == 0 {
		return true, nil
	}

	from := fmt.Sprintf("%s <%s>", s.FromName, s.User)
	msg := buildMIME(from, s.User, unique, subject, body, htmlContent)

	addr := fmt.Sprintf("%s:%d", s.Host, s.Port)
	auth := smtp.PlainAuth("", s.User, s.Password, s.Host)
	// 超时保护：拨号 10s，连接整个会话 30s，避免 SMTP 挂起拖死调用方；失败路径由 defer 统一清理
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	conn, err := tls.DialWithDialer(dialer, "tcp", addr, &tls.Config{ServerName: s.Host})
	if err != nil {
		return false, err
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(30 * time.Second))
	client, err := smtp.NewClient(conn, s.Host)
	if err != nil {
		return false, err
	}
	defer client.Close()
	if err := client.Auth(auth); err != nil {
		return false, err
	}
	if err := client.Mail(s.User); err != nil {
		return false, err
	}
	for _, r := range unique {
		if err := client.Rcpt(r); err != nil {
			return false, err
		}
	}
	w, err := client.Data()
	if err != nil {
		return false, err
	}
	if _, err := w.Write([]byte(msg)); err != nil {
		return false, err
	}
	if err := w.Close(); err != nil {
		return false, err
	}
	log.Printf("[EMAIL] 已发送 %s -> %v", subject, unique)
	return true, nil
}

// BuildHTML 生成渐变卡片 HTML（对齐 legacy build_email_html 简化版）。
func BuildHTML(label, title string, bodyLines []string, actionText, actionURL, footerNote string) string {
	var lines strings.Builder
	for _, l := range bodyLines {
		lines.WriteString(fmt.Sprintf("<p style=\"margin:0 0 12px;font-size:14px;color:#555;line-height:1.7\">%s</p>", l))
	}
	action := ""
	if actionText != "" && actionURL != "" {
		action = fmt.Sprintf(`<div style="text-align:center;margin:24px 0"><a href="%s" style="display:inline-block;padding:12px 36px;background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff;text-decoration:none;border-radius:8px;font-size:15px;font-weight:600">%s</a></div>`, actionURL, actionText)
	}
	footer := ""
	if footerNote != "" {
		footer = fmt.Sprintf(`<p style="font-size:12px;color:#999;text-align:center;margin-top:8px">%s</p>`, footerNote)
	}
	return fmt.Sprintf(`<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>%s</title></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif">
<div style="max-width:520px;margin:0 auto;padding:24px 16px">
<div style="text-align:center;padding:24px 0 16px"><div style="font-size:18px;font-weight:700;color:#1a1a2e">%s</div><div style="font-size:13px;color:#8b949e;margin-top:4px">妖精论坛</div></div>
<div style="background:#fff;border-radius:12px;padding:32px 28px;box-shadow:0 1px 3px rgba(0,0,0,.08)">
<h2 style="margin:0 0 8px;font-size:20px;color:#1a1a2e">%s</h2>
%s%s</div>
<div style="text-align:center;padding:20px 0"><p style="font-size:12px;color:#999;margin:4px 0">© 2026 妖精论坛 - 粉丝公益创作</p>%s</div>
</div></body></html>`, title, label, title, lines.String(), action, footer)
}

func buildMIME(from, to string, receivers []string, subject, plain, htmlContent string) string {
	var sb strings.Builder
	sb.WriteString("From: " + from + "\r\n")
	sb.WriteString("To: " + strings.Join(receivers, ", ") + "\r\n")
	sb.WriteString("Subject: =?UTF-8?B?" + b64(subject) + "?=\r\n")
	sb.WriteString("MIME-Version: 1.0\r\n")
	boundary := "----=_yjforum_" + fmt.Sprintf("%d", time.Now().UnixNano())
	if htmlContent != "" {
		sb.WriteString("Content-Type: multipart/alternative; boundary=\"" + boundary + "\"\r\n\r\n")
		sb.WriteString("--" + boundary + "\r\n")
		sb.WriteString("Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n")
		sb.WriteString(plain + "\r\n")
		sb.WriteString("--" + boundary + "\r\n")
		sb.WriteString("Content-Type: text/html; charset=UTF-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n")
		sb.WriteString(htmlContent + "\r\n")
		sb.WriteString("--" + boundary + "--\r\n")
	} else {
		sb.WriteString("Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n")
		sb.WriteString(plain + "\r\n")
	}
	return sb.String()
}

func b64(s string) string {
	return base64.StdEncoding.EncodeToString([]byte(s))
}
