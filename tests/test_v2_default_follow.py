"""V2 新用户默认关注官方账号（HG00000000000000000000）验收测试（契约先行）。

覆盖：
  P7 每个新用户在创建之初自动关注官方账号（config.DEFAULT_FOLLOW_USER_ID）。
     该动作必须「尽力而为」：可配置关闭、不关注自己、失败不阻断注册。

行为测试通过 monkeypatch 替换 execute_insert 完成，不会触碰真实数据库。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PY = (ROOT / "config.py").read_text(encoding="utf-8")
USER_DB = (ROOT / "db" / "user.py").read_text(encoding="utf-8")

DEFAULT_FOLLOW_ID = "HG00000000000000000000"


# ── 静态契约：配置 + 调用点 + SQL ──
def test_p7_config_declares_default_follow_account():
    assert f'DEFAULT_FOLLOW_USER_ID = "{DEFAULT_FOLLOW_ID}"' in CONFIG_PY, \
        "config.py 未声明新用户默认关注的官方账号 DEFAULT_FOLLOW_USER_ID"


def test_p7_create_user_triggers_auto_follow_after_insert():
    assert "def _auto_follow_default(user_id" in USER_DB, "db/user.py 缺少 _auto_follow_default 定义"
    # 必须在写入 users 之后调用
    assert USER_DB.index("INSERT INTO users") < USER_DB.index("_auto_follow_default(user_id)"), \
        "create_user 未在写入用户后调用 _auto_follow_default"
    assert "_auto_follow_default(user_id)" in USER_DB


def test_p7_auto_follow_sql_is_idempotent_and_graceful():
    assert "INSERT INTO user_follows" in USER_DB, "未写入 user_follows 表"
    assert "ON CONFLICT (follower_id, following_id) DO NOTHING" in USER_DB, \
        "缺少 ON CONFLICT DO NOTHING：重复关注会抛唯一约束错误"
    assert "except Exception" in USER_DB, "自动关注异常未兜底，会影响注册主流程"


# ── 行为测试（mock execute_insert，不连数据库）──
def test_p7_new_user_follows_official_account():
    import db.user as user_mod

    calls = []
    orig_insert = user_mod.execute_insert
    orig_choice = user_mod.random.choice
    user_mod.execute_insert = lambda q, p=None: (calls.append((q, p)), 1)[1]
    user_mod.random.choice = lambda seq: seq[0]
    try:
        res = user_mod.create_user("契约测试用户", "p7_contract@example.com", "Abcd1234ef")
    finally:
        user_mod.execute_insert = orig_insert
        user_mod.random.choice = orig_choice

    assert res.get("success"), f"create_user 应返回成功: {res}"
    follow = [c for c in calls if "INSERT INTO user_follows" in c[0]]
    assert follow, "create_user 未写入 user_follows（新用户不会自动关注官方账号）"
    sql, params = follow[0]
    assert params == (res["id"], DEFAULT_FOLLOW_ID), f"关注参数错误: {params}"
    assert "ON CONFLICT" in sql


def test_p7_auto_follow_can_be_disabled_and_never_self_follows():
    import config
    import db.user as user_mod

    calls = []
    orig_insert = user_mod.execute_insert
    orig_target = getattr(config, "DEFAULT_FOLLOW_USER_ID", None)
    user_mod.execute_insert = lambda q, p=None: (calls.append(p), 1)[1]
    try:
        user_mod._auto_follow_default("RLAAAAAAAAAAAAAAAA")
        assert calls == [("RLAAAAAAAAAAAAAAAA", DEFAULT_FOLLOW_ID)], "默认应关注官方账号"

        config.DEFAULT_FOLLOW_USER_ID = ""
        calls.clear()
        user_mod._auto_follow_default("RLAAAAAAAAAAAAAAAA")
        assert calls == [], "DEFAULT_FOLLOW_USER_ID 为空时应关闭自动关注"

        config.DEFAULT_FOLLOW_USER_ID = "RLSELFSELFSELFSELF"
        calls.clear()
        user_mod._auto_follow_default("RLSELFSELFSELFSELF")
        assert calls == [], "不应关注自己"
    finally:
        user_mod.execute_insert = orig_insert
        if orig_target is not None:
            config.DEFAULT_FOLLOW_USER_ID = orig_target


def test_p7_auto_follow_swallows_db_errors():
    import db.user as user_mod

    orig_insert = user_mod.execute_insert

    def boom(q, p=None):
        raise RuntimeError("模拟外键/连接失败")

    user_mod.execute_insert = boom
    try:
        user_mod._auto_follow_default("RLBBBBBBBBBBBBBBBB")  # 不应抛异常
    finally:
        user_mod.execute_insert = orig_insert
