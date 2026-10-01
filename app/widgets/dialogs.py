# -*- coding: utf-8 -*-
"""主题化弹窗：确认 / 外链安全确认 / 举报 / Bug 反馈 / 关注列表。"""

from __future__ import annotations

from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QLabel, QLineEdit,
                             QMessageBox, QPlainTextEdit, QRadioButton,
                             QScrollArea, QVBoxLayout, QWidget)

from .. import api as api_mod
from .. import constants, logger, theme, util, yearmode
from .common import (Card, Divider, Muted, TitleLabel, button, clear_layout, hbox,
                     vbox)
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


# ────────────────────────── 注销账号 ──────────────────────────


_DELETE_CONFIRM = constants.DELETE_ACCOUNT_CONFIRM_TEXT
_CODE_MAX = 6


class _CodeCooldown:
    """「获取验证码」按钮的 60 秒倒计时（随按钮一起销毁）。"""

    def __init__(self, button_widget, seconds: int = 60) -> None:
        self._button = button_widget
        self._seconds = int(seconds)
        self._left = 0
        self._timer = QTimer(button_widget)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def ready(self) -> bool:
        return self._left <= 0

    def start(self) -> None:
        self._left = self._seconds
        self._button.setEnabled(False)
        self._button.setText("%ds" % self._left)
        self._timer.start()

    def _tick(self) -> None:
        self._left -= 1
        if self._left <= 0:
            self._left = 0
            self._timer.stop()
            self._button.setText("获取验证码")
            self._button.setEnabled(True)
        else:
            self._button.setText("%ds" % self._left)


class DeleteAccountDialog(BaseDialog):
    """自助注销账号（密码或邮箱验证码二选一 + 输入「注销账号」确认）。\n    文本对照三端真源「八、你的权利 → 4. 注销账号」；成功后就地清空登录态、
    回到登录页。
    """

    def __init__(self, page, parent: QWidget | None = None) -> None:
        super().__init__(parent, title="注销账号", width=520)
        self._page = page
        self.deleted = False

        self.body.addWidget(Muted(
            "注销后你的账号将不可用。请选择注销方式并完成身份验证。"))

        self.mode_group = QButtonGroup(self)
        self.mode_purge = QRadioButton("彻底删除")
        self.mode_anon = QRadioButton("匿名化保留")
        self.mode_purge.setChecked(True)
        self.mode_group.addButton(self.mode_purge)
        self.mode_group.addButton(self.mode_anon)
        self.body.addWidget(self.mode_purge)
        self.body.addWidget(Muted(
            "删除账号及你发布的全部帖子、评论、点赞、收藏、关注、举报记录，"
            "该操作不可恢复。"))
        self.body.addWidget(self.mode_anon)
        self.body.addWidget(Muted(
            "删除邮箱、密码等身份信息，用户名统一显示为「已注销用户」，"
            "历史帖子与评论正文保留但无法再关联到你。"))

        self.body.addWidget(Divider())

        self.verify_group = QButtonGroup(self)
        self.verify_password = QRadioButton("使用账号密码验证")
        self.verify_code = QRadioButton("使用邮箱验证码验证")
        self.verify_password.setChecked(True)
        self.verify_group.addButton(self.verify_password)
        self.verify_group.addButton(self.verify_code)

        self.body.addWidget(self.verify_password)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMaxLength(constants.PASSWORD_MAX)
        self.password_input.setPlaceholderText("账号密码")
        self.field("密码", self.password_input)

        self.body.addWidget(self.verify_code)
        code_wrap = QWidget()
        code_row = hbox(code_wrap, spacing=8)
        self.code_input = QLineEdit()
        self.code_input.setMaxLength(_CODE_MAX)
        self.code_input.setPlaceholderText("6 位数字验证码")
        code_row.addWidget(self.code_input, 1)
        self.send_btn = button("获取验证码", None, self._send_code)
        code_row.addWidget(self.send_btn)
        self.field("邮箱验证码", code_wrap)
        self._cool = _CodeCooldown(self.send_btn)

        self.verify_password.toggled.connect(self._apply_verify)
        self.verify_code.toggled.connect(self._apply_verify)

        self.confirm_input = QLineEdit()
        self.confirm_input.setMaxLength(len(_DELETE_CONFIRM) + 2)
        self.confirm_input.setPlaceholderText(
            "请输入「%s」以确认" % _DELETE_CONFIRM)
        self.field("确认文字", self.confirm_input)

        self._apply_verify()

        self.add_action("取消", None, self.reject)
        self.submit_btn = self.add_action("确认注销", "danger", self._submit)

    def _apply_verify(self) -> None:
        use_password = self.verify_password.isChecked()
        self.password_input.setEnabled(use_password)
        self.code_input.setEnabled(not use_password)
        self.send_btn.setEnabled(not use_password)

    def _send_code(self) -> None:
        if not self._cool.ready():
            return
        self.clear_error()
        self.send_btn.setEnabled(False)
        self._page.run(lambda: self._page.api.send_delete_account_code(),
                       self._on_code_sent, self._on_code_failed, label="验证码")

    def _on_code_sent(self, result) -> None:
        if not result.ok:
            self.send_btn.setEnabled(True)
            self.show_error(result.message)
            return
        toast(result.message or "验证码已发送至绑定邮箱")
        self._cool.start()

    def _on_code_failed(self, message: str) -> None:
        self.send_btn.setEnabled(True)
        self.show_error(message)

    def _mode(self) -> str:
        return "purge" if self.mode_purge.isChecked() else "anonymize"

    def _submit(self) -> None:
        self.clear_error()
        password = ""
        code = ""
        if self.verify_password.isChecked():
            password = self.password_input.text()
        else:
            code = self.code_input.text().strip()
        if not password and not code:
            self.show_error("请输入账号密码或邮箱验证码")
            return
        if self.confirm_input.text().strip() != _DELETE_CONFIRM:
            self.show_error("请输入「%s」以确认操作" % _DELETE_CONFIRM)
            return
        answer = QMessageBox.warning(
            self, "再次确认",
            "确定要注销账号吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        mode = self._mode()
        self.submit_btn.setEnabled(False)
        self._page.run(
            lambda: self._page.api.delete_account(
                mode, password=password, code=code),
            self._on_submitted, self._on_submit_failed, label="注销账号")

    def _on_submitted(self, result) -> None:
        self.submit_btn.setEnabled(True)
        if not result.ok:
            self.show_error(result.message)
            return
        self.deleted = True
        toast(result.message or "账号已注销")
        page = self._page
        if page is not None:
            # api.delete_account 成功后已 clear_login()，这里刷新外壳并回登录页
            if getattr(page, "shell", None) is not None:
                try:
                    page.shell.refresh_user()
                except Exception:
                    pass
            page.go("auth", mode="login")
        self.accept()

    def _on_submit_failed(self, message: str) -> None:
        self.submit_btn.setEnabled(True)
        self.show_error(message)
