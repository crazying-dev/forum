# -*- coding: utf-8 -*-
"""回归：帖子接口必须返回 ``comment_count``（评论数）。

Bug：``/api/posts`` 与 ``/api/posts/<id>`` 返回的 post 对象里没有评论数字段，
安卓端 ``Post.from`` 读 ``comments`` / ``comment_count`` 都拿不到，
「评 N」恒为 0（详情页与列表卡片都一样）。
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

_FAKE_LIST_ROW = {
    "id": "P1",
    "user_id": "U1",
    "title": "标题",
    "summary": "摘要",
    "category": "general",
    "likes": 3,
    "views": 7,
    "comment_count": 5,
    "created_at": "2026-10-02 08:00:00",
    "user_name": "青深",
    "user_avatar": "/avatar/a.webp",
}

_FAKE_POST_ROW = {
    "id": "P1",
    "user_id": "U1",
    "title": "标题",
    "content": "# 正文",
    "category": "general",
    "likes": 3,
    "views": 7,
    "status": 1,
    "comment_count": 9,
    "created_at": "2026-10-02 08:00:00",
    "updated_at": "2026-10-02 08:00:00",
    "user_name": "青深",
    "user_avatar": "/avatar/a.webp",
}


def test_list_item_carries_comment_count():
    """列表项统一携带 comment_count；缺字段时回退 0（不能是 None）。"""
    import db.post as post_db

    item = post_db._to_list_item(dict(_FAKE_LIST_ROW))
    assert item["comment_count"] == 5, "列表项缺少 comment_count"

    row = dict(_FAKE_LIST_ROW)
    row.pop("comment_count")
    assert post_db._to_list_item(row)["comment_count"] == 0, "缺字段时应回退 0"


def test_get_post_carries_comment_count():
    """帖子详情（含内容）也要带 comment_count，且 SQL 带子查询。"""
    import db.post as post_db

    captured = {}

    def fake_execute_query(sql, params=None, **kwargs):
        captured["sql"] = sql
        return dict(_FAKE_POST_ROW)

    original = post_db.execute_query
    post_db.execute_query = fake_execute_query
    try:
        post = post_db.get_post("P1")
    finally:
        post_db.execute_query = original

    assert post["comment_count"] == 9, "详情缺少 comment_count"
    assert "AS comment_count" in captured["sql"], "详情 SQL 未统计评论数"
    assert "comments cm" in captured["sql"], "评论数子查询别名应为 cm"


def test_post_queries_count_comments():
    """列表 / 随机 / 个人主页 / 收藏：四条查询都要带评论数子查询。"""
    import db.post as post_db

    captured = []

    def fake_execute_query(sql, params=None, **kwargs):
        captured.append(sql)
        return [dict(_FAKE_LIST_ROW)]

    original = post_db.execute_query
    post_db.execute_query = fake_execute_query
    try:
        post_db.get_post_list(1, 20)
        post_db.get_post_list(1, 20, "general")
        post_db.get_random_posts(limit=3)
        post_db.get_user_posts("U1", 1, 20)
        post_db.get_user_favorites("U1", 1, 20)
    finally:
        post_db.execute_query = original

    assert len(captured) == 5, "应捕获 5 条查询，实际 %d" % len(captured)
    for sql in captured:
        assert "AS comment_count" in sql, "查询缺少评论数子查询：%s" % sql[:90]


def test_search_posts_carries_comment_count():
    """搜索结果的帖子同样要带 comment_count。"""
    import db.search as search_db

    captured = {}

    def fake_execute_query(sql, params=None, **kwargs):
        # 注意：主查询里也含 COUNT(*)（评论数子查询），只能用开头特征区分
        if sql.lstrip().startswith("SELECT COUNT(*)"):
            return {"count": 1}
        captured["sql"] = sql
        return [dict(_FAKE_LIST_ROW)]

    original = search_db.execute_query
    search_db.execute_query = fake_execute_query
    try:
        posts, total = search_db.search_posts("标题", 1, 20)
    finally:
        search_db.execute_query = original

    assert total == 1
    assert posts and posts[0]["comment_count"] == 5, "搜索结果缺少 comment_count"
    assert "AS comment_count" in captured.get("sql", ""), "搜索 SQL 未统计评论数"


def test_post_list_endpoint_exposes_comment_count():
    """接口层：GET /api/posts 每条帖子都要有 comment_count。"""
    from flask import Flask

    import api.post as post_api
    import db.post as post_db

    def fake_execute_query(sql, params=None, **kwargs):
        return [dict(_FAKE_LIST_ROW)]

    original = post_db.execute_query
    post_db.execute_query = fake_execute_query
    try:
        app = Flask(__name__)
        app.register_blueprint(post_api.post_bp, url_prefix="/api/posts")
        rv = app.test_client().get("/api/posts")
        body = rv.get_json()
    finally:
        post_db.execute_query = original

    assert rv.status_code == 200, "接口状态码 %s" % rv.status_code
    assert body["success"] is True
    assert body["posts"][0].get("comment_count") == 5, \
        "接口未返回 comment_count，安卓端会显示「评 0」"


if __name__ == "__main__":
    tests = [
        ("test_list_item_carries_comment_count",
         test_list_item_carries_comment_count),
        ("test_get_post_carries_comment_count",
         test_get_post_carries_comment_count),
        ("test_post_queries_count_comments",
         test_post_queries_count_comments),
        ("test_search_posts_carries_comment_count",
         test_search_posts_carries_comment_count),
        ("test_post_list_endpoint_exposes_comment_count",
         test_post_list_endpoint_exposes_comment_count),
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
