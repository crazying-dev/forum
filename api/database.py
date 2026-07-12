"""妖精论坛数据库模块。

提供用户、帖子、评论的 CRUD 操作。
基于 PostgreSQL 数据库，使用 psycopg2 驱动。

环境变量:
    DATABASE_URL: PostgreSQL 连接字符串

对外开放的函数:
    用户相关:
        new_user(name, email, password)           - 注册新用户
        get_user_by_id(user_id)                   - 按ID获取用户
        get_user_by_name(name)                     - 按用户名获取用户
        get_user_by_email(email)                   - 按邮箱获取用户
        update_user_last_login(user_id)            - 更新最后登录时间
        update_user_profile(user_id, **kwargs)     - 更新用户资料

    帖子相关:
        Send_Post(user_id, title, content)        - 发布帖子
        get_post(post_id)                         - 获取帖子详情
        get_post_list(page, page_size, category)  - 分页获取帖子列表
        get_user_posts(user_id, page, page_size) - 获取用户帖子
        increment_post_views(post_id)             - 增加浏览量
        like_post(post_id)                         - 点赞帖子

    评论相关:
        add_comment(post_id, user_id, content)    - 添加评论
        get_post_comments(post_id, page)          - 获取帖子评论

    内部函数（不建议直接调用）:
        get_conn()     - 获取数据库连接
        db_connect()   - 创建新连接
        init_tables()  - 初始化表结构
        ensure_tables() - 懒加载创建表
"""

import os
import time
import random
import atexit
import dotenv
import psycopg2
import re
from psycopg2 import pool
from contextlib import contextmanager
from api import config

dotenv.load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') or os.getenv('POSTGRES_PRISMA_URL')

if not DATABASE_URL:
	print("[DB] 警告: 未设置 DATABASE_URL 环境变量，数据库功能将不可用")

POST_ID_PREFIX = 'PS'
_table_checked = False

DANGEROUS_TAGS = {'script', 'style', 'iframe', 'embed', 'object', 'applet', 'base', 'form', 'input', 'textarea',
                  'select', 'option', 'button'}


