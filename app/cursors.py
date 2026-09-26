# -*- coding: utf-8 -*-
"""罗小黑鼠标指针：清单解析 / 应用内自定义光标 / Windows 系统级安装。

三层结构：

* :class:`RoleCursor`    —— 单个角色的帧序列（懒加载 :class:`QPixmap`）
* :class:`CursorPack`    —— 解析 ``resources/cursors/manifest.json``
* :class:`CursorManager` —— 挂在 ``QApplication`` 上的事件过滤器，按控件角色热切光标

系统级安装（写 ``.cur`` / ``.ani`` + 注册表）由 :func:`install_system_cursors`
与 :func:`restore_system_cursors` 提供；目标目录固定在用户目录下
``%LOCALAPPDATA%/Microsoft/Windows/Cursors/<方案名>/``，不触碰 %SystemRoot%。

本模块导入时不创建任何 :class:`QPixmap`，也不读大文件；所有像素级操作都在
存在 ``QApplication`` 之后按需发生。
"""

from __future__ import annotations

# 允许 `python app/cursors.py` 直接运行（此时没有包上下文）
if __package__ in (None, ""):  # pragma: no cover - 仅脚本方式运行时
    import os as _os
    import sys as _sys

    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    __package__ = "app"

import bisect
import functools
import json
import math
import os
import struct
import sys
import weakref
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtGui import QCursor, QGuiApplication, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import config as _config
from . import constants
from .logger import get_logger

log = get_logger("cursors")

__all__ = [
    "RoleCursor",
    "CursorPack",
    "CursorManager",
    "install_system_cursors",
    "restore_system_cursors",
    "system_cursors_installed",
]

# ────────────────────────── 缩放基准 ──────────────────────────

BASE_TARGET_PX = 32
SCALE_ENV = "CRFORUM_CURSOR_SCALE"
MIN_TICK_MS = 20
MAX_TICK_MS = 50
DEFAULT_DELAY_MS = 100


def _dpi_ratio() -> float:
    """主屏逻辑 DPI 相对 96 的比例；没有 QApplication 时回退 1.0。"""
    app = QGuiApplication.instance()
    if app is None:
        return 1.0
    try:
        screen = app.primaryScreen()
        if screen is not None:
            dpi = float(screen.logicalDotsPerInch())
            if dpi > 0:
                return dpi / 96.0
    except Exception:
        pass
    return 1.0


def _env_scale() -> float:
    raw = os.environ.get(SCALE_ENV)
    if raw:
        try:
            val = float(raw)
            if val > 0:
                return val
        except (TypeError, ValueError):
            pass
    return 1.0


def _pair(value: Any, default: tuple = (0, 0)) -> tuple:
    try:
        return (int(value[0]), int(value[1]))
    except Exception:
        return default


def _shape_value(shape) -> int:
    """``Qt.CursorShape`` → int。

    PyQt6 的枚举不是 ``IntEnum``，不能直接 ``int(shape)``；必须先取 ``.value``。
    """
    value = getattr(shape, "value", None)
    if isinstance(value, int):
        return value
    try:
        return int(shape)
    except (TypeError, ValueError):
        return 0


SHAPE_TO_ROLE: dict = {
    _shape_value(Qt.CursorShape.ArrowCursor): "arrow",
    _shape_value(Qt.CursorShape.UpArrowCursor): "uparrow",
    _shape_value(Qt.CursorShape.CrossCursor): "crosshair",
    _shape_value(Qt.CursorShape.WaitCursor): "wait",
    _shape_value(Qt.CursorShape.BusyCursor): "work",
    _shape_value(Qt.CursorShape.IBeamCursor): "text",
    _shape_value(Qt.CursorShape.SizeVerCursor): "sizens",
    _shape_value(Qt.CursorShape.SizeHorCursor): "sizewe",
    _shape_value(Qt.CursorShape.SizeFDiagCursor): "sizenwse",
    _shape_value(Qt.CursorShape.SizeBDiagCursor): "sizenesw",
    _shape_value(Qt.CursorShape.SizeAllCursor): "sizeall",
    _shape_value(Qt.CursorShape.PointingHandCursor): "link",
    _shape_value(Qt.CursorShape.ForbiddenCursor): "unavailable",
    _shape_value(Qt.CursorShape.WhatsThisCursor): "help",
}

ROLE_TO_SHAPE: dict = {
    role: Qt.CursorShape(shape) for shape, role in SHAPE_TO_ROLE.items()
}

WATCHED_EVENTS = frozenset({
    QEvent.Type.Enter,
    QEvent.Type.HoverEnter,
    QEvent.Type.MouseMove,
    QEvent.Type.Polish,
})

