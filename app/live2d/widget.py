# -*- coding: utf-8 -*-
"""Live2D 渲染控件（QOpenGLWidget + live2d-py 原生渲染）。

* 同一实例可以内嵌（WIKI·Live2D 页）也可以放进桌宠窗口
* OpenGL 上下文按要求为 3.3 Core（见 ``main._set_surface_format``）
* ``transparent=True`` 时用 alpha=0 清屏，以便无边框窗口挖空背景
* 视线跟随用 :meth:`Live2DWidget.set_focus`；点击命中用 HitArea → ``Tap<部位>`` 动作组
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QWidget

from .. import logger

_log = logger.get_logger("live2d.widget")

_live2d_module = None
_live2d_ready = False
_live2d_failed = ""

MOTION_PRIORITY_FORCE = 3


def load_live2d():
    """惰性导入 live2d-py（导入失败不抛，返回 None）。"""
    global _live2d_module, _live2d_failed
    if _live2d_module is not None:
        return _live2d_module
    try:
        from live2d import v3 as live2d_v3
        _live2d_module = live2d_v3
    except Exception as exc:  # noqa: BLE001
        _live2d_failed = str(exc)
        _log.error("无法导入 live2d 运行库：%s", exc)
        _live2d_module = None
    return _live2d_module


def live2d_error() -> str:
    return _live2d_failed


class Live2DWidget(QOpenGLWidget):
    """把 Cubism 模型画进 Qt 窗口。"""

    tapped = pyqtSignal(str)           # 命中的 HitArea 名（如「左耳」）
    loaded = pyqtSignal(bool, str)     # (是否成功, 说明)  信号名避开 QWidget.loaded 冲突
    ready = pyqtSignal()               # 首帧渲染完成

    def __init__(self, parent: QWidget | None = None, *, fps: int = 60,
                 transparent: bool = True) -> None:
        super().__init__(parent)
        self._transparent = bool(transparent)
        self._model = None
        self._pending_path = ""
        self._model_path = ""
        self._gl_ready = False
        self._first_frame = False
        self._error_reported = False
        self._scale = 1.0
        self._offset = (0.0, 0.0)
        self._motion_groups: dict = {}
        self._hit_names: list[str] = []
        self._last_drag = (0.0, 0.0)
        if self._transparent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setMinimumSize(80, 80)
        self._timer = QTimer(self)
        self._timer.setInterval(max(int(1000 / max(fps, 1)), 8))
        self._timer.timeout.connect(self.update)

    # ────────────────────── 公开 API ──────────────────────
    @property
    def model_path(self) -> str:
        return self._model_path

    def is_loaded(self) -> bool:
        return self._model is not None

    def set_fps(self, fps: int) -> None:
        self._timer.setInterval(max(int(1000 / max(int(fps), 1)), 8))

    def set_model_path(self, path: str) -> None:
        """设置模型（.model3.json 绝对路径）；GL 未就绪时先记住。"""
        path = str(path or "")
        if not path or not os.path.isfile(path):
            self.loaded.emit(False, "模型文件不存在")
            return
        self._pending_path = path
        if self._gl_ready:
            self._create_model(path)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def set_scale(self, scale: float) -> None:
        self._scale = max(0.05, float(scale or 1.0))
        self._apply_view()

    def set_offset(self, dx: float, dy: float) -> None:
        self._offset = (float(dx), float(dy))
        self._apply_view()

    def set_focus(self, x: float, y: float) -> None:
        """鼠标位置（控件像素坐标）→ 模型视线跟随。"""
        if self._model is None:
            return
        try:
            self._model.Drag(float(x), float(y))
        except Exception:
            pass

    def set_focus_centre(self) -> None:
        self.set_focus(self.width() * 0.5, self.height() * 0.5)

    def track_screen_pos(self) -> None:
        """按当前全局鼠标位置更新视线（鼠标在窗口外也生效）。

        ``QWidget`` 只能收到落在自己范围内的鼠标移动事件，所以鼠标离开
        桌宠窗口后视线就停住了。这里改用轮询全局光标位置，再映射成控件
        局部坐标；坐标会被夹到控件范围内，这样鼠标在窗口外时模型至少会
        朝那个方向看。
        """
        if self._model is None:
            return
        try:
            local = self.mapFromGlobal(QCursor.pos())
            width = float(max(self.width(), 1))
            height = float(max(self.height(), 1))
            x = min(max(float(local.x()), 0.0), width)
            y = min(max(float(local.y()), 0.0), height)
            self.set_focus(x, y)
        except Exception:
            pass

    def random_motion(self, group: str | None = None) -> None:
        if self._model is None:
            return
        try:
            self._model.StartRandomMotion(group, MOTION_PRIORITY_FORCE)
        except Exception:
            pass

    def play_motion(self, group: str, index: int = 0) -> bool:
        if self._model is None:
            return False
        try:
            self._model.StartMotion(group, int(index), MOTION_PRIORITY_FORCE)
            return True
        except Exception:
            return False

    def set_random_expression(self) -> None:
        if self._model is None:
            return
        try:
            self._model.SetRandomExpression()
        except Exception:
            pass

    def hit_areas(self) -> list[str]:
        return list(self._hit_names)

    # ────────────────────── GL ──────────────────────
    def initializeGL(self) -> None:  # noqa: N802
        global _live2d_ready
        live2d = load_live2d()
        if live2d is None:
            self.loaded.emit(False, "Live2D 运行库不可用：%s" % (_live2d_failed or "未知原因"))
            return
        try:
            if not _live2d_ready:
                live2d.init()
                _live2d_ready = True
            live2d.glInit()
        except Exception as exc:  # noqa: BLE001
            _log.error("Live2D / OpenGL 初始化失败：%s", exc, exc_info=True)
            self.loaded.emit(False, "OpenGL 初始化失败：%s" % exc)
            return
        self._gl_ready = True
        self._capture_hit_names()
        if self._pending_path:
            self._create_model(self._pending_path)

    def resizeGL(self, w: int, h: int) -> None:  # noqa: N802
        if self._model is not None:
            try:
                self._model.Resize(max(int(w), 1), max(int(h), 1))
            except Exception:
                pass

    def paintGL(self) -> None:  # noqa: N802
        live2d = _live2d_module
        if live2d is None:
            return
        alpha = 0.0 if self._transparent else 1.0
        try:
            live2d.clearBuffer(0.0, 0.0, 0.0, alpha)
        except TypeError:
            try:
                live2d.clearBuffer()
            except Exception:
                pass
        except Exception:
            pass
        if self._model is None:
            return
        try:
            self._model.Update()
            self._model.Draw()
        except Exception as exc:  # noqa: BLE001
            if not self._error_reported:
                self._error_reported = True
                _log.error("Live2D 渲染失败：%s", exc, exc_info=True)
            return
        if not self._first_frame:
            self._first_frame = True
            self.ready.emit()

    # ────────────────────── 内部 ──────────────────────
    def _capture_hit_names(self) -> None:
        """记下 HitArea 名，方便上层做“点击部位 → 动作”映射。"""
        names: list[str] = []
        path = self._pending_path or self._model_path
        if path and os.path.isfile(path):
            try:
                import json
                with open(path, encoding="utf-8") as fh:
                    payload = json.load(fh)
                for item in payload.get("HitAreas") or []:
                    if isinstance(item, dict) and item.get("Name"):
                        names.append(str(item["Name"]))
            except Exception:
                names = []
        self._hit_names = names

    def _create_model(self, path: str) -> None:
        live2d = _live2d_module
        if live2d is None:
            self.loaded.emit(False, "Live2D 运行库不可用")
            return
        try:
            model = live2d.LAppModel()
            model.LoadModelJson(path)
            model.SetAutoBreathEnable(True)
            model.SetAutoBlinkEnable(True)
        except Exception as exc:  # noqa: BLE001
            _log.error("加载 Live2D 模型失败：%s", exc, exc_info=True)
            self.loaded.emit(False, "模型加载失败：%s" % exc)
            return
        self._model = model
        self._model_path = path
        self._error_reported = False
        self._first_frame = False
        try:
            self._motion_groups = dict(model.GetMotionGroups() or {})
        except Exception:
            self._motion_groups = {}
        self._capture_hit_names()
        self._apply_view()
        self.start()
        self.loaded.emit(True, os.path.basename(path))

    def _apply_view(self) -> None:
        if self._model is None:
            return
        try:
            self._model.Resize(max(self.width(), 1), max(self.height(), 1))
        except Exception:
            pass
        try:
            self._model.SetScale(self._scale)
        except Exception:
            pass
        try:
            self._model.SetOffset(*self._offset)
        except Exception:
            pass

    # ────────────────────── 交互 ──────────────────────
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        position = event.position()
        self.set_focus(position.x(), position.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._model is not None:
            position = event.position()
            name = self._hit_test(position.x(), position.y())
            if name:
                self.tapped.emit(name)
                self._trigger_tap(name)
            else:
                self.random_motion("TapA") if "TapA" in self._motion_groups else self.random_motion()
        super().mouseReleaseEvent(event)

    def _hit_test(self, x: float, y: float) -> str:
        try:
            parts = self._model.HitPart(float(x), float(y), True)
        except Exception:
            return ""
        if not parts:
            return ""
        first = parts[0]
        return str(first)

    def _trigger_tap(self, hit_name: str) -> None:
        group = "Tap" + hit_name
        if group in self._motion_groups:
            self.play_motion(group, 0)
            return
        for candidate in ("Tap" + hit_name.strip(), "TapA", "TapB"):
            if candidate in self._motion_groups:
                self.play_motion(candidate, 0)
                return
        self.random_motion()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.stop()
        self._model = None
        super().closeEvent(event)
