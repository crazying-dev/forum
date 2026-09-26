# -*- coding: utf-8 -*-
"""通用界面基元：卡片 / 分隔线 / 标签 / 按钮 / 流式布局 / 滚动页。"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QLayoutItem,
                             QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                             QWidget)

from .. import theme


# ────────────────────────── 布局快捷方式 ──────────────────────────


def vbox(parent: QWidget | None = None, margins=(0, 0, 0, 0),
         spacing: int = 8) -> QVBoxLayout:
    layout = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def hbox(parent: QWidget | None = None, margins=(0, 0, 0, 0),
         spacing: int = 8) -> QHBoxLayout:
    layout = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def clear_layout(layout) -> None:
    """清空布局内所有控件（保留布局本身）。"""
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child is not None:
            clear_layout(child)


# ────────────────────────── 基础控件 ──────────────────────────


class Card(QFrame):
    """白底圆角卡片。"""

    def __init__(self, parent: QWidget | None = None, *, padding=(14, 14, 14, 14),
                 spacing: int = 8) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = vbox(self, margins=padding, spacing=spacing)


class Divider(QFrame):
    """1px 分隔线。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def divider(parent: QWidget | None = None) -> Divider:
    return Divider(parent)


class Chip(QLabel):
    """小标签（分区 / 头衔）。"""

    def __init__(self, text: str = "", kind: str = "category",
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("CategoryChip" if kind == "category" else "TitleChip")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


def chip(text: str, kind: str = "category", parent: QWidget | None = None) -> Chip:
    return Chip(text, kind, parent)


class TitleLabel(QLabel):
    """页面主标题。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("PageTitle")


class CardTitle(QLabel):
    """卡片小标题。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("CardTitle")


class Muted(QLabel):
    """次要文字。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("muted", "true")


class ElidedLabel(QLabel):
    """超长自动加省略号的单行标签（完整内容进 tooltip）。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt 命名
        self._full = text or ""
        self.setToolTip(self._full if len(self._full) > 40 else "")
        super().setText(self._full)

    def full_text(self) -> str:
        return self._full

    def paintEvent(self, event) -> None:  # noqa: N802
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full, Qt.TextElideMode.ElideRight,
                                    max(self.width() - 2, 10))
        if elided != self.text():
            super().setText(elided)
        super().paintEvent(event)