_MISSING = object()


def _target_px() -> int:
    """当前目标边长（设备无关像素）：32 * DPI 比例 * 缩放系数。"""
    override = getattr(RoleCursor, "scale_override", None)
    scale = 1.0
    if override:
        try:
            scale = float(override)
        except (TypeError, ValueError):
            scale = 1.0
    else:
        scale = _env_scale()
    if scale <= 0:
        scale = 1.0
    return max(1, int(round(BASE_TARGET_PX * _dpi_ratio() * scale)))


class RoleCursor:
    """单个角色的帧序列。

    帧与热点懒加载：只有在存在 ``QApplication`` 之后调用 :meth:`pixmaps`
    才会真正读盘并解码 PNG。
    """

    #: 允许用类属性覆盖缩放系数（倍数，用于预览/调试）；None 表示用环境变量。
    scale_override = None

    def __init__(self, role, *, windows_name="", qt_shape=None, label="",
                 size=(0, 0), hotspot=(0, 0), seq=None, delays=None, base_dir=None):
        self.role = str(role)
        self.windows_name = str(windows_name or self.role)
        self.qt_shape = str(qt_shape) if qt_shape else None
        self.label = str(label or self.role)
        self.size = _pair(size)
        self.hotspot = _pair(hotspot)
        self.seq = [str(name) for name in (seq or [])]
        self.base_dir = Path(base_dir) if base_dir else None

        values = [int(delay) for delay in (delays or [])]
        count = len(self.seq)
        if len(values) < count:
            values.extend([DEFAULT_DELAY_MS] * (count - len(values)))
        elif len(values) > count:
            values = values[:count]
        self.delays = values

        self._frames = None
        self._raw_frames = None
        self._scaled_hotspot = None
        self._cumulative = None

    @property
    def animated(self) -> bool:
        return len(self.seq) > 1

    def frame_paths(self):
        if self.base_dir is None:
            return []
        return [self.base_dir / name for name in self.seq]

    def __repr__(self) -> str:
        return "RoleCursor(%s, frames=%d)" % (self.role, len(self.seq))

    @staticmethod
    def _read_pixmap(path):
        if path is None:
            return QPixmap()
        try:
            return QPixmap(str(path))
        except Exception:
            return QPixmap()

    def raw_pixmaps(self):
        """原始尺寸帧（系统级 .cur/.ani 写出用）。"""
        if self._raw_frames is None:
            self._raw_frames = [self._read_pixmap(p) for p in self.frame_paths()]
        return list(self._raw_frames)

    def pixmaps(self):
        """按当前 DPI/缩放系数调整后的帧（应用内光标用），懒加载并缓存。"""
        if self._frames is None:
            target = _target_px()
            frames = []
            for path in self.frame_paths():
                pixmap = self._read_pixmap(path)
                if pixmap.isNull():
                    frames.append(pixmap)
                    continue
                if target > 0 and (pixmap.width() != target or pixmap.height() != target):
                    pixmap = pixmap.scaled(
                        target, target,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
                frames.append(pixmap)
            self._frames = frames

            first = frames[0] if frames else None
            src_w, src_h = self.size
            if first is not None and not first.isNull() and src_w > 0 and src_h > 0:
                self._scaled_hotspot = (
                    int(round(self.hotspot[0] * first.width() / float(src_w))),
                    int(round(self.hotspot[1] * first.height() / float(src_h))),
                )
            else:
                self._scaled_hotspot = self.hotspot
        return list(self._frames)

    def scaled_hotspot(self):
        """缩放后的热点（与 :meth:`pixmaps` 同比例）。"""
        if self._scaled_hotspot is None:
            self.pixmaps()
        return self._scaled_hotspot or self.hotspot

    def frame_at(self, elapsed_ms: int) -> int:
        """按累计 delay（毫秒）算出 elapsed_ms 时刻应显示的帧号。"""
        count = len(self.delays)
        if count <= 1:
            return 0
        if self._cumulative is None:
            cumulative = []
            total = 0
            for delay in self.delays:
                total += max(1, int(delay))
                cumulative.append(total)
            self._cumulative = cumulative
        total = self._cumulative[-1]
        if total <= 0:
            return 0
        position = int(elapsed_ms) % total
        return min(bisect.bisect_right(self._cumulative, position), count - 1)


class CursorPack:
    """``resources/cursors/manifest.json`` 的解析结果（可传入自定义路径）。"""

    def __init__(self, manifest_path=None):
        self.path = Path(manifest_path) if manifest_path else Path(constants.RES_CURSOR_MANIFEST)
        self._base = self.path.parent
        self._data = None
        self._roles_meta = {}
        self._variants = {}
        self._cache = {}
        self._load()

    def _load(self) -> None:
        try:
            if not self.path.is_file():
                log.warning("鼠标指针清单不存在：%s", self.path)
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("鼠标指针清单解析失败：%s", exc)
            return
        if not isinstance(data, dict):
            return
        roles = data.get("roles")
        variants = data.get("variants")
        if not isinstance(roles, dict) or not isinstance(variants, dict) or not variants:
            return
        self._data = data
        self._roles_meta = roles
        self._variants = variants

    @property
    def available(self) -> bool:
        return self._data is not None

    def variants(self):
        """[(key, 中文label)]，顺序固定 normal / large_dynamic / large_static。"""
        result = []
        known = {key for key, _ in constants.CURSOR_VARIANTS}
        for key, label in constants.CURSOR_VARIANTS:
            entry = self._variants.get(key)
            if isinstance(entry, dict):
                result.append((key, str(entry.get("label") or label)))
        for key, entry in self._variants.items():
            if key in known or not isinstance(entry, dict):
                continue
            result.append((key, str(entry.get("label") or key)))
        return result

    def roles(self, variant):
        """变体内所有角色 → :class:`RoleCursor`（同一变体重复调用返回同一对象）。"""
        entry = self._variants.get(str(variant))
        if not isinstance(entry, dict):
            return {}
        role_data = entry.get("roles")
        if not isinstance(role_data, dict):
            return {}
        cache = self._cache.setdefault(str(variant), {})
        order = list(self._roles_meta.keys())
        order += [key for key in role_data if key not in self._roles_meta]
        result = {}
        for role in order:
            data = role_data.get(role)
            if not isinstance(data, dict):
                continue
            cursor = cache.get(role)
            if cursor is None:
                cursor = self._build_role(role, data)
                cache[role] = cursor
            result[role] = cursor
        return result

    def _build_role(self, role, data):
        meta = self._roles_meta.get(role) or {}
        sub = str(data.get("dir") or "")
        base = self._base / sub if sub else self._base
        return RoleCursor(
            role,
            windows_name=meta.get("windows") or role,
            qt_shape=meta.get("qt"),
            label=meta.get("label") or role,
            size=data.get("size"),
            hotspot=data.get("hotspot"),
            seq=data.get("seq"),
            delays=data.get("delays"),
            base_dir=base,
        )


class CursorManager(QObject):
    """把罗小黑光标套到 Qt 控件上（挂在 QApplication 的事件过滤器上）。"""

    def __init__(self, parent=None, pack=None, config=None):
        super().__init__(parent)
        self._pack = pack if pack is not None else CursorPack()
        self._conf = config if config is not None else self._load_config()
        self._widgets = weakref.WeakSet()
        self._roles_of = weakref.WeakKeyDictionary()
        self._installed = False
        self._app = None
        self._clock_ms = 0
        self._enabled = self._read_enabled()
        self._variant = self._read_variant()
        self._timer = QTimer(self)
        try:
            self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        except Exception:
            pass
        self._timer.timeout.connect(self._on_tick)
        self._timer.setInterval(self._interval())

    @staticmethod
    def _load_config():
        try:
            return _config.current()
        except Exception:
            return None

    def _read_enabled(self) -> bool:
        if self._conf is None:
            return True
        try:
            return bool(self._conf.get("cursor_enabled", True))
        except Exception:
            return True

    def _read_variant(self) -> str:
        key = constants.CURSOR_VARIANT_DEFAULT
        if self._conf is not None:
            try:
                key = str(self._conf.get("cursor_variant", key) or key)
            except Exception:
                pass
        return self._normalize_variant(key)

    def _write_config(self, key, value) -> None:
        if self._conf is None:
            return
        try:
            self._conf.set(key, value)
        except Exception:
            pass

    def _normalize_variant(self, key) -> str:
        available = [k for k, _ in self._pack.variants()] if self._pack.available else []
        key = str(key or "")
        if not available:
            return key or constants.CURSOR_VARIANT_DEFAULT
        if key in available:
            return key
        if constants.CURSOR_VARIANT_DEFAULT in available:
            return constants.CURSOR_VARIANT_DEFAULT
        return available[0]

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def variant(self) -> str:
        return self._variant

    def _roles(self):
        if not self._pack.available:
            return {}
        try:
            return self._pack.roles(self._variant)
        except Exception:
            return {}

    def _interval(self) -> int:
        delays = []
        try:
            for cursor in self._roles().values():
                if cursor.animated:
                    delays.extend(int(d) for d in cursor.delays if int(d) > 0)
        except Exception:
            delays = []
        if not delays:
            return 33
        step = functools.reduce(math.gcd, delays)
        if step <= 0:
            return 33
        return max(MIN_TICK_MS, min(step, MAX_TICK_MS))

    def install(self, widgets=None) -> None:
        """在 QApplication 上装事件过滤器；widgets 为需要立即纳管的控件。"""
        app = QApplication.instance()
        if app is not None and self._app is not app:
            app.installEventFilter(self)
            self._app = app
        self._installed = True
        if widgets:
            for widget in widgets:
                self.attach(widget)
        self.refresh()

    def attach(self, widget) -> None:
        if not isinstance(widget, QWidget):
            return
        self._widgets.add(widget)
        self._ensure_orig_shape(widget)

    def detach(self, widget) -> None:
        try:
            self._widgets.discard(widget)
        except Exception:
            pass
        try:
            self._roles_of.pop(widget, None)
        except Exception:
            pass

    def _ensure_orig_shape(self, widget) -> None:
        try:
            if widget.property("_crf_orig_shape") is None:
                widget.setProperty("_crf_orig_shape", _shape_value(widget.cursor().shape()))
        except Exception:
            pass

    def set_enabled(self, enabled) -> None:
        """开关自定义光标；关闭时把所有纳管控件恢复为系统默认光标。"""
        self._enabled = bool(enabled)
        self._write_config("cursor_enabled", self._enabled)
        if self._enabled:
            self.refresh()
        else:
            self._timer.stop()
            self._restore_all()

    def set_variant(self, key) -> None:
        """热切换变体并立即刷新已纳管控件。"""
        self._variant = self._normalize_variant(str(key or ""))
        self._write_config("cursor_variant", self._variant)
        self._timer.setInterval(self._interval())
        self.refresh()

    def refresh(self) -> None:
        """重扫已纳管控件并重设光标（变体切换 / 启停后调用）。"""
        if not self._enabled or not self._pack.available:
            return
        roles = self._roles()
        active = False
        for widget in list(self._widgets):
            try:
                role = self._role_for(widget)
                self._roles_of[widget] = role
                if role is None:
                    continue
                cursor = roles.get(role)
                if cursor is None:
                    continue
                self._apply(widget, cursor)
                if cursor.animated and widget.underMouse():
                    active = True
            except RuntimeError:
                continue
        if active and not self._timer.isActive():
            self._timer.start()
        elif not active and self._timer.isActive():
            self._timer.stop()

    def cursor_for(self, role: str) -> QCursor:
        """取某角色「当前帧」的光标。"""
        role = str(role or "")
        cursor = self._roles().get(role) if self._pack.available else None
        fallback = ROLE_TO_SHAPE.get(role, Qt.CursorShape.ArrowCursor)
        if cursor is None:
            return QCursor(fallback)
        frames = cursor.pixmaps()
        if not frames:
            return QCursor(fallback)
        index = cursor.frame_at(self._clock_ms) if cursor.animated else 0
        if index < 0 or index >= len(frames):
            index = 0
        pixmap = frames[index]
        if pixmap is None or pixmap.isNull():
            return QCursor(fallback)
        hot_x, hot_y = cursor.scaled_hotspot()
        try:
            return QCursor(pixmap, int(hot_x), int(hot_y))
        except Exception:
            return QCursor(fallback)

    def eventFilter(self, obj, event):
        if not self._installed:
            return False
        try:
            etype = event.type()
            if etype == QEvent.Type.ChildAdded:
                child = event.child()
                if isinstance(child, QWidget):
                    self.attach(child)
                    self._apply_for(child)
            elif etype in WATCHED_EVENTS and isinstance(obj, QWidget):
                self.attach(obj)
                self._apply_for(obj)
        except Exception:
            pass
        return False

    def _apply_for(self, widget) -> None:
        if not self._enabled or not self._pack.available:
            return
        role = self._role_for(widget)
        try:
            self._roles_of[widget] = role
        except Exception:
            pass
        if role is None:
            return
        cursor = self._roles().get(role)
        if cursor is None:
            return
        self._apply(widget, cursor)
        if cursor.animated and not self._timer.isActive():
            self._timer.start()

    def _on_tick(self) -> None:
        self._clock_ms += self._timer.interval()
        if not self._enabled or not self._pack.available:
            self._timer.stop()
            return
        roles = self._roles()
        active = False
        for widget in list(self._roles_of.keys()):
            role = self._roles_of.get(widget, _MISSING)
            if role is _MISSING or role is None:
                continue
            cursor = roles.get(role)
            if cursor is None or not cursor.animated:
                continue
            try:
                if not widget.underMouse():
                    continue
            except RuntimeError:
                continue
            active = True
            self._apply(widget, cursor)
        if not active:
            self._timer.stop()

    def _apply(self, widget, cursor) -> None:
        frames = cursor.pixmaps()
        if not frames:
            return
        index = cursor.frame_at(self._clock_ms) if cursor.animated else 0
        if index < 0 or index >= len(frames):
            index = 0
        pixmap = frames[index]
        if pixmap is None or pixmap.isNull():
            return
        hot_x, hot_y = cursor.scaled_hotspot()
        try:
            widget.setCursor(QCursor(pixmap, int(hot_x), int(hot_y)))
        except RuntimeError:
            pass

    def _restore_all(self) -> None:
        for widget in list(self._widgets):
            self._restore_widget(widget)

    def _restore_widget(self, widget) -> None:
        try:
            shape = widget.property("_crf_orig_shape")
            if shape is None:
                widget.unsetCursor()
            else:
                widget.setCursor(QCursor(Qt.CursorShape(int(shape))))
        except (RuntimeError, TypeError, ValueError):
            pass

    def _role_for(self, widget):
        if not isinstance(widget, QWidget):
            return None
        try:
            if bool(widget.property("_crf_no_cursor")):
                return None
            if not self._should_manage(widget):
                return None
        except RuntimeError:
            return None
        forced = widget.property("_crf_role")
        if forced:
            return str(forced)
        self._ensure_orig_shape(widget)
        shape = widget.property("_crf_orig_shape")
        try:
            role = SHAPE_TO_ROLE.get(_shape_value(shape), "arrow")
        except (TypeError, ValueError):
            role = "arrow"
        return self._correct_role(widget, role)

    def _should_manage(self, widget) -> bool:
        try:
            if not widget.isWindow():
                return True
            return _is_popup_like(widget)
        except RuntimeError:
            return False

    def _correct_role(self, widget, role: str) -> str:
        if isinstance(widget, QTextBrowser):
            return "link" if self._anchor_at(widget) else "arrow"
        if isinstance(widget, QTextEdit):
            return "link" if self._anchor_at(widget) else "text"
        if isinstance(widget, (QPlainTextEdit, QLineEdit, QAbstractSpinBox)):
            return "text"
        if isinstance(widget, QComboBox):
            return "text" if widget.isEditable() else role
        if isinstance(widget, QLabel):
            return "link" if self._label_link_at(widget) else "arrow"
        return role

    @staticmethod
    def _anchor_at(widget) -> bool:
        try:
            anchor = getattr(widget, "anchorAt", None)
            if anchor is None:
                return False
            target = widget.viewport() if hasattr(widget, "viewport") else widget
            if target is None:
                target = widget
            return bool(anchor(target.mapFromGlobal(QCursor.pos())))
        except Exception:
            return False

    @staticmethod
    def _label_link_at(widget) -> bool:
        try:
            flags = widget.textInteractionFlags()
            if not (flags & Qt.TextInteractionFlag.LinksAccessibleByMouse):
                return False
            link_at = getattr(widget, "linkAt", None)
            if link_at is None:
                return False
            return bool(link_at(widget.mapFromGlobal(QCursor.pos())))
        except Exception:
            return False


def _is_popup_like(widget) -> bool:
    """弹窗类顶层窗口（对话框/菜单/下拉弹层）允许纳管；其余顶层（桌宠等）跳过。"""
    try:
        flags = widget.windowFlags()
        popup_flags = (Qt.WindowType.Popup
                       | Qt.WindowType.ToolTip
                       | Qt.WindowType.SplashScreen)
        if flags & popup_flags:
            return True
    except Exception:
        pass
    return isinstance(widget, (QDialog, QMenu, QComboBox))


# ────────────────────────── 系统级安装（.cur / .ani / 注册表）──────────────────────────

SCHEME_NAME = constants.SYSTEM_CURSOR_SCHEME
CURSOR_REG_PATH = os.path.join("Control Panel", "Cursors")
CURSOR_SCHEMES_PATH = os.path.join(CURSOR_REG_PATH, "Schemes")

CURSOR_VALUE_NAMES = (
    "AppStarting", "Arrow", "Crosshair", "Hand", "Help", "IBeam", "No", "NWPen",
    "SizeAll", "SizeNESW", "SizeNS", "SizeNWSE", "SizeWE", "UpArrow", "Wait",
)

# 方案字符串的 15 段顺序（Windows 方案定义顺序）
SCHEME_ORDER = (
    "Arrow", "Help", "AppStarting", "Wait", "Crosshair", "IBeam", "Hand", "No",
    "SizeNS", "SizeWE", "SizeNWSE", "SizeNESW", "SizeAll", "UpArrow", "Hand",
)

SPI_SETCURSORS = 0x0057
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02


def _system_cursor_dir() -> Path:
    """系统级安装目录：%LOCALAPPDATA%/Microsoft/Windows/Cursors/<方案名>/。"""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else (Path.home() / "AppData" / "Local")
    name = Path(constants.SYSTEM_CURSOR_DIR_NAME).name or SCHEME_NAME
    return root / "Microsoft" / "Windows" / "Cursors" / name


def _winreg_module():
    import winreg
    return winreg


def _broadcast_change() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETCURSORS, 0, None, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    except Exception as exc:
        log.warning("刷新系统光标失败：%s", exc)


def _image_bytes(image: QImage) -> bytes:
    try:
        pointer = image.constBits()
        pointer.setsize(image.sizeInBytes())
        return bytes(pointer)
    except Exception:
        pass
    buf = bytearray()
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            buf += bytes((color.blue(), color.green(), color.red(), color.alpha()))
    return bytes(buf)


def _encode_cur(pixmap: QPixmap, hot_x: int, hot_y: int) -> bytes:
    """把一张 QPixmap 编码成单帧 .cur（32 位 BGRA + AND 掩码）。"""
    if pixmap is None or pixmap.isNull():
        return b""
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()
    if width <= 0 or height <= 0:
        return b""
    raw = _image_bytes(image)
    stride = image.bytesPerLine()
    if len(raw) < stride * height:
        return b""

    row_bytes = width * 4
    xor_bitmap = bytearray()
    for y in range(height - 1, -1, -1):
        offset = y * stride
        xor_bitmap += raw[offset:offset + row_bytes]

    mask_stride = ((width + 31) // 32) * 4
    and_mask = bytearray()
    for y in range(height - 1, -1, -1):
        offset = y * stride
        row = bytearray(mask_stride)
        for x in range(width):
            if raw[offset + x * 4 + 3] == 0:
                row[x >> 3] |= 0x80 >> (x & 7)
        and_mask += row

    header = struct.pack(
        "<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0,
        width * height * 4, 0, 0, 0, 0)
    payload = header + bytes(xor_bitmap) + bytes(and_mask)
    entry = struct.pack(
        "<BBBBHHII",
        0 if width >= 256 else width,
        0 if height >= 256 else height,
        0, 0,
        int(hot_x) & 0xFFFF, int(hot_y) & 0xFFFF,
        len(payload), 22)
    return struct.pack("<HHH", 0, 2, 1) + entry + payload


def _riff_chunk(fourcc: bytes, data: bytes) -> bytes:
    data = bytes(data)
    out = fourcc + struct.pack("<I", len(data)) + data
    if len(data) % 2:
        out += bytes(1)
    return out


def _riff_list(list_type: bytes, payload: bytes) -> bytes:
    payload = bytes(payload)
    body = list_type + payload
    out = b"LIST" + struct.pack("<I", len(body)) + body
    if len(body) % 2:
        out += bytes(1)
    return out


def _encode_ani(frames, delays, name: str) -> bytes:
    """把多帧 .cur 数据打包成 RIFF/ACON 动画光标（自动去重并给出 seq）。"""
    unique = []
    sequence = []
    seen = {}
    for frame in frames:
        index = seen.get(frame)
        if index is None:
            index = len(unique)
            seen[frame] = index
            unique.append(frame)
        sequence.append(index)

    steps = len(frames)
    values = [int(d) for d in delays]
    if len(values) < steps:
        values.extend([DEFAULT_DELAY_MS] * (steps - len(values)))
    elif len(values) > steps:
        values = values[:steps]
    rates = [max(1, int(round(ms / 1000.0 * 60.0))) for ms in values]

    anih = struct.pack("<9I", 36, len(unique), steps, 32, 32, 32, 1, 6, 1)
    rate_chunk = struct.pack("<%dI" % steps, *rates) if steps else b""
    seq_chunk = struct.pack("<%dI" % steps, *sequence) if steps else b""

    info = _riff_list(b"INFO", _riff_chunk(b"INAM", name.encode("utf-8", "replace") + bytes(1)))
    frames_list = _riff_list(b"fram", b"".join(_riff_chunk(b"icon", f) for f in unique))
    riff = (b"ACON" + info
            + _riff_chunk(b"anih", anih)
            + _riff_chunk(b"rate", rate_chunk)
            + _riff_chunk(b"seq ", seq_chunk)
            + frames_list)

    out = b"RIFF" + struct.pack("<I", len(riff)) + riff
    if len(riff) % 2:
        out += bytes(1)
    return out


def _write_cursor_files(pack: CursorPack, variant: str, out_dir: Path):
    out_dir = Path(out_dir)          # 容忍 str（安装入口传进来的可能是字符串）
    roles = pack.roles(variant)
    if not roles:
        return None, "变体缺少指针数据：%s" % variant
    written = {}
    try:
        for role, cursor in roles.items():
            windows_name = cursor.windows_name or role
            raw = cursor.raw_pixmaps()
            if not raw or raw[0].isNull():
                return None, "缺少指针图片：%s" % role
            hot_x, hot_y = cursor.hotspot
            if cursor.animated:
                frames = [_encode_cur(pixmap, hot_x, hot_y) for pixmap in raw]
                if any(not frame for frame in frames):
                    return None, "指针帧编码失败：%s" % role
                data = _encode_ani(frames, cursor.delays, windows_name)
                suffix = ".ani"
            else:
                data = _encode_cur(raw[0], hot_x, hot_y)
                if not data:
                    return None, "指针编码失败：%s" % role
                suffix = ".cur"
            path = out_dir / (windows_name + suffix)
            path.write_bytes(data)
            written[windows_name] = path
    except OSError as exc:
        return None, "写入指针文件失败：%s" % exc
    except Exception as exc:
        return None, "生成指针文件失败：%s" % exc
    return written, ""


def _scheme_value(written) -> str:
    parts = []
    for name in SCHEME_ORDER:
        path = written.get(name)
        if path is None:
            return ""
        parts.append(str(path))
    return ",".join(parts)


def install_system_cursors(variant: str = "normal", *, target_dir=None,
                           dry_run: bool = False):
    """把指定变体写成 .cur/.ani 并注册为 Windows 系统鼠标指针。

    ``target_dir`` 可指向临时目录便于验证；``dry_run=True`` 时只写文件、跳过注册表。
    失败返回 ``(False, 中文原因)``，不抛异常。
    """
    pack = CursorPack()
    if not pack.available:
        return False, "鼠标指针资源清单缺失或无法解析"
    keys = [key for key, _ in pack.variants()]
    if variant not in keys:
        variant = (constants.CURSOR_VARIANT_DEFAULT
                   if constants.CURSOR_VARIANT_DEFAULT in keys
                   else (keys[0] if keys else variant))

    out_dir = Path(target_dir) if target_dir else _system_cursor_dir()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, "无法创建指针目录：%s" % exc

    written, error = _write_cursor_files(pack, variant, out_dir)
    if error:
        return False, error

    if dry_run:
        return True, "已生成指针文件（dry_run，未写注册表）：%s" % out_dir

    if sys.platform != "win32":
        return False, "仅支持 Windows 系统"
    try:
        winreg = _winreg_module()
    except Exception:
        return False, "当前环境不支持注册表操作"

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CURSOR_REG_PATH, 0,
                                winreg.KEY_SET_VALUE) as key:
            for name, path in written.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, str(path))
            try:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, SCHEME_NAME)
            except OSError:
                pass
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CURSOR_SCHEMES_PATH, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, SCHEME_NAME, 0, winreg.REG_EXPAND_SZ,
                              _scheme_value(written))
    except OSError as exc:
        return False, "注册表写入失败：%s" % exc
    except Exception as exc:
        return False, "注册表写入失败：%s" % exc

    _broadcast_change()
    return True, "已安装为系统鼠标指针：%s" % SCHEME_NAME


