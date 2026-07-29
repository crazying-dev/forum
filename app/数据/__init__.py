"""Faerydae 论坛 - 数据库核心模块

提供数据库连接、查询执行、表初始化、HTML净化等核心功能。
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

# 加载 .env 文件（Vercel 等生产环境无此文件时静默跳过，使用平台注入的环境变量）
try:
	dotenv.load_dotenv(override=False)
except Exception:
	pass
DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') or os.getenv('POSTGRES_PRISMA_URL')

# 清理 Neon 等云数据库附加的非标准参数（psycopg2/libpq 可能不支持）
if DATABASE_URL:
	import re as _re
	DATABASE_URL = _re.sub(r'[&?]channel_binding=[^&]*', '', DATABASE_URL)
	# 修复：移除 channel_binding 后剩余参数可能以 & 开头，需将首个 & 改为 ?
	if '&' in DATABASE_URL and '?' not in DATABASE_URL:
		DATABASE_URL = DATABASE_URL.replace('&', '?', 1)

if not DATABASE_URL:
	print("[DB] 警告: 未设置 DATABASE_URL 环境变量，数据库功能将不可用")

POST_ID_PREFIX = 'PS'
_table_checked = False

DANGEROUS_TAGS = {'script', 'iframe', 'embed', 'object', 'applet', 'base', 'form', 'input', 'textarea',
                  'select', 'option', 'button', 'link', 'meta', 'svg', 'math'}


def safe_html(content):
	"""对用户提交的 HTML 内容进行净化（黑名单 + 事件属性移除）。

	注意：这是基础净化。更严格的场景应使用 bleach 等专用库。
	"""
	if not content:
		return ''
	import html as html_module
	# 先反转义，确保实体编码的内容也能被检测到
	content = html_module.unescape(content)
	# 移除 HTML 注释（可藏恶意代码）
	content = re.sub(r'<!--[\s\S]*?-->', '', content)
	# 移除危险标签（开标签和自闭合）
	tag_pattern = '|'.join(sorted(DANGEROUS_TAGS))
	content = re.sub(rf'<(?:{tag_pattern})\b[^>]*>', '', content, flags=re.IGNORECASE)
	content = re.sub(rf'</(?:{tag_pattern})\s*>', '', content, flags=re.IGNORECASE)
	# 移除所有事件处理属性 onXxx=...
	content = re.sub(r'\son\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', content, flags=re.IGNORECASE)
	# 移除 javascript: 伪协议
	content = re.sub(r'(href|src|action|formaction)\s*=\s*("javascript:[^"]*"|\'javascript:[^\']*\'|javascript:[^\s>]+)',
	                 '', content, flags=re.IGNORECASE)
	# 移除 data: 伪协议中的非图片类型（防 HTML 注入）
	content = re.sub(r'(href|src|action)\s*=\s*("data:text/html[^"]*"|\'data:text/html[^\']*\')',
	                 '', content, flags=re.IGNORECASE)
	return content


# 图片基础 URL
Image_father_URL = "https://img.crazying-dev.top/text/one"

DEFAULT_AVATARS = [
	f'{Image_father_URL}/avatars/LaoJun.png',
	f'{Image_father_URL}/avatars/LuoXiaoHei1.png',
	f'{Image_father_URL}/avatars/LuoXiaoHei2.png',
	f'{Image_father_URL}/avatars/MuXiZi.png',
]

_connection_pool = None
POOL_ENABLED = False  # Vercel 数据库不需要连接池，为 False; 传统服务器改为 True
NowTime = lambda: time.time() * 10000


# ========================
# SQL 表定义（从 api/config.py 复制）
# ========================

CREATE_USER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    avatar TEXT NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    gender INTEGER DEFAULT 0,
    age VARCHAR(32) DEFAULT '',
    intro TEXT DEFAULT '',
    vip VARCHAR(32) NOT NULL DEFAULT '0',
    prefix VARCHAR(32) DEFAULT '',
    is_banned INTEGER NOT NULL DEFAULT 0,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
"""

