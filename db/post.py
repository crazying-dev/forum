"""帖子数据访问。"""
import random
import uuid

import config
from db import execute_query, execute_insert, safe_html


def _gen_id(prefix=None):
    p = prefix or config.POST_ID_PREFIX
    return f"{p}{uuid.uuid4().hex[:16].upper()}"


# ── 列表项公共字段 ──────────────────────────────
def _to_list_item(r):
    return {
        "id": r.get("id"),
        "user_id": r.get("user_id"),
        "title": r.get("title"),
        "summary": (r.get("summary") or "")[:200],
        "category": r.get("category"),
        "likes": r.get("likes") or 0,
        "views": r.get("views") or 0,
        "created_at": str(r.get("created_at")) if r.get("created_at") else None,
        "user_name": r.get("user_name"),
        "user_avatar": r.get("user_avatar"),
    }


# ── 发帖 ────────────────────────────────────────
def create_post(user_id, title, content, category="general"):
    """发布新帖子，返回 {"success": True, "id": post_id}。

    内容以原始 Markdown 存储，不在入库时做 HTML 净化；
    前端用 marked.js 渲染，渲染产物由 marked 默认转义保护。
    """
    post_id = _gen_id()
    if category not in config.ALLOWED_CATEGORIES:
        category = "general"
    try:
        execute_insert(
            "INSERT INTO posts (id, user_id, title, content, category) VALUES (%s, %s, %s, %s, %s)",
            (post_id, user_id, title, content, category),
        )
        return {"success": True, "id": post_id}
    except Exception as e:
        return {"success": False, "message": f"发布失败: {e}"}


# ── 帖子详情 ────────────────────────────────────
def get_post(post_id):
    """获取帖子详情（含作者信息），不存在或已删除返回 None。"""
    row = execute_query(
        """
        SELECT p.id, p.user_id, p.title, p.content, p.category, p.likes, p.views,
               p.status, p.created_at, p.updated_at, u.name AS user_name, u.avatar AS user_avatar
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = %s AND p.status = 1
        """,
        (post_id,),
        fetch=True,
    )
    if not row:
        return None
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "title": row.get("title"),
        "content": row.get("content"),
        "category": row.get("category"),
        "likes": row.get("likes") or 0,
        "views": row.get("views") or 0,
        "status": row.get("status"),
        "created_at": str(row.get("created_at")) if row.get("created_at") else None,
        "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        "user_name": row.get("user_name"),
        "user_avatar": row.get("user_avatar"),
    }


# ── 帖子列表 ────────────────────────────────────
def get_post_list(page=1, page_size=20, category=None):
    offset = (page - 1) * page_size
    if category:
        rows = execute_query(
            """
            SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,
                   p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.status = 1 AND p.category = %s
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (category, page_size, offset),
            fetch_all=True,
        )
    else:
        rows = execute_query(
            """
            SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,
                   p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.status = 1
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (page_size, offset),
            fetch_all=True,
        )
    return [_to_list_item(r) for r in rows]


def get_random_posts(user_id=None, limit=200):
    """随机获取帖子（user_id 保留兼容）。"""
    rows = execute_query(
        """
        SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,
               p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.status = 1
        ORDER BY RANDOM()
        LIMIT %s
        """,
        (limit,),
        fetch_all=True,
    )
    posts = [_to_list_item(r) for r in rows]
    random.shuffle(posts)
    return posts


