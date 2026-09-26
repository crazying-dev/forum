# -*- coding: utf-8 -*-
"""图标（SVG）与导航外壳用例：图标覆盖 / 导航项 / 整行点击 / 悬停展开 / 导航模式。"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, QSize, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

_app = None


def _app_instance():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _release(widget, x: float, y: float):
    point = QPointF(x, y)
    event = QMouseEvent(QEvent.Type.MouseButtonRelease, point, point,
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    widget.mouseReleaseEvent(event)


class _FakeBtn:
    """仅记录可见性的占位按钮。"""

    def __init__(self):
        self.visible = None

    def setVisible(self, value):  # noqa: N802 - Qt 命名
        self.visible = bool(value)


class _FakeConfig:
    def __init__(self, mode):
        self._mode = mode

    def get(self, key, default=None):
        return self._mode if key == "nav_mode" else default


# ────────────────────── 图标 ──────────────────────


def test_icons_cover_nav_items():
    _app_instance()
    from app import icons
    from app.shell import NAV_ICON_NAMES, NAV_ITEMS
    assert NAV_ITEMS, "导航项不能为空"
    for route, icon_name, label in NAV_ITEMS:
        assert icon_name, route
        assert label, route
        assert icons.exists(icon_name), "缺少图标文件：%s.svg（%s）" % (icon_name, route)
    assert set(NAV_ICON_NAMES) == {r for r, _i, _l in NAV_ITEMS}


def test_nav_items_removed_download_entry():
    """APP 端移除「下载」导航入口，但 download 路由本身保留（深链 / 托盘仍可用）。"""
    from app.shell import NAV_ITEMS, PAGE_MODULES
    routes = [r for r, _i, _l in NAV_ITEMS]
    assert "download" not in routes, "APP 端应移除「下载」入口"
    assert routes[0] == "home" and routes[-1] == "settings"
    assert "download" in PAGE_MODULES


def test_icons_pixmap_and_cache():
    _app_instance()
    from app import icons
    pix = icons.pixmap("home", 18, "#2E4659")
    assert not pix.isNull()
    assert pix.width() >= 18            # 以 2 倍分辨率渲染
    icons.clear_cache()
    again = icons.pixmap("home", 18, "#2E4659")
    assert not again.isNull()
    assert icons.pixmap("__missing__").isNull()   # 未知图标返回空位图，不抛异常


def test_button_with_icon():
    _app_instance()
    from app.widgets import button
    btn = button("发帖", "primary", icon="pencil", icon_size=15)
    assert not btn.icon().isNull()
    assert btn.iconSize() == QSize(15, 15)
    assert button("发帖", "primary").icon().isNull()


# ────────────────────── 导航行 / 侧栏 ──────────────────────


def test_nav_row_whole_row_clickable():
    """整行（不再只有图标）都能点击；行外点击不触发。"""
    _app_instance()
    from app.shell import _NavRow
    row = _NavRow()
    row.resize(150, 38)
    hits: list[int] = []
    row.clicked.connect(lambda: hits.append(1))
    _release(row, 140.0, 10.0)          # 行右侧（图标之外）
    assert hits == [1]
    _release(row, 400.0, 10.0)          # 行外
    assert hits == [1]


def test_nav_row_active_and_hover_property():
    _app_instance()
    from app.shell import _NavRow
    row = _NavRow()
    assert row.is_active() is False and row.is_hovered() is False
    row.set_active(True)
    assert row.is_active() is True
    assert row.property("active") == "true"
    row.set_active(False)
    assert row.property("active") == "false"


def test_sidenav_hover_expand_delay():
    """悬停不再立即展开：计时器间隔 = 2000ms，到点才展开。"""
    _app_instance()
    from app.shell import SideNav
    assert SideNav.HOVER_EXPAND_MS == 2000
    nav = SideNav()
    assert nav._hover_timer.interval() == 2000
    assert nav.is_expanded() is False
    nav._on_hover_timeout()             # 模拟悬停满 2 秒
    assert nav.is_expanded() is True
    nav.deleteLater()


def test_sidenav_toggle_pins_expanded():
    """展开按钮：点击后固定展开，再点收起（不随鼠标离开自动收起）。"""
    _app_instance()
    from app.shell import SideNav
    nav = SideNav()
    assert nav.is_expanded() is False
    nav.toggle()
    assert nav.is_expanded() is True and nav._pinned is True
    nav.toggle()
    assert nav.is_expanded() is False and nav._pinned is False
    nav.deleteLater()


def test_sidenav_set_active_marks_row():
    _app_instance()
    from app.shell import SideNav
    nav = SideNav()
    nav.set_active("forum")
    assert nav._rows["forum"].is_active() is True
    assert nav._rows["home"].is_active() is False
    nav.deleteLater()


# ────────────────────── 导航模式（顶部 / 左侧） ──────────────────────


def test_update_top_routes_respects_nav_mode():
    """默认「左侧」模式不得显示顶部导航（修复顶栏 + 侧栏同时出现的 BUG）。"""
    _app_instance()
    from app import api as api_mod
    from app.shell import Shell

    class _Dummy:
        pass

    dummy = _Dummy()
    dummy._top_nav_buttons = {"home": _FakeBtn(), "me": _FakeBtn()}
    dummy._nav_mode = lambda: dummy.config.get("nav_mode", "side")

    api = api_mod.api()
    saved = getattr(api, "_user", None)
    try:
        api._user = None
        dummy.config = _FakeConfig("side")
        Shell._update_top_routes(dummy)
        assert all(b.visible is False for b in dummy._top_nav_buttons.values()), \
            "左侧模式下顶部导航必须隐藏"

        dummy.config = _FakeConfig("top")
        Shell._update_top_routes(dummy)
        assert dummy._top_nav_buttons["home"].visible is True
        assert dummy._top_nav_buttons["me"].visible is False    # 未登录

        api._user = {"id": "RL1", "name": "小黑"}
        Shell._update_top_routes(dummy)
        assert dummy._top_nav_buttons["me"].visible is True
    finally:
        api._user = saved


def test_nav_mode_helper_reads_config():
    from app.shell import Shell

    class _Dummy:
        pass

    dummy = _Dummy()
    dummy.config = _FakeConfig("side")
    assert Shell._nav_mode(dummy) == "side"
    dummy.config = _FakeConfig("top")
    assert Shell._nav_mode(dummy) == "top"
