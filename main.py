import flask
import time
import json
import hashlib
import os

from admin.admin import AdminKernel

app = flask.Flask(__name__)

REQUEST_TIMEOUT = 120

kernel = AdminKernel()


def _error(msg, code=401):
	return flask.jsonify({'success': False, 'message': msg}), code


def _ok(data):
	return flask.jsonify({'success': True, 'data': data})


def _get_admin_tokens():
	try:
		with open("AdminsID.json", "r", encoding="utf-8") as f:
			data = json.load(f)
		if isinstance(data, dict):
			return data.get('tokens', {})
		# 兼容旧版列表格式
		if isinstance(data, list):
			from api.auth_utils import generate_auth_token
			return {str(aid): generate_auth_token(str(aid)) for aid in data}
		return {}
	except Exception:
		return {}


def _verify_signature(admin_id, send_time, signature, admin_token):
	raw = f"{admin_id}{admin_token}{send_time}"
	expected = hashlib.sha256(raw.encode('utf-8')).hexdigest()
	return signature == expected


def _dispatch(action, args):
	"""根据 action 名称分发到对应的 AdminKernel 方法。"""
	if action == 'list_reports':
		status = args.get('status')
		return kernel.list_reports(status)

	if action == 'resolve_report':
		return kernel.resolve_report(args.get('report_id'))

	if action == 'list_users':
		return kernel.list_users()

	if action == 'find_user':
		return kernel.find_user(args.get('key'), args.get('value'))

	if action == 'find_user_smart':
		return kernel.find_user_smart(args.get('identifier'))

	if action == 'update_user':
		return kernel.update_user(args.get('user_id'), args.get('key'), args.get('value'))

	if action == 'ban_user':
		return kernel.ban_user(args.get('user_id'))

	if action == 'unban_user':
		return kernel.unban_user(args.get('user_id'))

	if action == 'get_post_detail':
		return kernel.get_post_detail(args.get('post_id'))

	if action == 'delete_post':
		return kernel.delete_post(args.get('post_id'))

	if action == 'get_post_comments':
		return kernel.get_post_comments(args.get('post_id'))

	if action == 'delete_comment':
		return kernel.delete_comment(args.get('comment_id'))

	if action == 'get_stats':
		return kernel.get_stats()

	raise ValueError(f"未知操作: {action}")


@app.route('/', methods=['POST'])
def index():
	data = flask.request.get_json() or {}

	admin_id = data.get('adminId') or data.get('AdminID')
	signature = data.get('signature') or data.get('TimeToken')
	send_time = data.get('sendTime') or data.get('SendTime')
	run_message = data.get('runMessage') or data.get('RunMessage')
	admin_token_client = data.get('adminToken') or data.get('AdminToken')

	if not all([admin_id, signature, send_time, run_message]):
		return _error("参数不完整")

	admin_tokens = _get_admin_tokens()
	admin_token = admin_tokens.get(admin_id)
	if not admin_token:
		return _error("非管理员账号")

	sig_ok = _verify_signature(admin_id, str(send_time), signature, admin_token)
	if not sig_ok and admin_token_client:
		sig_ok = _verify_signature(admin_id, str(send_time), signature, admin_token_client)

	if not sig_ok:
		return _error("签名验证失败")

	try:
		sent_ts = float(send_time)
		if abs(time.time() - sent_ts) > REQUEST_TIMEOUT:
			return _error("请求已过期")
	except (ValueError, TypeError):
		return _error("时间格式错误")

	try:
		if isinstance(run_message, str):
			msg = json.loads(run_message)
		else:
			msg = run_message
	except json.JSONDecodeError:
		return _error("runMessage 格式错误，需要 JSON")

	action = msg.get('action')
	args = msg.get('args', {})

	if not action:
		return _error("缺少 action 字段")

	try:
		result = _dispatch(action, args)
		return _ok(result)
	except ValueError as e:
		return _error(str(e), 400)
	except Exception as e:
		return _error(f"执行失败: {str(e)}", 500)


@app.route('/ping', methods=['GET'])
def ping():
	return flask.jsonify({'success': True, 'message': 'pong'})


if __name__ == '__main__':
	app.run(debug=True, port=5001)
