# -*- coding: utf-8 -*-
"""人机验证弹窗（Cloudflare Turnstile 优先，自研滑块拼图兜底；三端同源）。

provider 由服务端 ``POST /api/captcha/challenge`` 返回的 ``provider`` 字段决定：

* ``turnstile`` —— 弹窗内嵌 ``QWebEngineView`` 加载**站内** ``/captcha-embed``
  页面（该页面再自行加载 Cloudflare 官方脚本并渲染 widget；不反代官方域名）；
  验证通过后页面把一次性 token 经 ``document.title``（``captcha:token:<token>``）
  回传，本模块解析后交给业务请求。
* ``slider`` —— 自研滑块拼图（无第三方依赖 / 无 WebEngine 时的兜底）。
* ``off`` —— 服务端关闭；``challenge`` 返回 ``enabled=false`` 时以空 token 放行。

服务端在 Site Key / Secret 缺失时会**自动**把 provider 回退为 slider，
因此这里只需按返回的 ``provider`` 分派，无需自己判断配置。

滑块流程（provider=slider 时，与服务端 ``api/captcha`` 一致）：

1. ``POST /api/captcha/challenge`` 拿挑战：背景图 + 拼图块 + 缺口纵向位置；
2. 拖动拼图块到位 —— 松手时 ``POST /api/captcha/verify {captcha_token, captcha_x}``；
3. 通过后把**同一个** token 塞进真实业务请求体（服务端校验时 ``pop`` 掉，一次性）。

为什么事件通道用 ``document.title`` 而不是 JS bridge
----------------------------------------------------
Qt WebEngine 没有 Android 那样的 ``addJavascriptInterface``；实测
``QWebEnginePage.titleChanged`` **不会截断**超长标题（3000+ 字符原样送达），
所以直接复用站内页面 ``hostReport()`` 的通用兜底通道即可，服务端零改动。

图像全靠 ``QPainter`` 绘制，拼图块可从背景图中裁出，与网页端 / 安卓端同一套服务端
素材。
"""

from __future__ import annotations

import base64
from urllib.parse import urlencode

from PyQt6.QtCore import QPointF, QRectF, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDialog, QWidget

from .. import api as api_mod
from .. import constants, logger, theme
from .common import Muted, vbox
from .dialogs import BaseDialog

_log = logger.get_logger("captcha")

TRACK_HEIGHT = 40   # 滑块轨道高度
TRACK_GAP = 10      # 轨道与拼图舞台的间距
HANDLE_WIDTH = 40   # 滑块手柄宽度
HANDLE_PAD = 3      # 手柄与轨道上下边缘的留白
DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 180
DEFAULT_PIECE = 50

# ── provider / 内嵌验证页（与 Android core/Captcha.kt、服务端 api/captcha 对齐）──
PROVIDER_SLIDER = "slider"
PROVIDER_TURNSTILE = "turnstile"
PROVIDER_OFF = "off"
# 服务端 / 旧版本可能用这些写法表示「关闭」
PROVIDER_OFF_SYNONYMS = ("off", "none", "disable", "disabled", "0", "false")
EMBED_PATH = "/captcha-embed"
# flexible：widget 撑满容器宽度，适配窄弹窗（官方 normal=300x65 会溢出）
EMBED_SIZE = "flexible"
EMBED_HEIGHT = 200          # 内嵌页面最小高度（px）
EVENT_PREFIX = "captcha:"   # 站内页面回传事件的标题前缀

SLIDER_HINT = "拖动下方滑块，把拼图块移到缺口处完成验证。"
TURNSTILE_HINT = "请完成下方安全验证。"

# 站内页面以这些「短码」表示无法验证的终态
EMBED_ERROR_TEXT = {
    "disabled": "人机验证已关闭",
    "unconfigured": "验证服务未配置，请联系管理员",
}


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


# ────────────────────────── provider / 事件解析（纯函数，便于单测） ──────────────────────────


def provider_of(raw) -> str:
    """归一化服务端返回的 provider；未知 / 空值一律回退自研滑块。"""
    text = str(raw or "").strip().lower()
    if text in PROVIDER_OFF_SYNONYMS:
        return PROVIDER_OFF
    if text == PROVIDER_TURNSTILE:
        return PROVIDER_TURNSTILE
    return PROVIDER_SLIDER


def embed_path_of(raw) -> str:
    """内嵌页面路径（空值回退 :data:`EMBED_PATH`）。"""
    return str(raw or "").strip() or EMBED_PATH


def embed_url(base_url, path=None, theme_name=None, size=None) -> str:
    """拼出内嵌验证页完整地址（与 Android ``Captcha.embedUrl`` 同口径）。

    * ``base_url`` 形如 ``https://www.yjlt.top``；
    * ``path`` 允许绝对地址 / ``//host/path`` / ``/path`` / ``path``；
    * ``theme_name`` 仅 ``dark`` 生效，其余一律 ``light``；
    * ``size`` 仅 ``normal`` / ``compact`` 生效，其余一律 ``flexible``。
    """
    base = str(base_url or "").strip().rstrip("/")
    target = embed_path_of(path)
    if target.startswith(("http://", "https://")):
        url = target
    elif target.startswith("//"):
        url = "https:" + target
    else:
        url = base + "/" + target.lstrip("/")
    mode = "dark" if str(theme_name or "").strip().lower() == "dark" else "light"
    dim = str(size or "").strip().lower()
    if dim not in ("normal", "compact"):
        dim = EMBED_SIZE
    joiner = "&" if "?" in url else "?"
    return "%s%s%s" % (url, joiner, urlencode({"theme": mode, "size": dim}))


