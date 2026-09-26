# -*- coding: utf-8 -*-
"""主题化弹窗：确认 / 外链安全确认 / 举报 / Bug 反馈 / 关注列表。"""

from __future__ import annotations

from urllib.parse import urlparse

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QComboBox, QDialog, QLabel, QPlainTextEdit, QLineEdit,
                             QScrollArea, QVBoxLayout, QWidget)

from .. import api as api_mod
from .. import constants, logger, theme, util, yearmode
from .common import Card, Muted, TitleLabel, button, clear_layout, hbox, vbox
from .images import Avatar
from .toast import toast

_log = logger.get_logger("dialogs")

REPORT_REASONS = ("违规内容", "广告垃圾", "人身攻击", "侵权", "其他")


class BaseDialog(QDialog):
    """统一风格的模态对话框骨架。"""

    def __init__(self, parent: QWidget | None = None, *, title: str = "",
                 width: int = 440) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or constants.APP_NAME)
        self.setModal(True)
        self.setMinimumWidth(width)
        self.root = vbox(self, margins=(18, 16, 18, 16), spacing=12)

        header = hbox(spacing=8)
        self.title_label = TitleLabel(title)
        header.addWidget(self.title_label)
        header.addStretch(1)
        close_btn = button("✕", "ghost", self.reject, tooltip="关闭")
        header.addWidget(close_btn)
        self.root.addLayout(header)

        self.body = vbox(spacing=10)
        self.root.addLayout(self.body)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.hide()
        self.root.addWidget(self.error)

        self.actions = hbox(spacing=8)
        self.actions.addStretch(1)
        self.root.addLayout(self.actions)

    # ── 工具 ──
    def add_action(self, text: str, variant: str | None, slot) -> QWidget:
        widget = button(text, variant, slot)
        self.actions.addWidget(widget)
        return widget

    def show_error(self, text: str) -> None:
        self.error.setText(str(text or ""))
        self.error.setStyleSheet("color: %s;" % theme.palette()["danger"])
        self.error.setVisible(bool(text))

    def clear_error(self) -> None:
        self.error.setText("")
        self.error.hide()

    def field(self, label: str, widget: QWidget) -> QWidget:
        box = vbox(spacing=4)
        caption = Muted(label)
        box.addWidget(caption)
        box.addWidget(widget)
        self.body.addLayout(box)
        return widget


# ────────────────────────── 确认 ──────────────────────────


def confirm(parent: QWidget | None, title: str, text: str, *,
            ok_text: str = "确定", cancel_text: str = "取消",
            danger: bool = False) -> bool:
    dialog = BaseDialog(parent, title=title, width=380)
    message = QLabel(text)
    message.setWordWrap(True)
    dialog.body.addWidget(message)
    dialog.add_action(cancel_text, None, dialog.reject)
    dialog.add_action(ok_text, "danger" if danger else "primary", dialog.accept)
    return dialog.exec() == QDialog.DialogCode.Accepted


def info_box(parent: QWidget | None, title: str, text: str, *,
             ok_text: str = "知道了") -> None:
    """信息提示弹窗（只有确认按钮），与 :func:`confirm` 同一套主题风格。"""
    dialog = BaseDialog(parent, title=title, width=380)
    message = QLabel(text)
    message.setWordWrap(True)
    dialog.body.addWidget(message)
    dialog.add_action(ok_text, "primary", dialog.accept)
    dialog.exec()


# ────────────────────────── 外链安全确认 ──────────────────────────


class ExternalLinkDialog(BaseDialog):
    """外部链接安全确认（对照 Web 端 /GoTo 确认页）。"""

    def __init__(self, url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, title="即将离开妖精论坛", width=460)
        self._url = str(url or "")
        host = ""
        try:
            parsed = urlparse(self._url)
            host = parsed.netloc or parsed.path.split("/")[0]
        except Exception:
            host = ""
        warn = QLabel("你即将访问外部网站：\n\n"
                      "目标站点：%s\n\n"
                      "该链接不是妖精论坛官方内容，请注意保护个人隐私与账号安全。"
                      % (host or self._url))
        warn.setWordWrap(True)
        self.body.addWidget(warn)
        address = QPlainTextEdit(self._url)
        address.setReadOnly(True)
        address.setFixedHeight(64)
        self.field("完整地址", address)
        self.add_action("复制链接", None, self._copy)
        self.add_action("取消", None, self.reject)
        self.add_action("继续访问", "primary", self._open)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._url)
        toast("链接已复制")

    def _open(self) -> None:
        if not util.open_in_system(self._url):
            self.show_error("无法打开系统浏览器，请手动复制链接访问")
            return
        self.accept()


