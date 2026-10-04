# -*- coding: utf-8 -*-
"""滑块拼图人机验证弹窗（对照服务端 ``/api/captcha/*``，三端同源）。

流程（两步式，与服务端 ``api/captcha/__init__.py`` 完全一致）：

1. ``POST /api/captcha/challenge`` 拿挑战：背景图 + 拼图块 + 缺口纵向位置；
2. 用户拖动拼图块到缺口处 —— 松手时
   ``POST /api/captcha/verify {captcha_token, captcha_x}``；
3. 通过后把**同一个** token 塞进真实业务请求体（服务端校验时 ``pop`` 掉，一次性）。

服务端关闭人机验证（``CAPTCHA_ENABLED=0``）时 ``challenge`` 返回
``{"success": true, "enabled": false}``，弹窗立即以空 token 关闭，调用方照常请求。

图像全靠 ``QPainter`` 绘制，拼图块可从背景图中裁出，与网页端 / 安卓端同一套服务端
素材，不引入任何第三方 SDK。
"""

from __future__ import annotations

import base64

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDialog, QWidget

from .. import api as api_mod
from .. import logger, theme
from .common import Muted
from .dialogs import BaseDialog

_log = logger.get_logger("captcha")

TRACK_HEIGHT = 40   # 滑块轨道高度
TRACK_GAP = 10      # 轨道与拼图舞台的间距
HANDLE_WIDTH = 40   # 滑块手柄宽度
HANDLE_PAD = 3      # 手柄与轨道上下边缘的留白
DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 180
DEFAULT_PIECE = 50


def decode_data_url(data_url: str) -> bytes:
    """把 ``data:image/png;base64,...`` 还原为原始字节（失败返回空）。"""
    text = str(data_url or "").strip()
    if "," in text:
        text = text.split(",", 1)[1]
    if not text:
        return b""
    try:
        return base64.b64decode(text)
    except Exception:  # noqa: BLE001
        return b""


