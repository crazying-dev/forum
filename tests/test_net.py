# -*- coding: utf-8 -*-
"""网络层用例：Result 语义 / 会话持久化 / URL 拼接 / 异步回调（联网用例需 --online）。"""

from __future__ import annotations

import os
import tempfile
import threading

from app import api as api_mod
from app import constants, session_store

ONLINE = os.environ.get("CRFORUM_ONLINE") == "1"


# ────────────────────── Result 语义 ──────────────────────


def test_result_ok_without_success_field():
    """实测：/api/posts 不返回 success 字段，必须仍视为成功。"""
    res = api_mod.Result(200, {"posts": [], "page": 1, "page_size": 1})
    assert res.ok is True
    assert res.rows("posts") == []
    assert res.message == ""


def test_result_ok_with_bare_array():
    res = api_mod.Result(200, [{"sender_name": "a"}])
    assert res.ok is True
    assert isinstance(res.data, list)


def test_result_success_false_is_failure():
    res = api_mod.Result(200, {"success": False, "message": "昵称已占用"})
    assert res.ok is False
    assert res.message == "昵称已占用"


def test_result_http_errors():
    cases = {
        400: "请求失败（HTTP 400）",
        401: "请先登录",
        403: "没有权限",
        404: "内容不存在或已被删除",
        429: "操作过于频繁，请稍后再试",
        500: "服务器开小差了，请稍后再试",
    }
    for status, expect in cases.items():
        res = api_mod.Result(status, None)
        assert res.ok is False
        assert res.message == expect, (status, res.message)
    assert api_mod.Result(404, {"success": False, "message": "帖子不存在"}).message == "帖子不存在"
    assert api_mod.Result(400, {"message": "昵称太短"}).message == "昵称太短"


def test_generic_post_is_not_shadowed_by_endpoint():
    """回归：endpoint 方法不能叫 post/user 之类的名字，否则会覆盖通用请求方法。"""
    import inspect
    for name, expected in (("post", "path"), ("put", "path"), ("get", "path")):
        sig = inspect.signature(getattr(api_mod.ForumApi, name))
        assert expected in sig.parameters, (name, list(sig.parameters))
        assert "post_id" not in sig.parameters, name
    sig = inspect.signature(api_mod.ForumApi.get_post)
    assert "post_id" in sig.parameters


def test_result_network_error():
    res = api_mod.Result(0, None, api_mod.NET_ERROR_TEXT)
    assert res.ok is False
    assert res.message == api_mod.NET_ERROR_TEXT


def test_result_unauthorized_flag():
    assert api_mod.Result(401, None).is_unauthorized is True
    assert api_mod.Result(200, {}).is_unauthorized is False


def test_result_parse_error():
    res = api_mod.Result(200, None, api_mod.PARSE_ERROR_TEXT)
    assert res.ok is False
    assert res.message == api_mod.PARSE_ERROR_TEXT


# ────────────────────── URL 拼接 ──────────────────────


def test_url_building():
    client = api_mod.ForumApi(store=session_store.SessionStore(
        os.path.join(tempfile.mkdtemp(), "account.bin")))
    assert client.base == constants.BASE_URL
    assert client._url("/api/posts") == constants.BASE_URL + "/api/posts"
    assert client._url("api/posts") == constants.BASE_URL + "/api/posts"
    assert client._url("https://x.com/a") == "https://x.com/a"
    assert client._host() == "www.yjlt.top"


def test_get_filters_empty_params():
    client = api_mod.ForumApi(store=session_store.SessionStore(
        os.path.join(tempfile.mkdtemp(), "account.bin")))
    seen = {}

    def _fake_request(method, path, **kwargs):
        seen["method"] = method
        seen["path"] = path
        seen["params"] = kwargs.get("params")
        return api_mod.Result(200, {"posts": []})

    client.request = _fake_request  # type: ignore[assignment]
    client.posts(page=1, page_size=20, category=None, sort="")
    assert seen["params"] == {"page": 1, "page_size": 20}
    client.search("abc", type_="posts")
    assert seen["params"] == {"k": "abc", "page": 1, "page_size": 20, "type": "posts"}


