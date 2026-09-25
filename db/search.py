"""搜索数据访问（帖子 + 用户，多关键词 AND 相关性排序）。"""
from db import execute_query


def _build_tokens(keyword):
    return [t for t in keyword.strip().split() if t]


# ── 帖子搜索 ────────────────────────────────────
def search_posts(keyword, page=1, page_size=20):
    keyword = keyword.strip()
    if not keyword or len(keyword) < 2:
        return [], 0
    tokens = _build_tokens(keyword) or [keyword]
    offset = (page - 1) * page_size
    likes = [f"%{t}%" for t in tokens]

    token_clauses, where_params = [], []
    for like in likes:
        token_clauses.append("(p.title ILIKE %s OR p.content ILIKE %s OR p.category ILIKE %s)")
        where_params.extend([like, like, like])
    where_clause = " AND ".join(token_clauses)

    count_row = execute_query(
        f"SELECT COUNT(*) AS count FROM posts p WHERE p.status = 1 AND ({where_clause})",
        tuple(where_params),
        fetch=True,
    )
    total = (count_row or {}).get("count", 0) or 0

    score_parts, score_params = [], []
    for like in likes:
        score_parts.append("(CASE WHEN p.title ILIKE %s THEN 100 ELSE 0 END)")
        score_parts.append("(CASE WHEN p.content ILIKE %s THEN 10 ELSE 0 END)")
        score_parts.append("(CASE WHEN p.category ILIKE %s THEN 5 ELSE 0 END)")
        score_params.extend([like, like, like])
    score_expr = " + ".join(score_parts)

    rows = execute_query(
        f"""
        SELECT p.id, p.user_id, p.title, LEFT(p.content, 200) AS summary, p.category,
               p.likes, p.views, p.created_at, u.name AS user_name, u.avatar AS user_avatar,
               ({score_expr}) AS relevance
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.status = 1 AND ({where_clause})
        ORDER BY relevance DESC, p.likes DESC, p.created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(score_params + where_params + [page_size, offset]),
        fetch_all=True,
    )
    posts = []
    for r in rows:
        posts.append({
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
        })
    return posts, total


# ── 用户搜索 ────────────────────────────────────
def search_users(keyword, page=1, page_size=20):
    keyword = keyword.strip()
    if not keyword or len(keyword) < 2:
        return [], 0
    tokens = _build_tokens(keyword) or [keyword]
    offset = (page - 1) * page_size
    likes = [f"%{t}%" for t in tokens]

    token_clauses, where_params = [], []
    for like in likes:
        token_clauses.append("(name ILIKE %s OR prefix ILIKE %s)")
        where_params.extend([like, like])
    where_clause = " AND ".join(token_clauses)

    count_row = execute_query(
        f"SELECT COUNT(*) AS count FROM users WHERE is_banned = 0 AND ({where_clause})",
        tuple(where_params),
        fetch=True,
    )
    total = (count_row or {}).get("count", 0) or 0

    score_parts, score_params = [], []
    for like in likes:
        score_parts.append("(CASE WHEN name ILIKE %s THEN 100 ELSE 0 END)")
        score_parts.append("(CASE WHEN prefix ILIKE %s THEN 30 ELSE 0 END)")
        score_params.extend([like, like])
    score_expr = " + ".join(score_parts)

    rows = execute_query(
        f"""
        SELECT id, name, avatar, vip, prefix, created_at, ({score_expr}) AS relevance
        FROM users
        WHERE is_banned = 0 AND ({where_clause})
        ORDER BY relevance DESC, created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(score_params + where_params + [page_size, offset]),
        fetch_all=True,
    )
    users = []
    for r in rows:
        users.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "avatar": r.get("avatar"),
            "vip": r.get("vip") or "0",
            "prefix": r.get("prefix") or "",
            "created_at": str(r.get("created_at")) if r.get("created_at") else None,
        })
    return users, total