def safe_html(content):
	if not content:
		return ''
	content = content.replace('<script', '<p')
	content = content.replace('</script>', '</p>')
	content = re.sub(r'<(script|style|iframe|embed|object|applet|base|form|input|textarea|select|option|button)[^>]*>',
	                 '', content, flags=re.IGNORECASE)
	content = re.sub(r'</(script|style|iframe|embed|object|applet|base|form|input|textarea|select|option|button)>', '',
	                 content, flags=re.IGNORECASE)
	content = re.sub(r'on\w+\s*=\s*["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
	content = re.sub(r'on\w+\s*=\s*[^>\s]+', '', content, flags=re.IGNORECASE)
	return content


DEFAULT_AVATARS = [
	f'{config.Image_father_URL}/avatars/LaoJun.png',
	f'{config.Image_father_URL}/avatars/LuoXiaoHei1.png',
	f'{config.Image_father_URL}/avatars/LuoXiaoHei2.png',
	f'{config.Image_father_URL}/avatars/MuXiZi.png',
]

_connection_pool = None
_POOL_ENABLED = config.POOL_ENABLED
NowTime = lambda: time.time() * 10000


def init_pool():
	"""初始化连接池（仅在非 Serverless 环境启用）。
    
    如果 _POOL_ENABLED 为 False，则不创建连接池。
    """
	global _connection_pool
	if not _POOL_ENABLED:
		return
	if _connection_pool is None:
		try:
			conn_params = _build_conn_params()
			_connection_pool = psycopg2.pool.SimpleConnectionPool(
				minconn=1,
				maxconn=10,
				dsn=DATABASE_URL,
				**conn_params
			)
		except Exception as e:
			print(f"[DB] 连接池初始化失败: {e}")
			_connection_pool = None


init_pool()


def _build_conn_params():
	"""构建数据库连接参数（针对 Neon 数据库优化）。"""
	if not DATABASE_URL:
		return {}
	params = {
		'connect_timeout': 30,
		'keepalives': 1,
		'keepalives_idle': 30,
		'keepalives_interval': 10,
		'keepalives_count': 5,
	}
	if 'neon.tech' in DATABASE_URL or 'ep-' in DATABASE_URL:
		params['sslmode'] = 'require'
		params['gssencmode'] = 'disable'
	return params


@contextmanager
def get_conn():
	"""获取数据库连接的上下文管理器。
    
    每次请求新建连接，执行完立即关闭（Serverless 环境）。
    使用方式:
        with get_conn() as (conn, cursor):
            cursor.execute(...)
    """
	conn = None
	cursor = None
	last_err = None
	conn_params = _build_conn_params()
	max_retries = 3
	
	for attempt in range(1, max_retries + 1):
		try:
			if not DATABASE_URL:
				raise RuntimeError("DATABASE_URL 环境变量未设置")
			conn = psycopg2.connect(DATABASE_URL, **conn_params)
			cursor = conn.cursor()
			yield conn, cursor
			return
		except Exception as e:
			last_err = e
			if conn:
				try:
					conn.rollback()
				except Exception:
					pass
				try:
					conn.close()
				except Exception:
					pass
				conn = None
			if cursor:
				try:
					cursor.close()
				except Exception:
					pass
				cursor = None
			if attempt < max_retries and ('SSL' in str(e) or 'eof' in str(e).lower() or 'Connection' in str(e)):
				import time
				time.sleep(1)
				continue
			raise e
	raise last_err


def db_connect():
	"""创建新的数据库连接（需手动关闭）。
    
    Returns:
        tuple: (conn, cursor) 数据库连接和游标
    Note:
        使用后需手动调用 conn.close() 关闭连接
    """
	conn_params = _build_conn_params()
	conn = psycopg2.connect(DATABASE_URL, **conn_params)
	cursor = conn.cursor()
	return conn, cursor


def init_tables():
	"""初始化数据库表。

    如果表已存在则跳过（使用 IF NOT EXISTS）。
    """
	with get_conn() as (conn, cursor):
		cursor.execute(config.CREATE_USER_TABLE_SQL)
		cursor.execute(config.CREATE_POST_TABLE_SQL)
		cursor.execute(config.CREATE_COMMENT_TABLE_SQL)
		cursor.execute(config.CREATE_World_TABLE_SQL)
		cursor.execute(config.CREATE_POST_LIKES_TABLE_SQL)
		cursor.execute(config.CREATE_POST_FAVORITES_TABLE_SQL)
		cursor.execute(config.CREATE_USER_FOLLOWS_TABLE_SQL)
		cursor.execute(config.CREATE_POST_REPORTS_TABLE_SQL)
		try:
			cursor.execute("ALTER TABLE comments ADD COLUMN IF NOT EXISTS parent_id VARCHAR(64)")
		except:
			pass
		try:
			cursor.execute("ALTER TABLE World ADD COLUMN IF NOT EXISTS parent_id INTEGER")
		except:
			pass
		for sql in config.CREATE_INDEX_SQLS:
			cursor.execute(sql)
		conn.commit()


def ensure_tables():
	"""懒加载：仅在需要时创建表。
    
    首次调用时检查并创建表，之后直接返回。
    如果表创建失败则打印错误。
    """
	global _table_checked
	if _table_checked:
		return
	try:
		init_tables()
		_table_checked = True
	except Exception as e:
		print(f"[DB] 初始化表失败: {e}")


def _gen_id(prefix):
	"""生成带前缀的唯一ID。
    
    Args:
        prefix (str): ID前缀，如 'YJ'(用户)、'PS'(帖子)、'CM'(评论)
    
    Returns:
        str: 形如 'YJ1234567890' 的唯一ID
    """
	return prefix + str(int(time.time() * 10000000000))


def execute_query(query, params=None, fetch=False, fetch_all=False):
	"""执行SQL查询。

    Args:
        query (str): SQL语句
        params (tuple): SQL参数
        fetch (bool): 是否获取单行结果
        fetch_all (bool): 是否获取所有结果

    Returns:
        根据参数返回 rowcount、fetchone 或 fetchall 结果

    Raises:
        UndefinedTable: 表不存在时会自动创建后重试
    """
	try:
		with get_conn() as (conn, cursor):
			cursor.execute(query, params or ())
			if fetch:
				result = cursor.fetchone()
			elif fetch_all:
				result = cursor.fetchall()
			else:
				conn.commit()
				result = cursor.rowcount
			return result
	except psycopg2.errors.UndefinedTable:
		ensure_tables()
		with get_conn() as (conn, cursor):
			cursor.execute(query, params or ())
			if fetch:
				result = cursor.fetchone()
			elif fetch_all:
				result = cursor.fetchall()
			else:
				conn.commit()
				result = cursor.rowcount
			return result


def execute_insert(query, params=None):
	"""执行SQL插入操作。

    Args:
        query (str): SQL插入语句
        params (tuple): SQL参数

    Returns:
        int: 受影响的行数

    Raises:
        UndefinedTable: 表不存在时会自动创建后重试
    """
	try:
		with get_conn() as (conn, cursor):
			cursor.execute(query, params or ())
			conn.commit()
			return cursor.rowcount
	except psycopg2.errors.UndefinedTable:
		ensure_tables()
		with get_conn() as (conn, cursor):
			cursor.execute(query, params or ())
			conn.commit()
			return cursor.rowcount


def GitWroldMessageWithAll():
	results = execute_query(
		"""
		SELECT id, sender_id, sender_name, content, parent_id, created_at
		FROM World
		ORDER BY created_at DESC
		LIMIT 100
		""",
		fetch_all=True
	)
	messages = []
	for message in results:
		messages.append({
			"id": message[0],
			"sender_id": message[1],
			"sender_name": message[2],
			"content": message[3],
			"parent_id": message[4],
			"created_at": message[5].isoformat() if message[5] else None
		})
	return messages


def SendWorldMessage(sender_id, sender_name, content, parent_id=None):
	"""发送世界频道消息，限制每用户每2秒只能发一条。支持引用回复。"""
	last = execute_query(
		"""
		SELECT created_at FROM World
		WHERE sender_id = %s
		ORDER BY created_at DESC
		LIMIT 1
		""",
		(sender_id,),
		fetch=True
	)
	if last and last[0]:
		from datetime import datetime
		now = datetime.now(last[0].tzinfo) if last[0].tzinfo else datetime.now()
		if (now - last[0]).total_seconds() < 2:
			return {"success": False, "message": "发言太快，请稍后再试"}
	execute_query("""
		DELETE FROM World
		WHERE created_at < NOW() - INTERVAL '5 minutes';
	""")
	execute_insert(
		"""
		INSERT INTO World (sender_id, sender_name, content, parent_id)
		VALUES (%s, %s, %s, %s)
		""",
		(sender_id, sender_name, content, parent_id)
	)
	return {"success": True, "message": "发送成功"}


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
              {"id", "name", "avatar", "email", "gender", "age", "intro", "vip", "created_at", "last_login"}
        None: 用户不存在时返回
    """
	result = execute_query(
		"SELECT id, name, avatar, email, gender, age, intro, vip, created_at, last_login FROM users WHERE id = %s",
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
			"created_at": str(result[8]) if result[8] else None,
			"last_login": str(result[9]) if result[9] else None,
		}
	return None


def get_user_by_name(name):
	"""根据用户名获取用户信息（包含密码，用于登录验证）。

    Args:
        name (str): 用户名

    Returns:
        dict: 用户信息字典，包含密码
              {"id", "name", "avatar", "email", "password", "gender", "age", "intro", "vip", "created_at", "last_login"}
        None: 用户不存在时返回
    """
	result = execute_query(
		"SELECT id, name, avatar, email, password, gender, age, intro, vip, created_at, last_login FROM users WHERE name = %s",
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
			"created_at": str(result[9]) if result[9] else None,
			"last_login": str(result[10]) if result[10] else None,
		}
	return None


def get_user_by_email(email):
	"""根据邮箱获取用户信息（包含密码，用于登录验证）。

    Args:
        email (str): 邮箱地址

    Returns:
        dict: 用户信息字典，包含密码
              {"id", "name", "avatar", "email", "password", "gender", "age", "intro", "vip", "created_at"}
        None: 用户不存在时返回
    """
	result = execute_query(
		"SELECT id, name, avatar, email, password, gender, age, intro, vip, created_at FROM users WHERE email = %s",
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
			"created_at": str(result[9]) if result[9] else None,
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


def Send_Post(user_id, title, content, category='general'):
	"""发布新帖子。

    Args:
        user_id (str): 发布者用户ID
        title (str): 帖子标题
        content (str): 帖子内容
        category (str): 分类，默认 'general'

    Returns:
        dict: {"success": True, "id": 帖子ID}
              或 {"success": False, "error": 错误信息}
    """
	post_id = _gen_id(POST_ID_PREFIX)
	content = safe_html(content)
	try:
		execute_insert(
			"INSERT INTO posts (id, user_id, title, content, category) VALUES (%s, %s, %s, %s, %s)",
			(post_id, user_id, title, content, category)
		)
		return {"success": True, "id": post_id}
	except Exception as e:
		return {"success": False, "error": str(e)}


def get_post(post_id):
	"""获取帖子详情（含作者信息）。

    Args:
        post_id (str): 帖子ID

    Returns:
        dict: 帖子详情字典
              {"id", "user_id", "title", "content", "category", "likes", "views", "status",
               "created_at", "updated_at", "user_name", "user_avatar"}
        None: 帖子不存在或已删除时返回
    """
	result = execute_query(
		"""
        SELECT p.id, p.user_id, p.title, p.content, p.category, p.likes, p.views, p.status, 
               p.created_at, p.updated_at, u.name, u.avatar
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = %s AND p.status = 1
        """,
		(post_id,),
		fetch=True
	)
	if result:
		return {
			"id": result[0],
			"user_id": result[1],
			"title": result[2],
			"content": result[3],
			"category": result[4],
			"likes": result[5],
			"views": result[6],
			"status": result[7],
			"created_at": str(result[8]) if result[8] else None,
			"updated_at": str(result[9]) if result[9] else None,
			"user_name": result[10],
			"user_avatar": result[11],
		}
	return None


def get_post_list(page=1, page_size=20, category=None):
	"""分页获取帖子列表。

    Args:
        page (int): 页码，从1开始
        page_size (int): 每页数量，默认20
        category (str): 分类筛选，为空则获取所有

    Returns:
        list: 帖子列表，每项包含
              {"id", "user_id", "title", "summary", "category", "likes", "views",
               "created_at", "user_name", "user_avatar"}
    """
	offset = (page - 1) * page_size
	if category:
		results = execute_query(
			"""
            SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views, 
                   p.created_at, u.name, u.avatar
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.status = 1 AND p.category = %s
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
            """,
			(category, page_size, offset),
			fetch_all=True
		)
	else:
		results = execute_query(
			"""
            SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views, 
                   p.created_at, u.name, u.avatar
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.status = 1
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
            """,
			(page_size, offset),
			fetch_all=True
		)
	posts = []
	for r in results:
		posts.append({
			"id": r[0],
			"user_id": r[1],
			"title": r[2],
			"summary": r[3] or '',
			"category": r[4],
			"likes": r[5],
			"views": r[6],
			"created_at": str(r[7]) if r[7] else None,
			"user_name": r[8],
			"user_avatar": r[9],
		})
	return posts


def get_random_posts(user_id=None):
	"""随机获取最多200条帖子，全部随机排序显示。

	Args:
	    user_id (str): 用户ID（保留兼容）

	Returns:
	    list: 帖子列表，最多200条，随机排序
	"""
	results = execute_query(
		"""
		SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views,
		       p.created_at, u.name, u.avatar
		FROM posts p
		JOIN users u ON p.user_id = u.id
		WHERE p.status = 1
		ORDER BY RANDOM()
		LIMIT 200
		""",
		fetch_all=True
	)
	import random as _rand
	posts = []
	for r in results:
		posts.append({
			"id": r[0],
			"user_id": r[1],
			"title": r[2],
			"summary": r[3] or '',
			"category": r[4],
			"likes": r[5],
			"views": r[6],
			"created_at": str(r[7]) if r[7] else None,
			"user_name": r[8],
			"user_avatar": r[9],
		})
	_rand.shuffle(posts)
	return posts


def get_user_posts(user_id, page=1, page_size=20):
	"""分页获取指定用户的帖子列表。

    Args:
        user_id (str): 用户ID
        page (int): 页码，从1开始
        page_size (int): 每页数量，默认20

    Returns:
        list: 帖子列表，每项包含
              {"id", "title", "summary", "category", "likes", "views", "created_at"}
    """
	offset = (page - 1) * page_size
	results = execute_query(
		"""
        SELECT id, title, LEFT(content, 200), category, likes, views, created_at
        FROM posts
        WHERE user_id = %s AND status = 1
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
		(user_id, page_size, offset),
		fetch_all=True
	)
	posts = []
	for r in results:
		posts.append({
			"id": r[0],
			"title": r[1],
			"summary": r[2] or '',
			"category": r[3],
			"likes": r[4],
			"views": r[5],
			"created_at": str(r[6]) if r[6] else None,
		})
	return posts


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