CREATE_POST_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS posts (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(64) DEFAULT 'general',
    likes INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    status INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_COMMENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS comments (
    id VARCHAR(64) PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    parent_id VARCHAR(64) DEFAULT NULL,
    likes INTEGER DEFAULT 0,
    status INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES comments(id) ON DELETE CASCADE
);
"""

CREATE_World_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS World (
    id SERIAL PRIMARY KEY,
    sender_id VARCHAR(255) NOT NULL,
    sender_name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    parent_id INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
"""

CREATE_POST_LIKES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_likes (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, user_id),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_POST_FAVORITES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_favorites (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, user_id),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_USER_FOLLOWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_follows (
    id SERIAL PRIMARY KEY,
    follower_id VARCHAR(64) NOT NULL,
    following_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(follower_id, following_id),
    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (following_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_VERIFY_TOKENS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verify_tokens (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    token VARCHAR(255) NOT NULL UNIQUE,
    token_type VARCHAR(32) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_POST_REPORTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_reports (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    reporter_id VARCHAR(64) NOT NULL,
    reason VARCHAR(64) NOT NULL,
    detail TEXT DEFAULT '',
    status INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_VERIFY_CODES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verify_codes (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    code VARCHAR(6) NOT NULL,
    purpose VARCHAR(32) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEX_SQLS = [
    "CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);",
    "CREATE INDEX IF NOT EXISTS idx_world_created_at ON World(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_post_likes_post_id ON post_likes(post_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_likes_user_id ON post_likes(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_favorites_user_id ON post_favorites(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_follows_follower ON user_follows(follower_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_follows_following ON user_follows(following_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_reports_post_id ON post_reports(post_id);",
    "CREATE INDEX IF NOT EXISTS idx_verify_codes_email_purpose ON verify_codes(email, purpose);",
    "CREATE INDEX IF NOT EXISTS idx_verify_codes_expires ON verify_codes(expires_at);",
]


# ========================
# 数据库连接
# ========================


def init_pool():
	"""初始化连接池（仅在非 Serverless 环境启用）。
    
    如果 POOL_ENABLED 为 False，则不创建连接池。
    """
	global _connection_pool
	if not POOL_ENABLED:
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


# ========================
# 表管理
# ========================


def init_tables():
	"""初始化数据库表。

    如果表已存在则跳过（使用 IF NOT EXISTS）。
    """
	with get_conn() as (conn, cursor):
		cursor.execute(CREATE_USER_TABLE_SQL)
		cursor.execute(CREATE_POST_TABLE_SQL)
		cursor.execute(CREATE_COMMENT_TABLE_SQL)
		cursor.execute(CREATE_World_TABLE_SQL)
		cursor.execute(CREATE_POST_LIKES_TABLE_SQL)
		cursor.execute(CREATE_POST_FAVORITES_TABLE_SQL)
		cursor.execute(CREATE_USER_FOLLOWS_TABLE_SQL)
		cursor.execute(CREATE_VERIFY_TOKENS_TABLE_SQL)
		cursor.execute(CREATE_VERIFY_CODES_TABLE_SQL)
		cursor.execute(CREATE_POST_REPORTS_TABLE_SQL)
		for alter_sql in (
			"ALTER TABLE comments ADD COLUMN IF NOT EXISTS parent_id VARCHAR(64)",
			"ALTER TABLE World ADD COLUMN IF NOT EXISTS parent_id INTEGER",
			"ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified INTEGER NOT NULL DEFAULT 0",
			"ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned INTEGER NOT NULL DEFAULT 0",
		):
			try:
				cursor.execute(alter_sql)
			except Exception as alter_err:
				print(f"[DB] ALTER 失败（已忽略）: {alter_err}")
		for sql in CREATE_INDEX_SQLS:
			try:
				cursor.execute(sql)
			except Exception as idx_err:
				print(f"[DB] 索引创建失败（已忽略）: {idx_err}")
		conn.commit()


def ensure_tables(force=False):
	"""懒加载：仅在需要时创建表。

	首次调用时检查并创建表，之后直接返回。
	如果表创建失败则打印错误。

	Args:
		force (bool): 为 True 时强制重新初始化（用于补齐缺失字段等情况）
	"""
	global _table_checked
	if _table_checked and not force:
		return
	try:
		init_tables()
		_table_checked = True
	except Exception as e:
		print(f"[DB] 初始化表失败: {e}")


# 已知需要补齐的列：表名 -> [(列名, 类型定义), ...]
_KNOWN_COLUMNS = {
	'users': [
		('email_verified', 'INTEGER NOT NULL DEFAULT 0'),
		('is_banned', 'INTEGER NOT NULL DEFAULT 0'),
		('prefix', 'VARCHAR(32) DEFAULT \'\''),
	],
	'comments': [
		('parent_id', 'VARCHAR(64)'),
	],
	'World': [
		('parent_id', 'INTEGER'),
	],
}


def _patch_missing_column(table_name, column_name):
	"""直接对指定表添加缺失列（带 IF NOT EXISTS）。"""
	type_def = ''
	for tbl, cols in _KNOWN_COLUMNS.items():
		if tbl == table_name:
			for col, td in cols:
				if col == column_name:
					type_def = td
					break
			break
	if not type_def:
		return False
	try:
		with get_conn() as (conn, cursor):
			cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {type_def}')
			conn.commit()
		return True
	except Exception as e:
		print(f"[DB] 补齐列 {table_name}.{column_name} 失败: {e}")
		return False


def _gen_id(prefix):
	"""生成带前缀的唯一ID。
    
    Args:
        prefix (str): ID前缀，如 'YJ'(用户)、'PS'(帖子)、'CM'(评论)
    
    Returns:
        str: 形如 'YJ1234567890' 的唯一ID
    """
	return prefix + str(int(time.time() * 10000000000))


def _handle_missing_schema(e):
	"""处理表/列缺失错误：解析错误信息，直接补齐缺失的列。

	Args:
		e: psycopg2 异常对象（UndefinedTable 或 UndefinedColumn）
	"""
	ensure_tables(force=True)
	# 如果是 UndefinedColumn，尝试从错误信息中提取列名并直接补齐
	err_msg = str(e)
	if 'does not exist' in err_msg and 'column' in err_msg:
		# 错误格式: column "email_verified" does not exist
		import re as _re
		col_match = _re.search(r'column "(\w+)" does not exist', err_msg)
		if col_match:
			missing_col = col_match.group(1)
			# 从 query 中推断表名（简单的启发式：查找 FROM/UPDATE/INTO 后的表名）
			for tbl in _KNOWN_COLUMNS:
				for col, _ in _KNOWN_COLUMNS[tbl]:
					if col == missing_col:
						_patch_missing_column(tbl, missing_col)
						return


# ========================
# 查询执行
# ========================


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
	except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
		_handle_missing_schema(e)
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
	except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
		_handle_missing_schema(e)
		with get_conn() as (conn, cursor):
			cursor.execute(query, params or ())
			conn.commit()
			return cursor.rowcount


def clean_expired_verify_codes():
	"""清理已过期或已使用的验证码。"""
	execute_query(
		"DELETE FROM verify_codes WHERE expires_at < CURRENT_TIMESTAMP OR used = 1"
	)


# ========================
# 连接池关闭
# ========================


def close_pool():
	"""关闭所有数据库连接池。
    
    在程序退出时自动调用。
    """
	global _connection_pool
	if _connection_pool:
		_connection_pool.closeall()
		_connection_pool = None


atexit.register(close_pool)
