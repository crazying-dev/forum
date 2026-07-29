# 验证数据访问
"""邮箱验证、验证码相关数据库操作。"""

from app.数据 import get_conn, execute_query, execute_insert


def create_verify_token(user_id, token_type, expires_minutes=30):
	"""创建验证token。

    Args:
        user_id (str): 用户ID
        token_type (str): token类型 ('email_verify', 'password_reset')
        expires_minutes (int): 过期时间（分钟）

    Returns:
        dict: {"success": True, "token": token}
    """
	import uuid
	import time
	token = str(uuid.uuid4())
	expires_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + expires_minutes * 60))
	
	try:
		execute_insert(
			"INSERT INTO verify_tokens (user_id, token, token_type, expires_at) VALUES (%s, %s, %s, %s)",
			(user_id, token, token_type, expires_at)
		)
		return {"success": True, "token": token}
	except Exception as e:
		print(f"[DB ERROR] create_verify_token: {e}")
		return {"success": False, "error": "操作失败"}


def get_verify_token(token, token_type):
	"""获取验证token信息。

    Args:
        token (str): token值
        token_type (str): token类型

    Returns:
        dict: token信息 {"user_id", "token", "token_type", "expires_at"}
        None: token不存在或已过期
    """
	result = execute_query(
		"SELECT user_id, token, token_type, expires_at FROM verify_tokens WHERE token = %s AND token_type = %s AND expires_at > CURRENT_TIMESTAMP",
		(token, token_type),
		fetch=True
	)
	if result:
		return {
			"user_id": result[0],
			"token": result[1],
			"token_type": result[2],
			"expires_at": str(result[3]) if result[3] else None,
		}
	return None


def delete_verify_token(token):
	"""删除验证token。

    Args:
        token (str): token值
    """
	execute_query(
		"DELETE FROM verify_tokens WHERE token = %s",
		(token,)
	)


def create_verify_code(email, code, purpose, expires_minutes=5):
	"""创建验证码。

	Args:
		email (str): 邮箱地址
		code (str): 验证码（如 6 位数字）
		purpose (str): 用途 ('register', 'login', 'email_verify', 'password_reset')
		expires_minutes (int): 过期时间（分钟）

	Returns:
		dict: {"success": True}
	"""
	import time
	expires_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + expires_minutes * 60))

	try:
		execute_insert(
			"INSERT INTO verify_codes (email, code, purpose, expires_at) VALUES (%s, %s, %s, %s)",
			(email, code, purpose, expires_at)
		)
		return {"success": True}
	except Exception as e:
		print(f"[DB ERROR] create_verify_code: {e}")
		return {"success": False, "error": "创建验证码失败"}


def get_verify_code(email, code, purpose):
	"""获取并验证验证码。

	检查验证码是否存在、未使用、未过期。

	Args:
		email (str): 邮箱地址
		code (str): 验证码
		purpose (str): 用途

	Returns:
		dict: 验证码信息 {"email", "code", "purpose", "expires_at"}
		None: 验证码不存在、已使用或已过期
	"""
	result = execute_query(
		"SELECT email, code, purpose, expires_at FROM verify_codes "
		"WHERE email = %s AND code = %s AND purpose = %s AND used = 0 AND expires_at > CURRENT_TIMESTAMP "
		"ORDER BY created_at DESC LIMIT 1",
		(email, code, purpose),
		fetch=True
	)
	if result:
		return {
			"email": result[0],
			"code": result[1],
			"purpose": result[2],
			"expires_at": str(result[3]) if result[3] else None,
		}
	return None


def mark_verify_code_used(email, code, purpose):
	"""将验证码标记为已使用。

	Args:
		email (str): 邮箱地址
		code (str): 验证码
		purpose (str): 用途
	"""
	execute_query(
		"UPDATE verify_codes SET used = 1 WHERE email = %s AND code = %s AND purpose = %s",
		(email, code, purpose)
	)


def increment_verify_code_attempts(email, purpose):
	"""增加验证码的尝试次数，用于防爆破。

	Args:
		email (str): 邮箱地址
		purpose (str): 用途
	"""
	execute_query(
		"UPDATE verify_codes SET attempts = attempts + 1 "
		"WHERE email = %s AND purpose = %s AND used = 0 AND expires_at > CURRENT_TIMESTAMP",
		(email, purpose)
	)
