# 评论数据访问
"""评论相关数据库操作：添加、查询、删除评论。"""

from app.数据 import get_conn, execute_query, execute_insert, safe_html, _gen_id
from app.数据.用户 import get_user_by_id


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
		# 对评论内容进行 XSS 净化
		content = safe_html(content)
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
		print(f"[DB ERROR] add_comment: {e}")
		return {"success": False, "error": "评论失败"}


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
