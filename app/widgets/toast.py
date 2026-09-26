# -*- coding: utf-8 -*-
"""轻提示（Toast）：浮动在主窗口顶部中央，2.2 秒自动消失。"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

TOAST_MS = 2200
MARGIN_TOP = 18
MAX_WIDTH = 560


class Toast(QWidget):
    """浮层提示控件（父控件内绝对定位）。"""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._label = QLabel(self)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_margin = 12
        self._label.setContentsMargins(layout_margin, 0, layout_margin, 0)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._host = host
        host.installEventFilter(self)
        self.hide()

    # ── 事件 ──
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._host and event.type() == QEvent.Type.Resize and self.isVisible():
            self._reposition()
        return False

    # ── 展示 ──
    def show_message(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        self._label.setText(text)
        self.adjustSize()
        self._reposition()
        self.raise_()
        self.show()
        self._timer.start(TOAST_MS)

    def _reposition(self) -> None:
        hint = self._label.sizeHint()
        width = min(max(hint.width() + 28, 140), MAX_WIDTH,
                    max(self._host.width() - 32, 140))
        # 换行后的高度：让 QLabel 在限定宽度下重新计算
        self._label.setFixedWidth(width - 24)
        height = max(self._label.sizeHint().height() + 22, 40)
        self.setGeometry((self._host.width() - width) // 2,
                         MARGIN_TOP, width, height)
        self._label.setGeometry(0, 0, width, height)


class ToastManager(QObject):
    """全局 Toast 管理器（绑定到一个宿主窗口）。"""

    _instance: "ToastManager | None" = None

    def __init__(self, host: QWidget | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._toast: Toast | None = None

    @classmethod
    def instance(cls) -> "ToastManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_host(self, host: QWidget) -> None:
        if self._toast is not None and self._toast.parent() is host:
            return
        if self._toast is not None:
            try:
                self._toast.setParent(None)
                self._toast.deleteLater()
            except Exception:
                pass
            self._toast = None
        if host is not None:
            self._toast = Toast(host)

    def show(self, text: str) -> None:
        if self._toast is None:
            return
        self._toast.show_message(text)


def toast(text: str) -> None:
    """模块级便捷函数（需先 :meth:`ToastManager.set_host`）。"""
    ToastManager.instance().show(text)
