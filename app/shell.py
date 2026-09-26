# -*- coding: utf-8 -*-
"""主窗口外壳：顶部栏 / 侧边导航 / 页面栈 / 世界频道面板 / 状态栏。

对外接口（页面与托盘都会用到）：

* :meth:`Shell.navigate` 打开路由（关闭页面时用 :meth:`Shell.go_back`）
* :meth:`Shell.handle_internal_url` 把站内 URL 映射成路由
* :meth:`Shell.refresh_user` 重拉登录态并刷新顶部用户区
* :meth:`Shell.on_config_changed` 配置变化（主题 / 导航模式 / 鼠标 / 桌宠）的响应
"""

from __future__ import annotations

import importlib
from urllib.parse import parse_qs, unquote, urlparse

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (QFrame, QLabel, QLineEdit, QMainWindow, QSizePolicy,
                             QSplitter, QStackedWidget, QStatusBar, QVBoxLayout,
                             QWidget)

from . import api as api_mod
from . import config, constants, icons, logger, theme, util
from .widgets import Chip, UserLink, button, hbox, vbox
from .widgets.images import Avatar
from .widgets.toast import ToastManager, toast
from .widgets.world_panel import WorldPanel

_log = logger.get_logger("shell")

# 导航项：(路由, 图标名, 文字)。图标名对应 resources/icons/<name>.svg，
# 由网页端同款 font-awesome@4.7.0 字形轮廓导出，两侧图形完全一致。
# 「下载」入口已从 APP 端移除（客户端本身就是下载产物，官网 /Download 已覆盖）。
NAV_ITEMS = (
    ("home", "home", "首页"),
    ("forum", "list", "论坛"),
    ("me", "user", "我的"),
    ("world", "globe", "世界"),
    ("wiki", "book", "WIKI"),
    ("easter_egg", "gift", "彩蛋"),
    ("settings", "cog", "设置"),
)

NAV_ICON_NAMES = {route: icon for route, icon, _label in NAV_ITEMS}

PAGE_MODULES = {
    "home": ("app.pages.home", "HomePage"),
    "forum": ("app.pages.forum", "ForumPage"),
    "post": ("app.pages.post_detail", "PostDetailPage"),
    "post_create": ("app.pages.post_create", "PostCreatePage"),
    "search": ("app.pages.search", "SearchPage"),
    "user": ("app.pages.user", "UserPage"),
    "me": ("app.pages.profile", "ProfilePage"),
    "world": ("app.pages.world", "WorldPage"),
    "wiki": ("app.pages.wiki", "WikiPage"),
    "auth": ("app.pages.auth", "AuthPage"),
    "settings": ("app.pages.settings", "SettingsPage"),
    "privacy": ("app.pages.misc", "PrivacyPage"),
    "huiguan": ("app.pages.misc", "HuiguanPage"),
    "easter_egg": ("app.pages.misc", "EasterEggPage"),
    "download": ("app.pages.download", "DownloadPage"),
}

NAV_WIDTH_COLLAPSED = 54
NAV_WIDTH_EXPANDED = 168
NAV_ICON_SIZE = 18    # 导航图标像素尺寸
NAV_ICON_BOX = 22     # 图标占位方框（保证折叠/展开时图标对齐）
NAV_ROW_HEIGHT = 38


class _NavRow(QWidget):
    """左侧导航的一行：**整行**都可点击（不再只有图标可点）。

    自带悬停 / 选中态，并向外广播 ``state_changed`` 供图标重新着色。
    """

    clicked = pyqtSignal()
    state_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NavRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(NAV_ROW_HEIGHT)
        self._active = False
        self._hover = False

    def is_active(self) -> bool:
        return self._active

    def is_hovered(self) -> bool:
        return self._hover

    def set_active(self, active: bool) -> None:
        active = bool(active)
        if active == self._active:
            return
        self._active = active
        self._sync()

    def _sync(self) -> None:
        self.setProperty("hover", "true" if self._hover else "false")
        self.setProperty("active", "true" if self._active else "false")
        theme.restyle(self)
        self.state_changed.emit()

    # ── 交互：整行响应鼠标 ──
    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and \
                self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._sync()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._sync()
        super().leaveEvent(event)


