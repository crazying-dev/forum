"""帖子数据访问。"""
import random
import threading
import time
import uuid

import config
from db import execute_query, execute_insert, safe_html


def _gen_id(prefix=None):
    p = prefix or config.POST_ID_PREFIX
    return f"{p}{uuid.uuid4().hex[:16].upper()}"


# ── 评论数（列表 / 详情统一附带）──────────────────
# 只统计未删除的评论（comments.status = 1）。子查询别名固定为 cm，
# 不占用外层 p / u / pf 等别名。客户端靠 ``comment_count`` 显示「评 N」，
# 之前接口不返回该字段，安卓端一律显示 0（历史 Bug）。
COMMENT_COUNT_SQL = (
    "(SELECT COUNT(*) FROM comments cm"
    " WHERE cm.post_id = p.id AND cm.status = 1) AS comment_count"
)


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
        "comment_count": r.get("comment_count") or 0,
        "created_at": str(r.get("created_at")) if r.get("created_at") else None,
        "user_name": r.get("user_name"),
        "user_avatar": r.get("user_avatar"),
    }


# ── 发帖 ────────────────────────────────────────
def create_post(user_id, title, content, category="general"):
    """发布新帖子，返回 {"success": True, "id": post_id}。

    内容以**用户原文**（Markdown / 纯文本）原样入库，不做任何 HTML 包装、
    不在入库时做 HTML 净化。三端渲染口径统一：一律按 Markdown 渲染，
    HTML 标签按字面文字展示（前端覆写 marked 的 html 渲染器，不解析 HTML）。
    历史上安卓客户端写入的 `<p>…<br>…</p>` 正文由 tool/content_migrate.py 迁移。
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
        f"""
        SELECT p.id, p.user_id, p.title, p.content, p.category, p.likes, p.views,
               p.status, p.created_at, p.updated_at, u.name AS user_name, u.avatar AS user_avatar,
               {COMMENT_COUNT_SQL}
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
        "comment_count": row.get("comment_count") or 0,
        "status": row.get("status"),
        "created_at": str(row.get("created_at")) if row.get("created_at") else None,
        "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        "user_name": row.get("user_name"),
        "user_avatar": row.get("user_avatar"),
    }


# ── 帖子列表 ────────────────────────────────────
# sort: 'time'（默认，最新发布）| 'comprehensive'（综合热度）| 'random'（随机）
_SORT_ORDER_SQL = {
    "time": "ORDER BY p.created_at DESC",
    "comprehensive": "ORDER BY (p.likes * 3 + p.views) DESC, p.created_at DESC",
    "random": "ORDER BY RANDOM()",
}


def get_post_list(page=1, page_size=20, category=None, sort="time"):
    offset = (page - 1) * page_size
    order_sql = _SORT_ORDER_SQL.get(sort, _SORT_ORDER_SQL["time"])
    base_select = (
        "SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,"
        " p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar,"
        " " + COMMENT_COUNT_SQL +
        " FROM posts p JOIN users u ON p.user_id = u.id WHERE p.status = 1"
    )
    if category:
        rows = execute_query(
            base_select + " AND p.category = %s " + order_sql + " LIMIT %s OFFSET %s",
            (category, page_size, offset),
            fetch_all=True,
        )
    else:
        rows = execute_query(
            base_select + " " + order_sql + " LIMIT %s OFFSET %s",
            (page_size, offset),
            fetch_all=True,
        )
    return [_to_list_item(r) for r in rows]


def get_random_posts(user_id=None, limit=200):
    """随机获取帖子（user_id 保留兼容）。"""
    rows = execute_query(
        f"""
        SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,
               p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar,
               {COMMENT_COUNT_SQL}
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
    """分页获取指定用户的帖子列表（含作者信息）。

    必须 JOIN users 取回 ``user_id`` / ``user_name`` / ``user_avatar``：
    旧实现只返回 id/title/summary/...，客户端拿不到作者就会回退成
    「匿名用户」+ 默认头像（个人主页帖子全部变匿名，历史 Bug）。
    字段结构与 :func:`_to_list_item` 保持一致。
    """
    offset = (page - 1) * page_size
    rows = execute_query(
        f"""
        SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,
               p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar,
               {COMMENT_COUNT_SQL}
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.user_id = %s AND p.status = 1
        ORDER BY p.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, page_size, offset),
        fetch_all=True,
    )
    return [_to_list_item(r) for r in rows]


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