def test_endpoint_paths():
    client = api_mod.ForumApi(store=session_store.SessionStore(
        os.path.join(tempfile.mkdtemp(), "account.bin")))
    calls: list[tuple] = []

    def _fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("json_body")))
        return api_mod.Result(200, {"success": True})

    client.request = _fake_request  # type: ignore[assignment]
    client.login("pw", name="n")
    client.register("n", "e@x.com", "pw", "123456")
    client.like_post("PS1")
    client.favorite_post("PS1")
    client.report_post("PS1", "广告垃圾", "x")
    client.delete_post("PS1")
    client.create_comment("PS1", "hi", "CM1")
    client.like_comment("CM1")
    client.delete_comment("CM1")
    client.report_comment("CM1", "a", "b")
    client.follow("RL1")
    client.world_send("hello")
    client.send_change_email_code("new@x.com")
    client.change_email("old", "new@x.com", "new")
    client.change_password("NewPass123", code="123456")
    paths = [c[1] for c in calls]
    assert "/api/user/login" in paths
    assert "/api/user/register" in paths
    assert "/api/posts/PS1/like" in paths
    assert "/api/posts/PS1/favorite" in paths
    assert "/api/posts/PS1/report" in paths
    assert "/api/posts/PS1/delete" in paths
    assert "/api/posts/PS1/comments/create" in paths
    assert "/api/comments/CM1/like" in paths
    assert "/api/comments/CM1/delete" in paths
    assert "/api/comments/CM1/report" in paths
    assert "/api/user/RL1/follow" in paths
    assert "/api/world/Send" in paths
    assert "/api/email/send-change-email-code" in paths
    assert "/api/user/email" in paths
    assert "/api/user/password" in paths
    login_body = [c[2] for c in calls if c[1] == "/api/user/login"][0]
    assert login_body == {"password": "pw", "name": "n"}
    pwd_body = [c[2] for c in calls if c[1] == "/api/user/password"][0]
    assert pwd_body["code"] == "123456" and pwd_body["new_password"] == "NewPass123"
    email_body = [c[2] for c in calls if c[1] == "/api/user/email"][0]
    assert email_body == {"old_code": "old", "email": "new@x.com", "code": "new"}


def test_user_property_is_not_shadowed_by_endpoint():
    """回归：api.user 必须是属性（当前用户），查别人的资料用 get_user()。"""
    client = api_mod.ForumApi(store=session_store.SessionStore(
        os.path.join(tempfile.mkdtemp(), "account.bin")))
    assert client.user is None
    assert not callable(client.user)
    assert callable(client.get_user)
    client._user = {"id": "RL1", "name": "n"}
    assert isinstance(client.user, dict) and client.user["id"] == "RL1"


# ────────────────────── 会话持久化 ──────────────────────


def test_session_store_round_trip():
    path = os.path.join(tempfile.mkdtemp(), "account.bin")
    store = session_store.SessionStore(path)
    assert store.has_credentials is False
    store.save({"token": "token---a.b---1700000000", "ID": "RL0000000000000001"},
               {"id": "RL0000000000000001", "name": "小黑"}, last_name="小黑")
    again = session_store.SessionStore(path)
    assert again.has_credentials is True
    assert again.user_id == "RL0000000000000001"
    assert again.user["name"] == "小黑"
    assert again.last_name == "小黑"
    raw = open(path, "rb").read()
    assert b"token---" not in raw, "凭证不能明文落盘"


def test_session_store_ignores_foreign_cookies():
    path = os.path.join(tempfile.mkdtemp(), "account.bin")
    store = session_store.SessionStore(path)
    store.save({"token": "t", "ID": "i", "other": "x"})
    assert session_store.SessionStore(path).cookies == {"token": "t", "ID": "i"}


