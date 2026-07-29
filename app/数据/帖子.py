# 帖子数据访问
"""帖子相关数据库操作：发布、查询、搜索、点赞等。"""

from app.数据 import get_conn, execute_query, execute_insert, safe_html, POST_ID_PREFIX, _gen_id


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
		print(f"[DB ERROR] Send_Post: {e}")
		return {"success": False, "error": "发布失败"}


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


def search_posts(keyword, page=1, page_size=20):
	"""搜索帖子（按标题和内容匹配，按相关性排序）。

    Returns:
        tuple: (posts: list, total: int)
    """
	keyword = keyword.strip()
	if not keyword or len(keyword) < 2:
		return [], 0
	offset = (page - 1) * page_size
	like = f'%{keyword}%'

	count_row = execute_query(
		"SELECT COUNT(*) FROM posts p WHERE p.status = 1 AND (p.title ILIKE %s OR p.content ILIKE %s)",
		(like, like), fetch=True
	)
	total = count_row[0] if count_row else 0

	results = execute_query(
		"""
        SELECT p.id, p.user_id, p.title, LEFT(p.content, 200), p.category, p.likes, p.views,
               p.created_at, u.name, u.avatar
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.status = 1 AND (p.title ILIKE %s OR p.content ILIKE %s)
        ORDER BY
            CASE WHEN p.title ILIKE %s THEN 0 ELSE 1 END,
            p.created_at DESC
        LIMIT %s OFFSET %s
        """,
		(like, like, like, page_size, offset),
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
	return posts, total


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


def get_replies_to_my_comments(user_id, page=1, page_size=50):
	"""获取回复了当前用户评论的回复列表（含对应的帖子标题）"""
	offset = (page - 1) * page_size
	results = execute_query(
		"""
        SELECT c.id, c.content, c.parent_id, c.created_at,
               r.user_id AS replier_id, r.content AS reply_content, r.created_at AS reply_created_at,
               u.name AS replier_name, u.avatar AS replier_avatar,
               p.id AS post_id, p.title AS post_title
        FROM comments c
        JOIN comments r ON r.parent_id = c.id AND r.status = 1
        JOIN users u ON r.user_id = u.id
        JOIN posts p ON c.post_id = p.id
        WHERE c.user_id = %s AND c.status = 1
        ORDER BY r.created_at DESC
        LIMIT %s OFFSET %s
        """,
		(user_id, page_size, offset),
		fetch_all=True
	)
	replies = []
	for r in results:
		replies.append({
			"comment_id": r[0],
			"comment_content": r[1],
			"parent_id": r[2],
			"comment_created_at": str(r[3]) if r[3] else None,
			"replier_id": r[4],
			"reply_content": r[5],
			"reply_created_at": str(r[6]) if r[6] else None,
			"replier_name": r[7],
			"replier_avatar": r[8],
			"post_id": r[9],
			"post_title": r[10],
		})
	
	# Also get total count
	count_result = execute_query(
		"""
        SELECT COUNT(*)
        FROM comments c
        JOIN comments r ON r.parent_id = c.id AND r.status = 1
        WHERE c.user_id = %s AND c.status = 1
        """,
		(user_id,),
		fetch=True
	)
	total = count_result[0] if count_result else 0
	
	return {"replies": replies, "total": total}