# ────────────────────────── 举报 ──────────────────────────


class ReportDialog(BaseDialog):
    """举报帖子 / 评论。"""

    def __init__(self, target_type: str = "post", target_id: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent, title="举报", width=440)
        self._target_type = target_type
        self._target_id = target_id
        self.reason = QComboBox()
        self.reason.addItem("请选择原因", "")
        for item in REPORT_REASONS:
            self.reason.addItem(item, item)
        self.field("举报原因", self.reason)
        self.detail = QPlainTextEdit()
        self.detail.setPlaceholderText("补充说明（最多 500 字，可选）")
        self.detail.setFixedHeight(96)
        self.field("补充说明", self.detail)
        self.add_action("取消", None, self.reject)
        self.submit = self.add_action("提交举报", "primary", self._submit)

    def values(self) -> tuple[str, str]:
        return str(self.reason.currentData() or ""), self.detail.toPlainText().strip()[:constants.COMMENT_MAX]

    def _submit(self) -> None:
        reason, detail = self.values()
        if not reason:
            self.show_error("请选择举报原因")
            return
        if not self._target_id:
            self.show_error("举报对象无效")
            return
        self.clear_error()
        self.submit.setEnabled(False)

        def _work():
            client = api_mod.api()
            if self._target_type == "comment":
                return client.report_comment(self._target_id, reason, detail)
            return client.report_post(self._target_id, reason, detail)

        def _done(result):
            self.submit.setEnabled(True)
            if result.ok:
                toast(result.message or "举报已提交，感谢反馈")
                self.accept()
            else:
                self.show_error(result.message)

        def _fail(message):
            self.submit.setEnabled(True)
            self.show_error(message)

        api_mod.run_async(_work, _done, _fail, label="举报")


# ────────────────────────── Bug 反馈 ──────────────────────────


class BugReportDialog(BaseDialog):
    """Bug 反馈（字段对照 Web 端 bugModal）。"""

    def __init__(self, parent: QWidget | None = None, *, page_url: str = "") -> None:
        super().__init__(parent, title="反馈 Bug", width=500)
        self._page_url = page_url or constants.BASE_URL
        self.title_input = QLineEdit()
        self.title_input.setMaxLength(200)
        self.title_input.setPlaceholderText("一句话描述问题")
        self.field("标题", self.title_input)

        self.detail_input = QPlainTextEdit()
        self.detail_input.setPlaceholderText("发生了什么？期望行为是什么？")
        self.detail_input.setFixedHeight(110)
        self.field("详细描述", self.detail_input)

        self.steps_input = QPlainTextEdit()
        self.steps_input.setPlaceholderText("1. … 2. …")
        self.steps_input.setFixedHeight(72)
        self.field("复现步骤（可选）", self.steps_input)

        self.contact_input = QLineEdit()
        self.contact_input.setMaxLength(constants.REPORT_REASON_MAX)
        self.contact_input.setPlaceholderText("邮箱 / QQ，便于回复")
        self.field("联系方式（可选）", self.contact_input)

        hint = Muted("提交后会带上当前客户端版本与数据目录，便于定位问题。")
        self.body.addWidget(hint)

        self.add_action("取消", None, self.reject)
        self.submit = self.add_action("提交反馈", "primary", self._submit)

    def values(self) -> dict:
        return {
            "title": self.title_input.text().strip(),
            "detail": self.detail_input.toPlainText().strip(),
            "steps": self.steps_input.toPlainText().strip(),
            "contact": self.contact_input.text().strip(),
            "page_url": self._page_url,
        }

    def _submit(self) -> None:
        values = self.values()
        if not values["title"]:
            self.show_error("请填写标题")
            return
        if not values["detail"]:
            self.show_error("请填写详细描述")
            return
        self.clear_error()
        self.submit.setEnabled(False)
        detail = values["detail"]
        detail += "\n\n—— 客户端信息 ——\n版本：%s\n数据目录：%s" % (
            constants.APP_VERSION, constants.DATA_DIR())

        def _work():
            return api_mod.api().report_bug(
                values["title"], detail, values["steps"],
                values["contact"], values["page_url"])

        def _done(result):
            self.submit.setEnabled(True)
            if result.ok:
                toast(result.message or "反馈已提交，感谢支持")
                self.accept()
            else:
                self.show_error(result.message)

        def _fail(message):
            self.submit.setEnabled(True)
            self.show_error(message)

        api_mod.run_async(_work, _done, _fail, label="反馈")


