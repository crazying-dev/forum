import random
import json
import os
import re
from flask import *
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, AnonymousUserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from api import database as db, config, cache as cache_api

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fairy-forum-secret-key-change-in-production')
CORS(app)

base = 'PATH/base.html'


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


@app.route('/WIKI/GuanFang/film')
def WIKIGuanFangFilm():
	return render_template(base, page_template='WIKI/GuanFang/film/film.html')


@app.route('/WIKI/Personal/mouse')
def WIKIPersonalMouse():
	return render_template(base, page_template='WIKI/Personal/mouse/mouse.html')


@app.route('/WIKI/Personal/mouse/Liunx')
def WIKIPersonalMouseLiunx():
	return render_template(base, page_template='WIKI/Personal/mouse/Liunx.html')


@app.route('/WIKI/GuanFang/film/FilmFor2')
def WIKIFilmFor2():
	return render_template(base, page_template='WIKI/GuanFang/film/FilmFor2.html')


@app.route('/WIKI/GuanFang/film/FilmFor1')
def WIKIFilmFor1():
	return render_template(base, page_template='WIKI/GuanFang/film/FilmFor1.html')


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

	db.update_user_last_login(user['id'])
	login_user(UserWrapper(user), remember=remember)
	return jsonify({'success': True, 'id': user['id']})


@app.route('/api/logout', methods=['POST', 'GET'])
def api_logout():
	logout_user()
	return jsonify({'success': True})


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
