import random
import json
import os
import re
import io
import hashlib
import requests as http_requests
from flask import *
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, AnonymousUserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from api import database as db, config, cache as cache_api

try:
	from PIL import Image
	_pil_available = True
except ImportError:
	Image = None
	_pil_available = False


def send_email(to_email, subject, body):
	"""发送邮件。

	Args:
		to_email (str): 收件人邮箱
		subject (str): 邮件主题
		body (str): 邮件正文

	Returns:
		bool: 是否发送成功
	"""
	if not config.SMTP_ENABLED:
		return False

	try:
		import smtplib
		from email.mime.text import MIMEText
		from email.header import Header

		msg = MIMEText(body, 'html', 'utf-8')
		msg['Subject'] = Header(subject, 'utf-8')
		msg['From'] = f"{config.SMTP_FROM_NAME} <{config.SMTP_USER}>"
		msg['To'] = to_email

		with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
			server.starttls()
			server.login(config.SMTP_USER, config.SMTP_PASSWORD)
			server.sendmail(config.SMTP_USER, [to_email], msg.as_string())
		return True
	except Exception as e:
		print(f"邮件发送失败: {e}")
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
		verify_url = f"{request.host_url}verify-email?token={token}"
		title = "邮箱验证"
		description = "点击下方按钮完成邮箱验证"
		button_text = "验证邮箱"
	else:
		verify_url = f"{request.host_url}reset-password?token={token}"
		title = "重置密码"
		description = "点击下方按钮重置密码"
		button_text = "重置密码"

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
            <div class="greeting">亲爱的 {user_name}，</div>
            <div class="description">{description}。<br><br>如果这不是您本人操作，请忽略此邮件。</div>
            <a href="{verify_url}" class="button">{button_text}</a>
            <div class="token-info">链接有效期：30分钟<br>链接地址：<a href="{verify_url}" class="link">{verify_url}</a></div>
        </div>
        <div class="footer">© 2024 妖精论坛 - 粉丝公益创作</div>
    </div>
