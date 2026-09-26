# -*- coding: utf-8 -*-
"""登录 / 注册 / 找回密码页（对照 Web 端 AuthView.vue）。

三种模式共用一张居中卡片：

* ``login``    账号（用户名或邮箱）+ 密码
* ``register`` 昵称 + 邮箱 + 验证码 + 密码
* ``reset``    两步式找回密码：邮箱 → 验证码 + 新密码（不使用邮件链接）

邮件服务不可用时后端会返回 503 与「邮件服务暂不可用…」，原话直接展示给用户。
"""

from __future__ import annotations

import re

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLabel, QLineEdit, QWidget

from .. import constants, theme
from ..widgets import Card, Muted, TitleLabel, button, hbox, set_active, vbox
from .base import Page

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CODE_RE = re.compile(r"^\d{6}$")
_CODE_COOLDOWN = 60
_CARD_MAX_WIDTH = 420


def _strong_password(text: str) -> bool:
    """密码需至少 8 位且同时包含字母与数字。"""
    if len(text or "") < constants.PASSWORD_MIN:
        return False
    return bool(re.search(r"[A-Za-z]", text)) and bool(re.search(r"\d", text))


class AuthPage(Page):
    """登录 / 注册 / 找回密码（路由 ``auth``，``on_show(mode="login")``）。"""

    ROUTE = "auth"
    TITLE = "登录"
    SHOW_WORLD_PANEL = False
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell=shell, parent=parent)
        self._mode = "login"
        self._reset_step = 1
        self._cooldown = 0
        self._busy = False
        self._build()
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.setInterval(1000)
        self._cooldown_timer.timeout.connect(self._tick_cooldown)
        self._refresh()

    # ────────────────────── 构建 ──────────────────────
    def _build(self) -> None:
        root = vbox(self, margins=(0, 0, 0, 0), spacing=0)
        root.addStretch(1)
        center = hbox(spacing=0)
        center.addStretch(1)
        card = Card(padding=(26, 24, 26, 24), spacing=12)
        card.setMinimumWidth(340)
        card.setMaximumWidth(_CARD_MAX_WIDTH)
        center.addWidget(card)
        center.addStretch(1)
        root.addLayout(center)
        root.addStretch(1)

        body = card.body
        body.addWidget(TitleLabel(constants.APP_NAME))
        body.addWidget(Muted("登录后可发帖、收藏与关注"))

        # 模式切换 chip
        self._tabs = hbox(spacing=6)
        self._tab_buttons: dict[str, QWidget] = {}
        for key, label in (("login", "登录"), ("register", "注册"), ("reset", "找回密码")):
            btn = button(label, "chip", lambda _=False, k=key: self.switch_mode(k))
            self._tab_buttons[key] = btn
            self._tabs.addWidget(btn)
        self._tabs.addStretch(1)
        body.addLayout(self._tabs)

        # 昵称（注册）
        self.name_input = QLineEdit()
        self.name_input.setMaxLength(constants.PROFILE_NAME_MAX)
        self.name_input.setPlaceholderText("2-20 个字符")
        self._name_field, _ = self._field("昵称", self.name_input)
        body.addWidget(self._name_field)

        # 账号 / 邮箱
        self.email_input = QLineEdit()
        self.email_input.setMaxLength(constants.EMAIL_MAX)
        self.email_input.setPlaceholderText("用户名或邮箱")
        self._email_field, self._email_label = self._field("账号（用户名或邮箱）", self.email_input)
        body.addWidget(self._email_field)

        # 找回密码第一步：邮箱 + 发送验证码
        self._reset_send_row = QWidget()
        reset_row = hbox(self._reset_send_row, margins=(0, 0, 0, 0), spacing=6)
        self._reset_send_btn = button("发送验证码", None, lambda: self._send_code("reset"))
        reset_row.addWidget(self._reset_send_btn)
        reset_row.addStretch(1)
        body.addWidget(self._reset_send_row)

        # 验证码（注册 / 找回密码第二步）
        self.code_input = QLineEdit()
        self.code_input.setMaxLength(6)
        self.code_input.setPlaceholderText("6 位数字验证码")
        code_row = QWidget()
        code_layout = hbox(code_row, margins=(0, 0, 0, 0), spacing=6)
        code_layout.addWidget(self.code_input, 1)
        self._send_btn = button("发送验证码", None, lambda: self._send_code("register"))
        code_layout.addWidget(self._send_btn)
        self._code_field, _ = self._field("邮箱验证码", code_row)
        body.addWidget(self._code_field)

        # 密码
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMaxLength(constants.PASSWORD_MAX)
        self.password_input.setPlaceholderText("至少 8 位，含字母和数字")
        self._password_field, self._password_label = self._field("密码", self.password_input)
        body.addWidget(self._password_field)

        # 卡内提示文字（错误红 / 成功主题色）
        self._message = QLabel("")
        self._message.setWordWrap(True)
        self._message.hide()
        body.addWidget(self._message)

        self._submit_btn = button("登录", "primary", self._submit)
        body.addWidget(self._submit_btn)
        self._back_btn = button("返回上一步", "ghost", self._to_reset_step1)
        self._back_btn.hide()
        body.addWidget(self._back_btn)

        for widget in (self.name_input, self.email_input, self.code_input, self.password_input):
            widget.returnPressed.connect(self._submit)

    def _field(self, label: str, widget: QWidget) -> tuple[QWidget, QLabel]:
        """带说明文字的输入组（返回整组控件与说明标签）。"""
        wrapper = QWidget()
        box = vbox(wrapper, margins=(0, 0, 0, 0), spacing=4)
        caption = Muted(label)
        box.addWidget(caption)
        box.addWidget(widget)
        return wrapper, caption

    # ────────────────────── 模式 / 可见性 ──────────────────────
    def switch_mode(self, mode: str) -> None:
        self._mode = mode if mode in ("login", "register", "reset") else "login"
        self._reset_step = 1
        self.code_input.clear()
        self.password_input.clear()
        self._set_message("")
        self._refresh()

    def _refresh(self) -> None:
        login = self._mode == "login"
        register = self._mode == "register"
        step2 = self._mode == "reset" and self._reset_step == 2

        self._name_field.setVisible(register)
        self._email_field.setVisible(not step2)
        self._email_label.setText("账号（用户名或邮箱）" if login else "邮箱")
        self.email_input.setPlaceholderText("用户名或邮箱" if login else "邮箱")
        self._reset_send_row.setVisible(self._mode == "reset" and self._reset_step == 1)
        self._code_field.setVisible(register or step2)
        self._password_field.setVisible(not (self._mode == "reset" and self._reset_step == 1))
        self._password_label.setText("新密码" if step2 else "密码")
        self._back_btn.setVisible(step2)

        if login:
            text = "登录"
        elif register:
            text = "注册"
        elif step2:
            text = "重置密码"
        else:
            text = "下一步"
        self._submit_btn.setText(text)
        self._submit_btn.setEnabled(not self._busy)
        for key, btn in self._tab_buttons.items():
            set_active(btn, key == self._mode)

    def _set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._submit_btn.setEnabled(not self._busy)
        if self._busy:
            self._submit_btn.setText("提交中…")
        else:
            self._refresh()
        self._paint_send_buttons()

    def _set_message(self, text: str, *, ok: bool = False) -> None:
        text = str(text or "").strip()
        self._message.setText(text)
        color = theme.palette()["primary"] if ok else theme.palette()["danger"]
        self._message.setStyleSheet("color: %s;" % color)
        self._message.setVisible(bool(text))

    def _fail(self, message: str) -> None:
        self._set_busy(False)
        self._set_message(message)

    # ────────────────────── 验证码倒计时 ──────────────────────
    def _send_code(self, kind: str) -> None:
        if self._cooldown > 0 or self._busy:
            return
        email = self.email_input.text().strip()
        if not email:
            self._set_message("请先输入邮箱")
            return
        if not _EMAIL_RE.match(email):
            self._set_message("邮箱格式不正确")
            return
        self._set_message("")
        self._set_busy(True)
        sender = self.api.send_register_code if kind == "register" else self.api.send_reset_code

        def _done(result):
            self._set_busy(False)
            if result.ok:
                self._set_message(result.message or "验证码已发送，请查收邮件", ok=True)
                self._start_cooldown()
            else:
                self._set_message(result.message)

        self.run(lambda: sender(email), _done, self._fail, "发送验证码")

    def _start_cooldown(self) -> None:
        self._cooldown = _CODE_COOLDOWN
        self._paint_send_buttons()
        self._cooldown_timer.start()

    def _tick_cooldown(self) -> None:
        self._cooldown = max(self._cooldown - 1, 0)
        if self._cooldown == 0:
            self._cooldown_timer.stop()
        self._paint_send_buttons()

    def _paint_send_buttons(self) -> None:
        cooling = self._cooldown > 0
        text = "%ds" % self._cooldown if cooling else "发送验证码"
        enabled = not cooling and not self._busy
        for btn in (self._send_btn, self._reset_send_btn):
            btn.setText(text)
            btn.setEnabled(enabled)

    # ────────────────────── 提交 ──────────────────────
    def _submit(self) -> None:
        if self._busy:
            return
        if self._mode == "login":
            self._login()
        elif self._mode == "register":
            self._register()
        elif self._reset_step == 1:
            self._to_reset_step2()
        else:
            self._reset_password()

    def _login(self) -> None:
        account = self.email_input.text().strip()
        password = self.password_input.text()
        if not account:
            self._set_message("请输入用户名或邮箱")
            return
        if not password:
            self._set_message("请输入密码")
            return
        self._set_message("")
        fields = {"email": account} if "@" in account else {"name": account}
        self._set_busy(True)

        def _done(result):
            self._set_busy(False)
            if not result.ok:
                self._set_message(result.message)
                return
            if self.shell is not None:
                self.shell.refresh_user()
            self.go("home")

        self.run(lambda: self.api.login(password=password, **fields), _done, self._fail, "登录")

    def _register(self) -> None:
        name = self.name_input.text().strip()
        email = self.email_input.text().strip()
        code = self.code_input.text().strip()
        password = self.password_input.text()
        if not 2 <= len(name) <= constants.PROFILE_NAME_MAX:
            self._set_message("昵称需为 2-%d 个字符" % constants.PROFILE_NAME_MAX)
            return
        if not _EMAIL_RE.match(email):
            self._set_message("请填写正确的邮箱")
            return
        if not _CODE_RE.match(code):
            self._set_message("请填写 6 位数字验证码")
            return
        if not _strong_password(password):
            self._set_message("密码至少 %d 位，且需同时包含字母和数字" % constants.PASSWORD_MIN)
            return
        self._set_message("")
        self._set_busy(True)

        def _done(result):
            self._set_busy(False)
            if not result.ok:
                self._set_message(result.message)
                return
            if self.shell is not None:
                self.shell.refresh_user()
            self.go("home")

        self.run(lambda: self.api.register(name, email, password, code), _done, self._fail, "注册")

    def _to_reset_step2(self) -> None:
        email = self.email_input.text().strip()
        if not _EMAIL_RE.match(email):
            self._set_message("请填写正确的邮箱")
            return
        self._reset_step = 2
        self.code_input.clear()
        self.password_input.clear()
        self._set_message("")
        self._refresh()

    def _to_reset_step1(self) -> None:
        self._reset_step = 1
        self.code_input.clear()
        self._set_message("")
        self._refresh()

    def _reset_password(self) -> None:
        email = self.email_input.text().strip()
        code = self.code_input.text().strip()
        password = self.password_input.text()
        if not _CODE_RE.match(code):
            self._set_message("请填写 6 位数字验证码")
            return
        if not _strong_password(password):
            self._set_message("密码至少 %d 位，且需同时包含字母和数字" % constants.PASSWORD_MIN)
            return
        self._set_message("")
        self._set_busy(True)

        def _done(result):
            self._set_busy(False)
            if not result.ok:
                self._set_message(result.message)
                return
            self.switch_mode("login")
            self._set_message(result.message or "密码已重置，请使用新密码登录", ok=True)

        self.run(
            lambda: self.api.reset_password_by_code(email, code, password),
            _done,
            self._fail,
            "重置密码",
        )

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, mode: str = "login", **kwargs) -> None:
        """进入页面时按 ``mode`` 切换：login / register / reset。"""
        super().on_show(**kwargs)
        self.switch_mode(mode)
