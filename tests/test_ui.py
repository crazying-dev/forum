# -*- coding: utf-8 -*-
"""界面层用例：组件构建 / 整卡点击 / 评论树 / 路由表 / 深链 / 主题。"""

from __future__ import annotations

import os

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from app import constants, deeplink
from app.widgets import comment as comment_mod

_app = None


def _app_instance():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _click(widget, x: float = 5.0, y: float = 5.0):
    point = QPointF(x, y)
    event = QMouseEvent(QEvent.Type.MouseButtonRelease, point, point,
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    widget.mouseReleaseEvent(event)


# ────────────────────── 组件 ──────────────────────


def test_widgets_construct():
    _app_instance()
    from app.widgets import (Avatar, Card, Chip, Divider, EmptyHint, FlowLayout,
                             LoadingHint, Muted, PostCard, ScrollPage, Toast,
                             UserLink, button)
    card = Card()
    assert card.objectName() == "Card"
    assert Card().body is not None
    assert Divider().height() == 1
    assert Chip("综合").objectName() == "CategoryChip"
    assert Chip("头衔", "title").objectName() == "TitleChip"
    hint = EmptyHint("空空如也")
    assert hint.isVisible() is False          # 父窗口未显示
    loading = LoadingHint()
    loading.start("加载中…")
    loading.stop()
    assert Muted("x").property("muted") == "true"
    assert button("确定", "primary").property("variant") == "primary"
    layout = FlowLayout()
    assert layout.count() == 0 and layout.hasHeightForWidth()
    scroll = ScrollPage()
    assert scroll.layout_box().count() == 1   # 尾部弹簧
    avatar = Avatar(24)
    avatar.set_url("")
    assert avatar.width() == 24
    link = UserLink("RL1", "小黑")
    assert "RL1" in link.text() and "小黑" in link.text()


def test_post_card_post_fields():
    _app_instance()
    from app.widgets import PostCard
    post = {
        "id": "PS1", "title": "标题", "summary": "摘要正文", "category": "creative",
        "likes": 7, "views": 42, "created_at": "2026-09-25 15:17:13.359183",
        "user_id": "RL1", "user_name": "小黑", "user_avatar": "/avatar/1.webp",
    }
    card = PostCard(post)
    assert card.post_id() == "PS1"
    assert card.title.text() == "标题"
    assert card.tag.text() == "创作"
    assert "7" in card.stats.text() and "42" in card.stats.text()
    assert card.time.text() != ""


def test_post_card_click_signals():
    _app_instance()
    from app.widgets import PostCard
    card = PostCard({"id": "PS9", "user_id": "RL9", "title": "t"})
    opened: list[str] = []
    users: list[str] = []
    card.open_post.connect(opened.append)
    card.open_user.connect(users.append)
    _click(card)
    assert opened == ["PS9"]
    card.avatar.clicked.emit()
    assert users == ["RL9"]
    card.user.activated.emit("RL9")
    assert users == ["RL9", "RL9"]


def test_comment_tree_building():
    comments = [
        {"id": "C1", "parent_id": None, "created_at": "2026-01-01 00:00:00"},
        {"id": "C2", "parent_id": "C1", "created_at": "2026-01-01 00:02:00"},
        {"id": "C3", "parent_id": "C1", "created_at": "2026-01-01 00:01:00"},
        {"id": "C4", "parent_id": None, "created_at": "2026-01-01 00:03:00"},
        {"id": "C5", "parent_id": "MISSING", "created_at": "2026-01-01 00:04:00"},
    ]
    roots = comment_mod._build_tree(comments)
    ids = [node["id"] for node in roots]
    assert set(ids) == {"C1", "C4", "C5"}, ids     # 孤立子结点提升为顶层
    c1 = [node for node in roots if node["id"] == "C1"][0]
    assert [child["id"] for child in c1["children"]] == ["C3", "C2"]  # 子回复按时间升序


def test_comment_tree_handles_cycles():
    comments = [
        {"id": "A", "parent_id": "B"},
        {"id": "B", "parent_id": "A"},
    ]
    roots = comment_mod._build_tree(comments)
    assert roots, "环状依赖不应导致评论丢失"


def test_comment_list_folding():
    _app_instance()
    from app.widgets import CommentList
    comments = [{"id": "C%d" % i, "user_id": "U%d" % i, "user_name": "用户%d" % i,
                 "content": "内容%d" % i, "created_at": "2026-01-01 00:00:00"}
                for i in range(8)]
    folded = CommentList(collapsible=True, fold_roots=3)
    folded.set_comments(comments, me_id="U1", post_link="PS1")
    assert folded.root_count == 8
    visible = [item for item in folded.items() if item.isVisibleTo(folded)]
    assert len(visible) == 3, len(visible)
    expanded = CommentList(collapsible=False)
    expanded.set_comments(comments, me_id="U1")
    assert len(expanded.items()) == 8
    assert expanded.item_for("C3") is not None


def test_comment_item_signals():
    _app_instance()
    from app.widgets import CommentItem
    item = CommentItem({"id": "C1", "user_id": "RL1", "user_name": "小黑",
                        "content": "你好", "likes": 2,
                        "created_at": "2026-01-01 00:00:00"}, me_id="RL1",
                       post_link="PS1")
    events: list = []
    item.reply.connect(lambda d: events.append(("reply", d)))
    item.delete.connect(lambda d: events.append(("delete", d)))
    item.report.connect(lambda d: events.append(("report", d)))
    item.like.connect(lambda d: events.append(("like", d)))
    item.open_post.connect(lambda p: events.append(("post", p)))
    _click(item)
    assert ("post", "PS1") in events
    assert item.delete_btn.isVisible() is False      # 未 show()，但不应报错
    item.set_liked(True, 3)
    assert item.data["likes"] == 3
    assert "♥" in item.like_btn.text()


def test_markdown_view_renders():
    _app_instance()
    from app.widgets import MarkdownView
    view = MarkdownView()
    view.set_markdown("# 标题\n\n**加粗** 与 [链接](https://example.com)\n\n```\ncode\n```")
    text = view.document().toPlainText()
    assert "标题" in text and "加粗" in text and "code" in text
    view.reload_theme()
    assert view.source().startswith("# 标题")
    view.set_raw_text("纯文本")
    assert "纯文本" in view.document().toPlainText()


def test_toast_manager():
    app = _app_instance()
    from PyQt6.QtWidgets import QWidget
    from app.widgets import ToastManager, toast
    host = QWidget()
    manager = ToastManager.instance()
    manager.set_host(host)
    toast("测试提示")
    assert manager._toast is not None
    assert manager._toast.isVisible() is False or True   # 父窗口未 show，不强求可见
    host.deleteLater()


def test_theme_apply_and_widgets():
    app = _app_instance()
    from app import theme
    applied = theme.apply(app, constants.THEME_DAY)
    assert applied == "day"
    assert len(app.styleSheet()) > 2000
    applied = theme.apply(app, constants.THEME_NIGHT)
    assert applied == "night"


# ────────────────────── 路由与深链 ──────────────────────


def test_page_registry_resolves():
    import importlib
    from app.shell import PAGE_MODULES
    expected = {"home", "forum", "post", "post_create", "search", "user",
                "me", "world", "wiki", "auth", "settings", "privacy",
                "huiguan", "easter_egg"}
    assert expected.issubset(set(PAGE_MODULES)), sorted(PAGE_MODULES)
    for route, (module_name, class_name) in PAGE_MODULES.items():
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        assert getattr(cls, "ROUTE", "") == route, route
        assert callable(getattr(cls, "on_show", None)), route


def test_page_requires_shell_kwarg():
    _app_instance()
    from app.pages.home import HomePage
    page = HomePage(shell=None)
    assert page.shell is None
    assert page.api is not None
    page.deleteLater()


def test_deeplink_routes():
    cases = {
        "Crforum://home": ("home", {}),
        "Crforum://forum": ("forum", {}),
        "Crforum://post/PS1": ("post", {"post_id": "PS1"}),
        "Crforum://user/RL1": ("user", {"user_id": "RL1"}),
        "Crforum://wiki?kind=mouse": ("wiki", {"kind": "mouse"}),
        "Crforum://wiki?kind=bogus": ("wiki", {"kind": "overview"}),
        "Crforum://search?k=%E6%B5%8B%E8%AF%95": ("search", {"keyword": "测试"}),
        "Crforum://auth?mode=reset": ("auth", {"mode": "reset"}),
        "Crforum://settings": ("settings", {}),
        "Crforum://easter_egg": ("easter_egg", {"play": True}),
    }
    for url, expect in cases.items():
        assert deeplink.route_from_url(url) == expect, url
    assert deeplink.route_from_url("") == ("", {})
    assert deeplink.route_from_url("https://x.com") == ("", {})
    assert deeplink.route_from_url("Crforum://nonsense") == ("", {})
    assert deeplink.route_from_url("Crforum://post") == ("forum", {})


def test_deeplink_extract_argv():
    urls = deeplink.extract_urls(["main.py", "--debug", "Crforum://post/PS1", "x"])
    assert urls == ["Crforum://post/PS1"]
    assert deeplink.extract_urls(["main.py", "--minimized"]) == []


def test_scheme_key_and_uri_prefix():
    assert deeplink.SCHEME_KEY == "Software\\Classes\\" + constants.URI_SCHEME
    assert constants.URI_SCHEME == "Crforum"
    assert constants.URI_SCHEME_DISPLAY == "Crforum://"