</body>
</html>"""

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fairy-forum-secret-key-change-in-production')
CORS(app)

base = 'PATH/base.html'


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


# ── 页面路由 ──────────────────────────────────────────────

@app.route('/login')
def login_page():
	if current_user.is_authenticated:
		return redirect('/')
	return render_template(base, page_template='auth.html')


@app.route('/')
def index_page():
	return render_template(base, page_template='index.html')


@app.route('/privacy')
def privacy_page():
	return render_template(base, page_template='privacy.html')


@app.route('/verify-email')
def verify_email_page():
	token = request.args.get('token', '')
	if token:
		token_info = db.get_verify_token(token, 'email_verify')
		if token_info:
			db.update_user_email_verified(token_info['user_id'])
			db.delete_verify_token(token)
			return render_template(base, page_template='verify_success.html')
		else:
			return render_template(base, page_template='verify_failed.html')
	return render_template(base, page_template='auth.html')


@app.route('/reset-password')
def reset_password_page():
	token = request.args.get('token', '')
	if token:
		token_info = db.get_verify_token(token, 'password_reset')
		if token_info:
			return render_template(base, page_template='auth.html')
		else:
			return render_template(base, page_template='verify_failed.html')
	return render_template(base, page_template='auth.html')


@app.route('/WIKI')
def WIKI():
	return render_template(base, page_template='WIKI/WIKI.html')


@app.route("/World")
def World():
	return render_template(base, page_template='World.html')


@app.route('/WIKI/GuanFang')
def WIKIGuanFang():
	return render_template(base, page_template='WIKI/GuanFang/GuanFang.html')


@app.route('/WIKI/Personal')
def WIKIPersonal():
	return render_template(base, page_template='WIKI/Personal/Personal.html')


@app.route('/WIKI/Personal/mouse')
def WIKIPersonalMouse():
	return render_template(base, page_template='WIKI/Personal/mouse/mouse.html')


@app.route('/WIKI/Personal/mouse/Liunx')
def WIKIPersonalMouseLiunx():
	return render_template(base, page_template='WIKI/Personal/mouse/Liunx.html')


@app.route('/forum')
def forum_page():
	return render_template(base, page_template='forum.html')


@app.route('/post/create')
def post_create_page():
	return render_template(base, page_template='post_create.html')


@app.route('/WIKI/Personal/Live2D')
def WIKIPersonalLive2D():
	return render_template(base, page_template='WIKI/Personal/Live2D.html')


@app.route('/users/<ID>')
def users_page(ID):
	UserInfo = db.get_user_by_id(ID)
	if not UserInfo:
		return "No this user", 401
	return render_template(base, page_template='UserPersonalinfo.html')


@app.route('/huiguan')
def huiguan_page():
	return render_template(base, page_template='huiguan.html')


@app.route('/api/huiguan')
def api_huiguan_list():
	try:
		with app.open_resource("huiguan.json", "r", encoding="utf-8") as f:
			data = json.load(f)
		return jsonify({
			'success': True,
			'list': data
		})
	except Exception as e:
		return jsonify({'success': False, 'message': str(e)}), 500


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

# ── 认证 API ──────────────────────────────────────────────

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
	user = db.get_user_by_id(user_id)
	if user:
		login_user(UserWrapper(user), remember=True)
	return jsonify({'success': True, 'id': user_id})


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

	if user.get('is_banned') == 1:
		return jsonify({'success': False, 'message': '该账号已被封禁'})

	db.update_user_last_login(user['id'])
	login_user(UserWrapper(user), remember=remember)
	return jsonify({'success': True, 'id': user['id']})


@app.route('/api/logout', methods=['POST', 'GET'])
def api_logout():
	logout_user()
	return jsonify({'success': True})


@app.route('/api/send-verify-email', methods=['POST'])
@login_required
def api_send_verify_email():
	user = db.get_user_by_id(current_user['id'])
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})

	token_result = db.create_verify_token(user['id'], 'email_verify')
	if not token_result.get('success'):
		return jsonify({'success': False, 'message': '生成验证链接失败'})

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
		return jsonify({'success': False, 'message': '验证链接无效'})

	token_info = db.get_verify_token(token, 'email_verify')
	if not token_info:
		return jsonify({'success': False, 'message': '验证链接已过期或无效'})

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
		return jsonify({'success': False, 'message': '该邮箱未注册'})

	token_result = db.create_verify_token(user['id'], 'password_reset')
	if not token_result.get('success'):
		return jsonify({'success': False, 'message': '生成重置链接失败'})

	token = token_result['token']
	subject = '【妖精论坛】重置密码'
	body = generate_verify_email_body(user['name'], token, 'password_reset')
	
	sent = send_email(email, subject, body)
	if sent:
		return jsonify({'success': True, 'message': '重置链接已发送，请查收邮箱'})
	else:
		return jsonify({'success': True, 'message': '重置链接已生成（邮件服务未启用）', 'token': token})


@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
	data = request.get_json() or {}
	token = data.get('token') or ''
	password = data.get('password') or ''

	if not token:
		return jsonify({'success': False, 'message': '重置链接无效'})
	if len(password) < 6:
		return jsonify({'success': False, 'message': '密码至少6位'})

	token_info = db.get_verify_token(token, 'password_reset')
	if not token_info:
		return jsonify({'success': False, 'message': '重置链接已过期或无效'})

	hashed = generate_password_hash(password)
	db.execute_query(
		"UPDATE users SET password = %s WHERE id = %s",
		(hashed, token_info['user_id'])
	)
	db.delete_verify_token(token)
	
	return jsonify({'success': True, 'message': '密码重置成功'})


@app.route('/api/user/info')
def api_user_info():
	if not current_user.is_authenticated:
		return jsonify({'success': False, 'message': '未登录'})
	return jsonify({
		'success': True,
		'user': {
			'id': current_user['id'],
			'name': current_user['name'],
			'avatar': current_user['avatar'],
			'vip': current_user['vip'],
			'email_verified': current_user.get('email_verified', 0),
		}
	})


# ── 用户 API ──────────────────────────────────────────────

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
				'email_verified': user.get('email_verified', 0),
				'created_at': user['created_at'],
				'last_login': user['last_login']
			},
			'stats': stats,
			'follow_stats': follow_stats
		}
		cache_api.user_info_cache.set(cache_key, result, l1_ttl=300, l2_ttl=1800)
	if current_user.is_authenticated:
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
@login_required
def api_user_change():
	data = request.get_json()
	Info = data.get("Info", None)
	if not Info:
		return jsonify({'success': False, 'message': "参数错误"}), 400
	if 'Name' in Info:
		name_for_check = strip_easter_egg(Info['Name'])
		if len(name_for_check) < 2 or len(name_for_check) > 20:
			return jsonify({'success': False, 'message': '用户名需要2-20个字符（不含彩蛋）'}), 400
	result = db.update_user_profile(current_user['id'], **Info)
	if result:
		cache_api.invalidate_user_cache(current_user['id'])
	return jsonify({'success': result})


@app.route('/api/user/avatar/upload', methods=['POST'])
@login_required
def api_avatar_upload():
	if not _pil_available:
		return jsonify({'success': False, 'message': '服务器未启用图片处理功能'}), 500
	file = request.files.get('avatar')
	if not file or not file.filename:
		return jsonify({'success': False, 'message': '请选择图片'}), 400
	try:
		img = Image.open(file.stream)
		img = img.convert('RGBA')
		bg = Image.new('RGBA', img.size, (255, 255, 255, 255))
		bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
		img = bg.convert('RGB')
		img = img.resize((400, 400), Image.LANCZOS)
		buf = io.BytesIO()
		img.save(buf, format='WEBP', quality=85)
		buf.seek(0)
		token = os.getenv('avatar_READ_WRITE_TOKEN')
		if not token:
			return jsonify({'success': False, 'message': '存储服务未配置'}), 500
		filename = hashlib.md5(f"{current_user['id']}{os.urandom(8).hex()}".encode()).hexdigest()
		pathname = f'avatars/{filename}.webp'
		upload_url = f'https://blob.vercel-storage.com/{pathname}'
		resp = http_requests.put(
			upload_url,
			data=buf.getvalue(),
			headers={
				'Authorization': f'Bearer {token}',
				'Content-Type': 'image/webp',
			},
			timeout=30
		)
		if resp.status_code != 200:
			return jsonify({'success': False, 'message': '上传失败'}), 500
		blob_url = resp.json().get('url')
		if not blob_url:
			return jsonify({'success': False, 'message': '获取URL失败'}), 500
		result = db.update_user_profile(current_user['id'], avatar=blob_url)
		if result:
			cache_api.invalidate_user_cache(current_user['id'])
		return jsonify({'success': result, 'avatar': blob_url})
	except Exception as e:
		return jsonify({'success': False, 'message': f'处理失败: {str(e)}'}), 500


@app.route('/api/users/<user_id>/favorites')
def api_user_favorites(user_id):
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 20, type=int)
	posts = db.get_user_favorites(user_id, page, page_size)
	return jsonify({
		'success': True,
		'posts': posts,
		'page': page,
		'page_size': page_size
	})


@app.route('/api/users/<user_id>/follow', methods=['POST'])
@login_required
def api_user_follow(user_id):
	result = db.toggle_follow(current_user['id'], user_id)
	if result.get('success'):
		cache_api.invalidate_user_cache(user_id)
		cache_api.invalidate_user_cache(current_user['id'])
	return jsonify(result)


@app.route('/api/users/<user_id>/following')
def api_user_following(user_id):
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 20, type=int)
	user = db.get_user_by_id(user_id)
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})
	users = db.get_following_list(user_id, page, page_size)
	result = {
		'success': True,
		'users': users,
		'page': page,
		'page_size': page_size
	}
	if current_user.is_authenticated:
		following_ids = [u['id'] for u in users]
		is_following_map = {}
		for uid in following_ids:
			is_following_map[uid] = db.is_following(current_user['id'], uid)
		for u in users:
			u['is_following'] = is_following_map.get(u['id'], False)
			u['is_self'] = current_user['id'] == u['id']
	else:
		for u in users:
			u['is_following'] = False
			u['is_self'] = False
	return jsonify(result)


@app.route('/api/users/<user_id>/followers')
def api_user_followers(user_id):
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 20, type=int)
	user = db.get_user_by_id(user_id)
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})
	users = db.get_follower_list(user_id, page, page_size)
	result = {
		'success': True,
		'users': users,
		'page': page,
		'page_size': page_size
	}
	if current_user.is_authenticated:
		following_ids = [u['id'] for u in users]
		is_following_map = {}
		for uid in following_ids:
			is_following_map[uid] = db.is_following(current_user['id'], uid)
		for u in users:
			u['is_following'] = is_following_map.get(u['id'], False)
			u['is_self'] = current_user['id'] == u['id']
	else:
		for u in users:
			u['is_following'] = False
			u['is_self'] = False
	return jsonify(result)


# ── 世界频道 API ──────────────────────────────────────────

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
@login_required
def Api_World_send():
	content = (request.json or {}).get('content', '').strip()
	parent_id = (request.json or {}).get('parent_id')
	if not content:
		return jsonify({'success': False, 'message': '内容不能为空'}), 400
	if len(content) > 500:
		return jsonify({'success': False, 'message': '内容过长（最多500字）'}), 400
	result = db.SendWorldMessage(current_user['id'], current_user['name'], content, parent_id)
	if result.get('success'):
		cache_api.invalidate_world_cache()
	return jsonify(result)


# ── 帖子 API ──────────────────────────────────────────────

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
	user_id = current_user['id'] if current_user.is_authenticated else None
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
	liked = False
	favorited = False
	if current_user.is_authenticated:
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
@login_required
def api_post_create():
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
	result = db.Send_Post(current_user['id'], title, content, category)
	if result.get('success'):
		cache_api.invalidate_post_cache()
		cache_api.invalidate_user_cache(current_user['id'])
	return jsonify(result)


@app.route('/api/posts/<post_id>/like', methods=['POST'])
@login_required
def api_post_like(post_id):
	result = db.like_post(post_id, current_user['id'])
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
@login_required
def api_post_delete(post_id):
	result = db.delete_post(post_id, current_user['id'])
	if result.get('success'):
		cache_api.invalidate_post_cache(post_id)
		cache_api.invalidate_user_cache(current_user['id'])
		return jsonify({'success': True})
	return jsonify(result)


@app.route('/api/posts/<post_id>/comments/create', methods=['POST'])
@login_required
def api_comment_create(post_id):
	data = request.get_json() or {}
	content = data.get('content', '').strip()
	parent_id = data.get('parent_id')
	if not content:
		return jsonify({'success': False, 'message': '评论内容不能为空'}), 400
	if len(content) > 500:
		return jsonify({'success': False, 'message': '评论过长（最多500字）'}), 400
	result = db.add_comment(post_id, current_user['id'], content, parent_id)
	if result.get('success'):
		cache_api.post_detail_cache.delete(f'post:{post_id}')
		cache_api.comment_cache.delete(f'comments:{post_id}:page:1:size:50')
		comment = result.get('comment')
		return jsonify({'success': True, 'comment': comment})
	return jsonify(result)


@app.route('/api/comments/<comment_id>/delete', methods=['POST'])
@login_required
def api_comment_delete(comment_id):
	result = db.delete_comment(comment_id, current_user['id'])
	if result.get('success'):
		post_id = result.get('post_id')
		if post_id:
			cache_api.post_detail_cache.delete(f'post:{post_id}')
			cache_api.comment_cache.delete(f'comments:{post_id}:page:1:size:50')
		return jsonify({'success': True})
	return jsonify(result)


@app.route('/api/posts/<post_id>/favorite', methods=['POST'])
@login_required
def api_post_favorite(post_id):
	result = db.toggle_favorite(post_id, current_user['id'])
	return jsonify(result)


@app.route('/api/posts/<post_id>/report', methods=['POST'])
@login_required
def api_post_report(post_id):
	data = request.get_json() or {}
	reason = (data.get('reason') or '').strip()
	detail = (data.get('detail') or '').strip()
	if not reason:
		return jsonify({'success': False, 'message': '请选择举报原因'}), 400
	if len(detail) > 500:
		return jsonify({'success': False, 'message': '描述过长（最多500字）'}), 400
	post = db.get_post(post_id)
	if not post:
		return jsonify({'success': False, 'message': '帖子不存在'}), 404
	result = db.report_post(post_id, current_user['id'], reason, detail)
	return jsonify(result)


# ── 搜索 API ──────────────────────────────────────────────

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
	users = db.search_users(keyword, page, page_size)
	result = {
		'success': True,
		'posts': posts,
		'users': users,
		'keyword': keyword,
		'page': page,
		'page_size': page_size
	}
	cache_api.search_cache.set(cache_key, result, l1_ttl=120, l2_ttl=600)
	return jsonify(result)


# ── 页面路由（续） ────────────────────────────────────────

@app.route('/search')
def search_page():
	return render_template(base, page_template='search.html')


@app.route('/post/<post_id>')
def page_post_detail(post_id):
	return render_template(base, page_template='post_detail.html')


@app.route('/rss.xml')
def RSS():
	return ""


if __name__ == '__main__':
	app.run(debug=True)