def test_session_store_clear():
    path = os.path.join(tempfile.mkdtemp(), "account.bin")
    store = session_store.SessionStore(path)
    store.save({"token": "t", "ID": "i"}, {"id": "i"})
    store.clear()
    fresh = session_store.SessionStore(path)
    assert fresh.has_credentials is False and fresh.user is None
    assert not os.path.exists(path)


def test_session_store_survives_corrupt_file():
    path = os.path.join(tempfile.mkdtemp(), "account.bin")
    with open(path, "wb") as fh:
        fh.write(b"not a sealed blob")
    store = session_store.SessionStore(path)
    assert store.has_credentials is False


def test_session_expiry_estimate():
    path = os.path.join(tempfile.mkdtemp(), "account.bin")
    store = session_store.SessionStore(path)
    assert store.is_expired is True
    store.save({"token": "t", "ID": "i"})
    assert store.is_expired is False


# ────────────────────── 异步执行 ──────────────────────


def test_run_async_callback_on_main_thread():
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    main_thread = threading.current_thread().ident
    result = {}
    loop = QEventLoop()

    def _work():
        return (threading.current_thread().ident, 21 * 2)

    def _done(value):
        result["thread"] = value[0]
        result["value"] = value[1]
        result["callback_thread"] = threading.current_thread().ident
        loop.quit()

    api_mod.run_async(_work, _done, label="test")
    QTimer.singleShot(4000, loop.quit)
    loop.exec()
    assert result.get("value") == 42
    assert result.get("thread") != main_thread, "工作应在后台线程"
    assert result.get("callback_thread") == main_thread, "回调应在主线程"


def test_run_async_error_callback():
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    got = {}
    loop = QEventLoop()

    def _work():
        raise RuntimeError("boom")

    def _fail(message):
        got["message"] = message
        loop.quit()

    api_mod.run_async(_work, None, _fail, label="test-error")
    QTimer.singleShot(4000, loop.quit)
    loop.exec()
    assert "boom" in got.get("message", "")


def test_download_reports_error_for_bad_url():
    client = api_mod.ForumApi(store=session_store.SessionStore(
        os.path.join(tempfile.mkdtemp(), "account.bin")))
    target = os.path.join(tempfile.mkdtemp(), "out.bin")
    res = client.download("https://127.0.0.1:1/none", target, timeout=(1, 2))
    assert res.ok is False
    assert res.message
    assert not os.path.exists(target)


# ────────────────────── 在线用例（--online）──────────────────────


def test_online_endpoints():
    if not ONLINE:
        return
    client = api_mod.ForumApi()
    health = client.healthz()
    assert health.ok, health.message
    posts = client.posts(page=1, page_size=3)
    assert posts.ok and posts.rows("posts"), posts.message
    world = client.world_all()
    assert isinstance(world.data, list)
    assert client.easter_egg().ok
    assert client.huiguan().ok
    assert client.search("test", page_size=3).ok
    assert client.get_user(constants.DEFAULT_FOLLOW_USER_ID).ok
    assert client.get("/INFO").ok is False          # 服务端已知 500，必须优雅降级


def test_online_write_path_reaches_server():
    """验证写操作真的打到了正确的端点（而不是被同名方法顶掉的错误路径）。

    用错误密码登录：应返回 400/401，而不是 404/405（后者说明路径写错了）。
    """
    if not ONLINE:
        return
    client = api_mod.ForumApi()
    result = client.login("definitely-not-a-real-password")
    assert result.ok is False
    assert result.status in (400, 401, 403, 404), result.status
    if result.status == 404:
        raise AssertionError("登录端点返回 404，说明请求路径不对")
    # 未登录时写操作应返回 401（而不是被当成帖子详情路径）
    bad = client.like_post("PS0000000000000000")
    assert bad.status in (400, 401, 403, 404), bad.status


def test_online_lpk_download():
    if not ONLINE:
        return
    from app.live2d.provider import Live2DProvider
    provider = Live2DProvider()
    path = provider.ensure()
    assert os.path.isfile(str(path))
    assert provider.is_ready()
