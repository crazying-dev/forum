# -*- coding: utf-8 -*-
"""矢量图标（SVG）——与网页端同一套图形。

网页端通过 CDN 引入 ``font-awesome@4.7.0``，客户端使用**同一版本字体轮廓**
导出的 ``resources/icons/*.svg``（同一字形、同一比例），因此两侧图标完全一致。

渲染时按主题色重着色并缓存（每个尺寸/颜色只渲染一次），等比放大不失真。

对外接口：

* :func:`pixmap` —— 指定尺寸/颜色的 ``QPixmap``
* :func:`icon`   —— 指定尺寸/颜色的 ``QIcon``
* :func:`clear_cache` —— 主题切换后清空缓存
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .paths import resource

DEFAULT_COLOR = "#2E4659"
_PLACEHOLDER = "#000000"
_RENDER_SCALE = 2.0  # 以 2 倍分辨率渲染再按 DPR 缩放，保证高分屏清晰

_cache: dict[tuple, QPixmap] = {}


def exists(name: str) -> bool:
    """图标文件是否存在。"""
    return resource("icons", "%s.svg" % name).is_file()


def _source(name: str) -> str:
    try:
        return resource("icons", "%s.svg" % name).read_text(encoding="utf-8")
    except OSError:
        return ""


def pixmap(name: str, size: int = 18, color: str = DEFAULT_COLOR) -> QPixmap:
    """取得指定尺寸与颜色的图标位图（失败时返回空 pixmap，不抛异常）。"""
    size = max(8, int(size))
    color = str(color or DEFAULT_COLOR)
    key = (str(name), size, color)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    pix = QPixmap()
    source = _source(name)
    if source:
        renderer = QSvgRenderer(QByteArray(source.replace(_PLACEHOLDER, color).encode("utf-8")))
        if renderer.isValid():
            pixels = max(1, int(round(size * _RENDER_SCALE)))
            pix = QPixmap(pixels, pixels)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            renderer.render(painter)
            painter.end()
            pix.setDevicePixelRatio(_RENDER_SCALE)
    _cache[key] = pix
    return pix


def icon(name: str, size: int = 18, color: str = DEFAULT_COLOR) -> QIcon:
    """取得指定尺寸与颜色的 ``QIcon``。"""
    return QIcon(pixmap(name, size=size, color=color))


def clear_cache() -> None:
    _cache.clear()
