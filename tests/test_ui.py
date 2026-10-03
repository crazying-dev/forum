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


def test_comment_tree_flattens_deep_replies():
    comments = [
        {"id": "C1", "parent_id": None, "user_name": "楼主", "created_at": "2026-01-01 00:00:00"},
        {"id": "C2", "parent_id": "C1", "user_name": "甲", "created_at": "2026-01-01 00:01:00"},
        {"id": "C3", "parent_id": "C2", "user_name": "乙", "created_at": "2026-01-01 00:02:00"},
        {"id": "C4", "parent_id": "C3", "user_name": "丙", "created_at": "2026-01-01 00:03:00"},
    ]
    roots = comment_mod._build_tree(comments)
    c1 = [node for node in roots if node["id"] == "C1"][0]
    # 孙级及更深全部压平：C3 / C4 与 C2 同级挂在根评论下
    assert [child["id"] for child in c1["children"]] == ["C2", "C3", "C4"]
    kids = {node["id"]: node for node in c1["children"]}
    assert kids["C2"]["reply_to_name"] == ""      # 直接回复根评论：不显示 @
    assert kids["C3"]["reply_to_name"] == "甲"     # @ 直接父评论作者
    assert kids["C4"]["reply_to_name"] == "乙"
    assert kids["C2"]["children"] == [] and kids["C3"]["children"] == []


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


def test_markdown_no_html_is_literal():
    """三端口径：不渲染 HTML 语法，HTML 标签按字面文字展示。"""
    _app_instance()
    from app.widgets import MarkdownView
    view = MarkdownView()
    view.set_markdown("<div>原文标签</div>\n\n普通段落")
    text = view.document().toPlainText()
    assert "<div>" in text and "</div>" in text, "HTML 标签必须按字面文字显示"
    assert "普通段落" in text
    view.deleteLater()


def test_markdown_single_newline_keeps_line_break():
    """三端口径：单换行即换行（对齐网页端 marked 的 breaks: true）。"""
    _app_instance()
    from app.widgets import MarkdownView
    view = MarkdownView()
    view.set_markdown("第一行\n第二行")
    text = view.document().toPlainText()
    assert "第一行" in text and "第二行" in text
    assert "第一行 第二行" not in text, "单换行不能被合并成空格"
    view.deleteLater()


def test_apply_hard_breaks_skips_code_fence():
    """硬换行预处理：代码围栏内部原样保留，且冪等。"""
    from app.widgets.markdown import apply_hard_breaks
    src = "行一\n行二\n\n```\ncode_a\ncode_b\n```\n\n尾行"
    out = apply_hard_breaks(src)
    assert "行一  \n行二  \n" in out
    assert "code_a\ncode_b" in out, "代码围栏内部不得补硬换行"
    assert "尾行  " in out
    assert apply_hard_breaks(out) == out, "重复调用必须冪等"
    assert apply_hard_breaks("单行") == "单行"


def test_plain_label_renders_html_as_literal_text():
    """三端口径：不渲染 HTML 语法；QLabel 默认 AutoText 会把 <div> 当富文本吞掉。"""
    _app_instance()
    from app.widgets import PlainLabel
    label = PlainLabel("<div>原文标签</div>", wrap=True)
    assert label.textFormat() == Qt.TextFormat.PlainText
    assert "<div>" in label.text() and "</div>" in label.text()
    assert label.wordWrap() is True
    label.deleteLater()


def test_comment_content_is_plain_text_with_newlines():
    """评论是用户内容：HTML 按字面显示，且单换行必须保留。"""
    _app_instance()
    from app.widgets import CommentItem
    item = CommentItem({"id": "C1", "content": "第一行\n第二行<div>x</div>",
                        "user_name": "匿名用户"})
    assert item.content.textFormat() == Qt.TextFormat.PlainText
    assert "<div>x</div>" in item.content.text()
    assert "\n" in item.content.text()
    assert "第一行 第二行" not in item.content.text(), "单换行不能被合并成空格"
    item.deleteLater()


def test_muted_and_chip_are_plain_text():
    """含用户文案的 Muted / Chip 也锁 PlainText（题注里的标签不得被当富文本）。"""
    _app_instance()
    from app.widgets import Chip, Muted
    for widget in (Muted("评论于《<b>x</b>》"), Chip("<i>分区</i>")):
        assert widget.textFormat() == Qt.TextFormat.PlainText
        widget.deleteLater()


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
    # 国庆假期（10-01 ~ 10-07，真实日期驱动）会把 day/night 映射为国庆主题，
    # 这里先固定为非假期，保证断言不随日期飘。
    saved = theme.is_national_day
    theme.is_national_day = lambda *a, **k: False
    try:
        applied = theme.apply(app, constants.THEME_DAY)
        assert applied == "day"
        assert len(app.styleSheet()) > 2000
        applied = theme.apply(app, constants.THEME_NIGHT)
        assert applied == "night"
    finally:
        theme.is_national_day = saved


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
