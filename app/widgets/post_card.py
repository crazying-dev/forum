# -*- coding: utf-8 -*-
"""帖子卡片：整卡可点击进详情，作者头像/用户名单独跳用户页。"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QWidget

from .. import constants, yearmode
from .common import Chip, Muted, UserLink, hbox, vbox
from .images import Avatar


def with_author(post: dict, *, user_id: str = "", name: str = "",
                avatar: str = "") -> dict:
    """补齐帖子作者信息（返回副本，不修改入参）。

    历史接口 ``/api/user/<id>/posts`` 不返回 ``user_id`` / ``user_name`` /
    ``user_avatar``，个人主页的帖子卡片因此回退成「匿名用户」+ 默认头像。
    而在「某个用户的主页」里，列表中的帖子必然属于该主页的主人，
    所以缺作者信息时可以用主页主人补齐（防御性兼容；服务端修好后不会触发）。
    """
    data = dict(post or {})
    if user_id and not str(data.get("user_id") or "").strip():
        data["user_id"] = user_id
    if name and not str(data.get("user_name") or "").strip():
        data["user_name"] = name
    if avatar and not str(data.get("user_avatar") or "").strip():
        data["user_avatar"] = avatar
    return data


class PostCard(QFrame):
    """列表中的一条帖子（布局对照 Web 端 PostCard.vue）。"""

    open_post = pyqtSignal(str)
    open_user = pyqtSignal(str)

    def __init__(self, post: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PostCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pid = ""
        self._uid = ""

        outer = vbox(self, margins=(13, 12, 13, 12), spacing=6)

        self.title = QLabel(self)
        self.title.setObjectName("PostTitle")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        outer.addWidget(self.title)

        self.summary = QLabel(self)
        self.summary.setObjectName("PostSummary")
        self.summary.setWordWrap(True)
        self.summary.setMaximumHeight(46)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        outer.addWidget(self.summary)

        meta = hbox(spacing=8)
        self.tag = Chip("", "category")
        meta.addWidget(self.tag)

        self.avatar = Avatar(24)
        self.avatar.clicked.connect(self._on_avatar)
        meta.addWidget(self.avatar)

        self.user = UserLink()
        self.user.activated.connect(self._on_user_link)
        meta.addWidget(self.user)

        self.title_chip = Chip("", "title")
        self.title_chip.hide()
        meta.addWidget(self.title_chip)

        self.stats = Muted("")
        meta.addWidget(self.stats)
        self.time = Muted("")
        meta.addWidget(self.time)
        meta.addStretch(1)
        outer.addLayout(meta)

        if post:
            self.set_post(post)

    # ── 数据 ──
    def post_id(self) -> str:
        return self._pid

    def set_post(self, post: dict) -> None:
        data = post or {}
        self._pid = str(data.get("id") or "")
        self._uid = str(data.get("user_id") or "")

        self.title.setText(str(data.get("title") or "（无标题）"))
        summary = str(data.get("summary") or "").replace("\n", " ").strip()
        self.summary.setText(summary)
        self.summary.setVisible(bool(summary))

        self.tag.setText(constants.category_label(data.get("category")))
        self.avatar.set_url(str(data.get("user_avatar") or ""))
        self.user.set_user(self._uid, str(data.get("user_name") or "匿名用户"))

        title_text = str(data.get("user_title") or data.get("title") or "").strip()
        self.title_chip.setText(title_text)
        self.title_chip.setVisible(bool(title_text))

        stats = []
        stats.append("♥ %d" % int(data.get("likes") or 0))
        stats.append("👁 %d" % int(data.get("views") or 0))
        comments = data.get("comments") or data.get("comment_count")
        if comments is not None:
            stats.append("💬 %d" % int(comments or 0))
        self.stats.setText("   ".join(stats))
        self.time.setText(yearmode.fmt_time(data.get("created_at")))

    # ── 交互 ──
    def _on_avatar(self) -> None:
        if self._uid:
            self.open_user.emit(self._uid)

    def _on_user_link(self, user_id: str) -> None:
        if user_id:
            self.open_user.emit(user_id)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._pid:
            self.open_post.emit(self._pid)
        event.accept()