def get_all_users():
	"""获取所有用户信息（调试用）。

    Returns:
        list: 用户列表，每项包含 {"id", "name", "avatar", "email", "gender", "age", "intro", "vip", "created_at", "last_login"}
    """
	results = execute_query(
		"""
        SELECT id, name, avatar, email, gender, age, intro, vip, created_at, last_login
        FROM users
        ORDER BY created_at DESC
        """,
		fetch_all=True
	)
	users = []
	for r in results:
		users.append({
			"id": r[0],
			"name": r[1],
			"avatar": r[2],
			"email": r[3],
			"gender": r[4],
			"age": r[5],
			"intro": r[6],
			"vip": r[7],
			"created_at": str(r[8]) if r[8] else None,
			"last_login": str(r[9]) if r[9] else None,
		})
	return users


def increment_post_views(post_id):
	"""增加帖子的浏览量。

    Args:
        post_id (str): 帖子ID
    """
	execute_query(
		"UPDATE posts SET views = views + 1 WHERE id = %s",
		(post_id,)
	)


def like_post(post_id, user_id):
	"""切换帖子点赞状态（点赞/取消点赞），防止重复点赞。

    Args:
        post_id (str): 帖子ID
        user_id (str): 用户ID

    Returns:
        dict: {"success": True, "liked": bool, "likes": int}
    """
	existing = execute_query(
		"SELECT id FROM post_likes WHERE post_id = %s AND user_id = %s",
		(post_id, user_id),
		fetch=True
	)
	if existing:
		execute_query(
			"DELETE FROM post_likes WHERE post_id = %s AND user_id = %s",
			(post_id, user_id,)
		)
		execute_query(
			"UPDATE posts SET likes = GREATEST(likes - 1, 0) WHERE id = %s",
			(post_id,)
		)
		liked = False
	else:
		execute_insert(
			"INSERT INTO post_likes (post_id, user_id) VALUES (%s, %s)",
			(post_id, user_id)
		)
		execute_query(
			"UPDATE posts SET likes = likes + 1 WHERE id = %s",
			(post_id,)
		)
		liked = True
	row = execute_query(
		"SELECT likes FROM posts WHERE id = %s",
		(post_id,),
		fetch=True
	)
	return {"success": True, "liked": liked, "likes": row[0] if row else 0}


