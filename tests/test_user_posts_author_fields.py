"""回归：个人主页帖子列表必须带作者信息（禁止「匿名用户」）。

Bug：``/api/user/<id>/posts`` 走的 ``db.post.get_user_posts`` 只 SELECT 了
id/title/summary/category/likes/views/created_at，缺少
``user_id`` / ``user_name`` / ``user_avatar``；客户端拿不到作者只能回退成
「匿名用户」+ 默认头像，表现为「自己的主页帖子全变匿名，看别人主页也全匿名」。
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

_FAKE_ROW = {
    "id": "P1",
    "user_id": "U1",
    "title": "标题",
    "summary": "摘要",
    "category": "general",
    "likes": 3,
    "views": 7,
    "created_at": "2026-09-26 10:00:00",
    "user_name": "青深",
    "user_avatar": "/avatar/a.webp",
}


def test_get_user_posts_selects_author_fields():
    """db.post.get_user_posts 必须 JOIN users 取回作者三件套。"""
    import db.post as post_db

    captured = {}

    def fake_execute_query(sql, params=None, **kwargs):
        captured["sql"] = sql
        captured["params"] = params
        return [dict(_FAKE_ROW)]

    original = post_db.execute_query
    post_db.execute_query = fake_execute_query
    try:
        rows = post_db.get_user_posts("U1", 1, 20)
    finally:
        post_db.execute_query = original

    assert len(rows) == 1, "应返回 1 条帖子"
    row = rows[0]
    assert row["user_id"] == "U1", "个人主页帖子必须带 user_id"
    assert row["user_name"] == "青深", "个人主页帖子必须带 user_name"
    assert row["user_avatar"] == "/avatar/a.webp", "个人主页帖子必须带 user_avatar"

    sql = captured["sql"]
    assert "JOIN users" in sql, "get_user_posts 未 JOIN users"
    assert "u.name AS user_name" in sql, "get_user_posts 未取用户昵称"
    assert "u.avatar AS user_avatar" in sql, "get_user_posts 未取用户头像"
    assert captured["params"][0] == "U1", "查询参数首位应为目标用户 ID"


def test_user_posts_endpoint_exposes_author():
    """接口层：GET /api/user/<id>/posts 每条帖子都不得缺少作者字段。"""
    from flask import Flask

    import db
    import db.post as post_db
    import api.user as user_api

    def fake_execute_query(sql, params=None, **kwargs):
        return [dict(_FAKE_ROW)]

    def fake_get_user_by_id(uid):
        return {"id": uid, "name": "青深", "avatar": "/avatar/a.webp"}

    orig_eq = post_db.execute_query
    orig_get = db.user.get_user_by_id
    post_db.execute_query = fake_execute_query
    db.user.get_user_by_id = fake_get_user_by_id
    try:
        app = Flask(__name__)
        app.register_blueprint(user_api.user_bp, url_prefix="/api/user")
        rv = app.test_client().get("/api/user/U1/posts")
        body = rv.get_json()
    finally:
        post_db.execute_query = orig_eq
        db.user.get_user_by_id = orig_get

    assert rv.status_code == 200, "接口状态码 %s" % rv.status_code
    assert body["success"] is True
    posts = body["posts"]
    assert posts, "应返回帖子列表"
    for key in ("user_id", "user_name", "user_avatar"):
        assert posts[0].get(key), \
            "个人主页帖子缺少 %s，客户端会显示「匿名用户」" % key


if __name__ == "__main__":
    tests = [
        ("test_get_user_posts_selects_author_fields",
         test_get_user_posts_selects_author_fields),
        ("test_user_posts_endpoint_exposes_author",
         test_user_posts_endpoint_exposes_author),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS  " + name)
        except Exception as e:  # noqa: BLE001
            print("FAIL  %s: %s: %s" % (name, type(e).__name__, e))
            failed += 1
    print("\n%s failed" % failed)
    sys.exit(0 if failed == 0 else 1)