def event_of(raw):
    """解析 ``captcha:<kind>:<payload>``；不符合协议返回 ``None``。

    只在 **首个** 冒号处切分，保证 token 里的 ``:`` / ``.`` 等字符原样保留。
    """
    text = str(raw or "")
    if not text.startswith(EVENT_PREFIX):
        return None
    kind, _sep, payload = text[len(EVENT_PREFIX):].partition(":")
    kind = kind.strip().lower()
    if not kind:
        return None
    return kind, payload


def token_from_event(raw):
    """仅从 ``token`` 事件取一次性 token；其它事件返回 ``None``。"""
    parsed = event_of(raw)
    if not parsed or parsed[0] != "token":
        return None
    return str(parsed[1] or "").strip() or None


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
    """人机验证弹窗；通过后 :attr:`result_token` 为一次性 token。

    按服务端 ``challenge`` 返回的 ``provider`` 呈现：

    * ``turnstile``：内嵌 ``QWebEngineView`` 加载站内 ``/captcha-embed`` 页面；
      页面验证通过后经 ``document.title``（``captcha:token:<token>``）回传。
    * ``slider``：自研滑块拼图（默认 / 兜底）。
    """

    def __init__(self, parent: QWidget | None = None, *,
                 autostart: bool = True) -> None:
        super().__init__(parent, title="人机验证", width=DEFAULT_WIDTH + 40)
        self.result_token = ""
        self.enabled = True
        self.provider = PROVIDER_SLIDER
        self._challenge_token = ""
        self._busy = False
        self._sitekey = ""
        self._embed_view = None
        # Turnstile 解不出来时的回退状态（只回退一次；回退后「刷新」也不回 Turnstile）
        self._tried_fallback = False
        self._slider_only = False

        self.hint = Muted(SLIDER_HINT)
        self.body.addWidget(self.hint)

        # 滑块舞台与内嵌 WebView 共用同一个容器，按 provider 切换显隐
        # （隐藏的 widget 不占布局位置，无需 replaceWidget 的麻烦）。
        self.captcha_area = QWidget()
        self.captcha_layout = vbox(self.captcha_area, spacing=0)
        self.stage = SliderStage()
        self.captcha_layout.addWidget(self.stage, 0, Qt.AlignmentFlag.AlignHCenter)
        self.body.addWidget(self.captcha_area, 0, Qt.AlignmentFlag.AlignHCenter)

        self.status = Muted("正在加载验证…")
        self.body.addWidget(self.status)

        self.stage.released.connect(self._on_released)
        self.refresh_btn = self.add_action("换一张", None, self.refresh)
        self.add_action("取消", None, self.reject)

        if autostart:
            self.refresh()

    # ────────────────────── 内嵌 Turnstile 页面 ──────────────────────
    def _embed_theme(self) -> str:
        """当前主题 → 内嵌页面的 ``theme`` 参数（仅 dark 生效）。"""
        try:
            mode = str(theme.resolve_mode() or "")
        except Exception:  # noqa: BLE001
            return "light"
        return "dark" if ("night" in mode or "dark" in mode) else "light"

    def _ensure_embed(self):
        """懒创建内嵌 WebView；PyQt6-WebEngine 不可用时返回 ``None``。"""
        if self._embed_view is not None:
            return self._embed_view
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:  # noqa: BLE001 — 未安装 PyQt6-WebEngine
            _log.warning("Qt WebEngine 不可用，无法承载 Turnstile：%s", exc)
            return None
        try:
            view = QWebEngineView(self.captcha_area)
            view.setMinimumHeight(EMBED_HEIGHT)
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            view.titleChanged.connect(self._on_embed_title)
            view.loadFinished.connect(self._on_embed_load_finished)
        except Exception as exc:  # noqa: BLE001
            _log.warning("QWebEngineView 创建失败：%s", exc)
            return None
        self.captcha_layout.addWidget(view)
        view.hide()
        self._embed_view = view
        return view

    def _show_stage(self) -> None:
        if self._embed_view is not None:
            try:
                self._embed_view.stop()
            except Exception:  # noqa: BLE001
                pass
            self._embed_view.hide()
        self.stage.show()

    def _show_embed(self) -> None:
        self.stage.hide()
        if self._embed_view is not None:
            self._embed_view.show()

    def _on_embed_title(self, title: str) -> None:
        """解析内嵌页面经 ``document.title`` 回传的事件。"""
        if self.provider != PROVIDER_TURNSTILE:
            return
        parsed = event_of(title)
        if not parsed:
            return
        kind, payload = parsed
        if kind == "token":
            token = token_from_event(title)
            if token:
                self.result_token = token
                self.accept()
            return
        if kind == "error":
            self._on_embed_error(payload)

    def _on_embed_error(self, payload: str) -> None:
        text = str(payload or "").strip()
        # Turnstile 组件报错 / 加载失败 / 超时 → 自动回退自研滑块（只回退一次）。
        if self.provider == PROVIDER_TURNSTILE and self._fallback_to_slider():
            return
        self.status.setText(EMBED_ERROR_TEXT.get(text, text) or "验证失败，请重试")

    def _on_embed_load_finished(self, ok: bool) -> None:
        """承载页加载失败（网络 / 站点不可达）→ 回退自研滑块。"""
        if ok or self.provider != PROVIDER_TURNSTILE:
            return
        self._on_embed_error("load")

    def _fallback_to_slider(self) -> bool:
        """Turnstile 解不出来时的兜底：改要一帧自研滑块挑战。

        只回退一次（避免 Turnstile / 滑块来回抖动）；回退后 :attr:`_slider_only` 置位，
        「换一张」也不再回到 Turnstile。返回是否真的发起了回退。
        """
        if self._tried_fallback:
            return False
        self._tried_fallback = True
        self._slider_only = True
        self.refresh(True)
        return True

    def _release_embed(self) -> None:
        """关闭弹窗时停掉内嵌页面，避免后台继续跑脚本 / 残留进程。"""
        view, self._embed_view = self._embed_view, None
        if view is None:
            return
        try:
            view.titleChanged.disconnect(self._on_embed_title)
        except Exception:  # noqa: BLE001
            pass
        try:
            view.stop()
            view.setUrl(QUrl("about:blank"))
        except Exception:  # noqa: BLE001
            pass
        try:
            view.setParent(None)
            view.deleteLater()
        except Exception:  # noqa: BLE001
            pass

    # ────────────────────── 获取挑战 ──────────────────────
    def refresh(self, force_slider=False) -> None:
        """重新申请挑战；``force_slider`` 为真时强制要自研滑块（回退通道）。

        注意：``refresh`` 也直接挂在「换一张」按钮的 ``clicked`` 信号上，
        该信号会附带一个 ``checked`` 参数（恒为 False），故这里按真值判断。
        """
        if force_slider:
            self._slider_only = True
        self._busy = True
        self._challenge_token = ""
        self.provider = PROVIDER_SLIDER
        self._sitekey = ""
        self._show_stage()
        self.stage.reset()
        self.stage.set_enabled(False)
        self.hint.setText(SLIDER_HINT)
        self.refresh_btn.setText("换一张")
        self.refresh_btn.setEnabled(False)
        self.status.setText("正在加载验证…")
        want = PROVIDER_SLIDER if self._slider_only else ""
        api_mod.run_async(lambda: api_mod.api().captcha_challenge(want),
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
        self.provider = provider_of(data.get("provider"))
        if self.provider == PROVIDER_TURNSTILE:
            self._apply_turnstile(data)
            return
        self._apply_challenge(data)

    def _apply_turnstile(self, data: dict) -> None:
        """渲染 Turnstile 内嵌页（与网络解耦，便于离线测试）。"""
        sitekey = str(data.get("sitekey") or "").strip()
        if not sitekey:
            # 服务端没给 sitekey（理论上不会发生）→ 改要一帧自研滑块挑战，不能白屏
            if not self._fallback_to_slider():
                self.provider = PROVIDER_SLIDER
                self.status.setText("验证服务未配置，请联系管理员")
            return
        self._sitekey = sitekey
        self.stage.reset()
        self.stage.set_enabled(False)
        self.hint.setText(TURNSTILE_HINT)
        self.refresh_btn.setText("刷新")
        view = self._ensure_embed()
        if view is None:
            # 系统缺 Qt WebEngine（或创建失败）→ 改走自研滑块，不把用户卡死
            if not self._fallback_to_slider():
                self.status.setText(
                    "当前系统缺少内嵌验证组件（Qt WebEngine），请更新客户端后重试")
            return
        self._show_embed()
        self.status.setText("请完成下方验证")
        url = embed_url(constants.BASE_URL,
                        data.get("embed_url") or EMBED_PATH,
                        self._embed_theme(), EMBED_SIZE)
        view.load(QUrl(url))

    def _apply_challenge(self, data: dict) -> None:
        """渲染一帧滑块挑战（与网络解耦，便于离线测试）。"""
        self.provider = PROVIDER_SLIDER
        self.hint.setText(SLIDER_HINT)
        self.refresh_btn.setText("换一张")
        self._show_stage()
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

    # ────────────────────── 校验（仅滑块） ──────────────────────
    def _on_released(self, value: float) -> None:
        if self.provider != PROVIDER_SLIDER:
            return
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

    # ────────────────────── 收尾 ──────────────────────
    def done(self, code) -> None:  # noqa: N802 — Qt 命名
        self._release_embed()
        super().done(code)


def ask_captcha(parent: QWidget | None = None) -> str | None:
    """弹出人机验证（Turnstile 或自研滑块）；通过返回一次性 token，取消返回 ``None``。

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
