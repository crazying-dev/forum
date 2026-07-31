"""认证相关 API 路由。"""
from flask import Blueprint, request, jsonify, redirect, Response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from api import database as db
from api import config
from Email import send_email
from main.main import app, base, generate_verify_email_body, strip_easter_egg, UserWrapper
import re
import random
import time
from app.middleware import rate_limit

auth_bp = Blueprint('auth', __name__)

@app.route('/robots.txt')
def robots():
    txt = """User-agent: *
Allow: /posts/*
Allow: /users/*
Disallow: /api/*"""

    return Response(txt, mimetype="text/plain")


@auth_bp.route('/api/send-register-code', methods=['POST'])
def api_send_register_code():
	"""发送6位验证码到邮箱用于注册（无需登录）。"""
	if rate_limit('register_code', 3, 300):
		return jsonify({'success': False, 'message': '请求过于频繁，请5分钟后再试'}), 429
	data = request.get_json() or {}
	email = (data.get('email') or '').strip().lower()

	if not email or '@' not in email:
		return jsonify({'success': False, 'message': '请输入有效的邮箱'})

	# 检查邮箱是否已被注册
	existing_user = db.get_user_by_email(email)
	if existing_user:
		return jsonify({'success': False, 'message': '该邮箱已被注册'})

	code = str(random.randint(100000, 999999))
	result = db.create_verify_code(email, code, 'register')
	if not result.get('success'):
		return jsonify({'success': False, 'message': '生成验证码失败'})

	subject = '【妖精论坛】注册验证码'
	body = f"""感谢您注册妖精论坛！

您的注册验证码为：{code}

验证码有效期5分钟，请勿泄露给他人。
如非本人操作，请忽略此邮件。

© 2026 妖精论坛 - 粉丝公益创作"""
	sent = send_email(subject, body, receiver_list=[email])
	if sent:
		return jsonify({'success': True, 'message': '验证码已发送至邮箱'})
	else:
		return jsonify({'success': False, 'message': '邮件服务暂不可用，请稍后重试或联系管理员'})


@auth_bp.route('/api/register', methods=['POST'])
def api_register():
	if rate_limit('register', 5, 300):
		return jsonify({'success': False, 'message': '注册过于频繁，请5分钟后再试'}), 429
	data = request.get_json() or {}
	name = (data.get('name') or '').strip()
	email = (data.get('email') or '').strip().lower()
	password = data.get('password') or ''

	name_for_check = strip_easter_egg(name)
	if len(name_for_check) < 2 or len(name_for_check) > 20:
		return jsonify({'success': False, 'message': '用户名需要2-20个字符（不含彩蛋）'})
	if not email or '@' not in email:
		return jsonify({'success': False, 'message': '请输入有效的邮箱'})
	if len(password) < 8:
		return jsonify({'success': False, 'message': '密码至少8位'})
	if not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
		return jsonify({'success': False, 'message': '密码需包含字母和数字'})

	# 注册验证码校验
	code = (data.get('code') or '').strip()
	if not code or not code.isdigit() or len(code) != 6:
		return jsonify({'success': False, 'message': '请输入6位数字验证码'})
	code_info = db.get_verify_code(email, code, 'register')
	if not code_info:
		db.increment_verify_code_attempts(email, 'register')
		return jsonify({'success': False, 'message': '验证码无效或已过期'})

	hashed = generate_password_hash(password)
	result = db.new_user(name, email, hashed)

	if not result.get('success'):
		return jsonify({'success': False, 'message': result.get('message', '注册失败')})

	# 验证码校验通过，标记已使用
	try:
		db.mark_verify_code_used(email, code, 'register')
		db.execute_query(
			"DELETE FROM verify_codes WHERE email = %s AND purpose = %s AND (expires_at < CURRENT_TIMESTAMP OR used = 1)",
			(email, 'register')
		)
	except Exception:
		pass

	user_id = result['id']
	user = db.get_user_by_id(user_id)
	if user:
		login_user(UserWrapper(user), remember=True)
	return jsonify({'success': True, 'id': user_id})


