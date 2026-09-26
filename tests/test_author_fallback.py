# -*- coding: utf-8 -*-
"""个人主页帖子作者兜底（``with_author``）的离线用例。

背景：历史接口 ``/api/user/<id>/posts`` 不返回 ``user_id`` /
``user_name`` / ``user_avatar``，导致「我的帖子」显示成匿名用户 +
默认头像。客户端在 ``PostCard`` 之前补一层 ``with_author`` 兜底。

不依赖 pytest 夹具：``tests/run_tests.py`` 以无参形式逐个调用用例函数。
"""

from __future__ import annotations

import inspect
import types

from app.pages.profile import ProfilePage
from app.pages.user import UserPage
from app.widgets import with_author
from app.widgets.post_card import with_author as _with_author_direct


# ────────────────────── with_author 本体 ──────────────────────


def test_with_author_exported_from_widgets():
    assert with_author is _with_author_direct


def test_with_author_fills_all_missing_fields():
    post = {"id": "p1", "title": "标题"}
    got = with_author(post, user_id="u1", name="阿黎", avatar="a.png")
    assert got["user_id"] == "u1"
    assert got["user_name"] == "阿黎"
    assert got["user_avatar"] == "a.png"
    assert got["title"] == "标题"


def test_with_author_keeps_existing_values():
    post = {"id": "p1", "user_id": "real", "user_name": "真名",
            "user_avatar": "real.png"}
    got = with_author(post, user_id="u1", name="阿黎", avatar="a.png")
    assert got["user_id"] == "real"
    assert got["user_name"] == "真名"
    assert got["user_avatar"] == "real.png"


def test_with_author_does_not_mutate_input():
    post = {"id": "p1"}
    with_author(post, user_id="u1", name="阿黎", avatar="a.png")
    assert post == {"id": "p1"}


def test_with_author_ignores_blank_defaults():
    post = {"id": "p1"}
    got = with_author(post, user_id="", name="", avatar="")
    assert "user_id" not in got
    assert "user_name" not in got
    assert "user_avatar" not in got


def test_with_author_treats_blank_values_as_missing():
    post = {"id": "p1", "user_name": "   "}
    got = with_author(post, user_id="u1", name="阿黎", avatar="a.png")
    assert got["user_name"] == "阿黎"
    assert got["user_id"] == "u1"


def test_with_author_accepts_none_like_post():
    assert with_author(None) == {}
    assert with_author({}, user_id="u1") == {"user_id": "u1"}


# ────────────────────── 页面兜底数据源 ──────────────────────


def test_user_page_author_defaults_uses_loaded_user():
    stub = types.SimpleNamespace(_user={"id": "u9", "name": "阿黎",
                                        "avatar": "a.png"},
                                 _user_id="u9")
    stub._author_defaults = types.MethodType(UserPage._author_defaults, stub)
    defaults = stub._author_defaults()
    assert defaults == {"user_id": "u9", "name": "阿黎", "avatar": "a.png"}


def test_user_page_author_defaults_falls_back_to_user_id():
    stub = types.SimpleNamespace(_user={}, _user_id="u9")
    stub._author_defaults = types.MethodType(UserPage._author_defaults, stub)
    defaults = stub._author_defaults()
    assert defaults["user_id"] == "u9"
    assert defaults["name"] == ""
    assert defaults["avatar"] == ""


def test_profile_page_author_defaults_prefers_profile_user():
    stub = types.SimpleNamespace(_user={"id": "u1", "name": "本人",
                                        "avatar": "me.png"},
                                 me={"id": "u1", "name": "旧",
                                     "avatar": "old.png"},
                                 _me_id=lambda: "u1")
    stub._author_defaults = types.MethodType(ProfilePage._author_defaults, stub)
    assert stub._author_defaults() == {"user_id": "u1", "name": "本人",
                                       "avatar": "me.png"}


def test_profile_page_author_defaults_falls_back_to_me():
    stub = types.SimpleNamespace(_user={},
                                 me={"id": "u1", "name": "本人",
                                     "avatar": "me.png"},
                                 _me_id=lambda: "u1")
    stub._author_defaults = types.MethodType(ProfilePage._author_defaults, stub)
    assert stub._author_defaults() == {"user_id": "u1", "name": "本人",
                                       "avatar": "me.png"}


def test_profile_page_author_defaults_falls_back_to_me_id():
    stub = types.SimpleNamespace(_user={}, me={}, _me_id=lambda: "u7")
    stub._author_defaults = types.MethodType(ProfilePage._author_defaults, stub)
    assert stub._author_defaults() == {"user_id": "u7", "name": "",
                                       "avatar": ""}


# ────────────────────── 卡片构建接入 ──────────────────────


def test_user_page_own_post_widget_injects_author():
    captured: dict = {}
    stub = types.SimpleNamespace(_user={"id": "u9", "name": "阿黎",
                                        "avatar": "a.png"},
                                 _user_id="u9")
    stub._author_defaults = types.MethodType(UserPage._author_defaults, stub)
    stub._build_post_widget = lambda post: captured.update(post) or "widget"
    out = UserPage._build_own_post_widget(stub, {"id": "p1", "title": "T"})
    assert out == "widget"
    assert captured["user_id"] == "u9"
    assert captured["user_name"] == "阿黎"
    assert captured["user_avatar"] == "a.png"


def test_profile_page_own_post_widget_injects_author():
    captured: dict = {}
    stub = types.SimpleNamespace(_user={"id": "u1", "name": "本人",
                                        "avatar": "me.png"},
                                 me={}, _me_id=lambda: "u1")
    stub._author_defaults = types.MethodType(ProfilePage._author_defaults, stub)
    stub._build_post_widget = lambda post: captured.update(post) or "widget"
    out = ProfilePage._build_own_post_widget(stub, {"id": "p2"})
    assert out == "widget"
    assert captured["user_name"] == "本人"
    assert captured["user_avatar"] == "me.png"


def test_user_posts_pane_wired_to_own_post_widget():
    src = inspect.getsource(UserPage._build_tabs)
    assert "posts_pane" in src
    assert "build_item=self._build_own_post_widget" in src
    assert "build_item=self._build_post_widget" in src  # 收藏页仍走普通卡片


def test_profile_posts_pane_wired_to_own_post_widget():
    src = inspect.getsource(ProfilePage._build_tabs)
    assert "posts_pane" in src
    assert "build_item=self._build_own_post_widget" in src


def test_own_post_widget_delegates_to_with_author():
    assert "with_author" in inspect.getsource(UserPage._build_own_post_widget)
    assert "with_author" in inspect.getsource(ProfilePage._build_own_post_widget)
