# -*- coding: utf-8 -*-
"""Live2D 桌宠：无边框 + 透明 + 置顶小窗，以及它的控制器。

行为（对齐已确认的需求）：

* 默认开启；主窗口里不渲染 Live2D（WIKI 页除外）
* 左键拖动移动位置，位置 / 屏幕 / 缩放 / 透明度全部记忆到 ``~/.Cr/forum/config.json``
* 鼠标穿透开关（开启后点击直接落到桌面）
* 模型只从网络下载一次，缓存于 ``~/.Cr/forum/Live2D/``
* 右键菜单：隐藏 / 重载模型 / 打开设置 / 设置面板
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QObject, QPoint, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QLabel, QMenu, QProgressBar, QVBoxLayout, QWidget)

from .. import api as api_mod
from .. import config, constants, logger, paths
from ..widgets.common import hbox, vbox
from ..widgets.toast import toast
from .provider import LPKError, Live2DProvider
from .widget import Live2DWidget

_log = logger.get_logger("live2d.pet")

DEFAULT_SIZE = (380, 560)
SCREEN_MARGIN = 24


class PetWindow(QWidget):
    """无边框透明置顶的桌宠窗口。"""

    hidden_by_user = pyqtSignal()
    position_changed = pyqtSignal(int, int, int)  # x, y, screen index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PetWindow")
        self.setWindowTitle("%s 桌宠" % constants.APP_NAME)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setProperty("_crf_no_cursor", True)
        self.setMinimumSize(160, 220)

        self._drag_origin: QPoint | None = None
        self._window_origin = QPoint(0, 0)
        self._passthrough = False

        layout = vbox(self, margins=(0, 0, 0, 0), spacing=0)
        self.view = Live2DWidget(self, fps=60, transparent=True)
        self.view.setProperty("_crf_no_cursor", True)
        layout.addWidget(self.view, 1)

        self.status = QLabel("正在准备 Live2D 模型…", self)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setStyleSheet(
            "color: #E8EEED; background: rgba(26, 36, 35, 160); border-radius: 8px; padding: 6px 10px;")
        self.status.hide()
        layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignHCenter)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setFixedWidth(220)
        self.progress.hide()
        layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignHCenter)

        self.view.loaded.connect(self._on_loaded)
        self.view.ready.connect(self._on_first_frame)

    # ────────────────────── 配置 ──────────────────────
    def apply_config(self, cfg=None) -> None:
        cfg = cfg or config.current()
        scale = float(cfg.get("pet.scale", 1.0) or 1.0)
        opacity = float(cfg.get("pet.opacity", 1.0) or 1.0)
        self.setWindowOpacity(max(0.15, min(1.0, opacity)))
        self.view.set_scale(scale)
        self.view.set_fps(int(cfg.get("pet.fps", 60) or 60))
        self.set_passthrough(bool(cfg.get("pet.passthrough", False)))

    def restore_position(self, cfg=None) -> None:
        cfg = cfg or config.current()
        width, height = DEFAULT_SIZE
        scale = float(cfg.get("pet.scale", 1.0) or 1.0)
        self.resize(int(width * max(scale, 0.4)), int(height * max(scale, 0.4)))
        screens = QGuiApplication.screens()
        index = cfg.get("pet.screen")
        screen = None
        if isinstance(index, int) and 0 <= index < len(screens):
            screen = screens[index]
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        x = cfg.get("pet.x")
        y = cfg.get("pet.y")
        if isinstance(x, int) and isinstance(y, int):
            self.move(x, y)
            self._clamp_to_screen()
        else:
            self.snap_to_corner(screen)

    def snap_to_corner(self, screen=None) -> None:
        screen = screen or self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.right() - self.width() - SCREEN_MARGIN
        y = area.bottom() - self.height() - SCREEN_MARGIN
        self.move(max(area.left(), x), max(area.top(), y))

    def _clamp_to_screen(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(self.x(), area.left() - self.width() // 2),
                area.right() - self.width() // 2)
        y = min(max(self.y(), area.top()), area.bottom() - 40)
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def _save_position(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        index = 0
        if screen is not None:
            try:
                index = QGuiApplication.screens().index(screen)
            except ValueError:
                index = 0
        try:
            config.current().update({
                "pet.x": int(self.x()),
                "pet.y": int(self.y()),
                "pet.screen": int(index),
            })
        except Exception:
            pass
        self.position_changed.emit(int(self.x()), int(self.y()), int(index))

    # ────────────────────── 穿透 / 显隐 ──────────────────────
    def set_passthrough(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self._passthrough = enabled
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        except Exception:
            pass
        self.view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)

    @property
    def passthrough(self) -> bool:
        return self._passthrough

    # ────────────────────── 模型 ──────────────────────
    def set_model(self, model_json: str) -> None:
        self.status.setText("正在加载模型…")
        self.status.show()
        self.view.set_model_path(model_json)

    def set_status(self, text: str, *, progress: int | None = None) -> None:
        if not text and progress is None:
            self.status.hide()
            self.progress.hide()
            return
        self.status.setText(text)
        self.status.show()
        if progress is None:
            self.progress.hide()
        else:
            self.progress.setValue(max(0, min(100, int(progress))))
            self.progress.show()

    def _on_loaded(self, ok: bool, message: str) -> None:
        if ok:
            self.set_status("")
        else:
            self.set_status("模型加载失败：%s" % message)
            _log.error("桌宠模型加载失败：%s", message)

    def _on_first_frame(self) -> None:
        self.status.hide()
        self.progress.hide()

    # ────────────────────── 鼠标 ──────────────────────
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._passthrough:
            self._drag_origin = event.globalPosition().toPoint()
            self._window_origin = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and not self._passthrough:
            delta = event.globalPosition().toPoint() - self._drag_origin
            self.move(self._window_origin + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
            self._clamp_to_screen()
            self._save_position()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        if self._passthrough:
            return
        menu = QMenu(self)
        menu.addAction("隐藏桌宠", self.hide)
        menu.addAction("回到右下角", self.snap_to_corner)
        menu.addSeparator()
        controller = getattr(self, "controller", None)
        if controller is not None:
            menu.addAction("重新下载模型", lambda: controller.reload_model(force=True))
        menu.addAction("打开设置", self._open_settings)
        menu.addSeparator()
        menu.addAction("退出客户端", self._quit)
        menu.exec(event.globalPos())

    def _open_settings(self) -> None:
        shell = getattr(self, "shell", None)
        if shell is not None:
            shell.show_window()
            shell.navigate("settings")

    def _quit(self) -> None:
        shell = getattr(self, "shell", None)
        if shell is not None:
            shell.request_quit()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.view.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.view.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_position()
        self.view.stop()
        super().closeEvent(event)


class PetController(QObject):
    """桌宠总控：建窗 / 准备模型 / 响应配置变化。"""

    started = pyqtSignal()
    stopped = pyqtSignal()
    # 下载/准备进度从工作线程排队回主线程（控件只能在主线程碰）
    model_progress = pyqtSignal(int, int)
    model_message = pyqtSignal(str)

    def __init__(self, shell=None, parent: QObject | None = None,
                 provider: Live2DProvider | None = None) -> None:
        super().__init__(parent)
        self.shell = shell
        self.provider = provider or Live2DProvider()
        self._window: PetWindow | None = None
        self._loading = False
        self._model_path = ""
        self._started = False
        self.model_progress.connect(self._ui_progress)
        self.model_message.connect(self._ui_message)

    # ────────────────────── 状态 ──────────────────────
    @property
    def running(self) -> bool:
        return bool(self._window is not None and self._window.isVisible())

    @property
    def window(self) -> PetWindow | None:
        return self._window

    @property
    def model_json(self) -> str:
        return self._model_path

    # ────────────────────── 启停 ──────────────────────
    def start(self) -> None:
        if self._started and self.running:
            return
        window = self._ensure_window()
        window.apply_config()
        window.restore_position()
        window.show()
        self._started = True
        self.started.emit()
        self._prepare_model()

    def stop(self) -> None:
        if self._window is not None:
            self._window.hide()
        self._started = False
        self.stopped.emit()

    def toggle(self) -> bool:
        if self.running:
            self.stop()
            return False
        self.start()
        return True

    def show(self) -> None:
        if self._window is not None:
            self._window.show()

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def apply_config(self) -> None:
        if self._window is not None:
            self._window.apply_config()
            self._window.restore_position()

    # ────────────────────── 主线程 UI 槽 ──────────────────────
    def _ui_progress(self, done: int, total: int) -> None:
        window = self._window
        if window is None or total <= 0:
            return
        window.set_status("正在下载 Live2D 模型…",
                          progress=int(done * 100 / total))

    def _ui_message(self, text: str) -> None:
        if self._window is not None:
            self._window.set_status(text)

    # ────────────────────── 模型 ──────────────────────
    def _prepare_model(self, *, force: bool = False) -> None:
        if self._loading:
            return
        if not force and self.provider.is_ready():
            self._model_path = str(self.provider.model_json)
            self._apply_model()
            return
        self._loading = True
        window = self._ensure_window()
        window.set_status("正在准备 Live2D 模型…", progress=0)

        def _log_cb(level, text):
            # 只写日志（线程安全），不碰任何控件
            if level in ("ERROR", "WARNING"):
                _log.warning("[模型] %s", text)

        def _progress(done, total):
            # 本回调在下载线程里执行 → 只能发信号，不能直接改界面
            self.model_progress.emit(int(done), int(total))

        def _work():
            return self.provider.ensure(on_progress=_progress, on_log=_log_cb, force=force)

        def _done(path):
            self._loading = False
            self._model_path = str(path)
            self._apply_model()

        def _fail(message):
            self._loading = False
            self.model_message.emit("Live2D 模型不可用：%s" % message)
            _log.error("桌宠模型准备失败：%s", message)

        api_mod.run_async(_work, _done, _fail, label="Live2D 模型")

    def _apply_model(self) -> None:
        window = self._ensure_window()
        window.set_model(self._model_path)

    def reload_model(self, *, force: bool = False) -> None:
        if force:
            try:
                self.provider.clear_cache(keep_lpk=False)
            except Exception as exc:  # noqa: BLE001
                _log.warning("清理模型缓存失败：%s", exc)
        if self._window is not None:
            self.model_message.emit("正在重新准备模型…")
        self._prepare_model(force=True)

    def prepare_async(self, on_done=None, on_error=None) -> None:
        """供 WIKI·Live2D 页等其他入口复用。"""
        def _work():
            return self.provider.ensure()

        def _ok(path):
            if on_done is not None:
                on_done(str(path))

        def _err(message):
            if on_error is not None:
                on_error(str(message))

        api_mod.run_async(_work, _ok, _err, label="Live2D 模型")

    # ────────────────────── 内部 ──────────────────────
    def _ensure_window(self) -> PetWindow:
        if self._window is None:
            window = PetWindow()
            window.controller = self
            window.shell = self.shell
            self._window = window
        return self._window