class SliderStage(QWidget):
    """拼图舞台：背景 + 可拖动拼图块 + 底部滑块轨道（纯 QPainter 绘制）。"""

    released = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bg = QPixmap()
        self.piece = QPixmap()
        self.stage_w = DEFAULT_WIDTH
        self.stage_h = DEFAULT_HEIGHT
        self.piece_size = DEFAULT_PIECE
        self.piece_y = 0
        self.drag_x = 0.0
        self._dragging = False
        self._enabled = False
        self._apply_size()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ────────────────────── 尺寸 / 状态 ──────────────────────
    def _apply_size(self) -> None:
        self.setFixedSize(self.stage_w, self.stage_h + TRACK_GAP + TRACK_HEIGHT)

    def set_challenge(self, bg: QPixmap, piece: QPixmap, *, width: int,
                      height: int, piece_size: int, piece_y: int) -> None:
        self.bg = bg
        self.piece = piece
        self.stage_w = max(int(width), 80)
        self.stage_h = max(int(height), 60)
        self.piece_size = max(int(piece_size), 10)
        self.piece_y = int(piece_y)
        self.drag_x = 0.0
        self._dragging = False
        self._apply_size()
        self.update()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._enabled
                       else Qt.CursorShape.ArrowCursor)
        self.update()

    def is_enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        self.drag_x = 0.0
        self._dragging = False
        self.update()

    # ────────────────────── 几何 / 拖动映射 ──────────────────────
    def max_piece_x(self) -> float:
        """拼图块最右可到位置（保证完整落在舞台内）。"""
        return float(max(self.stage_w - self.piece_size, 1))

    def track_rect(self) -> QRectF:
        return QRectF(0, self.stage_h + TRACK_GAP, self.stage_w, TRACK_HEIGHT)

    def handle_limits(self) -> tuple[float, float]:
        lo = float(HANDLE_PAD)
        hi = float(max(self.stage_w - HANDLE_WIDTH - HANDLE_PAD, HANDLE_PAD + 1))
        return lo, hi

    def handle_x(self) -> float:
        """手柄左边缘 x 坐标（0 → 拼图块在左端）。"""
        lo, hi = self.handle_limits()
        ratio = min(max(self.drag_x / self.max_piece_x(), 0.0), 1.0)
        return lo + ratio * (hi - lo)

    def set_drag(self, value: float) -> None:
        self.drag_x = min(max(float(value), 0.0), self.max_piece_x())
        self.update()

    def _set_from_pointer(self, x: float) -> None:
        """按指针位置反推拼图块 x（指针抓住手柄中心）。"""
        lo, hi = self.handle_limits()
        center = float(x) - HANDLE_WIDTH / 2.0
        ratio = (center - lo) / max(hi - lo, 1.0)
        self.set_drag(min(max(ratio, 0.0), 1.0) * self.max_piece_x())

    # ────────────────────── 鼠标 ──────────────────────
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if not self._enabled:
            return
        point = event.position()
        track = self.track_rect()
        if track.contains(point):
            self._dragging = True
            self._set_from_pointer(point.x())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._set_from_pointer(event.position().x())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if not self._dragging:
            return
        self._dragging = False
        self.released.emit(float(self.drag_x))

    # ────────────────────── 绘制 ──────────────────────
    def paintEvent(self, event) -> None:  # noqa: N802
        palette = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        stage = QRectF(0, 0, self.stage_w, self.stage_h)
        if not self.bg.isNull():
            painter.drawPixmap(0, 0, self.bg)
        else:
            painter.fillRect(stage, QColor(palette.get("bg_input", "#F9FBFA")))

        if not self.piece.isNull():
            painter.drawPixmap(QPointF(self.drag_x, float(self.piece_y)),
                               self.piece)

        track = self.track_rect()
        radius = TRACK_HEIGHT / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.get("bg_input", "#F9FBFA")))
        painter.drawRoundedRect(track, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(palette.get("border", "#E1E8E7")), 1))
        painter.drawRoundedRect(track.adjusted(0, 0, -1, -1), radius, radius)

        handle_x = self.handle_x()
        filled = QRectF(track.left(), track.top(),
                        handle_x + HANDLE_WIDTH / 2.0, track.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.get("primary", "#6A8C89")))
        painter.drawRoundedRect(filled, radius, radius)

        handle = QRectF(handle_x, track.top() + HANDLE_PAD,
                        HANDLE_WIDTH, TRACK_HEIGHT - 2 * HANDLE_PAD)
        painter.setBrush(QColor(palette.get("bg_card", "#FFFFFF")))
        painter.drawRoundedRect(handle, 6, 6)
        painter.setPen(QPen(QColor(palette.get("border", "#E1E8E7")), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(handle.adjusted(0, 0, -1, -1), 6, 6)
        painter.end()


class SliderCaptchaDialog(BaseDialog):
    """滑块拼图验证弹窗；通过后 :attr:`result_token` 为一次性 token。"""

    def __init__(self, parent: QWidget | None = None, *,
                 autostart: bool = True) -> None:
        super().__init__(parent, title="人机验证", width=DEFAULT_WIDTH + 40)
        self.result_token = ""
        self.enabled = True
        self._challenge_token = ""
        self._busy = False

        self.body.addWidget(Muted("拖动下方滑块，把拼图块移到缺口处完成验证。"))

        self.stage = SliderStage()
        self.body.addWidget(self.stage, 0, Qt.AlignmentFlag.AlignHCenter)

        self.status = Muted("正在加载验证…")
        self.body.addWidget(self.status)

        self.stage.released.connect(self._on_released)
        self.refresh_btn = self.add_action("换一张", None, self.refresh)
        self.add_action("取消", None, self.reject)

        if autostart:
            self.refresh()

    # ────────────────────── 获取挑战 ──────────────────────
    def refresh(self) -> None:
        self._busy = True
        self._challenge_token = ""
        self.stage.reset()
        self.stage.set_enabled(False)
        self.refresh_btn.setEnabled(False)
        self.status.setText("正在加载验证…")
        api_mod.run_async(lambda: api_mod.api().captcha_challenge(),
                          self._on_challenge, self._on_challenge_failed,
                          label="人机验证")

    def _on_challenge(self, result) -> None:
        self._busy = False
        self.refresh_btn.setEnabled(True)
        if not result.ok:
            self.stage.set_enabled(False)
            self.status.setText(result.message or "加载验证失败，请重试")
            return
        if result.get("enabled") is False:
            # 服务端已关闭人机验证：直接放行，业务请求无需携带 token
            self.enabled = False
            self.result_token = ""
            self.accept()
            return
        data = result.data if isinstance(result.data, dict) else {}
        self._apply_challenge(data)

    def _apply_challenge(self, data: dict) -> None:
        """渲染一帧挑战（与网络解耦，便于离线测试）。"""
        token = str(data.get("token") or "").strip()
        bg = QPixmap()
        bg.loadFromData(decode_data_url(str(data.get("bg") or "")))
        piece = QPixmap()
        piece.loadFromData(decode_data_url(str(data.get("piece") or "")))
        if not token or bg.isNull() or piece.isNull():
            self._challenge_token = ""
            self.stage.set_enabled(False)
            self.status.setText("验证素材加载失败，请点击「换一张」重试")
            return
        self._challenge_token = token
        self.stage.set_challenge(
            bg, piece,
            width=int(data.get("width") or DEFAULT_WIDTH),
            height=int(data.get("height") or DEFAULT_HEIGHT),
            piece_size=int(data.get("piece_size") or DEFAULT_PIECE),
            piece_y=int(data.get("y") or 0))
        self.stage.set_enabled(True)
        self.status.setText("拖动滑块把拼图块移到缺口处")

    def _on_challenge_failed(self, message: str) -> None:
        self._busy = False
        self.refresh_btn.setEnabled(True)
        self.stage.set_enabled(False)
        self.status.setText(message or "加载验证失败，请重试")

    # ────────────────────── 校验 ──────────────────────
    def _on_released(self, value: float) -> None:
        token = self._challenge_token
        if self._busy or not token:
            return
        self._busy = True
        self.stage.set_enabled(False)
        self.refresh_btn.setEnabled(False)
        self.status.setText("正在校验…")
        api_mod.run_async(lambda: api_mod.api().captcha_verify(token, value),
                          self._on_verified, self._on_verify_failed,
                          label="人机验证")

    def _on_verified(self, result) -> None:
        self._busy = False
        self.refresh_btn.setEnabled(True)
        if result.ok:
            self.result_token = str(result.get("token") or self._challenge_token)
            self.accept()
            return
        self.status.setText(result.message or "验证失败，请重试")
        self.refresh()

    def _on_verify_failed(self, message: str) -> None:
        self._busy = False
        self.refresh_btn.setEnabled(True)
        self.status.setText(message or "验证失败，请重试")


def ask_captcha(parent: QWidget | None = None) -> str | None:
    """弹出滑块拼图验证；通过返回一次性 token，用户取消返回 ``None``。

    服务端关闭人机验证时返回空串（调用方无需在请求体里携带 token）。
    异常一律记日志并返回 ``None``（宁可让业务请求失败，也不静默放行）。
    """
    try:
        dialog = SliderCaptchaDialog(parent)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        token = dialog.result_token
    except Exception as exc:  # noqa: BLE001
        _log.warning("人机验证弹窗异常：%s", exc)
        return None
    if not accepted:
        return None
    return str(token or "")
