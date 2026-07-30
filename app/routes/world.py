"""世界频道 API 路由。"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from api import database as db
from api import cache as cache_api
from main.main import app, base
from app.middleware import rate_limit

world_bp = Blueprint('world', __name__)


@world_bp.route('/api/World/ALL')
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


@world_bp.route('/api/World/Send', methods=['POST'])
@login_required
def Api_World_send():
	if rate_limit('world_send', 5, 60):
		return jsonify({'success': False, 'message': '发送过于频繁，请稍后再试'}), 429
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
