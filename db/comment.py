"""评论数据访问。"""
import uuid

import config
from db import execute_query, execute_insert, safe_html


def _gen_id():
    return f"{config.COMMENT_ID_PREFIX}{uuid.uuid4().hex[:16].upper()}"


def add_comment(post_id, user_id, content, parent_id=None):
    """添加评论，返回 {"success": True, "id": ..., "comment": {...}}。"""
    comment_id = _gen_id()
    content = safe_html(content)
    try:
        execute_insert(
            "INSERT INTO comments (id, post_id, user_id, content, parent_id) VALUES (%s, %s, %s, %s, %s)",
            (comment_id, post_id, user_id, content, parent_id),
        )
        from db.user import get_user_by_id
        user = get_user_by_id(user_id) or {}
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
                "user_name": user.get("name", "匿名"),
                "user_avatar": user.get("avatar", ""),
            },
        }
    except Exception as e:
        return {"success": False, "message": f"评论失败: {e}"}


def get_post_comments(post_id, page=1, page_size=50):
    """分页获取帖子评论列表。"""
    offset = (page - 1) * page_size
    rows = execute_query(
        """
        SELECT c.id, c.user_id, c.content, c.parent_id, c.likes, c.created_at,
               u.name AS user_name, u.avatar AS user_avatar
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id = %s AND c.status = 1
        ORDER BY c.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (post_id, page_size, offset),
        fetch_all=True,
    )
    comments = []
    for r in rows:
        comments.append({
            "id": r.get("id"),
            "user_id": r.get("user_id"),
            "content": r.get("content"),
            "parent_id": r.get("parent_id"),
            "likes": r.get("likes") or 0,
            "created_at": str(r.get("created_at")) if r.get("created_at") else None,
            "user_name": r.get("user_name"),
            "user_avatar": r.get("user_avatar"),
        })
    return comments


def delete_comment(comment_id, user_id):
    """删除评论（仅评论作者本人），返回 {"success": True, "post_id": ...}。"""
    row = execute_query(
        "SELECT user_id, post_id FROM comments WHERE id = %s AND status = 1",
        (comment_id,),
        fetch=True,
    )
    if not row:
        return {"success": False, "message": "评论不存在"}
    if row.get("user_id") != user_id:
        return {"success": False, "message": "无权删除此评论"}
    execute_query("UPDATE comments SET status = 0 WHERE id = %s", (comment_id,))
    return {"success": True, "post_id": row.get("post_id")}


def get_user_comments(user_id, page=1, page_size=20):
    """获取指定用户的所有评论（含对应帖子 ID/标题，用于个人主页跳转）。"""
    offset = (page - 1) * page_size
    rows = execute_query(
        """
        SELECT c.id, c.post_id, c.content, c.likes, c.created_at,
               p.title AS post_title
        FROM comments c
        JOIN posts p ON p.id = c.post_id
        WHERE c.user_id = %s AND c.status = 1 AND p.status = 1
        ORDER BY c.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, page_size, offset),
        fetch_all=True,
    )
    count_row = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM comments c
        JOIN posts p ON p.id = c.post_id
        WHERE c.user_id = %s AND c.status = 1 AND p.status = 1
        """,
        (user_id,),
        fetch=True,
    )
    comments = []
    for r in rows:
        comments.append({
            "id": r.get("id"),
            "post_id": r.get("post_id"),
            "post_title": r.get("post_title"),
            "content": r.get("content"),
            "likes": r.get("likes") or 0,
            "created_at": str(r.get("created_at")) if r.get("created_at") else None,
        })
    total = (count_row or {}).get("count", 0) or 0
    return comments, total


def report_comment(comment_id, reporter_id, reason, detail=""):
    """举报评论，返回 {"success": True}。"""
    row = execute_query(
        "SELECT id FROM comments WHERE id = %s AND status = 1",
        (comment_id,),
        fetch=True,
    )
    if not row:
        return {"success": False, "message": "评论不存在"}
    try:
        execute_insert(
            "INSERT INTO comment_reports (comment_id, reporter_id, reason, detail) VALUES (%s, %s, %s, %s)",
            (comment_id, reporter_id, reason, detail),
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": f"举报失败: {e}"}


def get_replies_to_my_comments(user_id, page=1, page_size=50):
    """获取回复了当前用户评论的回复列表（含对应帖子标题）。"""
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 50), 1), 100)
    offset = (page - 1) * page_size
    rows = execute_query(
        """
        SELECT c.id, c.content, c.parent_id, c.created_at,
               r.user_id AS replier_id, r.content AS reply_content, r.created_at AS reply_created_at,
               u.name AS replier_name, u.avatar AS replier_avatar,
               p.id AS post_id, p.title AS post_title
        FROM comments c
        JOIN comments r ON r.parent_id = c.id AND r.status = 1
        JOIN users u ON r.user_id = u.id
        JOIN posts p ON c.post_id = p.id
        WHERE c.user_id = %s AND c.status = 1 AND p.status = 1
        ORDER BY r.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, page_size, offset),
        fetch_all=True,
    )
    count_row = execute_query(
        """
        SELECT COUNT(*) AS count
        FROM comments c
        JOIN comments r ON r.parent_id = c.id AND r.status = 1
        WHERE c.user_id = %s AND c.status = 1
        """,
        (user_id,),
        fetch=True,
    )
    replies = []
    for r in rows:
        replies.append({
            "comment_id": r.get("id"),
            "comment_content": r.get("content"),
            "parent_id": r.get("parent_id"),
            "comment_created_at": str(r.get("created_at")) if r.get("created_at") else None,
            "replier_id": r.get("replier_id"),
            "reply_content": r.get("reply_content"),
            "reply_created_at": str(r.get("reply_created_at")) if r.get("reply_created_at") else None,
            "replier_name": r.get("replier_name"),
            "replier_avatar": r.get("replier_avatar"),
            "post_id": r.get("post_id"),
            "post_title": r.get("post_title"),
        })
    total = (count_row or {}).get("count", 0) or 0
    return {"replies": replies, "total": total}
