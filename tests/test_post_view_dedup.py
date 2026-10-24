# -*- coding: utf-8 -*-
"""回归：浏览量「每个登录用户对同一帖子每小时最多 +1」。

规则：
  * 仅登录用户浏览帖子详情时计数；未登录访问不 +1；
  * 同一用户对同一帖子在 60 分钟滚动窗口内最多 +1（post_view_log 去重）。

背景：``GET /api/posts/<id>`` 原先无条件 ``UPDATE posts SET views = views + 1``，
刷新页面即可无限刷浏览量，未登录也能刷。
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

ONE_HOUR = 3600


def test_view_log_table_defined_with_unique_pair():
    """建表 SQL 必须带 (post_id, user_id) 唯一约束，并注册进 ALL_TABLE_SQL。"""
    import config

    sql = getattr(config, "CREATE_POST_VIEW_LOG_TABLE_SQL", "")
    assert "CREATE TABLE IF NOT EXISTS post_view_log" in sql, "缺少 post_view_log 建表 SQL"
    assert "UNIQUE(post_id, user_id)" in sql, "缺少 (post_id, user_id) 唯一约束"
    assert "viewed_at" in sql, "缺少 viewed_at 最近计数时间列"
    assert config.CREATE_POST_VIEW_LOG_TABLE_SQL in config.ALL_TABLE_SQL, \
        "建表 SQL 未注册进 ALL_TABLE_SQL"
    assert any("idx_post_view_log" in s for s in config.CREATE_INDEX_SQLS), \
        "缺少 post_view_log 索引"


def test_window_is_one_hour():
    """滚动窗口必须是 3600 秒（1 小时）。"""
    import db.post as post_db
    assert post_db.VIEW_WINDOW_SECONDS == ONE_HOUR, \
        "窗口应为 3600 秒，实际 %s" % post_db.VIEW_WINDOW_SECONDS


def test_upsert_is_single_atomic_statement():
    """去重判定必须是单条 UPSERT（ON CONFLICT + WHERE + RETURNING），保证并发原子。"""
    import db.post as post_db

    captured = []

    def fake_execute_query(sql, params=None, **kwargs):
        captured.append(sql)
        return {"id": 1}

    orig_eq, orig_purge = post_db.execute_query, post_db._maybe_purge_view_log
    post_db.execute_query = fake_execute_query
    post_db._maybe_purge_view_log = lambda *a, **k: None
    try:
        assert post_db.try_count_post_view("P1", "U1") is True, "首次浏览应计数"
    finally:
        post_db.execute_query, post_db._maybe_purge_view_log = orig_eq, orig_purge

    upsert = captured[0]
    assert "INSERT INTO post_view_log" in upsert
    assert "ON CONFLICT (post_id, user_id)" in upsert, "缺少 ON CONFLICT 去重"
    assert "RETURNING" in upsert, "缺少 RETURNING 以判定是否计数"
    assert "make_interval" in upsert, "缺少 60 分钟窗口判断"
    assert any("UPDATE posts SET views = views + 1" in s for s in captured), \
        "计数时应执行 UPDATE posts"


def test_repeat_within_window_not_counted():
    """窗口内重复访问：UPSERT 不返回行 → 不再 +1。"""
    import db.post as post_db

    captured = []

    def fake_execute_query(sql, params=None, **kwargs):
        captured.append(sql)
        return None

    orig_eq, orig_purge = post_db.execute_query, post_db._maybe_purge_view_log
    post_db.execute_query = fake_execute_query
    post_db._maybe_purge_view_log = lambda *a, **k: None
    try:
        assert post_db.try_count_post_view("P1", "U1") is False, "窗口内不应计数"
    finally:
        post_db.execute_query, post_db._maybe_purge_view_log = orig_eq, orig_purge

    assert not any("UPDATE posts" in s for s in captured), "窗口内不应执行 UPDATE posts"


def test_anonymous_never_counted():
    """未登录（user_id 为空）一律不计数，且不触碰数据库。"""
    import db.post as post_db

    called = {"n": 0}

    def fake_execute_query(sql, params=None, **kwargs):
        called["n"] += 1
        return None

    orig_eq = post_db.execute_query
    post_db.execute_query = fake_execute_query
    try:
        assert post_db.try_count_post_view("P1", None) is False
        assert post_db.try_count_post_view("P1", "") is False
    finally:
        post_db.execute_query = orig_eq

    assert called["n"] == 0, "匿名访问不应触发任何 SQL"


def test_purge_removes_stale_rows():
    """过期记录会被清理（DELETE ... viewed_at < 窗口），避免表无限增长。"""
    import db.post as post_db

    captured = []
    orig_eq, orig_last = post_db.execute_query, post_db._purge_state["last"]
    post_db.execute_query = lambda sql, params=None, **k: captured.append(sql)
    post_db._purge_state["last"] = 0  # 允许本次清理
    try:
        post_db._maybe_purge_view_log(now=10 ** 9)
    finally:
        post_db.execute_query = orig_eq
        post_db._purge_state["last"] = orig_last

    assert any("DELETE FROM post_view_log" in s for s in captured), "未清理过期记录"


def _make_client(count_results, logged_in=True):
    """构造 Flask 测试客户端；count_results 为 try_count_post_view 的依次返回值。"""
    from flask import Flask, g

    import api.post as post_api
    import db.comment as comment_db
    import db.post as post_db

    state = {"i": 0, "views": 7}

    def fake_get_post(post_id):
        return {
            "id": post_id, "user_id": "U1", "title": "标题", "content": "正文",
            "category": "general", "likes": 0, "views": state["views"], "status": 1,
            "comment_count": 0, "created_at": "2026-10-03 08:00:00",
            "updated_at": "2026-10-03 08:00:00", "user_name": "青深",
            "user_avatar": "/avatar/a.webp",
        }

    def fake_try_count(post_id, user_id, window_seconds=None):
        i = state["i"]
        state["i"] += 1
        allowed = count_results[i] if i < len(count_results) else False
        if allowed:
            state["views"] += 1  # 模拟数据库真实的 views+1
        return allowed

    orig = (post_db.get_post, post_db.try_count_post_view,
            comment_db.get_post_comments, post_db.has_liked_post,
            post_db.has_favorited_post)
    post_db.get_post = fake_get_post
    post_db.try_count_post_view = fake_try_count
    comment_db.get_post_comments = lambda *a, **k: []
    post_db.has_liked_post = lambda *a, **k: False
    post_db.has_favorited_post = lambda *a, **k: False

    app = Flask(__name__)
    if logged_in:
        @app.before_request
        def _fake_auth():
            g.user = {"id": "U1", "name": "青深"}
    app.register_blueprint(post_api.post_bp, url_prefix="/api/posts")
    client = app.test_client()

    def restore():
        (post_db.get_post, post_db.try_count_post_view,
         comment_db.get_post_comments, post_db.has_liked_post,
         post_db.has_favorited_post) = orig

    return client, restore, state


def test_detail_counts_first_view_only():
    """登录用户：第一次 7→8，窗口内第二次仍为 8，数据库只 +1 一次。"""
    client, restore, state = _make_client([True, False])
    try:
        first = client.get("/api/posts/P1").get_json()["post"]["views"]
        second = client.get("/api/posts/P1").get_json()["post"]["views"]
    finally:
        restore()
    assert first == 8, "首次访问应 +1（7→8），实际 %s" % first
    assert second == 8, "窗口内重复访问不应再 +1，实际 %s" % second
    assert state["views"] == 8, "数据库只应 +1 一次，实际 %s" % state["views"]


def test_detail_anonymous_does_not_increment():
    """未登录访问：views 原样返回（7），且 try_count_post_view 不被调用。"""
    client, restore, state = _make_client([False], logged_in=False)
    try:
        views = client.get("/api/posts/P1").get_json()["post"]["views"]
    finally:
        restore()
    assert views == 7, "匿名访问不应 +1，实际 %s" % views
    assert state["i"] == 0, "匿名访问不应调用 try_count_post_view"


if __name__ == "__main__":
    tests = [
        ("test_view_log_table_defined_with_unique_pair",
         test_view_log_table_defined_with_unique_pair),
        ("test_window_is_one_hour", test_window_is_one_hour),
        ("test_upsert_is_single_atomic_statement",
         test_upsert_is_single_atomic_statement),
        ("test_repeat_within_window_not_counted",
         test_repeat_within_window_not_counted),
        ("test_anonymous_never_counted", test_anonymous_never_counted),
        ("test_purge_removes_stale_rows", test_purge_removes_stale_rows),
        ("test_detail_counts_first_view_only", test_detail_counts_first_view_only),
        ("test_detail_anonymous_does_not_increment",
         test_detail_anonymous_does_not_increment),
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