def has_liked_post(post_id, user_id):
	"""检查用户是否已点赞该帖子。

    Args:
        post_id (str): 帖子ID
        user_id (str): 用户ID

    Returns:
        bool: 是否已点赞
    """
	if not user_id:
		return False
	row = execute_query(
		"SELECT id FROM post_likes WHERE post_id = %s AND user_id = %s",
		(post_id, user_id),
		fetch=True
	)
	return row is not None


def toggle_favorite(post_id, user_id):
	"""切换帖子收藏状态（收藏/取消收藏）。

    Args:
        post_id (str): 帖子ID
        user_id (str): 用户ID

    Returns:
        dict: {"success": True, "favorited": bool}
    """
	existing = execute_query(
		"SELECT id FROM post_favorites WHERE post_id = %s AND user_id = %s",
		(post_id, user_id),
		fetch=True
	)
	if existing:
		execute_query(
			"DELETE FROM post_favorites WHERE post_id = %s AND user_id = %s",
			(post_id, user_id,)
		)
		return {"success": True, "favorited": False}
	else:
		execute_insert(
			"INSERT INTO post_favorites (post_id, user_id) VALUES (%s, %s)",
			(post_id, user_id)
		)
		return {"success": True, "favorited": True}


def has_favorited_post(post_id, user_id):
	"""检查用户是否已收藏该帖子。

    Args:
        post_id (str): 帖子ID
        user_id (str): 用户ID

    Returns:
        bool: 是否已收藏
    """
	if not user_id:
		return False
	row = execute_query(
		"SELECT id FROM post_favorites WHERE post_id = %s AND user_id = %s",
		(post_id, user_id),
		fetch=True
	)
	return row is not None


