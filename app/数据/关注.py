# 关注与收藏数据访问
"""关注、粉丝、收藏相关数据库操作。"""

from app.数据 import get_conn, execute_query, execute_insert


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


def get_following_list(user_id, page=1, page_size=20):
	"""获取用户关注的人列表。

    Args:
        user_id (str): 用户ID
        page (int): 页码
        page_size (int): 每页数量

    Returns:
        list: 用户列表
    """
	offset = (page - 1) * page_size
	results = execute_query(
		"""
		SELECT u.id, u.name, u.avatar, u.vip, u.intro, uf.created_at
		FROM user_follows uf
		JOIN users u ON uf.following_id = u.id
		WHERE uf.follower_id = %s
		ORDER BY uf.created_at DESC
		LIMIT %s OFFSET %s
		""",
		(user_id, page_size, offset),
		fetch_all=True
	)
	users = []
	for r in results:
		users.append({
			"id": r[0],
			"name": r[1],
			"avatar": r[2],
			"vip": r[3],
			"intro": r[4] or '',
			"followed_at": str(r[5]) if r[5] else None,
		})
	return users


def get_follower_list(user_id, page=1, page_size=20):
	"""获取用户的粉丝列表。

    Args:
        user_id (str): 用户ID
        page (int): 页码
        page_size (int): 每页数量

    Returns:
        list: 用户列表
    """
	offset = (page - 1) * page_size
	results = execute_query(
		"""
		SELECT u.id, u.name, u.avatar, u.vip, u.intro, uf.created_at
		FROM user_follows uf
		JOIN users u ON uf.follower_id = u.id
		WHERE uf.following_id = %s
		ORDER BY uf.created_at DESC
		LIMIT %s OFFSET %s
		""",
		(user_id, page_size, offset),
		fetch_all=True
	)
	users = []
	for r in results:
		users.append({
			"id": r[0],
			"name": r[1],
			"avatar": r[2],
			"vip": r[3],
			"intro": r[4] or '',
			"followed_at": str(r[5]) if r[5] else None,
		})
	return users


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
