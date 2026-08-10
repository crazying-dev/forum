import sys
from pathlib import Path

# Ensure project root is on sys.path so 'api' module can be found
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
	"""Generate verification email HTML."""
	safe_name = str(html_escape(user_name))
	safe_name = re.sub(r'<p[^>]*>', '', safe_name)
	safe_name = re.sub(r'</p>', '', safe_name)
	safe_name = safe_name.replace('|[TIME]', '')
	if token_type == 'email_verify':
		verify_url = f"{request.host_url}verify-email?token={token}"
		title = "Verify Email"
		body_title = "Verify your email address"
		body_desc = "Click to verify and activate your account."
		btn_text = "Verify"
	else:
		verify_url = f"{request.host_url}reset-password?token={token}"
		title = "Reset Password"
		body_title = "Reset your password"
		body_desc = "Click to set a new password."
		btn_text = "Reset"
	return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} - Forum</title>
<style>
body{{margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif}}
.wrapper{{max-width:520px;margin:0 auto;padding:24px 16px}}
.header{{text-align:center;padding:24px 0 16px}}
.header .site{{font-size:13px;color:#8b949e;margin-top:4px}}
.card{{background:#fff;border-radius:12px;padding:32px 28px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card h2{{margin:0 0 8px;font-size:20px;color:#1a1a2e}}
.card .desc{{margin:0 0 24px;font-size:14px;color:#666;line-height:1.6}}
.btn{{display:inline-block;padding:14px 40px;background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff;text-decoration:none;border-radius:8px;font-size:16px;font-weight:600}}
.divider{{height:1px;background:#e5e7eb;margin:24px 0}}
.link-box{{background:#f8f9fa;border-radius:8px;padding:14px;word-break:break-all}}
.link-box .url{{font-size:13px;color:#6366f1}}
.link-box .hint{{font-size:12px;color:#999;margin-top:6px}}
.footer{{text-align:center;padding:20px 0}}
.footer p{{font-size:12px;color:#999;margin:4px 0}}
</style></head><body>
<div class="wrapper">
<div class="header"><div class="site">Forum</div></div>
<div class="card">
<h2>{body_title}</h2>
<p class="desc">{body_desc}</p>
<div style="text-align:center"><a href="{verify_url}" class="btn">{btn_text}</a></div>
<div class="divider"></div>
<div class="link-box">
<div class="hint">Link valid for 30 minutes</div>
<a href="{verify_url}" class="url">{verify_url}</a>
</div></div>
<div class="footer"><p>(c) 2026 Forum</p></div>
</div></body></html>"""


_secret = os.getenv(chr(39)+chr(83)+chr(69)+chr(67)+chr(82)+chr(69)+chr(84)+chr(95)+chr(75)+chr(69)+chr(89)+chr(39)+chr(41))
if not _secret:
	import secrets as _secrets
	_secret = _secrets.token_hex(32)
	print(chr(91)+chr(83)+chr(69)+chr(67)+chr(85)+chr(82)+chr(73)+chr(84)+chr(89)+chr(32)+chr(87)+chr(65)+chr(82)+chr(78)+chr(73)+chr(78)+chr(71)+chr(93)+chr(32)+chr(83)+chr(69)+chr(67)+chr(82)+chr(69)+chr(84)+chr(95)+chr(75)+chr(69)+chr(89)+chr(32)+chr(26410)+chr(35774)+chr(32622))

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



# IP Security: malicious path detection + rate limiting

from app.security import detect_malicious

@app.before_request
def ip_security_check():
	block = detect_malicious()
	if block is not None:
		return block


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
