"""辅助函数。"""
import re
import random
import hashlib
import io
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from markupsafe import escape as html_escape
from flask import request
from flask_login import UserMixin, AnonymousUserMixin
from app.config import *

SENDER = SMTP_USER
SENDER_NAME = "妖精论坛"


def strip_easter_egg(name):
	"""去除用户名中的彩蛋标签/标记后返回纯文本，用于长度检查。

	新格式: |[TIME]
	旧格式（向后兼容）: <p...>...</p>
	"""
	name = name.replace('|[TIME]', '')
	name = re.sub(r'<p[^>]*>', '', name, flags=re.IGNORECASE)
	name = re.sub(r'</p>', '', name, flags=re.IGNORECASE)
	return name


def generate_verify_email_body(user_name, token, token_type):
	"""生成验证邮件正文。

	Args:
		user_name (str): 用户名
		token (str): 验证token
		token_type (str): token类型

	Returns:
		str: 邮件正文HTML
	"""
	if token_type == 'email_verify':
		verify_url = f"{request.host_url}verify-email?token={token}"
		title = "邮箱验证"
		description = "点击下方按钮完成邮箱验证"
		button_text = "验证邮箱"
	else:
		verify_url = f"{request.host_url}reset-password?token={token}"
		title = "重置密码"
		description = "点击下方按钮重置密码"
		button_text = "重置密码"

	safe_user_name = str(html_escape(user_name))
	return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 480px; margin: 0 auto; padding: 20px; }}
        .card {{ background: #fff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }}
        .logo {{ font-size: 24px; font-weight: bold; color: #333; margin-bottom: 16px; }}
        .greeting {{ font-size: 18px; color: #333; margin-bottom: 12px; }}
        .description {{ font-size: 14px; color: #666; margin-bottom: 24px; line-height: 1.6; }}
        .button {{ display: inline-block; padding: 12px 32px; background: #4f46e5; color: #fff; text-decoration: none; border-radius: 8px; font-size: 16px; font-weight: 500; }}
        .button:hover {{ background: #4338ca; }}
        .link {{ color: #4f46e5; text-decoration: none; }}
        .footer {{ font-size: 12px; color: #999; margin-top: 24px; text-align: center; }}
        .token-info {{ font-size: 12px; color: #999; margin-top: 16px; font-family: monospace; word-break: break-all; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo">妖精论坛</div>
            <div class="greeting">亲爱的 {safe_user_name}，</div>
            <div class="description">{description}。<br><br>如果这不是您本人操作，请忽略此邮件。</div>
            <a href="{verify_url}" class="button">{button_text}</a>
            <div class="token-info">链接有效期：30分钟<br>链接地址：<a href="{verify_url}" class="link">{verify_url}</a></div>
        </div>
        <div class="footer">© 2026 妖精论坛 - 粉丝公益创作</div>
    </div>
</body>
</html>"""


class UserWrapper(UserMixin):
	"""包装数据库返回的用户字典，使其兼容 Flask-Login。"""

	def __init__(self, user_dict):
		self._user = user_dict

	def get_id(self):
		return str(self._user['id'])

	def get(self, key, default=None):
		return self._user.get(key, default)

	def __getitem__(self, key):
		return self._user[key]

	def __contains__(self, key):
		return key in self._user

	def __getattr__(self, key):
		if key.startswith('_'):
			raise AttributeError(key)
		try:
			return self._user[key]
		except KeyError:
			raise AttributeError(key)


class AnonymousUser(AnonymousUserMixin):
	"""匿名用户，支持字典式访问以兼容旧代码。"""

	def __getitem__(self, key):
		return None

	@property
	def id(self):
		return None


def send_email(subject: str, content: str, receiver_list: list = None, RECEIVER=RECEIVERALL):
	"""发送邮件。

	Returns:
		tuple: (success: bool, error_message: str or None)
	"""
	if receiver_list is None:
		receiver_list = [RECEIVER]
	try:
		msg = MIMEMultipart()
		# 正确设置发件人，避免乱码
		msg["From"] = Header(SENDER_NAME, "utf-8").encode() + f" <{SENDER}>"
		msg["To"] = ",".join(receiver_list)
		msg["Subject"] = Header(subject, "utf-8").encode()

		# 纯文本正文
		text_part = MIMEText(content, "plain", "utf-8")
		msg.attach(text_part)

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
		print(f"内容: {content}")
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