def restore_system_cursors(*, dry_run: bool = False):
    """清空自定义指针注册项并删除方案，恢复系统默认。"""
    if dry_run:
        return True, "dry_run：跳过注册表恢复"
    if sys.platform != "win32":
        return False, "仅支持 Windows 系统"
    try:
        winreg = _winreg_module()
    except Exception:
        return False, "当前环境不支持注册表操作"

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CURSOR_REG_PATH, 0,
                                winreg.KEY_SET_VALUE) as key:
            for name in CURSOR_VALUE_NAMES:
                winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, "")
            try:
                current, _ = winreg.QueryValueEx(key, "")
                if str(current) == SCHEME_NAME:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "")
            except OSError:
                pass
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CURSOR_SCHEMES_PATH, 0,
                                    winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, SCHEME_NAME)
                except FileNotFoundError:
                    pass
        except OSError:
            pass
    except OSError as exc:
        return False, "注册表写入失败：%s" % exc
    except Exception as exc:
        return False, "注册表写入失败：%s" % exc

    _broadcast_change()
    return True, "已恢复系统默认鼠标指针"


def system_cursors_installed() -> bool:
    """判断 HKCU 的 Arrow 指针是否指向我们的目录。"""
    if sys.platform != "win32":
        return False
    try:
        winreg = _winreg_module()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CURSOR_REG_PATH, 0,
                            winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, "Arrow")
    except OSError:
        return False
    except Exception:
        return False
    if not value:
        return False
    target = os.path.normcase(os.path.normpath(str(_system_cursor_dir())))
    current = os.path.normcase(os.path.normpath(os.path.expandvars(str(value))))
    return current.startswith(target)


