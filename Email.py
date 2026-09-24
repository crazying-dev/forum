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

# SMTP 认证阶段错误码 → 中文提示（阿里云邮件推送常见码）
_AUTH_ERROR_HINTS = {
    535: "账号或独立SMTP密码错误",
    551: "发信账户状态异常，请到邮件推送控制台查看账户状态",
    436: "MAIL FROM 与实际发信地址不一致",
    552: "发信额度已用尽",
}

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


def _connect_smtp(context):
    """按 config.SMTP_TLS 建立 SMTP 连接。

    * "ssl"（默认，端口 465，兼容阿里云旧配置）：SMTP_SSL
    * "starttls"（端口 587）：SMTP + STARTTLS
    * "none"（纯明文，通常仅本地中继 / 特殊环境）

    注：很多云厂商封锁出站 25 端口，自建 Postfix 无法直投外部 MX，
    此时应改用 587/STARTTLS 中继或服务商解封。
    """
    mode = (getattr(config, "SMTP_TLS", "") or "").strip().lower()
    host, port = config.SMTP_HOST, config.SMTP_PORT
    timeout = int(getattr(config, "SMTP_TIMEOUT", 20) or 20)
    if mode in ("starttls", "tls", "587"):
        srv = smtplib.SMTP(host, port, timeout=timeout)
        srv.ehlo()
        srv.starttls(context=context)
        srv.ehlo()
        return srv
    if mode in ("none", "plain", "cleartext", "off"):
        return smtplib.SMTP(host, port, timeout=timeout)
    # 默认 SSL（465）
    return smtplib.SMTP_SSL(host, port, context=context, timeout=timeout)


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

    if getattr(config, "SMTP_USE_AUTH", True) and not config.SMTP_PASSWORD:
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
        server = _connect_smtp(context)
        if getattr(config, "SMTP_USE_AUTH", True):
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
    except smtplib.SMTPAuthenticationError as e:
        # 细化错误：把 SMTP 服务器返回的真实错误码/原因透出，避免误判为密码问题。
        # 例如阿里云邮件推送 551 表示「发信账户状态异常」，并非密码错误（535 才是）。
        code = getattr(e, "smtp_code", None)
        raw = getattr(e, "smtp_error", b"")
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "ignore")
        raw = str(raw or "").strip()
        hint = _AUTH_ERROR_HINTS.get(code, "账号或独立SMTP密码错误")
        msg = f"SMTP认证失败({code})：{hint}" if code else f"SMTP认证失败：{hint}"
        if raw:
            msg += f" - {raw}"
        return False, msg
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