def get_user_favorites(user_id, page=1, page_size=20):
	"""获取用户收藏的帖子列表。

    Args:
        user_id (str): 用户ID
        page (int): 页码
        page_size (int): 每页数量

    Returns:
        list: 帖子列表
    """
	offset = (page - 1) * page_size
	results = execute_query(
		"""
		SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views,
		       p.created_at, u.name, u.avatar
		FROM post_favorites pf
		JOIN posts p ON pf.post_id = p.id
		JOIN users u ON p.user_id = u.id
		WHERE pf.user_id = %s AND p.status = 1
		ORDER BY pf.created_at DESC
		LIMIT %s OFFSET %s
		""",
		(user_id, page_size, offset),
		fetch_all=True
	)
	posts = []
	for r in results:
		posts.append({
			"id": r[0],
			"user_id": r[1],
			"title": r[2],
			"summary": r[3] or '',
			"category": r[4],
			"likes": r[5],
			"views": r[6],
			"created_at": str(r[7]) if r[7] else None,
			"user_name": r[8],
			"user_avatar": r[9],
		})
	return posts


def toggle_follow(follower_id, following_id):
	"""切换关注状态（关注/取消关注）。

    Args:
        follower_id (str): 关注者ID
        following_id (str): 被关注者ID

    Returns:
        dict: {"success": True, "following": bool}
    """
	if follower_id == following_id:
		return {"success": False, "message": "不能关注自己"}
	existing = execute_query(
		"SELECT id FROM user_follows WHERE follower_id = %s AND following_id = %s",
		(follower_id, following_id),
		fetch=True
	)
	if existing:
		execute_query(
			"DELETE FROM user_follows WHERE follower_id = %s AND following_id = %s",
			(follower_id, following_id)
		)
		return {"success": True, "following": False}
	else:
		execute_insert(
			"INSERT INTO user_follows (follower_id, following_id) VALUES (%s, %s)",
			(follower_id, following_id)
		)
		return {"success": True, "following": True}