def get_user_posts(user_id, page=1, page_size=20):
    """分页获取指定用户的帖子列表。"""
    offset = (page - 1) * page_size
    rows = execute_query(
        """
        SELECT id, title, LEFT(content, 200) AS summary, category, likes, views, created_at
        FROM posts
        WHERE user_id = %s AND status = 1
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, page_size, offset),
        fetch_all=True,
    )
    posts = []
    for r in rows:
        posts.append({
            "id": r.get("id"),
            "title": r.get("title"),
            "summary": (r.get("summary") or "")[:200],
            "category": r.get("category"),
            "likes": r.get("likes") or 0,
            "views": r.get("views") or 0,
            "created_at": str(r.get("created_at")) if r.get("created_at") else None,
        })
    return posts


def get_user_stats(user_id):
    """获取用户帖子统计：帖子数 / 总点赞 / 总浏览。"""
    row = execute_query(
        """
        SELECT COUNT(*) AS post_count,
               COALESCE(SUM(likes), 0) AS total_likes,
               COALESCE(SUM(views), 0) AS total_views
        FROM posts
        WHERE user_id = %s AND status = 1
        """,
        (user_id,),
        fetch=True,
    )
    if not row:
        return {"post_count": 0, "total_likes": 0, "total_views": 0}
    return {
        "post_count": row.get("post_count") or 0,
        "total_likes": row.get("total_likes") or 0,
        "total_views": row.get("total_views") or 0,
    }


def increment_post_views(post_id):
    execute_query("UPDATE posts SET views = views + 1 WHERE id = %s", (post_id,))


# ── 点赞 ────────────────────────────────────────
def like_post(post_id, user_id):
    """切换点赞状态，返回 {"success": True, "liked": bool, "likes": int}。"""
    existing = execute_query(
        "SELECT id FROM post_likes WHERE post_id = %s AND user_id = %s",
        (post_id, user_id),
        fetch=True,
    )
    if existing:
        execute_query(
            "DELETE FROM post_likes WHERE post_id = %s AND user_id = %s",
            (post_id, user_id),
        )
        execute_query(
            "UPDATE posts SET likes = GREATEST(likes - 1, 0) WHERE id = %s",
            (post_id,),
        )
        liked = False
    else:
        execute_insert(
            "INSERT INTO post_likes (post_id, user_id) VALUES (%s, %s)",
            (post_id, user_id),
        )
        execute_query("UPDATE posts SET likes = likes + 1 WHERE id = %s", (post_id,))
        liked = True
    row = execute_query("SELECT likes FROM posts WHERE id = %s", (post_id,), fetch=True)
    return {"success": True, "liked": liked, "likes": (row or {}).get("likes", 0) or 0}


def has_liked_post(post_id, user_id):
    if not user_id:
        return False
    row = execute_query(
        "SELECT id FROM post_likes WHERE post_id = %s AND user_id = %s",
        (post_id, user_id),
        fetch=True,
    )
    return row is not None


# ── 收藏 ────────────────────────────────────────
def toggle_favorite(post_id, user_id):
    """切换收藏状态，返回 {"success": True, "favorited": bool}。"""
    existing = execute_query(
        "SELECT id FROM post_favorites WHERE post_id = %s AND user_id = %s",
        (post_id, user_id),
        fetch=True,
    )
    if existing:
        execute_query(
            "DELETE FROM post_favorites WHERE post_id = %s AND user_id = %s",
            (post_id, user_id),
        )
        return {"success": True, "favorited": False}
    execute_insert(
        "INSERT INTO post_favorites (post_id, user_id) VALUES (%s, %s)",
        (post_id, user_id),
    )
    return {"success": True, "favorited": True}


def has_favorited_post(post_id, user_id):
    if not user_id:
        return False
    row = execute_query(
        "SELECT id FROM post_favorites WHERE post_id = %s AND user_id = %s",
        (post_id, user_id),
        fetch=True,
    )
    return row is not None


def get_user_favorites(user_id, page=1, page_size=20):
    """获取用户收藏的帖子列表。"""
    offset = (page - 1) * page_size
    rows = execute_query(
        """
        SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,
               p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar
        FROM post_favorites pf
        JOIN posts p ON pf.post_id = p.id
        JOIN users u ON p.user_id = u.id
        WHERE pf.user_id = %s AND p.status = 1
        ORDER BY pf.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, page_size, offset),
        fetch_all=True,
    )
    return [_to_list_item(r) for r in rows]


# ── 举报 / 删除 ─────────────────────────────────
def report_post(post_id, reporter_id, reason, detail=""):
    execute_insert(
        "INSERT INTO post_reports (post_id, reporter_id, reason, detail) VALUES (%s, %s, %s, %s)",
        (post_id, reporter_id, reason, detail),
    )
    return {"success": True}


def delete_post(post_id, user_id):
    """删除帖子（仅作者本人）。"""
    post = get_post(post_id)
    if not post:
        return {"success": False, "message": "帖子不存在"}
    if post.get("user_id") != user_id:
        return {"success": False, "message": "无权删除此帖子"}
    execute_query("DELETE FROM posts WHERE id = %s", (post_id,))
    return {"success": True}
