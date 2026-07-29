# 用户数据访问
"""用户相关数据库操作：注册、查询、资料更新等。"""

import random
import psycopg2
from app.数据 import get_conn, execute_query, execute_insert, safe_html, POST_ID_PREFIX, DEFAULT_AVATARS, _gen_id
from api import config


def new_user(name, email, password):
	"""注册新用户。

    Args:
        name (str): 用户名
        email (str): 邮箱
        password (str): 密码

    Returns:
        dict: {"success": True, "id": 用户ID, "avatar": 头像路径}
              或 {"success": False, "error": 错误类型, "message": 错误信息}
    """
	user_id = _gen_id(config.USER_ID_PREFIX)
	avatar = random.choice(DEFAULT_AVATARS)
	try:
		execute_insert(
			"INSERT INTO users (id, name, avatar, email, password, vip) VALUES (%s, %s, %s, %s, %s, %s)",
			(user_id, name, avatar, email, password, config.vip)
		)
		return {"success": True, "id": user_id, "avatar": avatar}
	except psycopg2.IntegrityError as e:
		msg = str(e)
		if 'email' in msg.lower():
			return {"success": False, "error": "email_exists", "message": "邮箱已被注册"}
		elif 'name' in msg.lower():
			return {"success": False, "error": "name_exists", "message": "用户名已存在"}
		else:
			return {"success": False, "error": "integrity_error", "message": str(e)}


def get_user_by_id(user_id):
	"""根据用户ID获取用户信息。

    Args:
        user_id (str): 用户ID

    Returns:
        dict: 用户信息字典，不含密码
              {"id", "name", "avatar", "email", "gender", "age", "intro", "vip", "email_verified", "created_at", "last_login"}
        None: 用户不存在时返回
    """
	result = execute_query(
		"SELECT id, name, avatar, email, gender, age, intro, vip, email_verified, is_banned, created_at, last_login FROM users WHERE id = %s",
		(user_id,),
		fetch=True
	)
	if result:
		return {
			"id": result[0],
			"name": result[1],
			"avatar": result[2],
			"email": result[3],
			"gender": result[4],
			"age": result[5],
			"intro": result[6],
			"vip": result[7],
			"email_verified": result[8],
			"is_banned": result[9],
			"created_at": str(result[10]) if result[10] else None,
			"last_login": str(result[11]) if result[11] else None,
		}
	return None


def get_user_by_name(name):
	"""根据用户名获取用户信息（包含密码，用于登录验证）。

    Args:
        name (str): 用户名

    Returns:
        dict: 用户信息字典，包含密码
              {"id", "name", "avatar", "email", "password", "gender", "age", "intro", "vip", "email_verified", "created_at", "last_login"}
        None: 用户不存在时返回
    """
	result = execute_query(
		"SELECT id, name, avatar, email, password, gender, age, intro, vip, email_verified, is_banned, created_at, last_login FROM users WHERE name = %s",
		(name,),
		fetch=True
	)
	if result:
		return {
			"id": result[0],
			"name": result[1],
			"avatar": result[2],
			"email": result[3],
			"password": result[4],
			"gender": result[5],
			"age": result[6],
			"intro": result[7],
			"vip": result[8],
			"email_verified": result[9],
			"is_banned": result[10],
			"created_at": str(result[11]) if result[11] else None,
			"last_login": str(result[12]) if result[12] else None,
		}
	return None


def get_user_by_email(email):
	"""根据邮箱获取用户信息（包含密码，用于登录验证）。

    Args:
        email (str): 邮箱地址

    Returns:
        dict: 用户信息字典，包含密码
              {"id", "name", "avatar", "email", "password", "gender", "age", "intro", "vip", "email_verified", "created_at"}
        None: 用户不存在时返回
    """
	result = execute_query(
		"SELECT id, name, avatar, email, password, gender, age, intro, vip, email_verified, is_banned, created_at FROM users WHERE email = %s",
		(email,),
		fetch=True
	)
	if result:
		return {
			"id": result[0],
			"name": result[1],
			"avatar": result[2],
			"email": result[3],
			"password": result[4],
			"gender": result[5],
			"age": result[6],
			"intro": result[7],
			"vip": result[8],
			"email_verified": result[9],
			"is_banned": result[10],
			"created_at": str(result[11]) if result[11] else None,
		}
	return None


def update_user_last_login(user_id):
	"""更新用户的最后登录时间。

    Args:
        user_id (str): 用户ID
    """
	execute_query(
		"UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
		(user_id,)
	)


def update_user_profile(user_id, **kwargs):
	"""更新用户资料。

    Args:
        user_id (str): 用户ID
        **kwargs: 可选参数，支持 Name, avatar, gender, age, intro, password

    Returns:
        bool: 更新是否成功
    """
	allowed_fields = ['Name', 'avatar', 'gender', 'age', 'intro', 'password']
	updates = []
	params = []
	for key, value in kwargs.items():
		if key in allowed_fields:
			updates.append(f"{key} = %s")
			params.append(value)
	if not updates:
		return False
	params.append(user_id)
	sql = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
	affected = execute_query(sql, tuple(params))
	return affected > 0


def update_user_email_verified(user_id):
	"""更新用户邮箱验证状态为已验证。

    Args:
        user_id (str): 用户ID
    """
	execute_query(
		"UPDATE users SET email_verified = 1 WHERE id = %s",
		(user_id,)
	)


def get_user_stats(user_id):
	"""获取用户统计信息。

    Args:
        user_id (str): 用户ID

    Returns:
        dict: {"post_count", "total_likes", "total_views"}
    """
	result = execute_query(
		"""
        SELECT COUNT(*), COALESCE(SUM(likes), 0), COALESCE(SUM(views), 0)
        FROM posts
        WHERE user_id = %s AND status = 1
        """,
		(user_id,),
		fetch=True
	)
	if result:
		return {
			"post_count": result[0] or 0,
			"total_likes": result[1] or 0,
			"total_views": result[2] or 0,
		}
	return {"post_count": 0, "total_likes": 0, "total_views": 0}


def search_users(keyword, page=1, page_size=20):
	"""搜索用户（按名称匹配）。

    Returns:
        tuple: (users: list, total: int)
    """
	keyword = keyword.strip()
	if not keyword or len(keyword) < 2:
		return [], 0
	offset = (page - 1) * page_size
	like = f'%{keyword}%'

	count_row = execute_query(
		"SELECT COUNT(*) FROM users WHERE is_banned = 0 AND name ILIKE %s",
		(like,), fetch=True
	)
	total = count_row[0] if count_row else 0

	results = execute_query(
		"""
        SELECT id, name, avatar, vip, prefix, is_banned, created_at
        FROM users
        WHERE is_banned = 0 AND name ILIKE %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
		(like, page_size, offset),
		fetch_all=True
	)
	users = []
	for r in results:
		users.append({
			"id": r[0],
			"name": r[1],
			"avatar": r[2],
			"vip": r[3],
			"prefix": r[4],
			"status": r[5],
			"created_at": str(r[6]) if r[6] else None,
		})
	return users, total