class SideNav(QFrame):
    """左侧导航。

    * 折叠态仅图标、展开态图标 + 文字；**整行**都可点击
    * 不再「悬停立即展开」：悬停 ``HOVER_EXPAND_MS`` 毫秒才展开，
      或直接点击展开按钮（点击后固定展开，鼠标离开不再自动收起）
    """

    navigate = pyqtSignal(str)
    expand_changed = pyqtSignal(bool)
    HOVER_EXPAND_MS = 2000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SideNav")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(NAV_WIDTH_COLLAPSED)
        self._expanded = False
        self._pinned = False          # 点击展开按钮后固定展开，鼠标离开不自动收起
        self._rows: dict[str, _NavRow] = {}
        self._texts: list[QLabel] = []
        self._icon_rows: list[tuple[QLabel, _NavRow]] = []

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(self.HOVER_EXPAND_MS)
        self._hover_timer.timeout.connect(self._on_hover_timeout)

        root = vbox(self, margins=(6, 8, 6, 8), spacing=4)
        self._toggle_row, self._toggle_icon = self._make_row(
            "angle-right", "收起", self.toggle)
        self._toggle_row.setToolTip("展开 / 收起导航")
        root.addWidget(self._toggle_row)
        root.addSpacing(4)

        for route, icon_name, label in NAV_ITEMS:
            row, _icon = self._make_row(
                icon_name, label, lambda r=route: self.navigate.emit(r))
            self._rows[route] = row
            root.addWidget(row)
        root.addStretch(1)

        self._extra_row = hbox(spacing=4)
        self._bug_btn = button("", "ghost", lambda: self.navigate.emit("__bug__"),
                               tooltip="反馈 Bug", icon="bug", icon_size=NAV_ICON_SIZE)
        self._extra_row.addWidget(self._bug_btn)
        self._about_label = QLabel("v%s" % constants.APP_VERSION)
        self._about_label.setProperty("muted", "true")
        self._about_label.hide()
        self._extra_row.addWidget(self._about_label)
        self._extra_row.addStretch(1)
        root.addLayout(self._extra_row)
        self.reload_theme()

    # ── 构建 ──
    def _make_row(self, icon_name: str, label: str, on_click) -> tuple[_NavRow, QLabel]:
        row = _NavRow(self)
        row.clicked.connect(on_click)
        layout = hbox(row, margins=(12, 0, 10, 0), spacing=10)
        icon = QLabel(row)
        icon.setObjectName("NavIcon")
        icon.setFixedSize(NAV_ICON_BOX, NAV_ICON_BOX)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setProperty("icon", icon_name)
        layout.addWidget(icon)
        text = QLabel(label, row)
        text.setObjectName("NavText")
        text.hide()
        layout.addWidget(text)
        layout.addStretch(1)
        self._texts.append(text)
        self._icon_rows.append((icon, row))
        row.state_changed.connect(lambda ic=icon, r=row: self._paint_icon(ic, r))
        return row, icon

    # ── 图标着色 ──
    def _paint_icon(self, label: QLabel, row: _NavRow) -> None:
        name = str(label.property("icon") or "")
        if not name:
            return
        palette = theme.palette()
        if row.is_active():
            color = palette["primary"]
        elif row.is_hovered():
            color = palette["text_primary"]
        else:
            color = palette["text_secondary"]
        label.setPixmap(icons.pixmap(name, NAV_ICON_SIZE, color))

    def reload_theme(self) -> None:
        """主题切换后按状态重绘所有图标。"""
        for icon, row in self._icon_rows:
            self._paint_icon(icon, row)
        palette = theme.palette()
        self._bug_btn.setIcon(icons.icon("bug", NAV_ICON_SIZE, palette["text_secondary"]))
        self._bug_btn.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))

    # ── 展开 / 收起 ──
    def is_expanded(self) -> bool:
        return self._expanded

    def _on_hover_timeout(self) -> None:
        if not self._pinned:
            self.set_expanded(True)

    def enterEvent(self, event) -> None:  # noqa: N802
        if not self._expanded:
            self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_timer.stop()
        # 光标移到子控件上时 Qt 也会给父控件发 LeaveEvent：仍在栏内就别收起
        if self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            super().leaveEvent(event)
            return
        if not self._pinned and self._expanded:
            self.set_expanded(False)
        super().leaveEvent(event)

    def set_expanded(self, expanded: bool) -> None:
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.setFixedWidth(NAV_WIDTH_EXPANDED if expanded else NAV_WIDTH_COLLAPSED)
        for text in self._texts:
            text.setVisible(expanded)
        self._toggle_icon.setProperty("icon", "angle-left" if expanded else "angle-right")
        self._paint_icon(self._toggle_icon, self._toggle_row)
        self._about_label.setVisible(expanded)
        self.expand_changed.emit(expanded)

    def toggle(self) -> None:
        """展开按钮：点击后固定展开，再点收起。"""
        self._hover_timer.stop()
        if self._pinned:
            self._pinned = False
            self.set_expanded(False)
        else:
            self._pinned = True
            self.set_expanded(True)

    # ── 高亮 ──
    def set_active(self, route: str) -> None:
        for key, row in self._rows.items():
            row.set_active(key == route)


