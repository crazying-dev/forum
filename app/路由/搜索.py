"""搜索 API 路由。"""
from flask import Blueprint, request, jsonify
from api import database as db
from api import cache as cache_api
from main.main import app, base

搜索蓝图 = Blueprint('search', __name__)


@搜索蓝图.route('/api/search')
def api_search():
	keyword = request.args.get('k', '').strip()
	page = request.args.get('page', 1, type=int)
	page_size = request.args.get('page_size', 20, type=int)
	search_type = request.args.get('type', 'both')  # posts / users / both

	if len(keyword) < 2:
		return jsonify({'success': False, 'message': '关键词至少2个字符'}), 400

	cache_key = f'search:{search_type}:{keyword}:page:{page}:size:{page_size}'
	cached = cache_api.search_cache.get(cache_key)
	if cached is not None:
		return jsonify(cached)

	result = {
		'success': True,
		'keyword': keyword,
		'page': page,
		'page_size': page_size,
	}

	if search_type in ('posts', 'both'):
		posts, posts_total = db.search_posts(keyword, page, page_size)
		result['posts'] = posts
		result['posts_total'] = posts_total
		result['posts_has_more'] = (page * page_size) < posts_total

	if search_type in ('users', 'both'):
		users, users_total = db.search_users(keyword, page, page_size)
		result['users'] = users
		result['users_total'] = users_total
		result['users_has_more'] = (page * page_size) < users_total

	cache_api.search_cache.set(cache_key, result, l1_ttl=120, l2_ttl=600)
	return jsonify(result)
