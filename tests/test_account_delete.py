"""回归：自助注销账号（隐私政策「你的权利 → 注销 / 删除」）。

覆盖：
  * POST /api/user/delete 路由与参数校验（登录 / confirm / mode / 身份验证）
  * 「密码 或 邮箱验证码」二选一的身份验证分支
  * 注销成功后清理登录 cookie
  * db.user.purge_user（彻底删除：账号 + 帖子 + 评论 + 点赞 + 收藏 +
    关注关系 + 举报 + Bug 反馈 + 世界频道发言）
  * db.user.anonymize_user（匿名化保留：占位用户名/邮箱 + 随机密码 +
    清空性别/年龄/简介/头衔 + deleted_at）
  * 已注销账号不可再登录；旧 token 失效
  * 发码接口 POST /api/email/send-delete-account-code
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, g  # noqa: E402

import config  # noqa: E402
import db  # noqa: E402
import db.user as user_db  # noqa: E402
import api.user as user_api  # noqa: E402
import api.email as email_api  # noqa: E402
import api.ratelimit as ratelimit  # noqa: E402
from api.encrypt import hash_password  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_captcha():
    """本文件聚焦注销业务逻辑；人机验证由 test_captcha.py 覆盖，这里一律关闭。"""
    old = config.CAPTCHA_ENABLED
    config.CAPTCHA_ENABLED = False
    try:
        yield
    finally:
        config.CAPTCHA_ENABLED = old


_REAL_PASSWORD = "Abcd1234"
_CONFIRM = config.DELETE_ACCOUNT_CONFIRM_TEXT


def _reset_ratelimit() -> None:
    ratelimit._records.clear()


def _make_app(me=None):
    """最小 Flask 应用：只注册 user 蓝图；me 非空时注入已登录的 g.user。"""
    _reset_ratelimit()
    app = Flask(__name__)
    app.register_blueprint(user_api.user_bp, url_prefix="/api/user")
    if me is not None:
        @app.before_request
        def _inject_user():  # noqa: ANN202
            g.user = dict(me)
    return app


def _logged_in_user():
    return {"id": "U1", "name": "测试", "email": "u1@example.com",
            "password": hash_password(_REAL_PASSWORD)}


# ────────────────────── 路由 / 参数校验 ──────────────────────

def test_delete_requires_login():
    """未登录调用注销接口 → 401，且不落库。"""
    app = _make_app(None)
    rv = app.test_client().post(
        "/api/user/delete", json={"mode": "purge", "confirm": _CONFIRM})
    assert rv.status_code == 401, "未登录应返回 401，实际 %s" % rv.status_code


def test_delete_route_registered():
    """注销路由已注册到 user 蓝图，且支持 POST。"""
    app = _make_app(_logged_in_user())
    rules = {str(r.rule): sorted(r.methods - {"HEAD", "OPTIONS"})
             for r in app.url_map.iter_rules()}
    assert "/api/user/delete" in rules, "缺少 /api/user/delete 路由"
    assert rules["/api/user/delete"] == ["POST"], \
        "注销接口方法应为 POST，实际 %s" % rules["/api/user/delete"]


def test_delete_rejects_wrong_confirm_phrase():
    """缺少/错误的确认口令 → 400，且不落库。"""
    called = []
    orig = user_db.purge_user
    orig_get = user_db.get_user_by_id
    user_db.get_user_by_id = lambda uid: _logged_in_user()
    user_db.purge_user = lambda uid: called.append(uid) or {"success": True}
    try:
        app = _make_app(_logged_in_user())
        rv = app.test_client().post(
            "/api/user/delete",
            json={"mode": "purge", "confirm": "确定", "password": _REAL_PASSWORD})
    finally:
        user_db.purge_user = orig
        user_db.get_user_by_id = orig_get
    assert rv.status_code == 400, "确认口令错误应 400，实际 %s" % rv.status_code
    assert _CONFIRM in rv.get_json()["message"], "错误提示应包含确认口令文案"
    assert not called, "校验未通过不得落库"


def test_delete_rejects_unknown_mode():
    """未知 mode → 400。"""
    orig_get = user_db.get_user_by_id
    user_db.get_user_by_id = lambda uid: _logged_in_user()
    try:
        app = _make_app(_logged_in_user())
        rv = app.test_client().post(
            "/api/user/delete",
            json={"mode": "whatever", "confirm": _CONFIRM, "password": _REAL_PASSWORD})
    finally:
        user_db.get_user_by_id = orig_get
    assert rv.status_code == 400, "未知 mode 应 400，实际 %s" % rv.status_code


def test_delete_rejects_wrong_password():
    """密码错误且无验证码 → 400，且不落库。"""
    called = []
    orig = user_db.purge_user
    orig_get = user_db.get_user_by_id
    user_db.get_user_by_id = lambda uid: _logged_in_user()
    user_db.purge_user = lambda uid: called.append(uid) or {"success": True}
    try:
        app = _make_app(_logged_in_user())
        rv = app.test_client().post(
            "/api/user/delete",
            json={"mode": "purge", "confirm": _CONFIRM, "password": "wrong-password"})
    finally:
        user_db.purge_user = orig
        user_db.get_user_by_id = orig_get
    assert rv.status_code == 400, "身份验证失败应 400，实际 %s" % rv.status_code
    assert not called, "身份验证失败不得落库"


# ────────────────────── 身份验证：密码 / 邮箱验证码 ──────────────────────

def test_delete_with_password_purge_clears_cookies():
    """密码验证 + 彻底删除：调用 purge_user 并清理 token/ID cookie。"""
    called = []
    orig_purge = user_db.purge_user
    orig_get = user_db.get_user_by_id
    user_db.get_user_by_id = lambda uid: _logged_in_user()
    user_db.purge_user = lambda uid: called.append(uid) or {
        "success": True, "mode": "purge"}
    try:
        app = _make_app(_logged_in_user())
        rv = app.test_client().post(
            "/api/user/delete",
            json={"mode": "purge", "confirm": _CONFIRM, "password": _REAL_PASSWORD})
        body = rv.get_json()
        cookies = rv.headers.getlist("Set-Cookie")
    finally:
        user_db.purge_user = orig_purge
        user_db.get_user_by_id = orig_get
    assert rv.status_code == 200, "应 200，实际 %s：%s" % (rv.status_code, body)
    assert body["success"] is True
    assert called == ["U1"], "应调用 purge_user('U1')，实际 %s" % called
    joined = " ".join(cookies)
    assert config.TOKEN_COOKIE_NAME + "=;" in joined or \
        config.TOKEN_COOKIE_NAME + '=""' in joined, "注销后应清理 token cookie"
    assert config.ID_COOKIE_NAME in joined, "注销后应清理 ID cookie"


def test_delete_with_email_code_anonymize():
    """邮箱验证码验证 + 匿名化：调用 anonymize_user。"""
    called = []
    orig_anon = user_db.anonymize_user
    orig_get = user_db.get_user_by_id
    orig_verify = email_api.verify_delete_account_code
    orig_consume = email_api.consume_delete_account_code
    user_db.get_user_by_id = lambda uid: _logged_in_user()
    user_db.anonymize_user = lambda uid: called.append(uid) or {
        "success": True, "mode": "anonymize", "name": "已注销用户"}
    email_api.verify_delete_account_code = lambda email, code: (True, "")
    email_api.consume_delete_account_code = lambda email, code: None
    try:
        app = _make_app(_logged_in_user())
        rv = app.test_client().post(
            "/api/user/delete",
            json={"mode": "anonymize", "confirm": _CONFIRM, "code": "123456"})
        body = rv.get_json()
    finally:
        user_db.anonymize_user = orig_anon
        user_db.get_user_by_id = orig_get
        email_api.verify_delete_account_code = orig_verify
        email_api.consume_delete_account_code = orig_consume
    assert rv.status_code == 200, "应 200，实际 %s：%s" % (rv.status_code, body)
    assert called == ["U1"], "应调用 anonymize_user('U1')"
    assert body.get("mode") == "anonymize"


# ────────────────────── db 层：彻底删除 ──────────────────────

def test_purge_user_deletes_all_related_rows():
    """purge_user 必须清除帖子/评论/点赞/收藏/关注/举报/Bug/世界频道/账号。"""
    sqls = []
    orig_exec = user_db.execute_query
    orig_get = user_db.get_user_by_id
    user_db.get_user_by_id = lambda uid: {
        "id": uid, "email": "u1@example.com", "password": "H"}

    def fake_exec(sql, params=None, **kwargs):
        sqls.append(" ".join(sql.split()))
        return 1

    user_db.execute_query = fake_exec
    try:
        res = user_db.purge_user("U1")
    finally:
        user_db.execute_query = orig_exec
        user_db.get_user_by_id = orig_get

    assert res.get("success") is True, "purge_user 应成功：%s" % res
    blob = " | ".join(sqls)
    for table in ("post_reports", "comment_reports", "comment_likes", "post_likes",
                  "post_favorites", "user_follows", "verify_tokens", "comments",
                  "world", "bug_reports", "verify_codes", "posts", "users"):
        assert "DELETE FROM %s" % table in blob, "purge_user 未清理 %s" % table
    assert sqls[-1].startswith("DELETE FROM users WHERE id"), \
        "最后一步应是删除 users 行，实际：%s" % sqls[-1]


def test_purge_user_rejects_unknown_user():
    """用户不存在 → 失败，不执行任何删除。"""
    sqls = []
    orig_exec = user_db.execute_query
    orig_get = user_db.get_user_by_id
    user_db.get_user_by_id = lambda uid: None
    user_db.execute_query = lambda sql, params=None, **kw: sqls.append(sql) or 1
    try:
        res = user_db.purge_user("NOPE")
    finally:
        user_db.execute_query = orig_exec
        user_db.get_user_by_id = orig_get
    assert res.get("success") is False
    assert not sqls, "用户不存在时不应执行任何删除"


# ────────────────────── db 层：匿名化保留 ──────────────────────

def test_anonymize_user_scrubs_identity():
    """匿名化：占位用户名/邮箱 + 随机密码 + 清空资料 + deleted_at。"""
    captured = {}
    orig_exec = user_db.execute_query
    orig_get = user_db.get_user_by_id
    orig_by_name = user_db.get_user_by_name
    user_db.get_user_by_id = lambda uid: {
        "id": uid, "name": "青深", "email": "old@example.com", "password": "H"}
    user_db.get_user_by_name = lambda name: None

    def fake_exec(sql, params=None, **kwargs):
        if "UPDATE users SET name" in sql:
            captured["sql"] = " ".join(sql.split())
            captured["params"] = params
        return 1

    user_db.execute_query = fake_exec
    try:
        res = user_db.anonymize_user("U1")
    finally:
        user_db.execute_query = orig_exec
        user_db.get_user_by_id = orig_get
        user_db.get_user_by_name = orig_by_name

    assert res.get("success") is True, "anonymize_user 应成功：%s" % res
    params = captured.get("params") or ()
    assert params, "未执行 UPDATE users"
    assert params[0] == config.DELETED_USER_NAME, \
        "用户名应改为 %s，实际 %s" % (config.DELETED_USER_NAME, params[0])
    assert params[1] == "deleted+u1@%s" % config.DELETED_USER_EMAIL_DOMAIN, \
        "邮箱应改为不可投递的占位地址，实际 %s" % params[1]
    assert params[2] and params[2] != "H", "密码应被替换为随机哈希"
    sql = captured["sql"]
    assert "deleted_at" in sql, "匿名化必须写入 deleted_at"
    assert "gender = 0" in sql and "intro = ''" in sql, "匿名化应清空个人资料"


def test_anonymize_user_uses_suffix_when_name_taken():
    """「已注销用户」已被占用时追加后缀，避免 UNIQUE 冲突。"""
    captured = {}
    orig_exec = user_db.execute_query
    orig_get = user_db.get_user_by_id
    orig_by_name = user_db.get_user_by_name
    user_db.get_user_by_id = lambda uid: {
        "id": uid, "name": "青深", "email": "old@example.com", "password": "H"}
    user_db.get_user_by_name = lambda name: {"id": "OTHER"}

    def fake_exec(sql, params=None, **kwargs):
        if "UPDATE users SET name" in sql:
            captured["params"] = params
        return 1

    user_db.execute_query = fake_exec
    try:
        user_db.anonymize_user("U1")
    finally:
        user_db.execute_query = orig_exec
        user_db.get_user_by_id = orig_get
        user_db.get_user_by_name = orig_by_name
    name = (captured.get("params") or [""])[0]
    assert name.startswith(config.DELETED_USER_NAME) and name != config.DELETED_USER_NAME, \
        "重名时应追加后缀，实际 %s" % name


# ────────────────────── 已注销账号不可再登录 ──────────────────────

def test_deleted_user_cannot_login():
    """带 deleted_at 的账号登录一律失败。"""
    orig_get = user_db.get_user_by_login_identifier
    user_db.get_user_by_login_identifier = lambda ident: {
        "id": "U1", "name": "已注销用户", "password": hash_password(_REAL_PASSWORD),
        "deleted_at": "2026-10-01 10:00:00", "is_banned": 0}
    try:
        assert user_db.LoginINFOTrueorFlase("已注销用户", _REAL_PASSWORD) is False
    finally:
        user_db.get_user_by_login_identifier = orig_get


def test_auth_middleware_rejects_deleted_cookie():
    """_authenticate_from_cookies 对已注销账号直接置 g.user=None（旧 cookie 失效）。"""
    src = (open(os.path.join(PROJECT_ROOT, "api", "user", "__init__.py"),
                encoding="utf-8").read())
    assert 'user.get("deleted_at")' in src, \
        "鉴权中间件未拒绝已注销账号的旧 cookie"


# ────────────────────── 发码接口 ──────────────────────

def test_send_delete_account_code_endpoint_exists():
    """销号验证码发码接口已实现且发给当前绑定邮箱。"""
    src = open(os.path.join(PROJECT_ROOT, "api", "email", "__init__.py"),
               encoding="utf-8").read()
    assert '/email/send-delete-account-code' in src, "缺少销号验证码发码接口"
    assert 'create_verify_code(email, code, "delete_account")' in src, \
        "销号验证码未使用 delete_account 用途落库"
    assert "def verify_delete_account_code" in src and \
        "def consume_delete_account_code" in src, "缺少销号验证码校验/消费助手"
    # 鉴权：发码接口必须要求登录
    marker = '@email_bp.route("/email/send-delete-account-code", methods=["POST"])'
    idx = src.index(marker)
    assert "@login_required" in src[idx:idx + 200], "销号验证码发码接口应要求登录"


def test_config_declares_delete_account_constants():
    """config 声明了注销相关常量与 users.deleted_at 列（幂等 ALTER）。"""
    assert config.DELETED_USER_NAME
    assert config.DELETED_USER_EMAIL_DOMAIN
    assert config.DELETE_ACCOUNT_CONFIRM_TEXT
    joined = " ".join(config.ALL_TABLE_SQL)
    assert "ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at" in joined, \
        "缺少 users.deleted_at 的幂等 ALTER"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
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