class Shell(QMainWindow):
    """主窗口。"""

    theme_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Root")
        self.setWindowTitle("%s 客户端" % constants.APP_NAME)
        self.setMinimumSize(880, 600)

        self.config = config.current()
        self._pages: dict[str, QWidget] = {}
        self._history: list[tuple[str, dict]] = []
        self._current_spec: tuple[str, dict] = ("home", {})
        self._last_geometry: dict = {}
        self.pet_controller = None  # 由 main.py 注入（Live2D 桌宠）

        central = QWidget(self)
        self.setCentralWidget(central)
        root = vbox(central, margins=(0, 0, 0, 0), spacing=0)

        root.addWidget(self._build_topbar())

        middle = hbox(spacing=0)
        self.side_nav = SideNav(central)
        self.side_nav.navigate.connect(self._on_nav)
        self.side_nav.expand_changed.connect(self._on_nav_expand)
        middle.addWidget(self.side_nav)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        self.stack = QStackedWidget(self.splitter)
        self.splitter.addWidget(self.stack)
        self.world_panel = WorldPanel(self.splitter)
        self.world_panel.collapsed_changed.connect(self._on_world_collapsed)
        self.splitter.addWidget(self.world_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setCollapsible(1, True)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        middle.addWidget(self.splitter, 1)
        root.addLayout(middle, 1)

        status = QStatusBar(self)
        self.setStatusBar(status)
        self.status_label = QLabel("就绪")
        status.addWidget(self.status_label, 1)
        self.version_label = QLabel("v%s" % constants.APP_VERSION)
        self.version_label.setProperty("muted", "true")
        status.addPermanentWidget(self.version_label)

        ToastManager.instance().set_host(self)

        self._restore_geometry()
        self._apply_nav_mode()
        self._apply_world_width()
        self.refresh_user()
        self.navigate("home", push_history=False)
        self.world_panel.start()

        api_mod.api().add_unauthorized_listener(self._on_unauthorized)

    # ────────────────────── 顶部栏 ──────────────────────
    def _build_topbar(self) -> QWidget:
        bar = QFrame(self)
        bar.setObjectName("TopBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setFixedHeight(58)
        layout = hbox(bar, margins=(12, 8, 12, 8), spacing=10)

        self.back_btn = button("", "ghost", self.go_back, tooltip="后退",
                               icon="angle-left", icon_size=16)
        self.back_btn.hide()
        layout.addWidget(self.back_btn)

        logo = QLabel()
        if constants.RES_LOGO.is_file():
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(str(constants.RES_LOGO))
            if not pixmap.isNull():
                logo.setPixmap(pixmap.scaled(
                    30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(logo)

        title = QLabel(constants.APP_NAME)
        title.setObjectName("TopBarTitle")
        layout.addWidget(title)

        self.top_nav = hbox(spacing=2)  # 「顶部模式」导航容器
        layout.addLayout(self.top_nav)
        layout.addStretch(1)

        self.search_input = QLineEdit(bar)
        self.search_input.setObjectName("TopSearch")
        self.search_input.setPlaceholderText("搜索帖子 / 用户…")
        self.search_input.setFixedWidth(260)
        self.search_input.returnPressed.connect(self._do_search)
        layout.addWidget(self.search_input)
        self.search_btn = button("", "ghost", self._do_search, tooltip="搜索",
                                 icon="search", icon_size=16)
        layout.addWidget(self.search_btn)

        self.create_btn = button("发帖", "primary",
                                 lambda: self.navigate("post_create"),
                                 icon="pencil", icon_size=15)
        layout.addWidget(self.create_btn)

        self.user_area = QWidget(bar)
        self.user_layout = hbox(self.user_area, margins=(0, 0, 0, 0), spacing=6)
        layout.addWidget(self.user_area)
        return bar

    def _build_top_nav(self) -> None:
        while self.top_nav.count():
            item = self.top_nav.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._top_nav_buttons: dict[str, QWidget] = {}
        for route, icon_name, label in NAV_ITEMS:
            btn = button(label, "ghost",
                         lambda _checked=False, r=route: self._on_nav(r),
                         icon=icon_name, icon_size=15)
            self._top_nav_buttons[route] = btn
            self.top_nav.addWidget(btn)

    # ────────────────────── 异步 ──────────────────────
    def run(self, fn, on_success=None, on_error=None, label: str = "") -> None:
        api_mod.run_async(fn, on_success=on_success,
                          on_error=on_error or (lambda m: self.set_status(m)),
                          label=label or "shell")

    # ────────────────────── 用户区 ──────────────────────
    def refresh_user(self, *, reload: bool = False) -> None:
        def _done(_result=None):
            self._render_user_area()
            self.world_panel.refresh_user()
            page = self.stack.currentWidget()
            if page is not None:
                checker = getattr(page, "refresh_auth", None)
                if callable(checker):
                    try:
                        checker()
                    except Exception:
                        pass

        if reload or not api_mod.api().user:
            self.run(api_mod.api().me, _done, lambda _m: self._render_user_area(),
                     label="登录态")
        else:
            _done()

    def _render_user_area(self) -> None:
        while self.user_layout.count():
            item = self.user_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        user = api_mod.api().user
        if user:
            avatar = Avatar(30)
            avatar.set_url(str(user.get("avatar") or ""))
            avatar.clicked.connect(lambda: self.navigate("me"))
            self.user_layout.addWidget(avatar)
            name = UserLink(str(user.get("id") or ""), str(user.get("name") or ""))
            name.activated.connect(lambda _uid: self.navigate("me"))
            self.user_layout.addWidget(name)
            title_text = str(user.get("title") or "").strip()
            if title_text:
                self.user_layout.addWidget(Chip(title_text, "title"))
            self.create_btn.show()
        else:
            login = button("登录", "primary", lambda: self.navigate("auth"))
            self.user_layout.addWidget(login)
        self._update_top_routes()

    def _update_top_routes(self) -> None:
        # 顶部导航按钮只在「顶部模式」下显示，否则会与左侧栏同时出现（默认 BUG）。
        top = self._nav_mode() == "top"
        for route, btn in getattr(self, "_top_nav_buttons", {}).items():
            need_login = route == "me"
            btn.setVisible(top and (not need_login or bool(api_mod.api().user)))

    # ────────────────────── 导航 ──────────────────────
    def _on_nav(self, route: str) -> None:
        if route == "__bug__":
            from .widgets.dialogs import BugReportDialog
            BugReportDialog(self, page_url=constants.BASE_URL).exec()
            return
        if route == "easter_egg":
            self.navigate("easter_egg", play=True)
            return
        self.navigate(route)

    def _on_nav_expand(self, expanded: bool) -> None:
        self.config.set("nav_expanded", bool(expanded), save=False)

    def navigate(self, route: str, *, push_history: bool = True, **kwargs) -> None:
        route = str(route or "home")
        if route not in PAGE_MODULES:
            _log.warning("未知路由：%s", route)
            route = "home"
        if push_history and self.stack.currentWidget() is not None:
            self._history.append(self._current_spec)
            self.back_btn.setVisible(True)
        self._show(route, kwargs)

    def _show(self, route: str, kwargs: dict) -> None:
        page = self._pages.get(route)
        keep_alive = True
        if page is not None:
            keep_alive = bool(getattr(page, "KEEP_ALIVE", True))
            if not keep_alive:
                self.stack.removeWidget(page)
                page.setParent(None)
                page.deleteLater()
                self._pages.pop(route, None)
                page = None
        if page is None:
            try:
                page = self._instantiate(route)
            except Exception as exc:  # noqa: BLE001
                _log.error("页面 %s 创建失败：%s", route, exc, exc_info=True)
                toast("页面加载失败：%s" % exc)
                return
            self._pages[route] = page
            self.stack.addWidget(page)
        self._current_spec = (route, dict(kwargs or {}))
        self.stack.setCurrentWidget(page)
        try:
            page.on_show(**(kwargs or {}))
        except Exception as exc:  # noqa: BLE001
            _log.error("页面 %s on_show 失败：%s", route, exc, exc_info=True)
        self._apply_chrome(page, route)

    def _instantiate(self, route: str):
        module_name, class_name = PAGE_MODULES[route]
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        return cls(shell=self)

    def _apply_chrome(self, page, route: str) -> None:
        show_world = bool(getattr(page, "SHOW_WORLD_PANEL", True))
        self.world_panel.set_page_visible(show_world)
        if show_world:
            if not self.world_panel.is_collapsed():
                self.world_panel.show()
        else:
            self.world_panel.hide()
        self.create_btn.setVisible(route != "auth" and bool(api_mod.api().user))
        title = getattr(page, "title_text", None)
        self.set_status(title() if callable(title) else "就绪")
        nav_route = route
        if route in ("post", "post_create", "search", "user"):
            nav_route = "forum" if route in ("post", "post_create") else ""
        elif route == "wiki":
            nav_route = "wiki"
        self.side_nav.set_active(nav_route)
        for key, btn in getattr(self, "_top_nav_buttons", {}).items():
            theme_active = "true" if key == nav_route else "false"
            if btn.property("active") != theme_active:
                btn.setProperty("active", theme_active)
                theme.restyle(btn)
        self._update_top_routes()

    def go_back(self) -> None:
        if not self._history:
            return
        route, kwargs = self._history.pop()
        self.back_btn.setVisible(bool(self._history))
        self._show(route, kwargs)

    @property
    def current_route(self) -> str:
        return self._current_spec[0]

    def current_page(self):
        return self.stack.currentWidget()

    # ────────────────────── 站内链接 ──────────────────────
    def handle_internal_url(self, href: str) -> bool:
        s = str(href or "").strip()
        if not s:
            return False
        if s.startswith(("http://", "https://")):
            parsed = urlparse(s)
            host = (parsed.netloc or "").lower()
            if host not in ("www.yjlt.top", "yjlt.top"):
                return False
            path = unquote(parsed.path or "/")
            query = parse_qs(parsed.query)
        elif s.startswith("/"):
            parsed = urlparse(s)
            path = unquote(parsed.path or "/")
            query = parse_qs(parsed.query)
        elif s.startswith("crforum://"):
            return self.handle_deeplink(s)
        else:
            return False

        stripped = path.rstrip("/") or "/"
        if stripped == "/":
            self.navigate("home")
            return True
        if stripped == "/forum":
            self.navigate("forum")
            return True
        if stripped == "/post/create":
            self.navigate("post_create")
            return True
        if stripped.startswith("/post/"):
            self.navigate("post", post_id=stripped.split("/")[2])
            return True
        if stripped.startswith("/users/"):
            self.navigate("user", user_id=stripped.split("/")[2])
            return True
        if stripped == "/search":
            self.navigate("search", keyword=(query.get("k") or [""])[0])
            return True
        if stripped in ("/World", "/world"):
            self.navigate("world")
            return True
        if stripped == "/privacy":
            self.navigate("privacy")
            return True
        if stripped.lower() == "/download":
            self.navigate("download")
            return True
        if stripped == "/Live2D":
            self.navigate("wiki", kind="live2d")
            return True
        if stripped.startswith("/INFO"):
            self.navigate("easter_egg", play=True)
            return True
        if stripped.startswith("/auth") or stripped in ("/login", "/register", "/reset-password"):
            mode = (query.get("mode") or ["login"])[0]
            if stripped == "/register":
                mode = "register"
            elif stripped == "/reset-password":
                mode = "reset"
            self.navigate("auth", mode=mode)
            return True
        wiki_routes = (
            ("/WIKI/Personal/mouse/Liunx", "mouse_linux"),
            ("/WIKI/Personal/mouse", "mouse"),
            ("/WIKI/Personal/Live2D", "live2d"),
            ("/WIKI/Personal", "personal"),
            ("/WIKI/GuanFang", "official"),
            ("/WIKI", "overview"),
        )
        for prefix, kind in wiki_routes:
            if stripped == prefix:
                self.navigate("wiki", kind=kind)
                return True
        return False

    def handle_deeplink(self, url: str) -> bool:
        from .deeplink import route_from_url
        route, kwargs = route_from_url(url)
        if not route:
            return False
        self.navigate(route, **kwargs)
        self.show_window()
        return True

    # ────────────────────── 搜索 ──────────────────────
    def _do_search(self) -> None:
        keyword = self.search_input.text().strip()
        if len(keyword) < 2:
            toast("请输入至少 2 个字符")
            return
        self.navigate("search", keyword=keyword)

    # ────────────────────── 世界面板 ──────────────────────
    def _on_world_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.world_panel.hide()
        else:
            page = self.stack.currentWidget()
            if page is not None and getattr(page, "SHOW_WORLD_PANEL", True):
                self.world_panel.show()
                self._apply_world_width()

    def _apply_world_width(self) -> None:
        width = int(self.config.get("world.width", constants.WORLD_WIDTH_DEFAULT) or
                    constants.WORLD_WIDTH_DEFAULT)
        width = max(constants.WORLD_WIDTH_MIN,
                    min(constants.WORLD_WIDTH_MAX, width))
        total = max(self.splitter.width(), width + 400)
        self.splitter.setSizes([total - width, width])

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        sizes = self.splitter.sizes()
        if len(sizes) < 2:
            return
        width = sizes[1]
        if constants.WORLD_WIDTH_MIN <= width <= constants.WORLD_WIDTH_MAX:
            self.config.set("world.width", int(width), save=False)
            self._geometry_dirty = True
            self._schedule_geometry_save()

    # ────────────────────── 状态栏 ──────────────────────
    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text or ""))

    # ────────────────────── 导航模式 ──────────────────────
    def _nav_mode(self) -> str:
        return str(self.config.get("nav_mode", "side") or "side")

    def _apply_nav_mode(self) -> None:
        top = self._nav_mode() == "top"
        if not getattr(self, "_top_nav_buttons", None):
            self._build_top_nav()
        self.side_nav.setVisible(not top)
        self._update_top_routes()

    # ────────────────────── 配置变化 ──────────────────────
    def on_config_changed(self, key: str) -> None:
        if key in ("theme", "*"):
            self.apply_theme()
        elif key == "nav_mode":
            self._apply_nav_mode()
        elif key == "world.width" or key == "*":
            self._apply_world_width()

    def apply_theme(self) -> None:
        from PyQt6.QtWidgets import QApplication
        effective = theme.apply(QApplication.instance(), self.config.theme)
        self.theme_changed.emit(effective)
        self._reload_icons()
        for page in self._pages.values():
            reloader = getattr(page, "reload_theme", None)
            if callable(reloader):
                try:
                    reloader()
                except Exception:
                    pass

    def _reload_icons(self) -> None:
        """按新主题重绘外壳自带的 SVG 图标（侧栏导航 / 顶栏按钮）。"""
        nav = getattr(self, "side_nav", None)
        reloader = getattr(nav, "reload_theme", None)
        if callable(reloader):
            try:
                reloader()
            except Exception:
                pass
        palette = theme.palette()
        specs = (
            ("back_btn", "angle-left", 16, "text_secondary"),
            ("search_btn", "search", 16, "text_secondary"),
            ("create_btn", "pencil", 15, "primary_text"),
        )
        for attr, name, size, color_key in specs:
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            try:
                btn.setIcon(icons.icon(name, size, palette[color_key]))
                btn.setIconSize(QSize(size, size))
            except Exception:
                pass

    # ────────────────────── 登录失效 ──────────────────────
    def _on_unauthorized(self) -> None:
        if not self.isVisibleFromTray():
            return
        _log.info("登录状态已失效")
        self._render_user_area()
        self.world_panel.refresh_user()
        page = self.stack.currentWidget()
        guard = getattr(page, "on_unauthorized", None)
        if callable(guard):
            try:
                guard()
            except Exception:
                pass

    def isVisibleFromTray(self) -> bool:
        return True

    # ────────────────────── 窗口 ──────────────────────
    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _restore_geometry(self) -> None:
        geometry = self.config.get("window") or {}
        width = int(geometry.get("w") or 1180)
        height = int(geometry.get("h") or 760)
        self.resize(max(width, 880), max(height, 600))
        x, y = geometry.get("x"), geometry.get("y")
        if isinstance(x, int) and isinstance(y, int):
            self.move(x, y)
        if geometry.get("maximized"):
            self.showMaximized()

    def _schedule_geometry_save(self) -> None:
        if getattr(self, "_geometry_timer", None) is None:
            self._geometry_timer = QTimer(self)
            self._geometry_timer.setSingleShot(True)
            self._geometry_timer.setInterval(600)
            self._geometry_timer.timeout.connect(self.save_geometry)
        self._geometry_timer.start()

    def save_geometry(self) -> None:
        normal = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.config.update({
            "window.w": int(normal.width()),
            "window.h": int(normal.height()),
            "window.x": int(normal.x()),
            "window.y": int(normal.y()),
            "window.maximized": bool(self.isMaximized()),
        }, save=True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._schedule_geometry_save()

    def closeEvent(self, event) -> None:  # noqa: N802
        if getattr(self, "_force_close", False):
            self.save_geometry()
            self.world_panel.stop()
            self.config.save()
            event.accept()
            return
        # 默认收进托盘，不退出
        event.ignore()
        self.save_geometry()
        self.hide()
        toast("已最小化到系统托盘，双击托盘图标可恢复")

    def request_quit(self) -> None:
        self._force_close = True
        self.close()
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.quit()