def is_following(follower_id, following_id):
	"""检查是否已关注。

    Args:
        follower_id (str): 关注者ID
        following_id (str): 被关注者ID

    Returns:
        bool: 是否已关注
    """
	if not follower_id or not following_id:
		return False
	row = execute_query(
		"SELECT id FROM user_follows WHERE follower_id = %s AND following_id = %s",
		(follower_id, following_id),
		fetch=True
	)
	return row is not None


def get_follow_stats(user_id):
	"""获取用户关注/粉丝数。

    Args:
        user_id (str): 用户ID

    Returns:
        dict: {"following_count": int, "follower_count": int}
    """
	following = execute_query(
		"SELECT COUNT(*) FROM user_follows WHERE follower_id = %s",
		(user_id,),
		fetch=True
	)
	followers = execute_query(
		"SELECT COUNT(*) FROM user_follows WHERE following_id = %s",
		(user_id,),
		fetch=True
	)
	return {
		"following_count": following[0] if following else 0,
		"follower_count": followers[0] if followers else 0
	}


def report_post(post_id, reporter_id, reason, detail=''):
	"""举报帖子。

    Args:
        post_id (str): 帖子ID
        reporter_id (str): 举报者ID
        reason (str): 举报原因
        detail (str): 详细描述

    Returns:
        dict: {"success": True}
    """
	execute_insert(
		"INSERT INTO post_reports (post_id, reporter_id, reason, detail) VALUES (%s, %s, %s, %s)",
		(post_id, reporter_id, reason, detail)
	)
	return {"success": True}


def delete_post(post_id, user_id):
	"""删除帖子（仅允许帖子作者删除）。

    Args:
        post_id (str): 帖子ID
        user_id (str): 用户ID（用于验证权限）

    Returns:
        dict: {"success": True} 或 {"success": False, "message": 错误信息}
    """
	post = get_post(post_id)
	if not post:
		return {"success": False, "message": "帖子不存在"}
	if post.get("user_id") != user_id:
		return {"success": False, "message": "无权删除此帖子"}
	execute_query(
		"DELETE FROM posts WHERE id = %s",
		(post_id,)
	)
	return {"success": True}


