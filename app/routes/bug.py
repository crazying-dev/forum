"""Bug 举报相关路由。"""
import threading
import time
from flask import Blueprint, request, jsonify
from flask_login import current_user
from api import database as db
from api import config
from app.middleware import rate_limit
from Email import send_email, build_email_html

bug_bp = Blueprint('bug', __name__)


def _notify_admin_bug_async(report_id, title, detail, steps, contact, reporter_name, page_url, user_agent, host_url):
	"""后台线程：Bug 举报入库后发邮件通知管理员（RECEIVERALL）。"""
	try:
		now_str = time.strftime('%Y-%m-%d %H:%M:%S')
		# 纯文本兜底
		plain_body = (
			f'收到新的 Bug 举报（ID: {report_id}）\n\n'
			f'提交时间：{now_str}\n'
			f'举报人：{reporter_name or "（匿名游客）"}\n'
			f'联系方式：{contact or "未填写"}\n'
			f'发生页面：{page_url or "未填写"}\n\n'
			f'标题：{title}\n\n'
			f'详细描述：\n{detail}\n\n'
			f'复现步骤：\n{steps or "（未填写）"}\n\n'
			f'User-Agent：{user_agent or "未记录"}\n'
		)
		html_body = build_email_html(
			label='Bug 举报',
			title=f'新的 Bug 举报 #{report_id}',
			body_lines=[
				f'提交时间：<strong>{now_str}</strong>',
				f'举报人：<strong>{reporter_name or "（匿名游客）"}</strong>',
				f'联系方式：{contact or "未填写"}',
				f'发生页面：<a href="{page_url or "#"}" style="color:#a855f7;word-break:break-all;">{page_url or "未填写"}</a>',
				'',
				f'<div style="font-size:16px;font-weight:700;color:#1f2937;margin-top:8px;">标题</div>'
				f'<div style="background:#f9fafb;border-left:3px solid #a855f7;padding:10px 14px;border-radius:4px;color:#374151;white-space:pre-wrap;">{title}</div>',
				'',
				f'<div style="font-size:16px;font-weight:700;color:#1f2937;margin-top:8px;">详细描述</div>'
				f'<div style="background:#f9fafb;border-left:3px solid #a855f7;padding:10px 14px;border-radius:4px;color:#374151;white-space:pre-wrap;">{detail}</div>',
				'',
				f'<div style="font-size:16px;font-weight:700;color:#1f2937;margin-top:8px;">复现步骤</div>'
				f'<div style="background:#f9fafb;border-left:3px solid #a855f7;padding:10px 14px;border-radius:4px;color:#374151;white-space:pre-wrap;">{steps or "（未填写）"}</div>',
				'',
				f'<div style="font-size:12px;color:#9ca3af;line-height:1.6;word-break:break-all;">User-Agent：{user_agent or "未记录"}</div>',
			],
		)
		send_email(
			f'【妖精论坛】新 Bug 举报 #{report_id}: {title[:40]}',
			plain_body,
			receiver_list=[config.RECEIVERALL],
			html_content=html_body
		)
	except Exception as e:
		print(f"[EMAIL] Bug 举报通知管理员失败（忽略）: {e}")


@bug_bp.route('/api/report-bug', methods=['POST'])
def api_report_bug():
	"""提交 Bug 举报（游客可提交，登录用户自动记录身份）。"""
	# 双保险：接口入口即触发懒加载建表，避免后续 UndefinedTable
	try:
		db.ensure_tables()
	except Exception as e:
		print(f"[BUG] ensure_tables 失败（忽略）: {e}")

	if rate_limit('bug_report', 5, 300):
		return jsonify({'success': False, 'message': '提交过于频繁，请5分钟后再试'}), 429

	data = request.get_json() or {}
	title = (data.get('title') or '').strip()
	detail = (data.get('detail') or '').strip()
	steps = (data.get('steps') or '').strip()
	contact = (data.get('contact') or '').strip()
	page_url = (data.get('page_url') or '').strip()

	if not title:
		return jsonify({'success': False, 'message': '请填写 Bug 标题'}), 400
	if len(title) > 200:
		return jsonify({'success': False, 'message': '标题过长（最多200字）'}), 400
	if not detail:
		return jsonify({'success': False, 'message': '请填写 Bug 详细描述'}), 400
	if len(detail) > 5000:
		return jsonify({'success': False, 'message': '详细描述过长（最多5000字）'}), 400
	if steps and len(steps) > 3000:
		return jsonify({'success': False, 'message': '复现步骤过长（最多3000字）'}), 400
	if contact and len(contact) > 200:
		return jsonify({'success': False, 'message': '联系方式过长（最多200字）'}), 400

	reporter_id = None
	reporter_name = ''
	if current_user.is_authenticated:
		reporter_id = current_user['id']
		reporter_name = current_user.get('name') or ''

	user_agent = request.headers.get('User-Agent', '') or ''

	try:
		result = db.report_bug(
			title=title,
			detail=detail,
			steps=steps,
			contact=contact,
			reporter_id=reporter_id,
			reporter_name=reporter_name,
			user_agent=user_agent,
			page_url=page_url,
		)
	except Exception as e:
		print(f"[BUG] report_bug 异常: {e}")
		return jsonify({'success': False, 'message': '服务端处理失败，请稍后重试'}), 500

	if not result.get('success'):
		return jsonify(result), 400

	report_id = result.get('id')
	try:
		t = threading.Thread(
			target=_notify_admin_bug_async,
			args=(report_id, title, detail, steps, contact, reporter_name, page_url, user_agent, request.host_url),
			daemon=True
		)
		t.start()
	except Exception:
		pass

	return jsonify({'success': True, 'message': 'Bug 已提交，感谢反馈', 'id': report_id})