# ────────────────────────── 开发预览 ──────────────────────────

class _RoleTile(QWidget):
    """预览方块：画首帧与角色名；用 ``_crf_role`` 让管理器套对应指针。"""

    def __init__(self, role: str, label: str, parent=None):
        super().__init__(parent)
        self._role = role
        self._label = label
        self._preview = QPixmap()
        self.setFixedSize(112, 108)
        self.setProperty("_crf_role", role)
        self.setProperty("_crf_orig_shape", _shape_value(Qt.CursorShape.ArrowCursor))

    def set_preview(self, pixmap) -> None:
        self._preview = pixmap if pixmap is not None else QPixmap()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().window())
        if not self._preview.isNull():
            x = (self.width() - self._preview.width()) // 2
            painter.drawPixmap(x, 6, self._preview)
        painter.setPen(self.palette().windowText().color())
        painter.drawText(
            self.rect().adjusted(2, self.height() - 30, -2, -2),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "%s\n%s" % (self._role, self._label))
        painter.end()


class _PreviewDialog(QDialog):
    """开发预览窗口：选变体、看 15 个角色、安装/恢复系统指针。"""

    def __init__(self, pack=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("罗小黑鼠标指针 · 预览")
        self._pack = pack if pack is not None else CursorPack()
        self._tiles = {}
        self._manager = CursorManager(self, pack=self._pack)
        self._build()
        self._manager.install()
        for tile in self._tiles.values():
            self._manager.attach(tile)
        self._reload_previews()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("变体："))
        self._combo = QComboBox()
        for key, label in self._pack.variants():
            self._combo.addItem(label, key)
        index = self._combo.findData(self._manager.variant)
        if index >= 0:
            self._combo.setCurrentIndex(index)
        bar.addWidget(self._combo)

        self._check = QCheckBox("启用自定义指针")
        self._check.setChecked(self._manager.enabled)
        bar.addWidget(self._check)
        bar.addStretch(1)

        self._btn_install = QPushButton("安装为系统鼠标")
        self._btn_restore = QPushButton("恢复默认")
        bar.addWidget(self._btn_install)
        bar.addWidget(self._btn_restore)
        root.addLayout(bar)

        grid = QGridLayout()
        grid.setSpacing(6)
        roles = self._pack.roles(self._manager.variant)
        for index, (role, cursor) in enumerate(roles.items()):
            tile = _RoleTile(role, cursor.label, self)
            self._tiles[role] = tile
            grid.addWidget(tile, index // 5, index % 5)
        root.addLayout(grid)

        self._status = QLabel("把鼠标移到方块上查看实际指针；动画角色会实时播放。")
        root.addWidget(self._status)

        self._combo.currentIndexChanged.connect(self._on_variant)
        self._check.toggled.connect(self._on_enabled)
        self._btn_install.clicked.connect(self._on_install)
        self._btn_restore.clicked.connect(self._on_restore)

    def _on_variant(self, index: int) -> None:
        key = self._combo.itemData(index)
        if not key:
            return
        self._manager.set_variant(str(key))
        self._reload_previews()

    def _on_enabled(self, checked: bool) -> None:
        self._manager.set_enabled(bool(checked))

    def _on_install(self) -> None:
        ok, message = install_system_cursors(self._manager.variant)
        if ok:
            QMessageBox.information(self, "安装为系统鼠标", message)
        else:
            QMessageBox.warning(self, "安装为系统鼠标", message)

    def _on_restore(self) -> None:
        ok, message = restore_system_cursors()
        if ok:
            QMessageBox.information(self, "恢复默认", message)
        else:
            QMessageBox.warning(self, "恢复默认", message)

    def _reload_previews(self) -> None:
        roles = self._pack.roles(self._manager.variant)
        for role, tile in self._tiles.items():
            cursor = roles.get(role)
            if cursor is None:
                tile.set_preview(QPixmap())
                continue
            frames = cursor.pixmaps()
            if not frames or frames[0].isNull():
                tile.set_preview(QPixmap())
                continue
            tile.set_preview(frames[0].scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))


def main(argv=None) -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    dialog = _PreviewDialog()
    dialog.resize(660, 460)
    dialog.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