@auth_bp.route('/api/login', methods=['POST'])
def api_login():
	if rate_limit('login', 10, 300):
		return jsonify({'success': False, 'message': '登录尝试过于频繁，请5分钟后再试'}), 429
	data = request.get_json() or {}
	name_or_email = (data.get('name') or '').strip()
	password = data.get('password') or ''
	remember = data.get('remember', True)

	if not name_or_email or not password:
		return jsonify({'success': False, 'message': '请输入账号和密码'})

	user = None
	if '@' in name_or_email and '.' in name_or_email:
		user = db.get_user_by_email(name_or_email.lower())
	else:
		# 新格式：|[TIME] 直接匹配（无需替换）
		user = db.get_user_by_name(name_or_email)
		if not user:
			# 向后兼容：DB 中存的是旧 HTML 格式 "<p class=\"TimeWithUserNameAPI\"></p>"
			legacy_name = name_or_email.replace("[TIME]", '<p class="TimeWithUserNameAPI"></p>')
			user = db.get_user_by_name(legacy_name)

	if not user:
		return jsonify({'success': False, 'message': '账号或密码错误'})

	if not check_password_hash(user['password'], password):
		return jsonify({'success': False, 'message': '账号或密码错误'})

	if user.get('is_banned') == 1:
		return jsonify({'success': False, 'message': '该账号已被封禁'})

	db.update_user_last_login(user['id'])
	login_user(UserWrapper(user), remember=remember)

	# 发送登录提醒邮件（异步，不阻塞登录）
	user_email = user.get('email')
	if user_email:
		try:
			now_str = time.strftime('%Y-%m-%d %H:%M:%S')
			send_email(
				'【妖精论坛】登录提醒',
				f'尊敬的 {user["name"]}，您好！\n\n'
				f'您的账号已于 {now_str} 登录妖精论坛。\n'
				f'如非本人操作，请立即修改密码。\n\n'
				f'© 2026 妖精论坛 - 粉丝公益创作',
				receiver_list=[user_email]
			)
		except Exception:
			pass  # 邮件发送失败不影响登录流程

	return jsonify({'success': True, 'id': user['id']})


@auth_bp.route('/api/logout', methods=['POST', 'GET'])
def api_logout():
	logout_user()
	return jsonify({'success': True})


@auth_bp.route('/api/send-verify-email', methods=['POST'])
@login_required
def api_send_verify_email():
	if rate_limit('verify_email', 3, 300):
		return jsonify({'success': False, 'message': '请求过于频繁，请5分钟后再试'}), 429
	user = db.get_user_by_id(current_user['id'])
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})

	token_result = db.create_verify_token(user['id'], 'email_verify')
	if not token_result.get('success'):
		return jsonify({'success': False, 'message': '生成验证链接失败'})

	token = token_result['token']
	subject = '【妖精论坛】邮箱验证'
	body = generate_verify_email_body(user['name'], token, 'email_verify')
	
	sent = send_email(subject, body, receiver_list=[user['email']])
	if sent:
		return jsonify({'success': True, 'message': '验证邮件已发送，请查收邮箱'})
	else:
		return jsonify({'success': False, 'message': '邮件服务暂不可用，请稍后重试或联系管理员'})


@auth_bp.route('/api/verify-email', methods=['POST'])
def api_verify_email():
	data = request.get_json() or {}
	token = data.get('token') or ''

	if not token:
		return jsonify({'success': False, 'message': '验证链接无效'})

	token_info = db.get_verify_token(token, 'email_verify')
	if not token_info:
		return jsonify({'success': False, 'message': '验证链接已过期或无效'})

	db.update_user_email_verified(token_info['user_id'])
	db.delete_verify_token(token)
	
	return jsonify({'success': True, 'message': '邮箱验证成功'})


