# -*- coding: utf-8 -*-
"""世界频道独立页（``world`` 路由）。

与右侧常驻面板 :class:`app.widgets.world_panel.WorldPanel` 互斥：

* ``SHOW_WORLD_PANEL = False``，避免同一份消息渲染两遍
* ``on_show`` 启动轮询、``on_hide`` 停表；页面不可见时即使定时器意外触发也不再请求
* 失败指数退避：3s → 6s → 12s → 24s → 30s（对照 Web 端 ``WorldPageView.vue``）
* 后端未提供「在线人数」字段，状态行里如实标注为「无」
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QScrollArea, QWidget

from .. import api as api_mod
from .. import constants, logger, theme, yearmode
from ..widgets import UserLink, button, hbox, vbox
from ..widgets.images import Avatar
from .base import Page

_log = logger.get_logger("world_page")


class WorldMessageRow(QFrame):
    """单条世界消息（头像 + 昵称 + 内容 + 时间；自己的消息高亮）。"""

    def __init__(self, message: dict, mine: bool = False,
                 parent: QWidget | None = None, on_user=None) -> None:
        super().__init__(parent)
        self.setObjectName("WorldMsg")
        self.setProperty("mine", "true" if mine else "false")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        row = hbox(self, margins=(8, 6, 8, 6), spacing=8)
        sender_id = str(message.get("sender_id") or "")
        sender_name = str(message.get("sender_name") or "匿名")
        clickable = on_user is not None and bool(sender_id)
        avatar = Avatar(28)
        avatar.set_url(str(message.get("sender_avatar") or ""))
        if clickable:
            avatar.setToolTip("查看 %s 的主页" % sender_name)
            avatar.clicked.connect(lambda: on_user(sender_id))
        row.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        body = vbox(spacing=2)
        if clickable:
            name = UserLink(sender_id, sender_name)
            name.setObjectName("WorldName")
            name.activated.connect(on_user)
        else:
            name = QLabel(sender_name)
            name.setObjectName("WorldName")
        body.addWidget(name)
        content = QLabel(str(message.get("content") or ""))
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        body.addWidget(content)
        when = QLabel(yearmode.fmt_time(message.get("created_at")))
        when.setObjectName("WorldTime")
        body.addWidget(when)
        row.addLayout(body, 1)


class WorldPage(Page):
    """世界频道：全屏消息流 + 底部输入框 + 3 秒轮询。"""

    ROUTE = "world"
    TITLE = "世界频道"
    SHOW_WORLD_PANEL = False
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._messages: list[dict] = []
        self._my_id = ""
        self._retry = 0
        self._busy = False
        self._started = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._poll)

        root = vbox(self, margins=(12, 12, 12, 12), spacing=10)
        header, _ = self.make_header("世界频道", "全服实时消息，3 秒自动刷新")
        root.addWidget(header)

        status_row = hbox(spacing=8)
        self.status = QLabel("未连接")
        self.status.setObjectName("WorldStatus")
        status_row.addWidget(self.status)
        self.count_label = QLabel("在线人数：无（后端未提供）")
        self.count_label.setProperty("muted", "true")
        status_row.addWidget(self.count_label)
        status_row.addStretch(1)
        status_row.addWidget(button("刷新", "ghost", lambda: self._schedule(0)))
        root.addLayout(status_row)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._box = vbox(self._container, margins=(0, 0, 4, 0), spacing=4)
        self._box.addStretch(1)
        self.scroll.setWidget(self._container)
        root.addWidget(self.scroll, 1)

        self._empty = QLabel("暂无消息，快来抢沙发~")
        self._empty.setObjectName("EmptyHint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._empty)

        composer = hbox(spacing=6)
        self.input = QLineEdit(self)
        self.input.setObjectName("WorldInput")
        self.input.setMaxLength(constants.WORLD_MAX)
        self.input.setPlaceholderText("输入消息…（Enter 发送）")
        self.input.returnPressed.connect(self._send)
        composer.addWidget(self.input, 1)
        self.send_btn = button("发送", "primary", self._send)
        composer.addWidget(self.send_btn)
        root.addLayout(composer)

        self._refresh_identity()

    # ── 生命周期 ──
    def on_show(self, **kwargs) -> None:
        super().on_show(**kwargs)
        self._refresh_identity()
        self._started = True
        self._schedule(0)

    def on_hide(self) -> None:
        self._started = False
        self._timer.stop()
        super().on_hide()

    def refresh_auth(self) -> None:
        """登录态刷新后同步「自己」的身份，并重绘一次消息。"""
        self._refresh_identity()
        self._render()

    def _refresh_identity(self) -> None:
        user = self.api.user or {}
        self._my_id = str(user.get("id") or "")

    # ── 轮询 ──
    def _can_poll(self) -> bool:
        """仅在「已启动 + 页面可见 + 窗口未最小化」时轮询（对照 Web 端 visibilitychange）。"""
        if not self._started:
            return False
        if not self.isVisible() or self.width() <= 0:
            return False
        window = self.window()
        if window is not None and window.isMinimized():
            return False
        return True

    def _schedule(self, delay_ms: int) -> None:
        if self._started:
            self._timer.start(max(0, int(delay_ms)))

    def _backoff_ms(self) -> int:
        """失败退避：3s → 6s → 12s → 24s → 30s（封顶 30 秒）。"""
        return min(constants.WORLD_RETRY_MAX_MS,
                   constants.WORLD_POLL_MS * (2 ** min(max(self._retry - 1, 0), 5)))

    def _poll(self) -> None:
        if not self._can_poll() or self._busy:
            return
        self._busy = True
        if not self._messages:
            self._set_status("连接中…", "")

        def _done(result) -> None:
            self._busy = False
            if not self._can_poll():
                return
            if result.ok and isinstance(result.data, list):
                self._messages = [m for m in result.data[:constants.WORLD_LIMIT]
                                  if isinstance(m, dict)]
                self._render()
                self._set_status("在线", "online")
                self._retry = 0
                self._schedule(constants.WORLD_POLL_MS)
            else:
                self._set_status(result.message or "加载失败", "offline")
                self._retry += 1
                self._schedule(self._backoff_ms())

        def _fail(message: str) -> None:
            self._busy = False
            if not self._can_poll():
                return
            self._set_status("连接失败", "offline")
            self._retry += 1
            self._schedule(self._backoff_ms())
            _log.debug("世界频道轮询失败：%s", message)

        api_mod.run_async(lambda: self.api.world_all(), _done, _fail, label="世界频道")

    def _set_status(self, text: str, state: str) -> None:
        self.status.setText(text)
        self.status.setProperty("state", state)
        theme.restyle(self.status)

    # ── 渲染 ──
    def _render(self) -> None:
        while self._box.count() > 1:
            item = self._box.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if not self._messages:
            self._empty.show()
            return
        self._empty.hide()
        for message in reversed(self._messages):
            mine = bool(self._my_id) and str(message.get("sender_id") or "") == self._my_id
            self._box.insertWidget(max(self._box.count() - 1, 0),
                                   WorldMessageRow(message, mine, on_user=self.open_user))
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    # ── 发送 ──
    def _send(self) -> None:
        content = self.input.text().strip()
        if not content:
            return
        if not self.need_login("请先登录后在世界频道发言"):
            return
        self.input.clear()
        self.send_btn.setEnabled(False)

        def _done(result) -> None:
            self.send_btn.setEnabled(True)
            if result.ok:
                self._retry = 0
                self._schedule(200)
            else:
                self.toast(result.message or "发送失败")

        def _fail(message: str) -> None:
            self.send_btn.setEnabled(True)
            self.toast(message)

        api_mod.run_async(lambda: self.api.world_send(content), _done, _fail,
                          label="发送世界消息")