def add_comment(post_id, user_id, content, parent_id=None):
	"""添加评论。

    Args:
        post_id (str): 帖子ID
        user_id (str): 评论者用户ID
        content (str): 评论内容
        parent_id (str): 父评论ID（可选，用于回复评论）

    Returns:
        dict: {"success": True, "id": 评论ID, "comment": 评论详情}
              或 {"success": False, "error": 错误信息}
    """
	comment_id = _gen_id('CM')
	try:
		execute_insert(
			"INSERT INTO comments (id, post_id, user_id, content, parent_id) VALUES (%s, %s, %s, %s, %s)",
			(comment_id, post_id, user_id, content, parent_id)
		)
		user_info = get_user_by_id(user_id)
		return {
			"success": True,
			"id": comment_id,
			"comment": {
				"id": comment_id,
				"user_id": user_id,
				"content": content,
				"parent_id": parent_id,
				"likes": 0,
				"created_at": None,
				"user_name": user_info.get("name", "匿名"),
				"user_avatar": user_info.get("avatar", ""),
			}
		}
	except Exception as e:
		return {"success": False, "error": str(e)}


def get_post_comments(post_id, page=1, page_size=50):
	"""分页获取帖子的评论列表。

    Args:
        post_id (str): 帖子ID
        page (int): 页码，从1开始
        page_size (int): 每页数量，默认50

    Returns:
        list: 评论列表，每项包含
              {"id", "user_id", "content", "parent_id", "likes", "created_at", "user_name", "user_avatar"}
    """
	offset = (page - 1) * page_size
	results = execute_query(
		"""
        SELECT c.id, c.user_id, c.content, c.parent_id, c.likes, c.created_at, u.name, u.avatar
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id = %s AND c.status = 1
        ORDER BY c.created_at DESC
        LIMIT %s OFFSET %s
        """,
		(post_id, page_size, offset),
		fetch_all=True
	)
	comments = []
	for r in results:
		comments.append({
			"id": r[0],
			"user_id": r[1],
			"content": r[2],
			"parent_id": r[3],
			"likes": r[4],
			"created_at": str(r[5]) if r[5] else None,
			"user_name": r[6],
			"user_avatar": r[7],
		})
	return comments


def delete_comment(comment_id, user_id):
	"""删除评论（仅允许评论作者删除）。

    Args:
        comment_id (str): 评论ID
        user_id (str): 用户ID（用于验证权限）

    Returns:
        dict: {"success": True, "post_id": 帖子ID} 或 {"success": False, "message": 错误信息}
    """
	comment = execute_query(
		"SELECT user_id, post_id FROM comments WHERE id = %s AND status = 1",
		(comment_id,),
		fetch=True
	)
	if not comment:
		return {"success": False, "message": "评论不存在"}
	if comment[0] != user_id:
		return {"success": False, "message": "无权删除此评论"}
	post_id = comment[1]
	execute_query(
		"UPDATE comments SET status = 0 WHERE id = %s",
		(comment_id,)
	)
	return {"success": True, "post_id": post_id}


def search_posts(keyword, page=1, page_size=20):
	"""搜索帖子（按标题和内容匹配）。

    Args:
        keyword (str): 搜索关键词
        page (int): 页码，从1开始
        page_size (int): 每页数量

    Returns:
        list: 帖子列表
    """
	if not keyword or not keyword.strip():
		return []
	offset = (page - 1) * page_size
	results = execute_query(
		"""
        SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views,
               p.created_at, u.name, u.avatar
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.status = 1 AND (p.title ILIKE %s OR p.content ILIKE %s)
        ORDER BY p.created_at DESC
        LIMIT %s OFFSET %s
        """,
		(f"%{keyword}%", f"%{keyword}%", page_size, offset),
		fetch_all=True
	)
	posts = []
	for r in results:
		posts.append({
			"id": r[0],
			"user_id": r[1],
			"title": r[2],
			"summary": r[3] or '',
			"category": r[4],
			"likes": r[5],
			"views": r[6],
			"created_at": str(r[7]) if r[7] else None,
			"user_name": r[8],
			"user_avatar": r[9],
		})
	return posts


def search_users(keyword, page=1, page_size=20):
	if not keyword or not keyword.strip():
		return []
	offset = (page - 1) * page_size
	results = execute_query(
		"""
        SELECT id, name, avatar, vip, prefix, status, created_at
        FROM users
        WHERE status = 1 AND name ILIKE %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
		(f"%{keyword}%", page_size, offset),
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
	return users


def close_pool():
	"""关闭所有数据库连接池。
    
    在程序退出时自动调用。
    """
	global _connection_pool
	if _connection_pool:
		_connection_pool.closeall()
		_connection_pool = None


atexit.register(close_pool)
