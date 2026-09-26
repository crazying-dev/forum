# -*- coding: utf-8 -*-
"""首页：欢迎语 + 多个信息流（最新发布 / 随机推荐 / 综合排序），登录后多一个「我的收藏」。

对照 Web 端 HomeView.vue 与 AfterBody.js 的 ``initHome``：

* ``latest``        最新发布，分页加载（``/api/posts?sort=time``）
* ``random``        随机推荐，一次取满 200 条
* ``comprehensive`` 综合排序，一次取 100 条
* ``favorites``     我的收藏（仅登录后出现，一次取 20 条）
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from .. import constants
from ..widgets import (Muted, PostCard, TitleLabel, button, clear_layout, hbox,
                       set_active, vbox)
from .base import ListPage

_FEED_PAGE_SIZE = 20
_RANDOM_LIMIT = 200
_COMPREHENSIVE_LIMIT = 100
_FAVORITE_PAGE_SIZE = 20


class HomePage(ListPage):
    """首页信息流（路由 ``home``，开启世界频道侧栏）。"""

    ROUTE = "home"
    TITLE = "首页"
    SHOW_WORLD_PANEL = True
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell=shell, parent=parent, empty_text="暂无帖子")
        self._feed = "latest"
        self._page = 1
        self._busy = False
        self._has_more = False
        self._loaded = False
        self._chip_buttons: dict[str, QWidget] = {}
        self._build_header()
        self._paint_chips()
        self.load_more.connect(self._on_load_more)

    # ────────────────────── 头部 ──────────────────────
    def _build_header(self) -> None:
        head = QWidget(self)
        box = vbox(head, spacing=6)
        self._welcome = TitleLabel("首页")
        box.addWidget(self._welcome)
        self._hint = Muted("")
        box.addWidget(self._hint)
        chips_box = QWidget(head)
        self._chips = hbox(chips_box, spacing=6)
        box.addWidget(chips_box)
        self.header_layout.addWidget(head)

    def _paint_chips(self) -> None:
        """重建信息流 chip（登录状态变化时也会调用）。"""
        clear_layout(self._chips)
        self._chip_buttons = {}
        feeds = list(constants.HOME_FEEDS)
        if self.me:
            feeds.append(("favorites", "我的收藏", ""))
        for key, label, _url in feeds:
            btn = button(label, "chip", lambda _=False, k=key: self._select_feed(k))
            self._chip_buttons[key] = btn
            set_active(btn, key == self._feed)
            self._chips.addWidget(btn)
        self._chips.addStretch(1)
        name = str((self.me or {}).get("name") or "").strip()
        self._welcome.setText("欢迎回来，%s" % name if name else "首页")
        self._hint.setText("登录后可收藏与关注" if not name
                           else "切换上方信息流，点击帖子查看详情")

    def _select_feed(self, key: str) -> None:
        if key == self._feed and self._loaded:
            return
        self._feed = key
        self._paint_chips()
        self._reload()

    def refresh_auth(self) -> None:
        """登录状态变化后刷新头部（由 :meth:`Shell.refresh_user` 触发）。"""
        if self._feed == "favorites" and not self.me:
            self._feed = "latest"
        self._paint_chips()
        if self._feed == "favorites" and self.me and not self._loaded:
            self._reload()

    # ────────────────────── 加载 ──────────────────────
    def _reload(self) -> None:
        self._page = 1
        self._loaded = True
        self._has_more = False
        self._busy = False
        self.clear_items()
        self.reset_scroll()
        self.set_empty("", visible=False)
        self.set_has_more(False)
        self._load()

    def _on_load_more(self) -> None:
        """只有「最新发布」分页，其余信息流一次取完。"""
        if self._busy or not self._has_more or self._feed != "latest":
            return
        self._page += 1
        self.set_has_more(True, loading=True)
        self._load()

    def _request(self, page: int):
        """按当前信息流选择接口（URL 与 Web 端保持一致）。"""
        if self._feed == "random":
            return self.api.random_posts(_RANDOM_LIMIT)
        if self._feed == "comprehensive":
            return self.api.posts(page=1, page_size=_COMPREHENSIVE_LIMIT,
                                  sort="comprehensive")
        if self._feed == "favorites":
            uid = str((self.me or {}).get("id") or "")
            return self.api.user_favorites(uid, page=1, page_size=_FAVORITE_PAGE_SIZE)
        return self.api.posts(page=page, page_size=_FEED_PAGE_SIZE, sort="time")

    def _load(self) -> None:
        if self._busy:
            return
        page, feed = self._page, self._feed
        self._busy = True
        self.set_loading(True)

        def _done(result):
            self._busy = False
            if feed != self._feed:
                return
            self.set_loading(False)
            if not result.ok:
                self._load_failed(result.message)
                return
            posts = result.rows("posts")
            self._append(posts)
            self._has_more = feed == "latest" and len(posts) >= _FEED_PAGE_SIZE
            self.set_has_more(self._has_more)
            self.set_empty("暂无帖子", visible=self.item_count() == 0)

        self.run(lambda: self._request(page), _done, self._load_failed, "首页")

    def _append(self, posts: list) -> None:
        for post in posts:
            card = PostCard(post)
            card.open_post.connect(self.open_post)
            card.open_user.connect(self.open_user)
            self.add_item(card)

    def _load_failed(self, message: str) -> None:
        self._busy = False
        self._has_more = False
        self.set_loading(False)
        self.set_has_more(False)
        if message:
            self.toast(message)
        self.set_empty("加载失败，请稍后重试", visible=self.item_count() == 0)

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, **kwargs) -> None:
        super().on_show(**kwargs)
        self._paint_chips()
        if not self._loaded:
            self._reload()