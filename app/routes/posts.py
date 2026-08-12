"""帖子相关 API 路由。"""
import threading
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from api import database as db
from api import cache as cache_api
from main.main import app, base
from app.middleware import rate_limit
from Email import send_email, build_email_html

posts_bp = Blueprint('posts', __name__)


# ── 帖子发布 → 通知粉丝 ────────────────────────────────────
_CATEGORY_NAME_MAP = {
	'general': '综合讨论',
	'叶羽': '叶羽',
	'创意': '创意工坊',
	'求助': '求助提问',
}


def _notify_fans_new_post_async(author_id, author_name, post_id, title, category, host_url):
	"""后台线程：向粉丝群发「你关注的作者发了新帖」邮件。"""
	try:
		fans = db.get_follower_emails(author_id, limit=5000)
		if not fans:
			return
		email_list = []
		for f in fans:
			if f.get('id') == author_id:
				continue
			if f.get('email'):
				email_list.append(f['email'])
		if not email_list:
			return

		category_name = _CATEGORY_NAME_MAP.get(category, category or '综合讨论')
		post_url = f'{host_url.rstrip("/")}/post/{post_id}'
		plain_title = (title or '').strip()

		plain_body = (
			f'亲爱的粉丝，您好！\n\n'
			f'你关注的用户「{author_name}」刚刚发布了一篇新帖子：\n'
			f'分类：{category_name}\n'
			f'标题：{plain_title}\n\n'
			f'点击链接立即查看：{post_url}\n\n'
			f'© 2026 妖精论坛 - 粉丝公益创作'
		)

		html_body = build_email_html(
			label='新帖通知',
			title=f'你关注的 {author_name} 发布了新帖子',
			body_lines=[
				'亲爱的粉丝，您好！',
				f'你关注的用户「<strong style="color:#a855f7;">{author_name}</strong>」刚刚发布了一篇新帖子。',
				f'分类：{category_name}',
				f'标题：<strong>{plain_title}</strong>',
			],
			action_text='点击查看新帖子',
			action_url=post_url,
			footer_note='这是由您关注的作者发帖触发的通知，您可以在「关注列表」中取消关注来停止接收。'
		)

		chunk_size = 100
		total_sent = 0
		for i in range(0, len(email_list), chunk_size):
			chunk = email_list[i:i + chunk_size]
			try:
				send_email(
					f'【妖精论坛】你关注的 {author_name} 发布了新帖子',
					plain_body,
					receiver_list=chunk,
					html_content=html_body
				)
				total_sent += len(chunk)
			except Exception:
				continue
		print(f"[EMAIL] 新帖通知已发送：author={author_id} post={post_id} recipients={total_sent}")
	except Exception as e:
		print(f"[EMAIL] 新帖通知粉丝失败（忽略）: {e}")


@posts_bp.route('/api/posts')
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


@posts_bp.route('/api/posts/random')
def api_post_random():
	user_id = current_user['id'] if current_user.is_authenticated else None
	posts = db.get_random_posts(user_id)
	resp = jsonify({
		'success': True,
		'posts': posts
	})
	resp.headers['Cache-Control'] = 'max-age=30'
	return resp


@posts_bp.route('/api/posts/<post_id>')
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


@posts_bp.route('/api/posts/create', methods=['POST'])
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
		# ── 邮件通知粉丝（异步线程，不阻塞发布响应）──
		post_id = result.get('id')
		if post_id:
			try:
				t = threading.Thread(
					target=_notify_fans_new_post_async,
					args=(
						current_user['id'],
						current_user['name'],
						post_id,
						title,
						category,
						request.host_url
					),
					daemon=True
				)
				t.start()
			except Exception:
				pass
	return jsonify(result)


@posts_bp.route('/api/posts/<post_id>/like', methods=['POST'])
@login_required
def api_post_like(post_id):
	result = db.like_post(post_id, current_user['id'])
	cache_api.post_detail_cache.delete(f'post:{post_id}')
	return jsonify(result)


@posts_bp.route('/api/posts/<post_id>/delete', methods=['POST'])
@login_required
def api_post_delete(post_id):
	result = db.delete_post(post_id, current_user['id'])
	if result.get('success'):
		cache_api.invalidate_post_cache(post_id)
		cache_api.invalidate_user_cache(current_user['id'])
		return jsonify({'success': True})
	return jsonify(result)


@posts_bp.route('/api/posts/<post_id>/favorite', methods=['POST'])
@login_required
def api_post_favorite(post_id):
	result = db.toggle_favorite(post_id, current_user['id'])
	return jsonify(result)


@posts_bp.route('/api/posts/<post_id>/report', methods=['POST'])
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
