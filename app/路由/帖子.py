"""帖子相关 API 路由。"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from api import database as db
from api import cache as cache_api
from main.main import app, base
from app.中间件 import rate_limit

帖子蓝图 = Blueprint('posts', __name__)


@帖子蓝图.route('/api/posts')
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


@帖子蓝图.route('/api/posts/random')
def api_post_random():
	user_id = current_user['id'] if current_user.is_authenticated else None
	posts = db.get_random_posts(user_id)
	resp = jsonify({
		'success': True,
		'posts': posts
	})
	resp.headers['Cache-Control'] = 'max-age=30'
	return resp


@帖子蓝图.route('/api/posts/<post_id>')
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


@帖子蓝图.route('/api/posts/create', methods=['POST'])
@login_required
def api_post_create():
	if rate_limit('post_create', 10, 60):
		return jsonify({'success': False, 'message': '发帖过于频繁，请稍后再试'}), 429
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


@帖子蓝图.route('/api/posts/<post_id>/like', methods=['POST'])
@login_required
def api_post_like(post_id):
	result = db.like_post(post_id, current_user['id'])
	cache_api.post_detail_cache.delete(f'post:{post_id}')
	return jsonify(result)


@帖子蓝图.route('/api/posts/<post_id>/delete', methods=['POST'])
@login_required
def api_post_delete(post_id):
	result = db.delete_post(post_id, current_user['id'])
	if result.get('success'):
		cache_api.invalidate_post_cache(post_id)
		cache_api.invalidate_user_cache(current_user['id'])
		return jsonify({'success': True})
	return jsonify(result)


@帖子蓝图.route('/api/posts/<post_id>/favorite', methods=['POST'])
@login_required
def api_post_favorite(post_id):
	result = db.toggle_favorite(post_id, current_user['id'])
	return jsonify(result)


@帖子蓝图.route('/api/posts/<post_id>/report', methods=['POST'])
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
