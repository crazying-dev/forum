"""评论相关 API 路由。"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from api import database as db
from api import cache as cache_api
from Email import send_email
from main.main import app, base
from app.中间件 import rate_limit

评论蓝图 = Blueprint('comments', __name__)


@评论蓝图.route('/api/posts/<post_id>/comments')
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


@评论蓝图.route('/api/posts/<post_id>/comments/create', methods=['POST'])
@login_required
def api_comment_create(post_id):
	if rate_limit('comment', 20, 60):
		return jsonify({'success': False, 'message': '评论过于频繁，请稍后再试'}), 429
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

		# 如果是对评论的回复，发邮件通知原作者
		if parent_id:
			try:
				parent_result = db.execute_query(
					"SELECT c.user_id, p.title AS post_title, u2.name AS replier_name "
					"FROM comments c "
					"JOIN posts p ON c.post_id = p.id "
					"JOIN users u2 ON c.user_id = u2.id "
					"WHERE c.id = %s",
					(parent_id,),
					fetch=True
				)
				if parent_result:
					parent_user_id = parent_result[0]
					post_title = parent_result[1]
					replier_name = parent_result[2]
					parent_user = db.get_user_by_id(parent_user_id)
					if parent_user and parent_user.get('email'):
						send_email(
							'【妖精论坛】回复通知',
							f'尊敬的 {parent_user["name"]}，您好！\n\n'
							f'用户 {replier_name} 回复了您在帖子《{post_title}》中的评论：\n'
							f'"{content}"\n\n'
							f'点击查看：{request.host_url}post/{post_id}\n\n'
							f'© 2026 妖精论坛 - 粉丝公益创作',
							receiver_list=[parent_user['email']]
						)
			except Exception:
				pass  # 邮件发送失败不影响评论

		return jsonify({'success': True, 'comment': comment})
	return jsonify(result)


@评论蓝图.route('/api/comments/<comment_id>/delete', methods=['POST'])
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
