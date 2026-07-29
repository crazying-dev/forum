"""用户相关 API 路由。"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from api import database as db
from api import cache as cache_api
from main.main import app, base, strip_easter_egg
import hashlib
import os
import io
import requests as http_requests

用户蓝图 = Blueprint('users', __name__)

try:
	from PIL import Image
	_pil_available = True
except ImportError:
	Image = None
	_pil_available = False


@用户蓝图.route('/api/user/info')
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


@用户蓝图.route('/api/users/<user_id>/info')
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


@用户蓝图.route('/api/users/<user_id>/posts')
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


@用户蓝图.route('/api/users/change', methods=['POST'])
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


@用户蓝图.route('/api/user/avatar/upload', methods=['POST'])
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
		print(f"[ERROR] avatar upload: {e}")
		return jsonify({'success': False, 'message': '头像上传失败'}), 500


@用户蓝图.route('/api/users/<user_id>/favorites')
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


@用户蓝图.route('/api/users/<user_id>/follow', methods=['POST'])
@login_required
def api_user_follow(user_id):
	result = db.toggle_follow(current_user['id'], user_id)
	if result.get('success'):
		cache_api.invalidate_user_cache(user_id)
		cache_api.invalidate_user_cache(current_user['id'])
	return jsonify(result)


@用户蓝图.route('/api/users/<user_id>/following')
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


@用户蓝图.route('/api/users/<user_id>/followers')
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


@用户蓝图.route('/api/users/me/replies')
@login_required
def api_my_replies():
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 50, type=int)
	result = db.get_replies_to_my_comments(current_user['id'], page, page_size)
	return jsonify({"success": True, **result})
