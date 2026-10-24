"""用户关注数据访问。"""
from db import execute_query, execute_insert


def toggle_follow(follower_id, following_id):
    """切换关注状态（关注 / 取消关注）。"""
    if not follower_id or not following_id:
        return {"success": False, "message": "参数错误"}
    if follower_id == following_id:
        return {"success": False, "message": "不能关注自己"}
    existing = execute_query(
        "SELECT id FROM user_follows WHERE follower_id = %s AND following_id = %s",
        (follower_id, following_id),
        fetch=True,
    )
    if existing:
        execute_query(
            "DELETE FROM user_follows WHERE follower_id = %s AND following_id = %s",
            (follower_id, following_id),
        )
        return {"success": True, "following": False}
    execute_insert(
        "INSERT INTO user_follows (follower_id, following_id) VALUES (%s, %s)",
        (follower_id, following_id),
    )
    return {"success": True, "following": True}


def is_following(follower_id, following_id):
    if not follower_id or not following_id:
        return False
    row = execute_query(
        "SELECT id FROM user_follows WHERE follower_id = %s AND following_id = %s",
        (follower_id, following_id),
        fetch=True,
    )
    return row is not None


def get_follow_stats(user_id):
    following = execute_query(
        "SELECT COUNT(*) AS count FROM user_follows WHERE follower_id = %s",
        (user_id,), fetch=True,
    )
    followers = execute_query(
        "SELECT COUNT(*) AS count FROM user_follows WHERE following_id = %s",
        (user_id,), fetch=True,
    )
    return {
        "following_count": (following or {}).get("count", 0) or 0,
        "follower_count": (followers or {}).get("count", 0) or 0,
    }


def get_following_list(user_id, page=1, page_size=20):
    """获取用户关注的人列表。"""
    offset = (page - 1) * page_size
    rows = execute_query(
        """
        SELECT u.id, u.name, u.avatar, u.vip, u.intro, uf.created_at
        FROM user_follows uf
        JOIN users u ON uf.following_id = u.id
        WHERE uf.follower_id = %s
        ORDER BY uf.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, page_size, offset),
        fetch_all=True,
    )
    users = []
    for r in rows:
        users.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "avatar": r.get("avatar"),
            "vip": r.get("vip") or "0",
            "intro": r.get("intro") or "",
            "followed_at": str(r.get("created_at")) if r.get("created_at") else None,
        })
    return users


def get_follower_list(user_id, page=1, page_size=20):
    """获取用户的粉丝列表。"""
    offset = (page - 1) * page_size
    rows = execute_query(
        """
        SELECT u.id, u.name, u.avatar, u.vip, u.intro, uf.created_at
        FROM user_follows uf
        JOIN users u ON uf.follower_id = u.id
        WHERE uf.following_id = %s
        ORDER BY uf.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, page_size, offset),
        fetch_all=True,
    )
    users = []
    for r in rows:
        users.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "avatar": r.get("avatar"),
            "vip": r.get("vip") or "0",
            "intro": r.get("intro") or "",
            "followed_at": str(r.get("created_at")) if r.get("created_at") else None,
        })
    return users


def get_follower_emails(user_id, limit=5000):
    """批量获取粉丝邮箱（发帖通知用）。"""
    rows = execute_query(
        """
        SELECT u.id, u.name, u.email
        FROM user_follows uf
        JOIN users u ON uf.follower_id = u.id
        WHERE uf.following_id = %s AND u.email IS NOT NULL AND u.email <> ''
        ORDER BY uf.created_at DESC
        LIMIT %s
        """,
        (user_id, limit),
        fetch_all=True,
    )
    return [
        {"id": r.get("id"), "name": r.get("name"), "email": r.get("email")}
        for r in rows
    ]
