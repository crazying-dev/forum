import random
import json
import os
import re
from flask import *
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from api import database as db, config, cache as cache_api
import markdown
import gzip
import hashlib as _hashlib
from io import BytesIO as _BytesIO

try:
	from PIL import Image
	_pil_available = True
except ImportError:
	Image = None
	_pil_available = False


def send_email(to_email, subject, body):
	"""发送邮件（与 send_email_test.py 一致的实现）。

	Args:
		to_email (str): 收件人邮箱
		subject (str): 邮件主题
		body (str): 邮件正文（HTML格式）

	Returns:
		bool: 是否发送成功
	"""
	if not config.SMTP_ENABLED:
		return False

	try:
		import smtplib
		import ssl
		from email.mime.text import MIMEText
		from email.mime.multipart import MIMEMultipart
		from email.header import Header

		msg = MIMEMultipart()
		msg["From"] = Header(config.SMTP_FROM_NAME, "utf-8").encode() + f" <{config.SMTP_USER}>"
		msg["To"] = to_email
		msg["Subject"] = Header(subject, "utf-8").encode()

		html_part = MIMEText(body, "html", "utf-8")
		msg.attach(html_part)

		context = ssl.create_default_context()
		server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context)
		server.set_debuglevel(0)
		server.login(config.SMTP_USER, config.SMTP_PASSWORD)
		server.sendmail(config.SMTP_USER, [to_email], msg.as_string())
		server.quit()

		print(f"✅ 邮件发送成功 -> {to_email}")
		return True

	except smtplib.SMTPAuthenticationError:
		print("❌ SMTP认证失败：账号或密码错误")
		return False
	except smtplib.SMTPException as e:
		print(f"❌ SMTP发送异常: {e}")
		return False
	except Exception as e:
		print(f"❌ 邮件发送失败: {e}")
		return False


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
		title = "邮箱验证"
		description = "请使用以下验证码完成邮箱验证"
		action_text = "验证邮箱"
	else:
		title = "重置密码"
		description = "请使用以下验证码重置密码"
		action_text = "重置密码"

	return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }}
        .container {{ max-width: 480px; margin: 0 auto; padding: 20px; }}
        .card {{ background: #fff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }}
        .logo {{ font-size: 24px; font-weight: bold; color: #333; margin-bottom: 16px; text-align: center; }}
        .greeting {{ font-size: 18px; color: #333; margin-bottom: 12px; }}
        .description {{ font-size: 14px; color: #666; margin-bottom: 24px; line-height: 1.6; }}
        .code-box {{ background: #f0efff; border: 2px dashed #4f46e5; border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0; }}
        .code {{ font-size: 40px; font-weight: bold; letter-spacing: 8px; color: #4f46e5; font-family: 'Courier New', Consolas, monospace; }}
        .code-hint {{ font-size: 12px; color: #888; margin-top: 12px; }}
        .footer {{ font-size: 12px; color: #999; margin-top: 24px; text-align: center; }}
        .notice {{ font-size: 13px; color: #999; margin-top: 16px; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo">🐱 妖精论坛</div>
            <div class="greeting">亲爱的 {safe_user_name}，</div>
            <div class="description">{description}。<br>验证码有效期为30分钟，请勿泄露给他人。</div>
            <div class="code-box">
                <div class="code">{token}</div>
                <div class="code-hint">{action_text}验证码（6位数字）</div>
            </div>
            <div class="notice">如果这不是您本人操作，请忽略此邮件。</div>
        </div>
        <div class="footer">© 2024 妖精论坛 - 粉丝公益创作</div>
    </div>
</body>
</html>"""

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fairy-forum-secret-key-change-in-production')
CORS(app)

base = 'PATH/base.html'
COOKIE_USER_ID = 'user_id'
COOKIE_USER_TOKEN = 'user_token'
TOKEN_EXPIRE_DAYS = 30


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
	# 无 Origin 和 Referer 的纯 API 客户端请求（如 curl）放行，但浏览器请求必须带其中之一
	if not origin and not referer:
		return
	return jsonify({'success': False, 'message': '跨站请求已被拦截'}), 403


# ── 速率限制（内存，按 IP 维度）───────────────────────────

_rate_limit_store = {}
_user_last_post_time = {}  # 用户发帖冷却：user_id → 上次发帖时间戳

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
	client_ip = request.headers.get('x-forwarded-for', '').split(',')[0].strip() or request.remote_addr or 'unknown'
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

import gzip
import hashlib as _hashlib
from io import BytesIO as _BytesIO

STATIC_ROUTES = {
	'/', '/privacy', '/WIKI', '/WIKI/GuanFang', '/WIKI/Personal',
	'/WIKI/Personal/mouse', '/WIKI/Personal/mouse/Liunx',
	'/WIKI/Personal/Live2D', '/forum', '/huiguan'
}


@app.before_request
def static_page_cache_check():
	if request.method != 'GET':
		return None
	if current_user.is_authenticated:
		return None
	if request.path not in STATIC_ROUTES:
		return None
	cache_key = f'static:{request.path}'
	cached_content = cache_api.get_static_page(cache_key)
	if cached_content:
		return cached_content
	return None


@app.after_request
def performance_optimize(response):
	# 静态页面缓存
	if request.method == 'GET' and response.status_code == 200:
		if not current_user.is_authenticated and request.path in STATIC_ROUTES:
			content_type = response.content_type or ''
			if 'text/html' in content_type:
				content = response.get_data(as_text=True)
				cache_key = f'static:{request.path}'
				cache_api.set_static_page(cache_key, content, ttl=300)

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

	# 为 GET 请求的 HTML/JSON 响应添加 ETag
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

	return response


# ── Flask-Login 配置 ──────────────────────────────────────

class UserWrapper(UserMixin):
	"""包装数据库返回的用户字典，使其兼容 Flask-Login。"""

	def __init__(self, user_dict):
		self._user = user_dict

	def get_id(self):
		return str(self._user['id'])

	def __getitem__(self, key):
		return self._user[key]

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
	"""去除用户名中的彩蛋标签后返回纯文本，用于长度检查。

	彩蛋格式: <p...>...</p>
	"""
	name = re.sub(r'<p[^>]*>', '', name, flags=re.IGNORECASE)
	name = re.sub(r'</p>', '', name, flags=re.IGNORECASE)
	return name


def get_current_user():
	"""
	
	:return:{id", "name", "avatar", "email", "gender", "age", "intro", "vip", "created_at", "last_login"}
	"""
	user_id = request.cookies.get(COOKIE_USER_ID)
	token = request.cookies.get(COOKIE_USER_TOKEN)
	if verify_auth_token(user_id, token):
		user = db.get_user_by_id(user_id)
		if user:
			return user
	return None


@app.route('/login')
def login_page():
	if get_current_user():
		return redirect('/')
	return render_template(base)


@app.route('/login/GET')
def login_get():
	return render_template('auth.html')


@app.route('/GET')
def indexGet():
	return render_template('index.html')


@app.route('/privacy/GET')
def PrivacyGet():
	return render_template('privacy.html')


@app.route('/')
@app.route('/privacy')
@app.route('/WIKI')
@app.route("/World")
@app.route('/WIKI/GuanFang')
@app.route('/WIKI/Personal')
@app.route('/WIKI/GuanFang/film')
@app.route('/WIKI/Personal/mouse')
@app.route('/WIKI/Personal/mouse/Liunx')
@app.route('/WIKI/GuanFang/film/FilmFor2')
@app.route('/WIKI/GuanFang/film/FilmFor1')
@app.route('/forum')
@app.route('/post/create')
@app.route('/WIKI/Personal/Live2D')
def BaseWithAll():
	return render_template(base)


@app.route('/users/<ID>')
def usersbase(ID):
	return render_template(base)


@app.route('/favicon.ico')
def favicon():
	return redirect(config.Image_father_URL + '/favicon.png')


@app.route('/Easter-Egg')
def EasterEgg():
	try:
		with app.open_resource("EasterEgg/1.json", "r", encoding="utf-8") as f:
			data = random.choice(json.load(f))
		return jsonify(data)
	except Exception as e:
		return jsonify({"error": str(e)}), 500


@app.route('/WIKI/GET')
def WIKI():
	return render_template('WIKI/WIKI.html')


@app.route('/WIKI/GuanFang/GET')
def WIKIGuanFang():
	return render_template('WIKI/GuanFang/GuanFang.html')


@app.route('/WIKI/GuanFang/film/GET')
def WIKIGuanFangFilm():
	return render_template('WIKI/GuanFang/film/film.html')


@app.route('/WIKI/GuanFang/film/FilmFor1/GET')
def WIKIFilmFor1():
	return render_template('WIKI/GuanFang/film/FilmFor1.html')


@app.route('/WIKI/GuanFang/film/FilmFor2/GET')
def WIKIFilmFor2():
	return render_template('WIKI/GuanFang/film/FilmFor2.html')


@app.route('/WIKI/Personal/GET')
def WIKIPersonal():
	return render_template('WIKI/Personal/Personal.html')


@app.route('/WIKI/Personal/mouse/GET')
def WIKIPersonalMouse():
	return render_template('WIKI/Personal/mouse/mouse.html')


@app.route('/WIKI/Personal/mouse/Liunx/GET')
def WIKIPersonalMouseLiunx():
	return render_template('WIKI/Personal/mouse/Liunx.html')


@app.route('/WIKI/Personal/Live2D/GET')
def WIKIPersonalLive2D():
	return render_template('WIKI/Personal/Live2D.html')


@app.route('/users/<ID>/GET')
def users(ID):
	UserInfo = db.get_user_by_id(ID)
	if not UserInfo:
		return "No this user", 401
	return render_template('UserPersonalinfo.html')


@app.route('/World/GET')
def Wrold():
	return render_template("World.html")


@app.route('/WIKI/GuanFang/film/FilmFor2/Photo')
def WIKIFilmFor2Photo():
	return redirect(config.Image_father_URL + "/" + random.choice(
		[
			"f0a6658d490a588add803b536a1ebe12.jpg",
			"Camera_XHS_17826569776881040g00832023q3k2jq6g5nqj.jpg"
		]
	))


@app.route('/WIKI/GuanFang/film/Photo')
def WIKIFilmPhoto():
	return redirect(config.Image_father_URL + "/" + random.choice(
		[
			"32ea892873b7c4214dd82c6070ffa1f5.jpg",
			"20190930192812_ZdJUw.jpeg",
			"Camera_XHS_17826569776881040g00832023q3k2jq6g5nqj.jpg",
			"f0a6658d490a588add803b536a1ebe12.jpg",
			"Image_1782657911213_521.png"
		]
	))


@app.route('/api/register', methods=['POST'])
def api_register():
	data = request.get_json() or {}
	name = (data.get('name') or '').strip()
	email = (data.get('email') or '').strip().lower()
	password = data.get('password') or ''

	name_for_check = strip_easter_egg(name)
	if len(name_for_check) < 2 or len(name_for_check) > 20:
		return jsonify({'success': False, 'message': '用户名需要2-20个字符（不含彩蛋）'})
	if not email or '@' not in email:
		return jsonify({'success': False, 'message': '请输入有效的邮箱'})
	if len(password) < 6:
		return jsonify({'success': False, 'message': '密码至少6位'})

	hashed = generate_password_hash(password)
	result = db.new_user(name, email, hashed)
	
	if not result.get('success'):
		return jsonify({'success': False, 'message': result.get('message', '注册失败')})
	
	user_id = result['id']

	# 注册成功后自动发送邮箱验证邮件
	token_result = db.create_verify_token(user_id, 'email_verify')
	email_sent = False
	if token_result.get('success'):
		subject = '【妖精论坛】邮箱验证'
		body = generate_verify_email_body(name, token_result['token'], 'email_verify')
		email_sent = send_email(email, subject, body)

	user = db.get_user_by_id(user_id)
	if user:
		login_user(UserWrapper(user), remember=True)

	if email_sent:
		return jsonify({'success': True, 'id': user_id, 'message': '注册成功，验证邮件已发送至您的邮箱'})
	else:
		return jsonify({'success': True, 'id': user_id, 'message': '注册成功，但验证邮件发送失败，请稍后重试'})


@app.route('/api/login', methods=['POST'])
def api_login():
	data = request.get_json() or {}
	name_or_email = (data.get('name') or '').strip()
	password = data.get('password') or ''
	remember = data.get('remember', True)
	
	if not name_or_email or not password:
		return jsonify({'success': False, 'message': '请输入账号和密码'})
	
	user = None
	if '@' in name_or_email and '.' in name_or_email:
		user = db.get_user_by_email(name_or_email.lower())
	else:
		name_or_email = name_or_email.replace("[TIME]", '<p class="TimeWithUserNameAPI"></p>')
		user = db.get_user_by_name(name_or_email)
	
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})
	
	if not check_password_hash(user['password'], password):
		return jsonify({'success': False, 'message': '密码错误'})
	
	db.update_user_last_login(user['id'])
	token = generate_auth_token(user['id'])
	max_age = TOKEN_EXPIRE_DAYS * 86400 if remember else None
	resp = make_response(jsonify({'success': True, 'id': user['id']}))
	resp.set_cookie(COOKIE_USER_ID, user['id'], max_age=max_age, httponly=True, samesite='Lax')
	resp.set_cookie(COOKIE_USER_TOKEN, token, max_age=max_age, httponly=True, samesite='Lax')
	return resp


@app.route('/api/logout', methods=['POST', 'GET'])
def api_logout():
	resp = make_response(redirect('/'))
	resp.delete_cookie(COOKIE_USER_ID)
	resp.delete_cookie(COOKIE_USER_TOKEN)
	return resp


@app.route('/api/send-verify-email', methods=['POST'])
@login_required
def api_send_verify_email():
	user = db.get_user_by_id(current_user['id'])
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})

	token_result = db.create_verify_token(user['id'], 'email_verify')
	if not token_result.get('success'):
		return jsonify({'success': False, 'message': '生成验证码失败'})

	token = token_result['token']
	subject = '【妖精论坛】邮箱验证'
	body = generate_verify_email_body(user['name'], token, 'email_verify')
	
	sent = send_email(user['email'], subject, body)
	if sent:
		return jsonify({'success': True, 'message': '验证邮件已发送，请查收邮箱'})
	else:
		return jsonify({'success': True, 'message': '验证链接已生成（邮件服务未启用）', 'token': token})


@app.route('/api/verify-email', methods=['POST'])
def api_verify_email():
	data = request.get_json() or {}
	token = data.get('token') or ''

	if not token:
		return jsonify({'success': False, 'message': '验证码无效'})

	token_info = db.get_verify_token(token, 'email_verify')
	if not token_info:
		return jsonify({'success': False, 'message': '验证码已过期或无效'})

	db.update_user_email_verified(token_info['user_id'])
	db.delete_verify_token(token)
	
	return jsonify({'success': True, 'message': '邮箱验证成功'})


@app.route('/api/send-reset-password', methods=['POST'])
def api_send_reset_password():
	data = request.get_json() or {}
	email = (data.get('email') or '').strip().lower()

	if not email or '@' not in email:
		return jsonify({'success': False, 'message': '请输入有效的邮箱'})

	user = db.get_user_by_email(email)
	if not user:
		# 防止邮箱枚举：无论邮箱是否存在都返回相同信息
		return jsonify({'success': True, 'message': '如果该邮箱已注册，重置验证码已发送至邮箱'})

	token_result = db.create_verify_token(user['id'], 'password_reset')
	if not token_result.get('success'):
		return jsonify({'success': False, 'message': '生成重置验证码失败'})

	token = token_result['token']
	subject = '【妖精论坛】重置密码'
	body = generate_verify_email_body(user['name'], token, 'password_reset')
	
	sent = send_email(email, subject, body)
	if sent:
		return jsonify({'success': True, 'message': '如果该邮箱已注册，重置验证码已发送至邮箱'})
	else:
		return jsonify({'success': True, 'message': '重置链接已生成（邮件服务未启用）', 'token': token})


@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
	data = request.get_json() or {}
	token = data.get('token') or ''
	password = data.get('password') or ''

	if not token:
		return jsonify({'success': False, 'message': '重置验证码无效'})
	if len(password) < 8:
		return jsonify({'success': False, 'message': '密码至少8位'})
	if not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
		return jsonify({'success': False, 'message': '密码需包含字母和数字'})

	token_info = db.get_verify_token(token, 'password_reset')
	if not token_info:
		return jsonify({'success': False, 'message': '重置验证码已过期或无效'})

	hashed = generate_password_hash(password)
	db.execute_query(
		"UPDATE users SET password = %s WHERE id = %s",
		(hashed, token_info['user_id'])
	)
	db.delete_verify_token(token)
	
	return jsonify({'success': True, 'message': '密码重置成功'})


@app.route('/api/user/info')
def api_user_info():
	user = get_current_user()
	if not user:
		return jsonify({'success': False, 'message': '未登录'})
	return jsonify({
		'success': True,
		'user': {
			'id': user['id'],
			'name': user['name'],
			'avatar': user['avatar'],
			'vip': user['vip'],
		}
	})


@app.route('/api/users/<user_id>/info')
def api_user_profile_info(user_id):
	cache_key = f'user:{user_id}'
	cached = cache_api.user_info_cache.get(cache_key)
	if cached is not None:
		result = dict(cached)
	else:
		user = db.get_user_by_id(user_id)
		if not user:
			return jsonify({'success': False, 'message': '用户不存在'})
		stats = db.get_user_stats(user_id)
		follow_stats = db.get_follow_stats(user_id)
		result = {
			'success': True,
			'user': {
				'id': user['id'],
				'name': user['name'],
				'avatar': user['avatar'],
				'gender': user['gender'],
				'age': user['age'],
				'intro': user['intro'],
				'vip': user['vip'],
				'created_at': user['created_at'],
				'last_login': user['last_login']
			},
			'stats': stats,
			'follow_stats': follow_stats
		}
		cache_api.user_info_cache.set(cache_key, result, l1_ttl=300, l2_ttl=1800)
	current_user = get_current_user()
	if current_user:
		result['is_following'] = db.is_following(current_user['id'], user_id)
		result['is_self'] = current_user['id'] == user_id
	else:
		result['is_following'] = False
		result['is_self'] = False
	return jsonify(result)


@app.route('/api/users/<user_id>/posts')
def api_user_profile_posts(user_id):
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 20, type=int)
	cache_key = f'user_posts:{user_id}:page:{page}:size:{page_size}'
	cached = cache_api.user_info_cache.get(cache_key)
	if cached is not None:
		return jsonify(cached)
	user = db.get_user_by_id(user_id)
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})
	posts = db.get_user_posts(user_id, page, page_size)
	result = {
		'success': True,
		'posts': posts,
		'page': page,
		'page_size': page_size
	}
	cache_api.user_info_cache.set(cache_key, result, l1_ttl=60, l2_ttl=300)
	return jsonify(result)


@app.route('/api/users/change', methods=['POST'])
def api_user_change():
	user = get_current_user()
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'}), 401
	data = request.get_json()
	Info = data.get("Info", None)
	if not Info:
		return jsonify({'success': False, 'message': "参数错误"}), 400
	if 'Name' in Info:
		name_for_check = strip_easter_egg(Info['Name'])
		if len(name_for_check) < 2 or len(name_for_check) > 20:
			return jsonify({'success': False, 'message': '用户名需要2-20个字符（不含彩蛋）'}), 400
	result = db.update_user_profile(user["id"], **Info)
	if result:
		cache_api.invalidate_user_cache(user['id'])
	return jsonify({'success': result})


@app.route('/api/World/ALL')
def Api_World_all():
	cache_key = 'world:all'
	cached = cache_api.world_cache.get(cache_key)
	if cached is not None:
		resp = jsonify(cached)
		resp.headers['Cache-Control'] = 'max-age=2'
		resp.headers['X-Cache'] = 'HIT'
		return resp
	data = db.GitWroldMessageWithAll()
	cache_api.world_cache.set(cache_key, data, l1_ttl=2, l2_ttl=10)
	resp = jsonify(data)
	resp.headers['Cache-Control'] = 'max-age=2'
	resp.headers['X-Cache'] = 'MISS'
	return resp


@app.route('/api/World/Send', methods=['POST'])
def Api_World_send():
	user = get_current_user()
	if not user:
		return jsonify({'success': False, 'message': '请先登录'}), 401
	content = (request.json or {}).get('content', '').strip()
	parent_id = (request.json or {}).get('parent_id')
	if not content:
		return jsonify({'success': False, 'message': '内容不能为空'}), 400
	if len(content) > 500:
		return jsonify({'success': False, 'message': '内容过长（最多500字）'}), 400
	result = db.SendWorldMessage(user['id'], user['name'], content, parent_id)
	if result.get('success'):
		cache_api.invalidate_world_cache()
	return jsonify(result)


@app.route('/api/posts')
def api_post_list():
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 20, type=int)
	category = request.args.get('category', None)
	cache_key = f'posts:page:{page}:size:{page_size}'
	if category:
		cache_key += f':cat:{category}'
	cached = cache_api.post_list_cache.get(cache_key)
	if cached is not None:
		resp = jsonify(cached)
		resp.headers['Cache-Control'] = 'max-age=30'
		resp.headers['X-Cache'] = 'HIT'
		return resp
	posts = db.get_post_list(page, page_size, category)
	result = {
		'success': True,
		'posts': posts,
		'page': page,
		'page_size': page_size
	}
	cache_api.post_list_cache.set(cache_key, result, l1_ttl=30, l2_ttl=120)
	resp = jsonify(result)
	resp.headers['Cache-Control'] = 'max-age=30'
	resp.headers['X-Cache'] = 'MISS'
	return resp


@app.route('/api/posts/random')
def api_post_random():
	user = get_current_user()
	user_id = user['id'] if user else None
	posts = db.get_random_posts(user_id)
	resp = jsonify({
		'success': True,
		'posts': posts
	})
	resp.headers['Cache-Control'] = 'max-age=30'
	return resp


@app.route('/api/posts/<post_id>')
def api_post_detail(post_id):
	cache_key = f'post:{post_id}'
	cached = cache_api.post_detail_cache.get(cache_key)
	if cached is not None:
		post = cached.get('post')
		comments = cached.get('comments')
	else:
		post = db.get_post(post_id)
		if not post:
			return jsonify({'success': False, 'message': '帖子不存在'}), 404
		comments = db.get_post_comments(post_id, 1, 50)
		cache_api.post_detail_cache.set(cache_key, {'post': post, 'comments': comments}, l1_ttl=60, l2_ttl=300)
	db.increment_post_views(post_id)
	post['views'] = post.get('views', 0) + 1
	current_user = get_current_user()
	liked = False
	favorited = False
	if current_user:
		liked = db.has_liked_post(post_id, current_user['id'])
		favorited = db.has_favorited_post(post_id, current_user['id'])
	return jsonify({
		'success': True,
		'post': post,
		'comments': comments,
		'liked': liked,
		'favorited': favorited
	})


@app.route('/api/posts/create', methods=['POST'])
def api_post_create():
	if rate_limit('post_create', 10, 60):
		return jsonify({'success': False, 'message': '发帖过于频繁，请稍后再试'}), 429
	
	# 用户级发帖冷却：同一用户两次发帖间隔至少 60 秒
	now = time.time()
	last_time = _user_last_post_time.get(current_user['id'], 0)
	if now - last_time < 60:
		remaining = int(60 - (now - last_time))
		return jsonify({
			'success': False,
			'message': f'发帖过于频繁，请等待 {remaining} 秒后再试'
		}), 429
	
	data = request.get_json() or {}
	title = data.get('title', '').strip()
	content = data.get('content', '').strip()
	category = data.get('category', 'general')
	if not title:
		return jsonify({'success': False, 'message': '标题不能为空'}), 400
	if len(title) > 100:
		return jsonify({'success': False, 'message': '标题过长（最多100字）'}), 400
	if not content:
		return jsonify({'success': False, 'message': '内容不能为空'}), 400
	# 将 Markdown 内容转换为 HTML，再经 safe_html 过滤后存储
	content = markdown.markdown(content, extensions=['extra', 'codehilite'])
	result = db.Send_Post(current_user['id'], title, content, category)
	if result.get('success'):
		_user_last_post_time[current_user['id']] = time.time()  # 记录成功发帖时间
		cache_api.invalidate_post_cache()
		cache_api.invalidate_user_cache(user['id'])
	return jsonify(result)


@app.route('/api/posts/<post_id>/like', methods=['POST'])
def api_post_like(post_id):
	user = get_current_user()
	if not user:
		return jsonify({'success': False, 'message': '请先登录'}), 401
	result = db.like_post(post_id, user['id'])
	cache_api.post_detail_cache.delete(f'post:{post_id}')
	return jsonify(result)


@app.route('/api/posts/<post_id>/comments')
def api_post_comments(post_id):
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 50, type=int)
	cache_key = f'comments:{post_id}:page:{page}:size:{page_size}'
	cached = cache_api.comment_cache.get(cache_key)
	if cached is not None:
		return jsonify(cached)
	comments = db.get_post_comments(post_id, page, page_size)
	result = {
		'success': True,
		'comments': comments,
		'page': page,
		'page_size': page_size
	}
	cache_api.comment_cache.set(cache_key, result, l1_ttl=60, l2_ttl=300)
	return jsonify(result)


@app.route('/api/posts/<post_id>/delete', methods=['POST'])
def api_post_delete(post_id):
	user = get_current_user()
	if not user:
		return jsonify({'success': False, 'message': '请先登录'}), 401
	result = db.delete_post(post_id, user['id'])
	if result.get('success'):
		cache_api.invalidate_post_cache(post_id)
		cache_api.invalidate_user_cache(user['id'])
		return jsonify({'success': True})
	return jsonify(result)


@app.route('/api/posts/<post_id>/comments/create', methods=['POST'])
def api_comment_create(post_id):
	user = get_current_user()
	if not user:
		return jsonify({'success': False, 'message': '请先登录'}), 401
	data = request.get_json() or {}
	content = data.get('content', '').strip()
	parent_id = data.get('parent_id')
	if not content:
		return jsonify({'success': False, 'message': '评论内容不能为空'}), 400
	if len(content) > 500:
		return jsonify({'success': False, 'message': '评论过长（最多500字）'}), 400
	result = db.add_comment(post_id, user['id'], content, parent_id)
	if result.get('success'):
		cache_api.post_detail_cache.delete(f'post:{post_id}')
		cache_api.comment_cache.delete(f'comments:{post_id}:page:1:size:50')
		comment = result.get('comment')
		return jsonify({'success': True, 'comment': comment})
	return jsonify(result)


@app.route('/api/comments/<comment_id>/delete', methods=['POST'])
def api_comment_delete(comment_id):
	user = get_current_user()
	if not user:
		return jsonify({'success': False, 'message': '请先登录'}), 401
	result = db.delete_comment(comment_id, user['id'])
	if result.get('success'):
		post_id = result.get('post_id')
		if post_id:
			cache_api.post_detail_cache.delete(f'post:{post_id}')
			cache_api.comment_cache.delete(f'comments:{post_id}:page:1:size:50')
		return jsonify({'success': True})
	return jsonify(result)


@app.route('/api/search')
def api_search():
	keyword = request.args.get('k', '').strip()
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 20, type=int)
	if not keyword:
		return jsonify({'success': False, 'message': '请输入搜索关键词'}), 400
	cache_key = f'search:{keyword}:page:{page}:size:{page_size}'
	cached = cache_api.search_cache.get(cache_key)
	if cached is not None:
		return jsonify(cached)
	posts = db.search_posts(keyword, page, page_size)
	result = {
		'success': True,
		'posts': posts,
		'keyword': keyword,
		'page': page,
		'page_size': page_size
	}
	cache_api.search_cache.set(cache_key, result, l1_ttl=120, l2_ttl=600)
	return jsonify(result)


@app.route('/search')
def search_page():
	return render_template(base)


@app.route('/search/GET')
def search_get():
	return render_template('search.html')


@app.route('/forum/GET')
def forum_get():
	return render_template('forum.html')


@app.route('/post/create/GET')
def post_create_get():
	return render_template('post_create.html')


@app.route('/post/<post_id>')
def page_post_detail(post_id):
	return render_template(base)


@app.route('/post/<post_id>/GET')
def post_detail_get(post_id):
	return render_template('post_detail.html')


@app.route('/rss.xml')
def RSS():
	return ""


@app.route('/QQ/redirect')
def QQ_redirect():
	return redirect("https://qm.qq.com/q/bLxr68HnUI")


# ─────── 蓝溪拾遗用户头像返回API ───────
subdomain_rule = re.compile(r"^https://[\w\-]+\.navifox\.net$")

@app.route('/api/users/avatar/navifox/', methods=['GET'])
@cross_origin(origins="")
def navifox_avatar():return ""

# ─────── 众生之门API ───────
@app.route("/TheDoorOfBings/UUID4/")
def TheDoorOfBings_UUID():
	return jsonify([str(uuid.uuid4())])


if __name__ == '__main__':
	app.run(debug=True)
