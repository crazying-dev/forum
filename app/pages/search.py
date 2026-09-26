# -*- coding: utf-8 -*-
"""搜索页：关键词 + 类型（帖子 / 用户 / 全部）→ ``/api/search``。

关键词少于 2 个字符时与后端一致地不发起请求，直接给出提示；
根据 ``posts_has_more`` / ``users_has_more`` 决定是否展示「加载更多」。
"""

from __future__ import annotations

from PyQt6.QtWidgets import QLineEdit, QWidget

from .. import constants
from ..widgets import (Avatar, CardTitle, PostCard, UserLink, button,
                       clear_layout, hbox, set_active, set_variant)
from .base import ListPage

_PAGE_SIZE = 20
_MIN_KEYWORD = 2


class SearchPage(ListPage):
    """搜索结果页（路由 ``search``，``on_show(keyword=...)``）。"""

    ROUTE = "search"
    TITLE = "搜索"
    SHOW_WORLD_PANEL = True
    KEEP_ALIVE = False

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell=shell, parent=parent, empty_text="输入关键词开始搜索")
        self._keyword = ""
        self._type = "both"
        self._page = 1
        self._busy = False
        self._has_more = False
        self._build_header()
        self.load_more.connect(self._on_load_more)

    # ────────────────────── 头部 ──────────────────────
    def _build_header(self) -> None:
        head, layout = self.make_header("搜索", "查找帖子与用户")
        row = hbox(spacing=6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("输入关键词，至少 2 个字符")
        self._input.returnPressed.connect(self._search)
        row.addWidget(self._input, 1)
        row.addWidget(button("搜索", "primary", self._search))
        layout.addLayout(row)
        chips_box = QWidget(head)
        self._chips = hbox(chips_box, spacing=6)
        layout.addWidget(chips_box)
        self.header_layout.addWidget(head)
        self._paint_chips()

    def _paint_chips(self) -> None:
        clear_layout(self._chips)
        for key, label in constants.SEARCH_TYPES:
            btn = button(label, "chip", lambda _=False, k=key: self._select_type(k))
            set_active(btn, key == self._type)
            self._chips.addWidget(btn)
        self._chips.addStretch(1)

    def _select_type(self, key: str) -> None:
        if key == self._type:
            return
        self._type = key
        self._paint_chips()
        if self._keyword:
            self._reload()

    def _search(self) -> None:
        """回车 / 点「搜索」触发；不足 2 个字符时不请求，直接提示。"""
        keyword = self._input.text().strip()
        self._keyword = keyword
        if len(keyword) < _MIN_KEYWORD:
            self._busy = False
            self.clear_items()
            self.set_loading(False)
            self.set_has_more(False)
            self.set_empty("请输入至少 2 个字符的关键词", visible=True)
            return
        self._reload()

    # ────────────────────── 加载 ──────────────────────
    def _reload(self) -> None:
        self._page = 1
        self._has_more = False
        self._busy = False
        self.clear_items()
        self.reset_scroll()
        self.set_empty("", visible=False)
        self.set_has_more(False)
        self._load()

    def _on_load_more(self) -> None:
        if self._busy or not self._has_more:
            return
        self._page += 1
        self.set_has_more(True, loading=True)
        self._load()

    def _load(self) -> None:
        if self._busy or len(self._keyword) < _MIN_KEYWORD:
            return
        page, keyword, type_ = self._page, self._keyword, self._type
        first = page == 1
        self._busy = True
        self.set_loading(True)

        def _done(result):
            self._busy = False
            if keyword != self._keyword or type_ != self._type:
                return
            self.set_loading(False)
            if not result.ok:
                self._load_failed(result.message)
                return
            posts = result.rows("posts")
            users = result.rows("users")
            if first and posts and type_ != "users":
                self.add_item(CardTitle("帖子（%s）" % result.get("posts_total", len(posts))))
            for post in posts:
                card = PostCard(post)
                card.open_post.connect(self.open_post)
                card.open_user.connect(self.open_user)
                self.add_item(card)
            if first and users and type_ != "posts":
                self.add_item(CardTitle("用户（%s）" % result.get("users_total", len(users))))
            for user in users:
                self.add_item(self._user_row(user))
            posts_more = type_ != "users" and bool(result.get("posts_has_more"))
            users_more = type_ != "posts" and bool(result.get("users_has_more"))
            self._has_more = posts_more or users_more
            self.set_has_more(self._has_more)
            self.set_empty("没有找到相关内容", visible=self.item_count() == 0)

        self.run(lambda: self.api.search(keyword, page=page, page_size=_PAGE_SIZE,
                                         type_=type_),
                 _done, self._load_failed, "搜索")

    # ────────────────────── 用户行 ──────────────────────
    def _user_row(self, user: dict) -> QWidget:
        uid = str(user.get("id") or "")
        row = QWidget()
        box = hbox(row, margins=(10, 8, 10, 8), spacing=8)
        avatar = Avatar(36)
        avatar.set_url(str(user.get("avatar") or ""))
        avatar.clicked.connect(lambda: self.open_user(uid))
        box.addWidget(avatar)
        name = UserLink(uid, str(user.get("name") or "匿名用户"))
        name.activated.connect(self.open_user)
        box.addWidget(name)
        box.addStretch(1)
        if uid and not self._is_self(uid):
            following = bool(user.get("is_following"))
            follow_btn = button("已关注" if following else "关注",
                                "ghost" if following else "primary")
            follow_btn.clicked.connect(
                lambda _=False, u=uid, w=follow_btn: self._toggle_follow(u, w))
            box.addWidget(follow_btn)
        return row

    def _is_self(self, user_id: str) -> bool:
        me = self.me or {}
        return bool(user_id) and str(me.get("id") or "") == user_id

    def _toggle_follow(self, user_id: str, btn) -> None:
        if not self.need_login("请先登录后再关注"):
            return
        btn.setEnabled(False)

        def _done(result):
            btn.setEnabled(True)
            if not result.ok:
                self.toast(result.message)
                return
            following = bool(result.get("following"))
            set_variant(btn, "ghost" if following else "primary")
            btn.setText("已关注" if following else "关注")
            self.toast("已关注" if following else "已取消关注")

        def _failed(message: str) -> None:
            btn.setEnabled(True)
            self.toast(message)

        self.run(lambda: self.api.follow(user_id), _done, _failed, "关注")

    def _load_failed(self, message: str) -> None:
        self._busy = False
        self._has_more = False
        self.set_loading(False)
        self.set_has_more(False)
        if message:
            self.toast(message)
        self.set_empty("加载失败，请稍后重试", visible=self.item_count() == 0)

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, keyword: str = "", **kwargs) -> None:
        super().on_show(**kwargs)
        keyword = str(keyword or "").strip()
        if keyword:
            self._input.setText(keyword)
            self._keyword = keyword
            self._reload()
        else:
            self._keyword = ""
            self.set_empty("输入关键词开始搜索", visible=True)