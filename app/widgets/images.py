# -*- coding: utf-8 -*-
"""图片缓存与展示：头像（圆形）与内嵌图片（异步加载）。

所有远端图片落地到 ``~/.Cr/forum/cache/avatar/``、``~/.Cr/forum/cache/image/``，
同一 URL 只请求一次，之后直接用本地文件。
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import requests
from PyQt6.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from .. import api as api_mod
from .. import constants, logger, paths

_log = logger.get_logger("images")

_MEMORY_LIMIT = 400


class ImageCache(QObject):
    """远端图片 → 本地文件缓存。"""

    ready = pyqtSignal(str, str)  # (url, 本地路径)

    def __init__(self, folder: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._folder = Path(folder) if folder else paths.image_cache_dir()
        self._lock = threading.Lock()
        self._pending: dict[str, bool] = {}
        self._memory: dict[str, QPixmap] = {}

    # ── 路径 ──
    def key_for(self, url: str) -> str:
        return hashlib.sha1(str(url).encode("utf-8")).hexdigest()

    def path_for(self, url: str) -> Path:
        suffix = ""
        raw = str(url).split("?")[0]
        if "." in raw.rsplit("/", 1)[-1]:
            suffix = "." + raw.rsplit(".", 1)[-1][:6]
        return self._folder / (self.key_for(url) + suffix)

    def local(self, url: str) -> str:
        """已缓存则返回本地路径，否则空串。"""
        if not url:
            return ""
        path = self.path_for(url)
        return str(path) if path.is_file() else ""

    def cached_pixmap(self, url: str) -> QPixmap | None:
        """只读缓存（不发请求）。"""
        if not url:
            return None
        pixmap = self._memory.get(url)
        if pixmap is not None and not pixmap.isNull():
            return pixmap
        local = self.local(url)
        if not local:
            return None
        pixmap = QPixmap(local)
        if pixmap.isNull():
            return None
        self._remember(url, pixmap)
        return pixmap

    def _remember(self, url: str, pixmap: QPixmap) -> None:
        if len(self._memory) > _MEMORY_LIMIT:
            self._memory.clear()
        self._memory[url] = pixmap

    def remember(self, url: str, pixmap: QPixmap) -> None:
        if not pixmap.isNull():
            self._remember(url, pixmap)

    # ── 下载 ──
    def fetch(self, url: str, on_ready=None, on_error=None, *, force: bool = False) -> str:
        """异步取图。已缓存时同步回调，返回本地路径（未命中时为空串）。"""
        if not url:
            if on_error is not None:
                on_error("地址为空")
            return ""
        if not force:
            local = self.local(url)
            if local:
                if on_ready is not None:
                    on_ready(url, local)
                return local
        with self._lock:
            if self._pending.get(url):
                return ""
            self._pending[url] = True

        def _work():
            try:
                return self._download(url)
            finally:
                with self._lock:
                    self._pending.pop(url, None)

        def _ok(path):
            if on_ready is not None:
                on_ready(url, str(path))
            self.ready.emit(url, str(path))

        def _fail(message):
            if on_error is not None:
                on_error(message)

        api_mod.run_async(_work, on_success=_ok, on_error=_fail, label="取图")
        return ""

    def _download(self, url: str) -> Path:
        target = self.path_for(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(
            str(url), timeout=(8, 25),
            headers={"User-Agent": constants.CLIENT_UA, "Accept": "image/*,*/*"})
        if response.status_code >= 400:
            raise RuntimeError("HTTP %s" % response.status_code)
        data = response.content
        if not data:
            raise RuntimeError("空响应")
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)
        return target


image_cache = ImageCache()
avatar_cache = ImageCache(paths.avatar_cache_dir())


def _alive(widget) -> bool:
    """控件是否仍然活着（异步回调可能在页面销毁后才跑）。"""
    try:
        widget.objectName()
        return True
    except RuntimeError:
        return False
    except Exception:
        return True


# ────────────────────────── 头像 ──────────────────────────


def _circular(source: QPixmap, size: int) -> QPixmap:
    """裁成正方形后缩放，并做圆形遮罩。"""
    if source.isNull() or size <= 0:
        return QPixmap()
    side = min(source.width(), source.height())
    if side <= 0:
        return QPixmap()
    cropped = source.copy((source.width() - side) // 2, (source.height() - side) // 2,
                          side, side)
    scaled = cropped.scaled(size, size,
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                           QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return out


class Avatar(QWidget):
    """圆形头像；未加载时显示默认头像资源。"""

    clicked = pyqtSignal()

    def __init__(self, size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = int(size)
        self._url = ""
        self._pixmap = QPixmap()
        self._fallback = QPixmap()
        self.setFixedSize(self._size, self._size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, False)
        self._load_fallback()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _load_fallback(self) -> None:
        path = constants.DEFAULT_AVATAR
        if path.is_file():
            source = QPixmap(str(path))
            if not source.isNull():
                self._fallback = _circular(source, self._size)

    def set_size(self, size: int) -> None:
        self._size = int(size)
        self.setFixedSize(self._size, self._size)
        self._load_fallback()
        if not self._pixmap.isNull():
            self._pixmap = _circular(self._pixmap, self._size)

    def set_url(self, url: str) -> None:
        url = str(url or "").strip()
        self._url = url
        if not url:
            self._pixmap = QPixmap()
            self.update()
            return
        absolute = constants.absolute(url)
        cached = avatar_cache.cached_pixmap(absolute)
        if cached is not None:
            self._set_source(cached)
            return
        self._pixmap = QPixmap()
        self.update()

        def _ok(_url, local_path):
            pixmap = QPixmap(local_path)
            if pixmap.isNull() or self._url != url or not _alive(self):
                return
            avatar_cache.remember(absolute, pixmap)
            self._set_source(pixmap)

        avatar_cache.fetch(absolute, on_ready=_ok)

    def _set_source(self, source: QPixmap) -> None:
        self._pixmap = _circular(source, self._size)
        self.update()

    def clear(self) -> None:
        self._url = ""
        self._pixmap = QPixmap()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.SmoothPixmapTransform)
        if not self._pixmap.isNull():
            painter.drawPixmap(0, 0, self._pixmap)
        elif not self._fallback.isNull():
            painter.drawPixmap(0, 0, self._fallback)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#6A8C89")))
            painter.drawEllipse(0, 0, self._size, self._size)
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()


# ────────────────────────── 内嵌图片 ──────────────────────────


class AsyncImage(QLabel):
    """异步加载的图片（保持宽高比，最大宽度自适应）。"""

    clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None, *, max_width: int = 0,
                 radius: int = 10) -> None:
        super().__init__(parent)
        self._max_width = int(max_width)
        self._radius = radius
        self._url = ""
        self._source = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(60)
        self.setText("图片加载中…")

    def set_max_width(self, width: int) -> None:
        self._max_width = int(width)
        self._apply()

    def set_url(self, url: str) -> None:
        url = str(url or "").strip()
        self._url = url
        if not url:
            self.setText("")
            return
        absolute = constants.absolute(url)
        cached = image_cache.cached_pixmap(absolute)
        if cached is not None:
            self._source = cached
            self._apply()
            return
        self.setText("图片加载中…")

        def _ok(_u, local_path):
            pixmap = QPixmap(local_path)
            if pixmap.isNull() or self._url != url or not _alive(self):
                return
            image_cache.remember(absolute, pixmap)
            self._source = pixmap
            self._apply()

        def _fail(_msg):
            if self._url == url and _alive(self):
                self.setText("图片加载失败")

        image_cache.fetch(absolute, on_ready=_ok, on_error=_fail)

    def set_local(self, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.setText("图片不可用")
            return
        self._source = pixmap
        self._apply()

    def _apply(self) -> None:
        if self._source.isNull():
            return
        width = self._max_width or self.width() or 320
        if width <= 0:
            width = 320
        if self._source.width() > width:
            scaled = self._source.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        else:
            scaled = self._source
        self.setPixmap(scaled)
        self.setMinimumHeight(0)
        self.setText("")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._max_width <= 0 and not self._source.isNull():
            self._apply()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._url:
            self.clicked.emit(self._url)
        super().mouseReleaseEvent(event)
