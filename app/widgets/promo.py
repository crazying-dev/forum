# -*- coding: utf-8 -*-
"""「支持作者」弹窗：启动时按概率随机弹出，或由常驻入口主动打开。

* 启动随机弹窗：次数记在 ``config.json`` 的 ``launch_count``（每次启动 +1，无论是否弹窗），
  弹出概率取 :data:`constants.PROMO_PROBABILITY`（默认 30%）
* 常驻入口（托盘菜单 / 设置页「关于」）：调用 :func:`show_support`，不掷概率、不动计数
* 赞赏码是远端图片，复用 :data:`app.widgets.images.image_cache` 落盘缓存
  （仅首次下载，之后直接读本地缓存，与网页端、Android 端同源同图）
"""

from __future__ import annotations

import random

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

from .. import config as config_mod
from .. import constants, logger
from .common import Muted
from .dialogs import BaseDialog
from .images import AsyncImage

_log = logger.get_logger("promo")

QR_MAX_WIDTH = 220


def bump_launch_count(cfg=None) -> int:
    """启动次数 +1 并返回新值（``cfg`` 仅测试时注入）。"""
    config = cfg if cfg is not None else config_mod.current()
    try:
        count = int(config.get("launch_count", 0) or 0) + 1
    except (TypeError, ValueError):
        count = 1
    try:
        config.set("launch_count", count)
    except Exception as exc:  # noqa: BLE001
        _log.warning("启动次数写入失败：%s", exc)
    return count


def should_show(*, probability: float | None = None, rand: float | None = None) -> bool:
    """是否弹出（概率命中）。``rand`` 仅供测试注入 ``[0, 1)``。"""
    limit = constants.PROMO_PROBABILITY if probability is None else float(probability)
    value = random.random() if rand is None else float(rand)
    return value < limit


def promo_text(count: int) -> str:
    """启动随机弹窗主文案（带本地打开次数）。"""
    return "你已经第 %d 次打开妖精论坛了，要不要支持一下我～" % int(count)


MANUAL_TEXT = ("妖精论坛是纯公益的粉丝二创项目，服务器与开发全凭热爱维持。"
               "如果它帮到了你，请我喝杯奶茶就好～")


class PromoDialog(BaseDialog):
    """支持作者弹窗：文案 + 赞赏码 + 关闭按钮。

    * 启动随机弹窗（``manual=False``，默认）：文案带打开次数，按钮为「以后再说」
    * 常驻入口（``manual=True``）：固定公益文案，按钮为「关闭」
    """

    def __init__(self, parent: QWidget | None = None, *, count: int = 0,
                 manual: bool = False) -> None:
        super().__init__(parent,
                         title="支持妖精论坛" if manual else "支持一下妖精论坛",
                         width=360)
        message = QLabel(MANUAL_TEXT if manual else promo_text(count))
        message.setWordWrap(True)
        self.body.addWidget(message)

        self.qr = AsyncImage(max_width=QR_MAX_WIDTH, radius=8)
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr.setMinimumHeight(QR_MAX_WIDTH)
        self.qr.set_url(constants.PROMO_QR_URL)
        self.body.addWidget(self.qr, 0, Qt.AlignmentFlag.AlignHCenter)

        self.body.addWidget(Muted("扫码请我喝杯奶茶，感谢每一位支持者～"))
        self.add_action("关闭" if manual else "以后再说", "primary", self.accept)


def show_support(parent: QWidget | None = None) -> bool:
    """常驻入口：直接打开「支持作者」弹窗（不掷概率、不改启动计数）。

    与 :func:`maybe_show` 共用 :class:`PromoDialog`；异常只记日志，绝不打断调用方。
    """
    try:
        PromoDialog(parent, manual=True).exec()
    except Exception as exc:  # noqa: BLE001
        _log.warning("支持弹窗展示失败：%s", exc)
        return False
    return True


def maybe_show(parent: QWidget | None = None, *, count: int | None = None,
               rand: float | None = None) -> bool:
    """按概率决定是否弹出；返回是否真的弹了（异常只记日志，不影响启动）。"""
    if not should_show(rand=rand):
        return False
    try:
        dialog = PromoDialog(parent, count=int(count or 0))
        dialog.exec()
    except Exception as exc:  # noqa: BLE001
        _log.warning("支持弹窗展示失败：%s", exc)
        return False
    return True
