# -*- coding: utf-8 -*-
"""论坛列表页：分区 chip + 排序下拉 + 分页帖子列表（对照 Web 端 ForumView.vue）。

数据源 ``/api/posts?page=&page_size=20&category=&sort=``；
返回条数小于每页大小即视为没有更多。
"""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QWidget

from .. import constants
from ..widgets import PostCard, button, clear_layout, hbox, set_active
from .base import ListPage

_PAGE_SIZE = constants.PAGE_SIZE


class ForumPage(ListPage):
    """论坛分区列表（路由 ``forum``）。"""

    ROUTE = "forum"
    TITLE = "论坛"
    SHOW_WORLD_PANEL = True
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell=shell, parent=parent, empty_text="该分区暂无帖子")
        self._category = ""
        self._sort = "time"
        self._page = 1
        self._busy = False
        self._has_more = False
        self._loaded = False
        self._build_header()
        self.load_more.connect(self._on_load_more)

    # ────────────────────── 头部 ──────────────────────
    def _build_header(self) -> None:
        head, layout = self.make_header("论坛", "按分区浏览帖子")
        self._sort_box = QComboBox()
        for key, label in constants.FORUM_SORTS:
            self._sort_box.addItem(label, key)
        self._sort_box.currentIndexChanged.connect(self._on_sort_changed)
        head.actions.addWidget(self._sort_box)
        chips_box = QWidget(head)
        self._chips = hbox(chips_box, spacing=6)
        layout.addWidget(chips_box)
        self.header_layout.addWidget(head)
        self._paint_chips()

    def _paint_chips(self) -> None:
        clear_layout(self._chips)
        items = [("", "全部")] + [(key, constants.category_label(key))
                                  for key in constants.CATEGORY_ORDER]
        for key, label in items:
            btn = button(label, "chip", lambda _=False, k=key: self._select_category(k))
            set_active(btn, key == self._category)
            self._chips.addWidget(btn)
        self._chips.addStretch(1)

    def _select_category(self, key: str) -> None:
        if key == self._category:
            return
        self._category = key
        self._paint_chips()
        self._reload()

    def _on_sort_changed(self, index: int) -> None:
        key = self._sort_box.itemData(index) or "time"
        if key == self._sort:
            return
        self._sort = key
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
        if self._busy or not self._has_more:
            return
        self._page += 1
        self.set_has_more(True, loading=True)
        self._load()

    def _load(self) -> None:
        if self._busy:
            return
        page, category, sort = self._page, self._category, self._sort
        self._busy = True
        self.set_loading(True)

        def _done(result):
            self._busy = False
            if category != self._category or sort != self._sort:
                return
            self.set_loading(False)
            if not result.ok:
                self._load_failed(result.message)
                return
            posts = result.rows("posts")
            for post in posts:
                card = PostCard(post)
                card.open_post.connect(self.open_post)
                card.open_user.connect(self.open_user)
                self.add_item(card)
            self._has_more = len(posts) >= _PAGE_SIZE
            self.set_has_more(self._has_more)
            self.set_empty("该分区暂无帖子", visible=self.item_count() == 0)

        self.run(lambda: self.api.posts(page=page, page_size=_PAGE_SIZE,
                                        category=category or None, sort=sort),
                 _done, self._load_failed, "论坛列表")

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
        if not self._loaded:
            self._reload()