"""SMTP 邮件发送模块（forum-new）。

配置来源：config.py（SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM_NAME / RECEIVERALL）。
"""
import smtplib
import ssl
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

import config

SENDER = config.SMTP_USER
SENDER_NAME = config.SMTP_FROM_NAME or "妖精论坛"

# 同一邮箱 1 秒内最多发一封邮件，避免短时间重复推送
_EMAIL_MIN_INTERVAL = 1.0
_email_send_lock = threading.Lock()
_email_send_timestamps = {}


def _esc(text):
    """HTML 转义"""
    if text is None:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def build_email_html(label, title, body_lines, action_text=None, action_url=None, footer_note=None):
    """统一的 HTML 邮件模板构建器。

    Args:
        label: 顶栏右侧的小标签（如“邮箱验证”“重置密码”）
        title: 卡片内主标题
        body_lines: list[str]，正文段落；段内可包含简单 HTML（如 <strong>）
        action_text: 可选，CTA 按钮文案
        action_url: 可选，CTA 按钮链接
        footer_note: 可选，底部额外提示
    """
    lines_html = ""
    for line in body_lines:
        lines_html += f'<div style="font-size:15px;line-height:1.8;color:#4b5563;margin:0 0 10px;">{line}</div>\n'

    action_html = ""
    if action_text and action_url:
        url_esc = _esc(action_url)
        action_html = (
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="margin:8px 0 22px;">'
            f'<tr><td align="center">'
            f'<a href="{url_esc}" style="display:inline-block;padding:11px 32px;border-radius:6px;'
            f'background:#6A8C89;color:#ffffff;text-decoration:none;'
            f'font-size:14px;">{_esc(action_text)}</a>'
            f'</td></tr></table>'
        )

    footer_html = ""
    if footer_note:
        footer_html = f'<div style="font-size:12px;line-height:1.7;color:#9ca3af;margin-top:8px;">{_esc(footer_note)}</div>'

    return (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="UTF-8" />'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0" />'
        f'<title>{_esc(title)}</title></head>'
        '<body style="margin:0;padding:0;background:#f2f5f5;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif;color:#374151;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="background:#f2f5f5;padding:32px 0;">'
        '<tr><td align="center">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="max-width:560px;margin:0 auto;">'
        '<tr><td style="padding:14px 24px;background:#6A8C89;border-radius:10px 10px 0 0;color:#ffffff;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">'
        '<tr><td style="font-size:16px;font-weight:700;">妖精论坛</td>'
        f'<td align="right" style="font-size:12px;opacity:0.9;">{_esc(label)}</td></tr></table></td></tr>'
        '<tr><td style="background:#ffffff;padding:28px 24px;border-radius:0 0 10px 10px;">'
        f'<div style="font-size:18px;font-weight:700;color:#1f2937;margin:0 0 16px;">{_esc(title)}</div>'
        f'{lines_html}{action_html}{footer_html}</td></tr>'
        '<tr><td align="center" style="padding-top:20px;font-size:12px;color:#9ca3af;line-height:1.8;">'
        '&copy; 2026 妖精论坛 &middot; 粉丝公益创作</td></tr>'
        '</table></td></tr></table></body></html>'
    )


def send_email(subject: str, content: str, receiver_list: list | None = None, html_content: str | None = None):
    """发送邮件。

    为保护收件人隐私，**逐个单独发送**：每个收件人只会在自己邮件的 To 头里看到自己的邮箱，
    不会看到其他收件人。SMTP 连接 / 登录只建立一次以降低开销。

    Args:
        subject: 主题
        content: 纯文本正文
        receiver_list: 收件人邮箱列表；缺省时发给 config.RECEIVERALL
        html_content: 可选 HTML 正文

    Returns:
        tuple: (success: bool, error_message: str | None)
    """
    if receiver_list is None:
        receiver_list = [config.RECEIVERALL]

    # 同一收件人 1 秒内去重
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
        return True, None
    receiver_list = deduped

    if not config.SMTP_PASSWORD:
        return False, "SMTP 密码未配置（SMTP_PASSWORD）"

    # 预构建正文部分（可在多封邮件之间复用，节省内存/时间）
    body_parts = MIMEMultipart("alternative")
    body_parts.attach(MIMEText(content, "plain", "utf-8"))
    if html_content:
        body_parts.attach(MIMEText(html_content, "html", "utf-8"))

    last_err: str | None = None
    context = ssl.create_default_context()
    server = None
    try:
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context)
        server.login(SENDER, config.SMTP_PASSWORD)

        from_header = Header(SENDER_NAME, "utf-8").encode() + f" <{SENDER}>"
        subject_header = Header(subject, "utf-8").encode()

        for rcpt in receiver_list:
            msg = MIMEMultipart("mixed")
            msg["From"] = from_header
            msg["To"] = rcpt  # 每封邮件只写一个收件人，不暴露其他人
            msg["Subject"] = subject_header
            msg.attach(body_parts)
            try:
                server.sendmail(SENDER, [rcpt], msg.as_string())
            except smtplib.SMTPException as e:
                # 单个收件人失败不阻断其他收件人
                last_err = f"部分发送失败({rcpt}): {e}"

        return (True, None) if last_err is None else (False, last_err)
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP认证失败：账号或独立SMTP密码错误"
    except smtplib.SMTPException as e:
        return False, f"SMTP发送异常: {e}"
    except Exception as e:
        return False, f"邮件发送未知错误: {e}"
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass
