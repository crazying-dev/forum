import random
import json
import os
import re
import io
import time
import hashlib
import uuid

import requests as http_requests
from flask import *
from flask_cors import CORS, cross_origin
from flask_login import LoginManager, UserMixin, AnonymousUserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from markupsafe import escape as html_escape
from api import database as db, config, cache as cache_api
from Email import send_email
import gzip
import hashlib as _hashlib
from io import BytesIO as _BytesIO

try:
	from PIL import Image
	_pil_available = True
except ImportError:
	Image = None
	_pil_available = False

app = Flask(__name__)

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

# 安全配置：SECRET_KEY 必须由环境变量提供
_secret = os.getenv('SECRET_KEY')
if not _secret:
	import secrets as _secrets
	_secret = _secrets.token_hex(32)
	print("[SECURITY WARNING] SECRET_KEY 未设置，已生成临时密钥。生产环境请配置 SECRET_KEY 环境变量。")
app.secret_key = _secret

# Session/Cookie 安全加固
app.config.update(
	SESSION_COOKIE_HTTPONLY=True,
	SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV') == 'production',
	SESSION_COOKIE_SAMESITE='Lax',
	PERMANENT_SESSION_LIFETIME=86400,
	REMEMBER_COOKIE_HTTPONLY=True,
	REMEMBER_COOKIE_SECURE=os.getenv('FLASK_ENV') == 'production',
	REMEMBER_COOKIE_SAMESITE='Lax',
)

# CORS 限定已知域名
_allowed_origins = os.getenv('CORS_ORIGINS', '').split(',')
_allowed_origins = [o.strip() for o in _allowed_origins if o.strip()]
CORS(app, origins=_allowed_origins or True)

# ProxyFix：解析反向代理传递的真实客户端 IP，防止 X-Forwarded-For 伪造
# x_for=1 信任一层代理（Vercel Edge / Nginx），使 request.remote_addr 取到真实 IP
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

base = 'PATH/base.html'


# ── CSRF 保护：校验 Origin/Referer ─────────────────────────

_ALLOWED_ORIGINS_SET = set(_allowed_origins) if _allowed_origins else set()

@app.before_request
def csrf_protect():
	"""对状态变更请求（POST/PUT/DELETE/PATCH）校验 Origin/Referer。"""
	if request.method in ('GET', 'HEAD', 'OPTIONS'):
		return
	origin = request.headers.get('Origin') or ''
	referer = request.headers.get('Referer') or ''
	host = request.host_url.rstrip('/')

	def _is_allowed(url):
		if not url:
			return False
		# 同源请求
		if url.startswith(host) or url.rstrip('/') == host:
			return True
		# 命中白名单
		for ao in _ALLOWED_ORIGINS_SET:
			if url.startswith(ao.rstrip('/')):
				return True
		return False

	if _is_allowed(origin) or _is_allowed(referer):
		return
	# 所有 POST/PUT/DELETE/PATCH 请求都必须携带 Origin 或 Referer 中的至少一个。
	# 拒绝 curl、Postman 等纯 API 客户端发起的无头请求，防止 CSRF 利用。
	return jsonify({'success': False, 'message': '跨站请求已被拦截'}), 403


# ── 速率限制（内存，按 IP 维度）───────────────────────────

_rate_limit_store = {}

def rate_limit(key, max_count, window_seconds):
	"""简易速率限制装饰器。

	Args:
		key: 限流维度标识
		max_count: 窗口内最大请求次数
		window_seconds: 窗口时长（秒）
	Returns:
		403 响应或 None
	"""
	now = time.time()
	# 使用 request.remote_addr 获取客户端 IP。
	# 生产环境启用 ProxyFix 后，remote_addr 自动为反向代理传递的真实 IP，不受 X-Forwarded-For 伪造影响。
	client_ip = request.remote_addr or 'unknown'
	rk = f"{key}:{client_ip}"
	bucket = _rate_limit_store.get(rk, [])
	bucket = [t for t in bucket if t > now - window_seconds]
	if len(bucket) >= max_count:
		return True
	bucket.append(now)
	_rate_limit_store[rk] = bucket
	# 清理过期条目，防止内存泄漏
	if len(_rate_limit_store) > 10000:
		cutoff = now - max(window_seconds, 3600)
		_rate_limit_store.clear()
		for k, v in list(_rate_limit_store.items()):
			v_clean = [t for t in v if t > cutoff]
			if v_clean:
				_rate_limit_store[k] = v_clean
	return False


# ── 性能优化：gzip 压缩 + ETag ────────────────────────────
@app.after_request
def performance_optimize(response):
	# ── 安全响应头 ──
	response.headers.setdefault('X-Content-Type-Options', 'nosniff')
	response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
	response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
	response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=(), payment=()')
	response.headers.setdefault('X-XSS-Protection', '1; mode=block')
	# HSTS 仅在 HTTPS 下生效
	if request.is_secure or request.headers.get('x-forwarded-proto') == 'https':
		response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')

	# 在 gzip 压缩前计算 ETag（基于原始未压缩数据），保证 ETag 不受 Accept-Encoding 影响
	if request.method == 'GET' and response.status_code == 200:
		content_type = response.content_type or ''
		if any(ct in content_type for ct in ('text/html', 'application/json')):
			resp_data = response.get_data()
			if resp_data:
				etag = _hashlib.md5(resp_data).hexdigest()[:16]
				response.headers['ETag'] = f'"{etag}"'
				if response.headers.get('ETag') == request.headers.get('If-None-Match'):
					response.status_code = 304
					response.set_data(b'')
					response.headers['Content-Length'] = '0'
					response.headers.pop('Content-Encoding', None)
					return response

	# gzip 压缩文本类响应
	accept_encoding = request.headers.get('Accept-Encoding', '')
	if 'gzip' in accept_encoding and response.status_code < 500:
		content_type = response.content_type or ''
		if any(ct in content_type for ct in ('text/', 'application/json', 'application/javascript', 'image/svg+xml')):
			resp_data = response.get_data()
			if len(resp_data) > 500:
				buf = _BytesIO()
				with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as f:
					f.write(resp_data)
				response.set_data(buf.getvalue())
				response.headers['Content-Encoding'] = 'gzip'
				response.headers['Content-Length'] = len(response.get_data())
				response.headers['Vary'] = 'Accept-Encoding'

	return response


# ── Flask-Login 配置 ──────────────────────────────────────

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


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.anonymous_user = AnonymousUser


@login_manager.unauthorized_handler
def unauthorized():
	return jsonify({'success': False, 'message': '请先登录'}), 401


@login_manager.user_loader
def load_user(user_id):
	user = db.get_user_by_id(user_id)
	if user:
		return UserWrapper(user)
	return None


# ── 工具函数 ──────────────────────────────────────────────

def strip_easter_egg(name):
	"""去除用户名中的彩蛋标签/标记后返回纯文本，用于长度检查。

	新格式: |[TIME]
	旧格式（向后兼容）: <p...>...</p>
	"""
	name = name.replace('|[TIME]', '')                              # 新格式
	name = re.sub(r'<p[^>]*>', '', name, flags=re.IGNORECASE)      # 旧格式
	name = re.sub(r'</p>', '', name, flags=re.IGNORECASE)           # 旧格式
	return name


# ── 页面路由（已移至 app/路由/页面.py Blueprint）───


# ── Blueprint 注册 ───────────────────────────────
from app.routes import register_routes
register_routes(app)

if __name__ == '__main__':
	app.run()
