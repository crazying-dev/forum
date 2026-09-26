# -*- coding: utf-8 -*-
"""世界频道面板（右侧常驻，3 秒轮询）。

对照 Web 端 ``AfterBody.js::connectWorld``：

* 仅面板可见且窗口激活时轮询，否则停表（省流量）
* 失败指数退避：3s → 6s → 12s → 24s → 30s
* 消息最多保留 200 条，已发送高亮，发送后自动滚到底部
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                             QSizePolicy, QVBoxLayout, QWidget)

from .. import api as api_mod
from .. import config, constants, logger, theme, yearmode
from .common import button, hbox, vbox
from .images import Avatar
from .toast import toast

_log = logger.get_logger("world")


class WorldMessage(QFrame):
    """单条世界消息。"""

    def __init__(self, message: dict, mine: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorldMsg")
        self.setProperty("mine", "true" if mine else "false")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = hbox(self, margins=(8, 6, 8, 6), spacing=8)
        avatar = Avatar(26)
        avatar.set_url(str(message.get("sender_avatar") or ""))
        row.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
        body = vbox(spacing=2)
        name = QLabel(str(message.get("sender_name") or "匿名"))
        name.setObjectName("WorldName")
        body.addWidget(name)
        content = QLabel(str(message.get("content") or ""))
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        body.addWidget(content)
        time_label = QLabel(yearmode.fmt_time(message.get("created_at")))
        time_label.setObjectName("WorldTime")
        body.addWidget(time_label)
        row.addLayout(body, 1)


class WorldPanel(QFrame):
    """右侧世界频道面板。"""

    collapsed_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorldPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(0)

        self._client = api_mod.api()
        self._messages: list[dict] = []
        self._my_id = ""
        self._retry = 0
        self._busy = False
        self._collapsed = False
        self._started = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._poll)

        root = vbox(self, margins=(10, 10, 10, 10), spacing=8)

        header = hbox(spacing=6)
        title = QLabel("世界频道")
        title.setObjectName("WorldHeader")
        header.addWidget(title)
        self.status = QLabel("未连接")
        self.status.setObjectName("WorldStatus")
        header.addWidget(self.status)
        header.addStretch(1)
        self.open_btn = button("独立页", "ghost", self._open_page, tooltip="在新页面打开世界频道")
        header.addWidget(self.open_btn)
        self.collapse_btn = button("收起", "ghost", self.toggle_collapsed)
        header.addWidget(self.collapse_btn)
        root.addLayout(header)

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
        self.input.returnPressed.connect(self.send)
        composer.addWidget(self.input, 1)
        self.send_btn = button("发送", "primary", self.send)
        composer.addWidget(self.send_btn)
        root.addLayout(composer)

        self.refresh_user()

    # ── 生命周期 ──
    def start(self) -> None:
        self._started = True
        self._schedule(0)

    def stop(self) -> None:
        self._started = False
        self._timer.stop()

    def refresh_user(self) -> None:
        user = api_mod.api().user or {}
        self._my_id = str(user.get("id") or "")

    # ── 收起 ──
    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool, *, persist: bool = True,
                      notify: bool = True) -> None:
        collapsed = bool(collapsed)
        changed = collapsed != self._collapsed
        self._collapsed = collapsed
        self.collapse_btn.setText("展开" if collapsed else "收起")
        if persist:
            try:
                config.current().set("world.collapsed", collapsed)
            except Exception:
                pass
        if changed and notify:
            self.collapsed_changed.emit(collapsed)
        if collapsed:
            self._timer.stop()
        elif self._started:
            self._schedule(0)

    # ── 页面可见性 ──
    def set_page_visible(self, visible: bool) -> None:
        """由外壳告知“当前页面是否允许显示世界频道”。"""
        self._page_visible = bool(visible)
        if not visible:
            self._timer.stop()
        elif self._started and not self._collapsed:
            self._schedule(0)

    def _can_poll(self) -> bool:
        if not self._started or self._collapsed:
            return False
        if not self.isVisible() or self.width() <= 0:
            return False
        if not getattr(self, "_page_visible", True):
            return False
        window = self.window()
        if window is not None and window.isMinimized():
            return False
        return True

    # ── 轮询 ──
    def _schedule(self, delay_ms: int) -> None:
        if self._started:
            self._timer.start(max(0, int(delay_ms)))

    def _poll(self) -> None:
        if not self._can_poll():
            # 面板未显示 / 窗口最小化等原因先跳过；但必须把定时器挂回来，
            # 否则窗口恢复后就再也不会轮询了（世界频道“卡在未连接”的成因）。
            if self._started and not self._collapsed:
                self._schedule(constants.WORLD_IDLE_POLL_MS)
            return
        if self._busy:
            return
        self._busy = True

        def _work():
            return self._client.world_all()

        def _done(result):
            self._busy = False
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
                self._schedule(min(constants.WORLD_RETRY_MAX_MS,
                                   constants.WORLD_POLL_MS * (2 ** min(self._retry, 4))))

        def _fail(message):
            self._busy = False
            self._set_status("连接失败", "offline")
            self._retry += 1
            self._schedule(min(constants.WORLD_RETRY_MAX_MS,
                               constants.WORLD_POLL_MS * (2 ** min(self._retry, 4))))
            _log.info("世界频道轮询失败：%s", message)

        if not self._messages:
            self._set_status("连接中…", "")
        api_mod.run_async(_work, _done, _fail, label="世界频道")

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
                                   WorldMessage(message, mine))
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    # ── 发送 ──
    def send(self) -> None:
        content = self.input.text().strip()
        if not content:
            return
        if not api_mod.api().user:
            toast("请先登录")
            return
        self.input.clear()
        self.send_btn.setEnabled(False)

        def _work():
            return self._client.world_send(content)

        def _done(result):
            self.send_btn.setEnabled(True)
            if result.ok:
                self._retry = 0
                self._schedule(200)
            else:
                toast(result.message or "发送失败")

        api_mod.run_async(_work, _done,
                          lambda m: (self.send_btn.setEnabled(True), toast(m)),
                          label="发送世界消息")

    def _open_page(self) -> None:
        host = self.parent()
        while host is not None and not hasattr(host, "navigate"):
            host = host.parent()
        if host is not None:
            host.navigate("world")
