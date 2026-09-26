# -*- coding: utf-8 -*-
"""页面基类：所有业务页面的统一契约。

约定：

* 子类在 ``__init__`` 里先 ``super().__init__(shell=shell)``，再构建自己的控件
* 外部输入统一走 ``on_show(**kwargs)`` / ``on_hide()``，可在此处发起请求
* 所有阻塞调用用 :meth:`Page.run`（回调在主线程）
* 跳转用 :meth:`Page.go`，不要直接操作主窗口
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QWidget

from .. import api as api_mod
from .. import constants, logger, theme, util, yearmode
from ..widgets import (Card, EmptyHint, ScrollPage, TitleLabel, button, hbox, vbox)
from ..widgets.dialogs import (BugReportDialog, ExternalLinkDialog, ReportDialog, confirm)
from ..widgets.toast import toast

_log = logger.get_logger("pages")


class Page(QWidget):
    """页面基类。"""

    ROUTE = ""
    TITLE = ""
    SHOW_WORLD_PANEL = True
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.shell = shell
        self._active = False

    # ── 便捷访问 ──
    @property
    def api(self):
        return api_mod.api()

    #: 与 :attr:`api` 同义，写起来更短
    client = api

    @property
    def me(self) -> dict | None:
        return api_mod.api().user

    def title_text(self) -> str:
        return self.TITLE

    # ── 跳转 ──
    def go(self, route: str, **kwargs) -> None:
        if self.shell is not None:
            self.shell.navigate(route, **kwargs)

    def open_post(self, post_id: str) -> None:
        if post_id:
            self.go("post", post_id=str(post_id))

    def open_user(self, user_id: str) -> None:
        if user_id:
            self.go("user", user_id=str(user_id))

    def go_back(self) -> None:
        if self.shell is not None:
            self.shell.go_back()

    # ── 提示与弹窗 ──
    def toast(self, text: str) -> None:
        toast(text)

    def confirm(self, title: str, text: str, *, ok_text: str = "确定",
                cancel_text: str = "取消", danger: bool = False) -> bool:
        return confirm(self.window(), title, text, ok_text=ok_text,
                       cancel_text=cancel_text, danger=danger)

    def warn(self, text: str) -> None:
        self.toast(text)

    def need_login(self, tip: str = "请先登录") -> bool:
        """未登录时跳登录页并返回 False。"""
        if api_mod.api().user:
            return True
        self.toast(tip)
        self.go("auth")
        return False

    def report_dialog(self, kind: str, target_id: str) -> None:
        if not self.need_login("请先登录后再举报"):
            return
        ReportDialog(kind, target_id, self.window()).exec()

    def bug_report(self) -> None:
        BugReportDialog(self.window(), page_url=self.route_url()).exec()

    def route_url(self) -> str:
        return constants.BASE_URL + "/"

    # ── 链接 ──
    def open_link(self, href: str) -> None:
        """处理内容里的链接：站内跳转，站外先确认。"""
        href = str(href or "").strip()
        if not href:
            return
        if self.shell is not None and self.shell.handle_internal_url(href):
            return
        if util.is_external_link(href):
            ExternalLinkDialog(href, self.window()).exec()
        elif util.open_in_system(href):
            return

    # ── 异步 ──
    def run(self, fn, on_success=None, on_error=None, label: str = "") -> None:
        api_mod.run_async(fn, on_success=on_success,
                          on_error=on_error or (lambda m: self.toast(m)),
                          label=label or self.ROUTE)

    # ── 生命周期 ──
    def on_show(self, **kwargs) -> None:
        self._active = True

    def on_hide(self) -> None:
        self._active = False

    def reload_theme(self) -> None:
        """主题切换后刷新自定义绘制/文档样式。"""
        for child in self.findChildren(QWidget):
            reload = getattr(child, "reload_theme", None)
            if callable(reload):
                try:
                    reload()
                except Exception:
                    pass

    def apply_theme(self) -> None:
        self.reload_theme()

    # ── 便捷构建 ──
    def make_header(self, title: str, subtitle: str = "") -> tuple[QWidget, object]:
        """标题行（标题 + 副标题 + 右侧动作区）。"""
        box = QWidget(self)
        layout = vbox(box, margins=(0, 0, 0, 4), spacing=2)
        row = hbox(spacing=8)
        row.addWidget(TitleLabel(title))
        row.addStretch(1)
        box.actions = row
        # 同时挂到 layout 上：调用方不管解包出的是 widget 还是 layout，都能用 .actions
        layout.actions = row
        layout.addLayout(row)
        if subtitle:
            hint = QLabel(subtitle)
            hint.setProperty("muted", "true")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        return box, layout

    def make_card(self, parent: QWidget | None = None) -> Card:
        return Card(parent)


class ListPage(Page):
    """带滚动列表 / 空态 / 加载态 / 「加载更多」的页面骨架。"""

    load_more = pyqtSignal()

    def __init__(self, shell=None, parent: QWidget | None = None, *,
                 empty_text: str = "暂无内容", spacing: int = 10) -> None:
        super().__init__(shell, parent)
        self._root = vbox(self, margins=(0, 0, 0, 0), spacing=10)
        self.header_box = QWidget(self)
        self.header_layout = vbox(self.header_box, margins=(0, 0, 0, 0), spacing=8)
        self._root.addWidget(self.header_box)

        self.loading_hint = QLabel("加载中…")
        self.loading_hint.setObjectName("LoadingHint")
        self.loading_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_hint.hide()
        self._root.addWidget(self.loading_hint)

        self.scroll = ScrollPage(self, spacing=spacing)
        self._root.addWidget(self.scroll, 1)
        self._items_box = self.scroll.layout_box()

        self.empty_hint = EmptyHint(empty_text)
        self.empty_hint.hide()
        self._root.addWidget(self.empty_hint)

        self.more_btn = button("加载更多", None, self.request_more)
        self.more_btn.hide()
        more_row = hbox()
        more_row.addStretch(1)
        more_row.addWidget(self.more_btn)
        more_row.addStretch(1)
        self._root.addLayout(more_row)

        self.scroll.load_more.connect(self.request_more)
        self.scroll.set_load_more_enabled(True)

    # ── 列表操作 ──
    def request_more(self) -> None:
        if self.more_btn.isVisible() and self.more_btn.isEnabled():
            self.more_btn.setText("加载中…")
        self.load_more.emit()

    def clear_items(self) -> None:
        self.scroll.clear()

    def add_item(self, widget: QWidget) -> QWidget:
        return self.scroll.add(widget)

    def add_widget(self, widget: QWidget) -> QWidget:
        return self._root.addWidget(widget) if False else self.scroll.add(widget)

    def item_count(self) -> int:
        return max(self.scroll.layout_box().count() - 1, 0)

    # ── 状态 ──
    def set_loading(self, loading: bool, text: str = "加载中…") -> None:
        self.loading_hint.setText(text)
        self.loading_hint.setVisible(bool(loading))
        if loading:
            self.empty_hint.hide()

    def set_empty(self, text: str = "", *, visible: bool | None = None) -> None:
        if text:
            self.empty_hint.setText(text)
        self.empty_hint.setVisible(not self.item_count() if visible is None else visible)

    def set_has_more(self, has_more: bool, *, loading: bool = False) -> None:
        self.more_btn.setVisible(bool(has_more))
        self.more_btn.setEnabled(not loading)
        self.more_btn.setText("加载中…" if loading else "加载更多")
        self.scroll.set_busy(bool(loading))
        self.scroll.set_load_more_enabled(bool(has_more))

    def reset_scroll(self) -> None:
        self.scroll.scroll_to_top()
