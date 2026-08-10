"""用户相关 API 路由。"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from api import database as db
from api import cache as cache_api
from main.main import app, base, strip_easter_egg
import hashlib
import os
import io

users_bp = Blueprint('users', __name__)

try:
	from PIL import Image
	_pil_available = True
except ImportError:
	Image = None
	_pil_available = False


@users_bp.route('/api/user/info')
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


@users_bp.route('/api/users/<user_id>/info')
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
		# 缓存里只存「公开、不依赖当前访问者」的字段
		cache_api.user_info_cache.set(cache_key, result, l1_ttl=300, l2_ttl=1800)

	# ── 当前访问者视角字段，每次动态计算，避免缓存污染 A→B 的数据给 C ──
	if current_user.is_authenticated:
		try:
			viewer_id = current_user['id']
		except Exception:
			viewer_id = None
		result['is_following'] = bool(viewer_id) and db.is_following(viewer_id, user_id)
		result['is_self'] = bool(viewer_id) and viewer_id == user_id
	else:
		result['is_following'] = False
		result['is_self'] = False
	return jsonify(result)


@users_bp.route('/api/users/<user_id>/posts')
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


@users_bp.route('/api/users/change', methods=['POST'])
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


@users_bp.route('/api/user/avatar/upload', methods=['POST'])
@login_required
def api_avatar_upload():
	if not _pil_available:
		return jsonify({'success': False, 'message': '服务器未启用图片处理功能'}), 500
	file = request.files.get('avatar')
	if not file or not file.filename:
		return jsonify({'success': False, 'message': '请选择图片'}), 400
	img = None
	bg = None
	buf = None
	avatar_file = None
	try:
		img = Image.open(file.stream)
		img = img.convert('RGBA')
		bg = Image.new('RGBA', img.size, (255, 255, 255, 255))
		bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
		# 释放原图（转换后原对象不再需要）
		try:
			img.close()
		except Exception:
			pass
		img = bg.convert('RGB')
		# 释放 bg
		try:
			bg.close()
		except Exception:
			pass
		bg = None
		img = img.resize((400, 400), Image.LANCZOS)
		buf = io.BytesIO()
		img.save(buf, format='WEBP', quality=85)
		img_data = buf.getvalue()
		import uuid
		avatar_id = str(uuid.uuid4())
		avatar_dir = '/root/db/avatar'
		os.makedirs(avatar_dir, exist_ok=True)
		avatar_path = f'{avatar_dir}/{avatar_id}.webp'
		with open(avatar_path, 'wb') as avatar_file:
			avatar_file.write(img_data)
		avatar_file = None
		avatar_url = f'/avatar/{avatar_id}.webp'
		result = db.update_user_profile(current_user['id'], avatar=avatar_url)
		if result:
			cache_api.invalidate_user_cache(current_user['id'])
		return jsonify({'success': result, 'avatar': avatar_url})
	except Exception as e:
		print(f"[ERROR] avatar upload: {e}")
		return jsonify({'success': False, 'message': '头像上传失败'}), 500
	finally:
		# ── 显式释放 PIL / BytesIO / 文件句柄，减轻 GC 压力 ──
		if img is not None:
			try:
				img.close()
			except Exception:
				pass
		if bg is not None:
			try:
				bg.close()
			except Exception:
				pass
		if buf is not None:
			try:
				buf.close()
			except Exception:
				pass
		if avatar_file is not None:
			try:
				avatar_file.close()
			except Exception:
				pass
		# 手动解除引用，便于 GC 立刻回收
		img = bg = buf = avatar_file = None


@users_bp.route('/api/users/<user_id>/favorites')
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


@users_bp.route('/api/users/<user_id>/follow', methods=['POST'])
@login_required
def api_user_follow(user_id):
	result = db.toggle_follow(current_user['id'], user_id)
	if result.get('success'):
		cache_api.invalidate_user_cache(user_id)
		cache_api.invalidate_user_cache(current_user['id'])
	return jsonify(result)


def _current_viewer_id():
	"""安全获取当前登录者 ID；未登录 / 异常时返回 None，避免 500。"""
	if not current_user.is_authenticated:
		return None
	try:
		vid = current_user['id']
		return vid if vid else None
	except Exception:
		try:
			vid = current_user.get_id()
			return vid if vid else None
		except Exception:
			return None


@users_bp.route('/api/users/<user_id>/following')
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
	viewer_id = _current_viewer_id()
	if viewer_id:
		# 批量一次性查询当前登录者对这批人的关注关系（最多 page_size 条）
		if users:
			ids_in_page = [u['id'] for u in users]
			is_following_map = {}
			for uid in ids_in_page:
				is_following_map[uid] = db.is_following(viewer_id, uid)
			for u in users:
				u['is_following'] = bool(is_following_map.get(u['id']))
				u['is_self'] = viewer_id == u['id']
		else:
			for u in users:
				u['is_following'] = False
				u['is_self'] = False
	else:
		for u in users:
			u['is_following'] = False
			u['is_self'] = False
	return jsonify(result)


@users_bp.route('/api/users/<user_id>/followers')
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
	viewer_id = _current_viewer_id()
	if viewer_id:
		if users:
			ids_in_page = [u['id'] for u in users]
			is_following_map = {}
			for uid in ids_in_page:
				is_following_map[uid] = db.is_following(viewer_id, uid)
			for u in users:
				u['is_following'] = bool(is_following_map.get(u['id']))
				u['is_self'] = viewer_id == u['id']
		else:
			for u in users:
				u['is_following'] = False
				u['is_self'] = False
	else:
		for u in users:
			u['is_following'] = False
			u['is_self'] = False
	return jsonify(result)


@users_bp.route('/api/users/me/replies')
@login_required
def api_my_replies():
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 50, type=int)
	result = db.get_replies_to_my_comments(current_user['id'], page, page_size)
	return jsonify({"success": True, **result})