class EmptyHint(QLabel):
    """空列表占位。"""

    def __init__(self, text: str = "暂无内容", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("EmptyHint")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        self.setVisible(bool(text))


class LoadingHint(QLabel):
    """加载中占位。"""

    def __init__(self, text: str = "加载中…", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("LoadingHint")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def start(self, text: str = "加载中…") -> None:
        self.setText(text)
        self.setVisible(True)

    def stop(self) -> None:
        self.setVisible(False)


def button(text: str, variant: str | None = None, on_click=None,
           parent: QWidget | None = None, *, tooltip: str = "",
           icon: str = "", icon_size: int = 16, icon_color: str = "") -> QPushButton:
    """主题化按钮；variant ∈ {None, 'primary', 'ghost', 'danger', 'chip'}。

    ``icon`` 为内置 SVG 图标名（见 :mod:`app.icons`，与网页端同形）；
    ``icon_color`` 缺省时按 variant 取主题色（primary 用 primary_text，
    其余用 text_secondary），保证与按钮前景色一致。
    """
    btn = QPushButton(text, parent)
    if variant:
        btn.setProperty("variant", variant)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        btn.setToolTip(tooltip)
    if icon:
        from .. import icons
        color = str(icon_color or "")
        if not color:
            palette = theme.palette()
            color = palette["primary_text" if variant == "primary" else "text_secondary"]
        btn.setIcon(icons.icon(icon, icon_size, color))
        btn.setIconSize(QSize(icon_size, icon_size))
    if on_click is not None:
        btn.clicked.connect(on_click)
    return btn


def ghost_button(text: str, on_click=None, parent: QWidget | None = None,
                 *, tooltip: str = "", icon: str = "", icon_size: int = 16) -> QPushButton:
    return button(text, "ghost", on_click, parent, tooltip=tooltip,
                  icon=icon, icon_size=icon_size)


def set_variant(widget: QWidget, variant: str | None) -> None:
    """运行时切换控件 variant 属性并重算样式。"""
    if variant:
        widget.setProperty("variant", variant)
    else:
        widget.setProperty("variant", None)
    theme.restyle(widget)


def set_active(widget: QWidget, active: bool) -> None:
    widget.setProperty("active", "true" if active else "false")
    theme.restyle(widget)


class UserLink(QLabel):
    """可点击的用户名（富文本链接，不阻塞父控件的整体点击）。"""

    activated = pyqtSignal(str)

    def __init__(self, user_id: str = "", name: str = "",
                 parent: QWidget | None = None, *, bold: bool = False) -> None:
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.linkActivated.connect(self._on_link)
        self._bold = bool(bold)
        self.set_user(user_id, name)

    def set_user(self, user_id: str, name: str) -> None:
        from .. import util
        uid = str(user_id or "")
        safe = util.html_escape(name or "匿名用户")
        color = theme.palette()["text_accent"]
        weight = "font-weight:700;" if self._bold else ""
        self.setText('<a href="cruser:%s" style="color:%s;text-decoration:none;%s">%s</a>'
                     % (util.html_escape(uid), color, weight, safe))

    def _on_link(self, href: str) -> None:
        if href.startswith("cruser:"):
            self.activated.emit(href[len("cruser:"):])


# ────────────────────────── 流式布局 ──────────────────────────


class FlowLayout(QLayout):
    """自动换行的水平布局（标签 / 按钮组用）。"""

    def __init__(self, parent: QWidget | None = None, margin: int = 0,
                 h_spacing: int = 6, v_spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h = h_spacing
        self._v = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(),
                            margins.top() + margins.bottom())

    def _layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(),
                                  -margins.right(), -margins.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h
            if next_x - self._h > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v
                next_x = x + hint.width() + self._h
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


# ────────────────────────── 滚动页 ──────────────────────────


class ScrollPage(QScrollArea):
    """纵向滚动容器；滚到底部附近时发 :attr:`load_more`。"""

    load_more = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, *, spacing: int = 10,
                 margins=(0, 0, 6, 0)) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content = QWidget()
        self._content.setObjectName("ScrollContent")
        self.vbox = vbox(self._content, margins=margins, spacing=spacing)
        self.vbox.addStretch(1)
        self.setWidget(self._content)
        self._load_more_enabled = False
        self._busy = False
        self.verticalScrollBar().valueChanged.connect(self._maybe_load_more)

    # ── 内容 ──
    @property
    def content(self) -> QWidget:
        return self._content

    def layout_box(self) -> QVBoxLayout:
        return self.vbox

    def add(self, widget: QWidget) -> QWidget:
        self.vbox.insertWidget(max(self.vbox.count() - 1, 0), widget)
        return widget

    def add_layout(self, layout) -> None:
        self.vbox.insertLayout(max(self.vbox.count() - 1, 0), layout)

    def clear(self) -> None:
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            child = item.layout()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            elif child is not None:
                clear_layout(child)
        self._busy = False

    # ── 加载更多 ──
    def set_load_more_enabled(self, enabled: bool) -> None:
        self._load_more_enabled = bool(enabled)

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)

    def _maybe_load_more(self, value: int) -> None:
        if not self._load_more_enabled or self._busy:
            return
        bar = self.verticalScrollBar()
        if bar.maximum() <= 0:
            return
        if value >= bar.maximum() - 160:
            self.load_more.emit()

    def scroll_to_top(self) -> None:
        self.verticalScrollBar().setValue(0)

    def scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