# ────────────────────────── 关注 / 粉丝列表 ──────────────────────────


class UserListDialog(BaseDialog):
    """关注 / 粉丝列表（支持直接关注）。"""

    open_user = pyqtSignal(str)

    def __init__(self, user_id: str, kind: str = "following",
                 parent: QWidget | None = None, *, title: str = "") -> None:
        super().__init__(parent, title=title or ("关注" if kind == "following" else "粉丝"),
                         width=460)
        self._user_id = user_id
        self._kind = kind
        self._rows: list[dict] = []
        self.loading = Muted("加载中…")
        self.body.addWidget(self.loading)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setMinimumHeight(300)
        self.container = QWidget()
        self.list_box = vbox(self.container, margins=(0, 0, 6, 0), spacing=6)
        self.list_box.addStretch(1)
        self.scroll.setWidget(self.container)
        self.body.addWidget(self.scroll)

        self.add_action("关闭", None, self.accept)
        self.reload()

    def reload(self) -> None:
        self.loading.setText("加载中…")
        self.loading.show()
        user_id = self._user_id
        kind = self._kind

        def _work():
            client = api_mod.api()
            if kind == "following":
                return client.following(user_id, 1, 100)
            return client.followers(user_id, 1, 100)

        def _done(result):
            if not result.ok:
                self.loading.setText(result.message)
                return
            rows = result.rows("users") or result.get("list") or []
            if not isinstance(rows, list):
                rows = []
            self._rows = [r for r in rows if isinstance(r, dict)]
            self._render()

        def _fail(message):
            self.loading.setText(message)

        api_mod.run_async(_work, _done, _fail, label="用户列表")

    def _render(self) -> None:
        clear_layout(self.list_box)
        if not self._rows:
            self.loading.setText("这里空空如也")
            self.loading.show()
            self.list_box.addStretch(1)
            return
        self.loading.hide()
        me = api_mod.api().user or {}
        me_id = str(me.get("id") or "")
        for row in self._rows:
            self.list_box.addWidget(self._row_widget(row, me_id))
        self.list_box.addStretch(1)

    def _row_widget(self, row: dict, me_id: str) -> QWidget:
        card = Card(padding=(10, 8, 10, 8), spacing=6)
        line = hbox(spacing=8)
        avatar = Avatar(32)
        avatar.set_url(str(row.get("avatar") or ""))
        uid = str(row.get("id") or "")
        avatar.clicked.connect(lambda: self._open(uid))
        line.addWidget(avatar)

        from .common import UserLink
        name = UserLink(uid, str(row.get("name") or "匿名用户"))
        name.activated.connect(self._open)
        line.addWidget(name)

        prefix = str(row.get("prefix") or "").strip()
        if prefix:
            from .common import Chip
            line.addWidget(Chip(prefix, "title"))
        line.addStretch(1)

        if uid and uid != me_id:
            following = bool(row.get("is_following"))
            btn = button("已关注" if following else "关注",
                         "ghost" if following else "primary",
                         lambda _=False, u=uid, b=None: None)
            btn.clicked.disconnect()
            btn.clicked.connect(lambda _ignored=False, u=uid, widget=btn: self._toggle(u, widget))
            line.addWidget(btn)
        card.body.addLayout(line)
        return card

    def _toggle(self, user_id: str, widget) -> None:
        widget.setEnabled(False)

        def _work():
            return api_mod.api().follow(user_id)

        def _done(result):
            widget.setEnabled(True)
            if result.ok:
                following = bool(result.get("following"))
                widget.setText("已关注" if following else "关注")
                from .common import set_variant
                set_variant(widget, "ghost" if following else "primary")
                toast("已关注" if following else "已取消关注")
            else:
                toast(result.message)

        api_mod.run_async(_work, _done, lambda m: (widget.setEnabled(True), toast(m)),
                          label="关注")

    def _open(self, user_id: str) -> None:
        if user_id:
            self.open_user.emit(user_id)
