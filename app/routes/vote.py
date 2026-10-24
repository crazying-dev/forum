"""版本投票（V1/V2 选择）相关路由。"""
from flask import Blueprint, request, jsonify
from flask_login import current_user
from api import database as db
from app.middleware import rate_limit

vote_bp = Blueprint('vote', __name__)


def _client_ip():
	"""获取客户端 IP（兼容代理，取 X-Forwarded-For 首个 IP）。"""
	ip = (request.headers.get('X-Forwarded-For') or '').strip()
	if ip:
		return ip.split(',')[0].strip()
	return request.remote_addr or 'unknown'


@vote_bp.route('/api/vote/version', methods=['POST'])
def api_vote_version():
	"""投票选择 V1/V2 版本（登录按账号记录，游客按 IP 记录，可改投）。"""
	try:
		db.ensure_tables()
	except Exception as e:
		print(f"[VOTE] ensure_tables 失败（忽略）: {e}")

	if rate_limit('version_vote', 10, 300):
		return jsonify({'success': False, 'message': '操作过于频繁，请稍后再试'}), 429

	data = request.get_json() or {}
	choice = (data.get('choice') or '').strip().lower()
	if choice not in ('v1', 'v2'):
		return jsonify({'success': False, 'message': '无效的选项'}), 400

	if current_user.is_authenticated:
		voter_key = 'u:' + str(current_user['id'])
		voter_id = str(current_user['id'])
		voter_name = current_user.get('name') or ''
	else:
		voter_key = 'ip:' + _client_ip()
		voter_id = None
		voter_name = ''

	try:
		result = db.vote_version(voter_key, choice, voter_id, voter_name)
	except Exception as e:
		print(f"[VOTE] vote_version 异常: {e}")
		return jsonify({'success': False, 'message': '服务端处理失败，请稍后重试'}), 500

	if not result.get('success'):
		return jsonify(result), 400

	stats = db.get_version_vote_stats()
	return jsonify({'success': True, 'message': '投票成功', 'stats': stats})


@vote_bp.route('/api/vote/version/stats', methods=['GET'])
def api_version_vote_stats():
	"""获取当前 V1/V2 票数统计。"""
	try:
		db.ensure_tables()
	except Exception as e:
		print(f"[VOTE] ensure_tables 失败（忽略）: {e}")
	stats = db.get_version_vote_stats()
	return jsonify({'success': True, 'stats': stats})