# ── 浏览量去重：同一登录用户对同一帖子 60 分钟内最多 +1 ──────────────
# 规则：仅登录用户浏览帖子详情时计数；未登录访问不计。
# 用 post_view_log 记录每个 (post_id, user_id) 的「最近一次计数时间」，
# 滚动窗口内重复访问不再 +1（防刷新刷量）。
VIEW_WINDOW_SECONDS = 3600

# 过期记录清理：每 _PURGE_INTERVAL_SECONDS 秒最多执行一次（进程内节流，静默失败）
_PURGE_INTERVAL_SECONDS = 600
_purge_state = {"last": 0.0}
_purge_lock = threading.Lock()


def _maybe_purge_view_log(now=None):
    """偶发清理超出窗口期的历史记录，避免表无限增长。"""
    now = time.time() if now is None else now
    if now - _purge_state["last"] < _PURGE_INTERVAL_SECONDS:
        return
    with _purge_lock:
        if now - _purge_state["last"] < _PURGE_INTERVAL_SECONDS:
            return
        _purge_state["last"] = now
    try:
        execute_query(
            "DELETE FROM post_view_log"
            " WHERE viewed_at < NOW() - make_interval(secs => %s)",
            (VIEW_WINDOW_SECONDS,),
        )
    except Exception:
        pass


def try_count_post_view(post_id, user_id, window_seconds=VIEW_WINDOW_SECONDS):
    """登录用户浏览帖子时尝试计数，成功 +1 返回 True。

    单条 UPSERT 原子判定，并发安全：
      * 首次浏览 → 插入成功 → 计数；
      * 已存在且距上次计数已超过 window_seconds → 刷新 viewed_at → 计数；
      * 仍在窗口内 → ``WHERE`` 不成立、``RETURNING`` 无行 → 本次不计数。
    """
    if not post_id or not user_id:
        return False
    _maybe_purge_view_log()
    row = execute_query(
        """
        INSERT INTO post_view_log (post_id, user_id, viewed_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (post_id, user_id)
        DO UPDATE SET viewed_at = NOW()
        WHERE post_view_log.viewed_at < NOW() - make_interval(secs => %s)
        RETURNING id
        """,
        (post_id, user_id, window_seconds),
        fetch=True,
    )
    if not row:
        return False
    increment_post_views(post_id)
    return True


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
        f"""
        SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,
               p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar,
               {COMMENT_COUNT_SQL}
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
    """删除帖子（仅作者本人）。

    删除帖子时一并删除其相关数据：举报、点赞、收藏、评论，
    以及这些评论的举报记录。各子表外键虽已声明 ON DELETE CASCADE，
    此处仍显式清理，保证不依赖数据库级联也能完整清除。
    """
    post = get_post(post_id)
    if not post:
        return {"success": False, "message": "帖子不存在"}
    if post.get("user_id") != user_id:
        return {"success": False, "message": "无权删除此帖子"}
    # 一并清理相关数据（顺序：先子表，后评论，最后帖子）
    execute_query("DELETE FROM post_reports WHERE post_id = %s", (post_id,))
    execute_query("DELETE FROM post_likes WHERE post_id = %s", (post_id,))
    execute_query("DELETE FROM post_favorites WHERE post_id = %s", (post_id,))
    execute_query(
        "DELETE FROM comment_reports WHERE comment_id IN (SELECT id FROM comments WHERE post_id = %s)",
        (post_id,),
    )
    execute_query("DELETE FROM comments WHERE post_id = %s", (post_id,))
    execute_query("DELETE FROM posts WHERE id = %s", (post_id,))
    return {"success": True}