@auth_bp.route('/api/send-reset-password', methods=['POST'])
def api_send_reset_password():
	if rate_limit('reset_pwd', 3, 300):
		return jsonify({'success': False, 'message': '请求过于频繁，请5分钟后再试'}), 429
	data = request.get_json() or {}
	email = (data.get('email') or '').strip().lower()

	if not email or '@' not in email:
		return jsonify({'success': False, 'message': '请输入有效的邮箱'})

	user = db.get_user_by_email(email)
	if not user:
		# 防止邮箱枚举：无论邮箱是否存在都返回相同信息
		return jsonify({'success': True, 'message': '如果该邮箱已注册，重置链接已发送至邮箱'})

	token_result = db.create_verify_token(user['id'], 'password_reset')
	if not token_result.get('success'):
		return jsonify({'success': False, 'message': '生成重置链接失败'})

	token = token_result['token']
	subject = '【妖精论坛】重置密码'
	body = generate_verify_email_body(user['name'], token, 'password_reset')
	
	sent = send_email(subject, body, receiver_list=[email])
	if sent:
		return jsonify({'success': True, 'message': '如果该邮箱已注册，重置链接已发送至邮箱'})
	else:
		return jsonify({'success': False, 'message': '邮件服务暂不可用，请稍后重试或联系管理员'})


@auth_bp.route('/api/reset-password', methods=['POST'])
def api_reset_password():
	data = request.get_json() or {}
	token = data.get('token') or ''
	password = data.get('password') or ''

	if not token:
		return jsonify({'success': False, 'message': '重置链接无效'})
	if len(password) < 8:
		return jsonify({'success': False, 'message': '密码至少8位'})
	if not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
		return jsonify({'success': False, 'message': '密码需包含字母和数字'})

	token_info = db.get_verify_token(token, 'password_reset')
	if not token_info:
		return jsonify({'success': False, 'message': '重置链接已过期或无效'})

	hashed = generate_password_hash(password)
	db.execute_query(
		"UPDATE users SET password = %s WHERE id = %s",
		(hashed, token_info['user_id'])
	)
	db.delete_verify_token(token)
	
	return jsonify({'success': True, 'message': '密码重置成功'})


@auth_bp.route('/api/send-verify-code', methods=['POST'])
@login_required
def api_send_verify_code():
	"""发送6位验证码到当前登录用户的邮箱（用于邮箱验证）。"""
	if rate_limit('verify_code', 3, 300):
		return jsonify({'success': False, 'message': '请求过于频繁，请5分钟后再试'}), 429
	user = db.get_user_by_id(current_user['id'])
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})
	if user.get('email_verified'):
		return jsonify({'success': False, 'message': '邮箱已验证，无需重复验证'})

	code = str(random.randint(100000, 999999))
	result = db.create_verify_code(user['email'], code, 'email_verify')
	if not result.get('success'):
		return jsonify({'success': False, 'message': '生成验证码失败'})

	subject = '【妖精论坛】邮箱验证码'
	body = f"""尊敬的 {user['name']}，您好！

您的邮箱验证码为：{code}

验证码有效期5分钟，请勿泄露给他人。
如非本人操作，请忽略此邮件。

© 2026 妖精论坛 - 粉丝公益创作"""
	sent = send_email(subject, body, receiver_list=[user['email']])
	if sent:
		return jsonify({'success': True, 'message': '验证码已发送至邮箱'})
	else:
		return jsonify({'success': False, 'message': '邮件服务暂不可用，请稍后重试或联系管理员'})


