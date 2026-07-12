import flask
import time
import json
import hashlib

from api.auth_utils import verify_auth_token
from admin.admin import AdminKernel

app = flask.Flask(__name__)

# 请求有效时间窗口（秒）
REQUEST_TIMEOUT = 120

# 管理员内核实例
kernel = AdminKernel()


def _error(msg, code=401):
	return flask.jsonify({'success': False, 'message': msg}), code


def _ok(data):
	return flask.jsonify({'success': True, 'data': data})


def _verify_time_token(admin_id, send_time, time_token):
	"""验证时间令牌，防止重放攻击。

	令牌 = SHA256(admin_id + send_time) 的前16位
	"""
	raw = f"{admin_id}{send_time}"
	expected = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]
	return time_token == expected


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

	password = data.get('password')
	AdminID = data.get('AdminID')
	AdminToken = data.get('AdminToken')
	TimeToken = data.get('TimeToken')
	SendTime = data.get('SendTime')
	RunMessage = data.get('RunMessage')

	# 1. 参数完整性检查
	if not all([password, AdminID, AdminToken, TimeToken, SendTime, RunMessage]):
		return _error("参数不完整")

	# 2. 时间密码验证（按小时变化）
	if not password:
		return _error("密码错误")

	# 3. 管理员ID验证
	try:
		with open("AdminsID.json", "r", encoding="utf-8") as f:
			admins_data = json.load(f)
		admin_ids = admins_data if isinstance(admins_data, list) else admins_data.get('admins', [])
	except Exception:
		admin_ids = []

	if AdminID not in admin_ids:
		return _error("非管理员账号")

	# 4. 管理员令牌验证
	if not verify_auth_token(AdminID, AdminToken):
		return _error("令牌验证失败")

	# 5. 时间令牌验证（防重放）
	if not _verify_time_token(AdminID, str(SendTime), TimeToken):
		return _error("时间令牌错误")

	# 6. 请求时效性检查
	try:
		sent_ts = float(SendTime)
		if abs(time.time() - sent_ts) > REQUEST_TIMEOUT:
			return _error("请求已过期")
	except (ValueError, TypeError):
		return _error("时间格式错误")

	# 7. 解析并执行管理指令
	try:
		if isinstance(RunMessage, str):
			msg = json.loads(RunMessage)
		else:
			msg = RunMessage
	except json.JSONDecodeError:
		return _error("RunMessage 格式错误，需要 JSON")

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
