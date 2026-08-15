import smtplib
import ssl
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from api.config import *

SENDER = SMTP_USER
SENDER_NAME = "妖精论坛"

# 同一邮箱 1 秒内最多发一封邮件，避免短时间重复推送
_EMAIL_MIN_INTERVAL = 1.0
_email_send_lock = threading.Lock()
_email_send_timestamps = {}


def _esc(text):
	"""HTML 转义"""
	if text is None:
		return ''
	return (str(text)
			.replace('&', '&amp;')
			.replace('<', '&lt;')
			.replace('>', '&gt;')
			.replace('"', '&quot;')
			.replace("'", '&#39;'))


def build_email_html(label, title, body_lines, action_text=None, action_url=None, footer_note=None):
	"""统一的 HTML 邮件模板构建器。

	Args:
		label: 顶栏右侧的小标签（如"新帖通知""评论通知"）
		title: 卡片内主标题（如"你关注的作者发布了新帖子"）
		body_lines: list[str]，正文段落，每段渲染为一行；段内可包含简单 HTML（如 <strong>）
		action_text: 可选，CTA 按钮文案
		action_url: 可选，CTA 按钮链接
		footer_note: 可选，底部额外提示

	Returns:
		str: 完整 HTML 文档字符串
	"""
	from html import escape as _h
	lines_html = ''
	for line in body_lines:
		lines_html += f'<div style="font-size:15px;line-height:1.8;color:#4b5563;margin:0 0 10px;">{line}</div>\n'

	action_html = ''
	if action_text and action_url:
		url_esc = _esc(action_url)
		action_html = f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="margin:8px 0 22px;">
<tr><td align="center">
<a href="{url_esc}" style="display:inline-block;padding:13px 40px;border-radius:8px;background:linear-gradient(135deg,#a855f7,#ec4899);color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;">
{_esc(action_text)}
</a>
</td></tr></table>'''

	footer_html = ''
	if footer_note:
		footer_html = f'<div style="font-size:12px;line-height:1.7;color:#9ca3af;margin-top:8px;">{_esc(footer_note)}</div>'

	return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1.0" />
<title>{_esc(title)}</title>
</head>
<body style="margin:0;padding:0;background:#f5f3ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#374151;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="background:#f5f3ff;padding:32px 0;">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="max-width:560px;margin:0 auto;">
<tr>
<td style="padding:16px 28px;background:linear-gradient(135deg,#a855f7,#ec4899);border-radius:16px 16px 0 0;color:#ffffff;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
<tr>
<td style="font-size:18px;font-weight:700;letter-spacing:1px;">妖精论坛</td>
<td align="right" style="font-size:13px;opacity:0.9;">{_esc(label)}</td>
</tr>
</table>
</td>
</tr>
<tr>
<td style="background:#ffffff;padding:32px 28px;border-radius:0 0 16px 16px;box-shadow:0 4px 20px -8px rgba(168,85,247,0.2);">
<div style="font-size:20px;font-weight:700;color:#1f2937;margin:0 0 20px;">{_esc(title)}</div>
{lines_html}
{action_html}
{footer_html}
</td>
</tr>
<tr>
<td align="center" style="padding-top:20px;font-size:12px;color:#9ca3af;line-height:1.8;">
&copy; 2026 妖精论坛 · 粉丝公益创作
</td>
</tr>
</table>
</td></tr>
</table>
</body>
</html>'''


def send_email(subject: str, content: str, receiver_list: list = None, RECEIVER = RECEIVERALL, html_content: str | None = None):
    """发送邮件。

    Args:
        subject: 主题
        content: 纯文本正文（兼容不支持 HTML 的客户端）
        receiver_list: 收件人邮箱列表
        RECEIVER: 默认收件人
        html_content: 可选，HTML 格式正文（会同时 attach，支持的客户端优先展示 HTML）

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    if receiver_list is None:
        receiver_list = [RECEIVER]

    # 同一邮箱 1 秒内去重：过滤掉刚刚发过的收件人
    now = time.monotonic()
    with _email_send_lock:
        deduped = []
        for addr in receiver_list:
            last = _email_send_timestamps.get(addr)
            if last is not None and (now - last) < _EMAIL_MIN_INTERVAL:
                continue
            deduped.append(addr)
            _email_send_timestamps[addr] = now
    if not deduped:
        print(f"⏭️ 跳过发送：收件人 {receiver_list} 在 {_EMAIL_MIN_INTERVAL}s 内已发过邮件")
        return True, None
    receiver_list = deduped

    try:
        # 外容器：mixed（保留将来加附件的能力）
        msg = MIMEMultipart("mixed")
        msg["From"] = Header(SENDER_NAME, "utf-8").encode() + f" <{SENDER}>"
        msg["To"] = ",".join(receiver_list)
        msg["Subject"] = Header(subject, "utf-8").encode()

        # 正文容器：alternative，客户端从 plain / html 中选最合适的显示
        body = MIMEMultipart("alternative")
        text_part = MIMEText(content, "plain", "utf-8")
        body.attach(text_part)
        if html_content:
            html_part = MIMEText(html_content, "html", "utf-8")
            body.attach(html_part)
        msg.attach(body)

        # SSL安全上下文
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context)
        server.set_debuglevel(0)  # 1开启详细调试日志，正式环境改为0

        server.login(SENDER, SMTP_PASSWORD)
        server.sendmail(SENDER, receiver_list, msg.as_string())
        server.quit()

        print("✅ 邮件发送成功")
        print(f"发件人: {SENDER}")
        print(f"收件人: {receiver_list}")
        print(f"主题: {subject}")
        print(f"内容(纯文本): {content[:200]}{'...' if len(content) > 200 else ''}")
        return True, None

    except smtplib.SMTPAuthenticationError:
        msg = "SMTP认证失败：账号或独立SMTP密码错误"
        print(f"❌ {msg}")
        return False, msg
    except smtplib.SMTPException as e:
        msg = f"SMTP发送异常: {e}"
        print(f"❌ {msg}")
        return False, msg
    except Exception as e:
        msg = f"邮件发送未知错误: {e}"
        print(f"❌ {msg}")
        return False, msg