@auth_bp.route('/api/verify-code-email', methods=['POST'])
@login_required
def api_verify_code_email():
	"""使用6位验证码验证邮箱。"""
	if rate_limit('verify_code', 5, 300):
		return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'}), 429
	user = db.get_user_by_id(current_user['id'])
	if not user:
		return jsonify({'success': False, 'message': '用户不存在'})

	data = request.get_json() or {}
	code = (data.get('code') or '').strip()

	if not code or not code.isdigit() or len(code) != 6:
		return jsonify({'success': False, 'message': '请输入6位数字验证码'})

	code_info = db.get_verify_code(user['email'], code, 'email_verify')
	if not code_info:
		db.increment_verify_code_attempts(user['email'], 'email_verify')
		return jsonify({'success': False, 'message': '验证码无效或已过期'})

	db.update_user_email_verified(current_user['id'])
	db.mark_verify_code_used(user['email'], code, 'email_verify')

	# 清理该邮箱此用途的过期验证码
	try:
		db.execute_query(
			"DELETE FROM verify_codes WHERE email = %s AND purpose = %s AND (expires_at < CURRENT_TIMESTAMP OR used = 1)",
			(user['email'], 'email_verify')
		)
	except Exception:
		pass

	return jsonify({'success': True, 'message': '邮箱验证成功'})


@auth_bp.route('/api/send-code-reset-password', methods=['POST'])
def api_send_code_reset_password():
	"""发送6位验证码到用户邮箱用于重置密码。"""
	if rate_limit('reset_pwd_code', 3, 300):
		return jsonify({'success': False, 'message': '请求过于频繁，请5分钟后再试'}), 429
	data = request.get_json() or {}
	email = (data.get('email') or '').strip().lower()

	if not email or '@' not in email:
		return jsonify({'success': False, 'message': '请输入有效的邮箱'})

	user = db.get_user_by_email(email)
	if not user:
		# 防止邮箱枚举
		return jsonify({'success': True, 'message': '如果该邮箱已注册，验证码已发送至邮箱'})

	code = str(random.randint(100000, 999999))
	result = db.create_verify_code(email, code, 'password_reset')
	if not result.get('success'):
		return jsonify({'success': False, 'message': '生成验证码失败'})

	subject = '【妖精论坛】重置密码验证码'
	body = f"""尊敬的 {user['name']}，您好！

您正在请求重置密码，验证码为：{code}

验证码有效期5分钟，请勿泄露给他人。
如非本人操作，请忽略此邮件。

© 2026 妖精论坛 - 粉丝公益创作"""
	sent = send_email(subject, body, receiver_list=[email])
	if sent:
		return jsonify({'success': True, 'message': '如果该邮箱已注册，验证码已发送至邮箱'})
	else:
		return jsonify({'success': False, 'message': '邮件服务暂不可用，请稍后重试或联系管理员'})


@auth_bp.route('/api/reset-password-by-code', methods=['POST'])
def api_reset_password_by_code():
	"""使用6位验证码重置密码。"""
	if rate_limit('reset_pwd_code', 5, 300):
		return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'}), 429
	data = request.get_json() or {}
	email = (data.get('email') or '').strip().lower()
	code = (data.get('code') or '').strip()
	password = data.get('password') or ''

	if not email or '@' not in email:
		return jsonify({'success': False, 'message': '请输入有效的邮箱'})
	if not code or not code.isdigit() or len(code) != 6:
		return jsonify({'success': False, 'message': '请输入6位数字验证码'})
	if len(password) < 8:
		return jsonify({'success': False, 'message': '密码至少8位'})
	if not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
		return jsonify({'success': False, 'message': '密码需包含字母和数字'})

	user = db.get_user_by_email(email)
	if not user:
		return jsonify({'success': False, 'message': '该邮箱未注册'})

	code_info = db.get_verify_code(email, code, 'password_reset')
	if not code_info:
		db.increment_verify_code_attempts(email, 'password_reset')
		return jsonify({'success': False, 'message': '验证码无效或已过期'})

	hashed = generate_password_hash(password)
	db.execute_query(
		"UPDATE users SET password = %s WHERE id = %s",
		(hashed, user['id'])
	)
	db.mark_verify_code_used(email, code, 'password_reset')

	# 清理该邮箱此用途的过期验证码
	try:
		db.execute_query(
			"DELETE FROM verify_codes WHERE email = %s AND purpose = %s AND (expires_at < CURRENT_TIMESTAMP OR used = 1)",
			(email, 'password_reset')
		)
	except Exception:
		pass

	return jsonify({'success': True, 'message': '密码重置成功'})
