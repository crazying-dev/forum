# -*- coding: utf-8 -*-
"""「我的」页面（对照 Web 端 ``UserView.vue`` 的本人视图）。

* 未登录：只显示登录 / 注册入口
* 已登录：资料卡（头像 / 昵称 / 称号前缀 / 头衔 / 性别 / 生日 / 简介 / 注册时间）
  + 统计行（帖子 / 获赞 / 浏览 + 可点击的「关注」「粉丝」）
  + 账号操作（编辑资料 / 修改密码 / 更换绑定邮箱）
* 四个页签：我的帖子 / 我的收藏 / 我的评论 / 我的回复，均支持「加载更多」

``KEEP_ALIVE`` 保持默认（True）：页面常驻，登录态或资料变化时由
:meth:`ProfilePage.refresh_auth` 就地重绘，避免反复重建。
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDate, Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QFileDialog,
                             QLabel, QLineEdit, QPlainTextEdit, QTabWidget,
                             QWidget)

from .. import constants, yearmode
from ..widgets import (BaseDialog, Card, Chip, EmptyHint, Muted, PostCard,
                       ScrollPage, UserLink, UserListDialog, button, hbox,
                       toast, vbox)
from ..widgets.images import Avatar
from .base import Page

_GENDER_LABELS = {0: "未设置", 1: "男", 2: "女"}
_INTRO_MAX = 200          # 对照 Web 端简介 maxlength
_CODE_MAX = 6             # 邮箱验证码位数
_EMAIL_MAX = 120          # 对照 Web 端新邮箱 maxlength
_COOLDOWN_SECONDS = 60    # 验证码重发冷却
_AVATAR_TOO_LARGE = "图片过大，请选择不超过 5 MB 的图片"


def _field(layout, label: str, widget: QWidget) -> QWidget:
    """在任意布局里插入「说明文字 + 控件」（对话框分步面板用）。"""
    box = vbox(spacing=4)
    box.addWidget(Muted(label))
    box.addWidget(widget)
    layout.addLayout(box)
    return widget


class _ListPane(QWidget):
    """滚动列表 + 空态 / 加载态 / 「加载更多」（帖子与回复共用）。"""

    def __init__(self, page, fetch, *, rows_key: str, build_item,
                 empty_text: str = "暂无内容", page_size: int = 0,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = page
        self._fetch = fetch
        self._rows_key = rows_key
        self._build_item = build_item
        self._page_size = int(page_size or constants.PAGE_SIZE)
        self._page_no = 0
        self._rows: list[dict] = []
        self._busy = False
        self._has_more = True
        self.loaded = False

        root = vbox(self, margins=(6, 8, 6, 8), spacing=6)
        self.scroll = ScrollPage(self, spacing=8)
        self.scroll.load_more.connect(self.load_more)
        root.addWidget(self.scroll, 1)

        self.empty = EmptyHint(empty_text)
        self.empty.hide()
        root.addWidget(self.empty)

        self.more_btn = button("加载更多", None, self.load_more)
        self.more_btn.hide()
        more_row = hbox()
        more_row.addStretch(1)
        more_row.addWidget(self.more_btn)
        more_row.addStretch(1)
        root.addLayout(more_row)

    # ── 状态 ──
    def row_count(self) -> int:
        return len(self._rows)

    def reset(self) -> None:
        self._page_no = 0
        self._rows = []
        self._busy = False
        self._has_more = True
        self.loaded = False
        self.scroll.clear()
        self.scroll.set_load_more_enabled(False)
        self.scroll.set_busy(False)
        self.more_btn.hide()
        self.empty.hide()

    def show_message(self, text: str) -> None:
        """不发请求，直接显示一句提示。"""
        self.reset()
        self.loaded = True
        self.empty.setText(text)
        self.empty.show()

    # ── 数据 ──
    def reload(self) -> None:
        self.reset()
        self.load_more()

    def load_more(self) -> None:
        if self._busy or not self._has_more:
            return
        self._busy = True
        self._page_no += 1
        self.more_btn.setEnabled(False)
        self.more_btn.setText("加载中…")
        self.empty.hide()
        page_no = self._page_no
        self._page.run(lambda: self._fetch(page_no), self._on_loaded,
                       self._on_failed, "列表")

    def _on_loaded(self, result) -> None:
        self._busy = False
        self.loaded = True
        self.more_btn.setEnabled(True)
        self.more_btn.setText("加载更多")
        self.scroll.set_busy(False)
        if not result.ok:
            self._page.toast(result.message)
            self._has_more = False
            self.more_btn.hide()
            self.scroll.set_load_more_enabled(False)
            if not self._rows:
                self.empty.setText(result.message or "加载失败")
                self.empty.show()
            return
        rows = [row for row in result.rows(self._rows_key) if isinstance(row, dict)]
        self._rows.extend(rows)
        self._render()
        self._has_more = len(rows) >= self._page_size
        self.more_btn.setVisible(self._has_more)
        self.scroll.set_load_more_enabled(self._has_more)

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.more_btn.setEnabled(True)
        self.more_btn.setText("加载更多")
        self._page.toast(message)
        if not self._rows:
            self.empty.setText(message or "加载失败")
            self.empty.show()

    def _render(self) -> None:
        self.scroll.clear()
        for row in self._rows:
            widget = self._build_item(row)
            if widget is not None:
                self.scroll.add(widget)
        self.empty.setVisible(not self._rows)


class ProfilePage(Page):
    """「我的」：资料卡 + 账号操作 + 帖子 / 收藏 / 评论 / 回复。"""

    ROUTE = "me"
    TITLE = "我的"

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._user: dict = {}

        root = vbox(self, margins=(14, 12, 14, 10), spacing=10)
        header, header_layout = self.make_header("我的", "")
        header.actions.addWidget(button("刷新", "ghost", self.reload))
        self.hint = Muted("")
        header_layout.addWidget(self.hint)
        root.addWidget(header)

        self.guest_card = self._build_guest_card()
        root.addWidget(self.guest_card)

        self.main_box = QWidget(self)
        main = vbox(self.main_box, margins=(0, 0, 0, 0), spacing=10)
        main.addWidget(self._build_profile_card())
        main.addLayout(self._build_tools())
        self.tabs = self._build_tabs()
        main.addWidget(self.tabs, 1)
        root.addWidget(self.main_box, 1)

        self._show_view(False)

    # ────────────────────── 构建 ──────────────────────
    def _build_guest_card(self) -> Card:
        card = Card(padding=(20, 22, 20, 22), spacing=10)
        title = QLabel("登录后查看你的个人主页")
        title.setWordWrap(True)
        card.body.addWidget(title)
        card.body.addWidget(Muted("登录后可管理资料、查看收藏与评论，并发布新帖。"))
        row = hbox(spacing=8)
        row.addWidget(button("登录", "primary",
                             lambda: self.go("auth", mode="login")))
        row.addWidget(button("注册", None,
                             lambda: self.go("auth", mode="register")))
        row.addStretch(1)
        card.body.addLayout(row)
        return card

    def _build_profile_card(self) -> Card:
        card = Card(padding=(16, 14, 16, 14), spacing=8)
        row = hbox(spacing=14)
        self.avatar = Avatar(72)
        row.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)

        info = vbox(spacing=6)
        name_row = hbox(spacing=6)
        self.name_link = UserLink(bold=True)
        self.name_link.activated.connect(self.open_user)
        name_row.addWidget(self.name_link)
        self.prefix_chip = Chip("", "category")
        self.prefix_chip.hide()
        name_row.addWidget(self.prefix_chip)
        self.title_chip = Chip("", "title")
        self.title_chip.hide()
        name_row.addWidget(self.title_chip)
        name_row.addStretch(1)
        info.addLayout(name_row)

        self.meta = Muted("")
        info.addWidget(self.meta)

        stats = hbox(spacing=12)
        self.stat_posts = Muted("帖子 0")
        stats.addWidget(self.stat_posts)
        self.stat_likes = Muted("获赞 0")
        stats.addWidget(self.stat_likes)
        self.stat_views = Muted("浏览 0")
        stats.addWidget(self.stat_views)
        self.following_btn = button("关注 0", "ghost",
                                    lambda: self._open_user_list("following"),
                                    tooltip="查看关注列表")
        stats.addWidget(self.following_btn)
        self.followers_btn = button("粉丝 0", "ghost",
                                    lambda: self._open_user_list("followers"),
                                    tooltip="查看粉丝列表")
        stats.addWidget(self.followers_btn)
        stats.addStretch(1)
        info.addLayout(stats)

        self.intro = QLabel("")
        self.intro.setWordWrap(True)
        self.intro.hide()
        info.addWidget(self.intro)

        self.reg_meta = Muted("")
        info.addWidget(self.reg_meta)
        row.addLayout(info, 1)
        card.body.addLayout(row)
        return card

    def _build_tools(self):
        row = hbox(spacing=8)
        self.edit_btn = button("编辑资料", "primary", self._open_edit)
        row.addWidget(self.edit_btn)
        row.addWidget(button("修改密码", None, self._open_password))
        row.addWidget(button("更换邮箱", None, self._open_email))
        row.addStretch(1)
        return row

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        self.posts_pane = _ListPane(self, self._fetch_posts, rows_key="posts",
                                    build_item=self._build_post_widget,
                                    empty_text="暂无帖子")
        tabs.addTab(self.posts_pane, "我的帖子")
        self.favorites_pane = _ListPane(self, self._fetch_favorites,
                                        rows_key="posts",
                                        build_item=self._build_post_widget,
                                        empty_text="暂无收藏")
        tabs.addTab(self.favorites_pane, "我的收藏")
        self.comments_pane = _ListPane(self, self._fetch_comments,
                                       rows_key="comments",
                                       build_item=self._build_comment_widget,
                                       empty_text="暂无评论")
        tabs.addTab(self.comments_pane, "我的评论")
        self.replies_pane = _ListPane(self, self._fetch_replies,
                                      rows_key="replies",
                                      build_item=self._build_reply_widget,
                                      empty_text="暂无回复")
        tabs.addTab(self.replies_pane, "我的回复")
        tabs.currentChanged.connect(self._on_tab_changed)
        return tabs

    def _build_post_widget(self, post: dict) -> QWidget:
        card = PostCard(post)
        card.open_post.connect(self.open_post)
        card.open_user.connect(self.open_user)
        return card

    def _build_comment_widget(self, comment: dict) -> QWidget:
        card = Card(padding=(12, 10, 12, 10), spacing=6)
        content = QLabel(str(comment.get("content") or ""))
        content.setWordWrap(True)
        card.body.addWidget(content)

        post_id = str(comment.get("post_id") or "")
        title = str(comment.get("post_title") or "") or ("帖子 %s" % post_id)
        likes = int(comment.get("likes") or 0)
        meta = hbox(spacing=6)
        meta.addWidget(Muted("评论于《%s》" % title))
        meta.addWidget(Muted("赞 %d" % likes))
        meta.addWidget(Muted(yearmode.fmt_time(comment.get("created_at"))))
        meta.addStretch(1)
        meta.addWidget(button("查看原帖", "ghost",
                              lambda: self.open_post(post_id)))
        meta.addWidget(button("删除", "ghost",
                              lambda: self._delete_comment(comment)))
        card.body.addLayout(meta)
        return card

    def _build_reply_widget(self, row: dict) -> QWidget:
        card = Card(padding=(12, 10, 12, 10), spacing=6)
        head = hbox(spacing=6)
        avatar = Avatar(28)
        avatar.set_url(str(row.get("replier_avatar") or ""))
        replier_id = str(row.get("replier_id") or "")
        avatar.clicked.connect(lambda: self.open_user(replier_id))
        head.addWidget(avatar)
        replier = UserLink(replier_id, str(row.get("replier_name") or "匿名用户"))
        replier.activated.connect(self.open_user)
        head.addWidget(replier)
        head.addWidget(Muted("回复了你的评论"))
        head.addWidget(Muted(yearmode.fmt_time(row.get("reply_created_at"))))
        head.addStretch(1)
        card.body.addLayout(head)

        reply = QLabel(str(row.get("reply_content") or ""))
        reply.setWordWrap(True)
        card.body.addWidget(reply)

        my_comment = str(row.get("comment_content") or "")
        if my_comment:
            card.body.addWidget(Muted("你的评论：%s" % my_comment))

        post_id = str(row.get("post_id") or "")
        title = str(row.get("post_title") or "") or ("帖子 %s" % post_id)
        meta = hbox(spacing=6)
        meta.addWidget(Muted("来自《%s》" % title))
        meta.addStretch(1)
        meta.addWidget(button("查看原帖", "ghost",
                              lambda: self.open_post(post_id)))
        card.body.addLayout(meta)
        return card

    # ────────────────────── 数据 ──
    def _me_id(self) -> str:
        return str((self.me or {}).get("id") or "")

    def _fetch_posts(self, page_no: int):
        return self.api.user_posts(self._me_id(), page_no, constants.PAGE_SIZE)

    def _fetch_favorites(self, page_no: int):
        return self.api.user_favorites(self._me_id(), page_no, constants.PAGE_SIZE)

    def _fetch_comments(self, page_no: int):
        return self.api.user_comments(self._me_id(), page_no, constants.PAGE_SIZE)

    def _fetch_replies(self, page_no: int):
        return self.api.my_replies(page_no, constants.PAGE_SIZE)

    def _panes(self) -> tuple:
        return (self.posts_pane, self.favorites_pane,
                self.comments_pane, self.replies_pane)

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, **kwargs) -> None:
        super().on_show(**kwargs)
        self.reload()

    def reload(self) -> None:
        if not self.me:
            self._render_guest()
            return
        self.hint.setText("加载中…")
        self.run(lambda: self.api.me(), self._on_me, self._on_failed,
                 label="我的资料")

    def refresh_auth(self) -> None:
        """登录态变化后就地重绘（Shell.refresh_user 会回调，不再发请求）。"""
        if self.me:
            self.hint.setText("")
            self._render_profile(self.me)
            self._show_view(True)
            self._load_current_tab()
        else:
            self._render_guest()

    def title_text(self) -> str:
        name = str((self.me or {}).get("name") or "")
        return "%s · %s" % (self.TITLE, name) if name else self.TITLE

    def _on_failed(self, message: str) -> None:
        self.hint.setText(message or "加载失败")
        self.toast(message)

    def _on_me(self, result) -> None:
        if not result.ok:
            self.hint.setText(result.message or "资料加载失败")
            self.toast(result.message)
            return
        user = result.get("user") or {}
        if not user:
            self.hint.setText("登录状态已失效，请重新登录")
            self._render_guest()
            return
        self.hint.setText("")
        self._render_profile(user)
        self._show_view(True)
        self._load_current_tab()

    # ────────────────────── 渲染 ──────────────────────
    def _show_view(self, logged_in: bool) -> None:
        self.guest_card.setVisible(not logged_in)
        self.main_box.setVisible(logged_in)

    def _render_guest(self) -> None:
        self._user = {}
        self.hint.setText("")
        self._show_view(False)
        for pane in self._panes():
            pane.reset()
        self.tabs.setCurrentIndex(0)

    def _render_profile(self, user: dict) -> None:
        self._user = dict(user or {})
        data = self._user
        uid = str(data.get("id") or "")
        self.avatar.set_url(str(data.get("avatar") or ""))
        self.name_link.set_user(uid, str(data.get("name") or "匿名用户"))

        prefix = str(data.get("prefix") or "").strip()
        self.prefix_chip.setText(prefix)
        self.prefix_chip.setVisible(bool(prefix))
        title = str(data.get("title") or "").strip()
        self.title_chip.setText(title)
        self.title_chip.setVisible(bool(title))

        self.meta.setText("   ".join(self._meta_parts(data)))

        intro = str(data.get("intro") or "").strip()
        self.intro.setText(intro)
        self.intro.setVisible(bool(intro))

        stats = data.get("stats") or {}
        self.stat_posts.setText("帖子 %d" % int(stats.get("post_count") or 0))
        self.stat_likes.setText("获赞 %d" % int(stats.get("total_likes") or 0))
        self.stat_views.setText("浏览 %d" % int(stats.get("total_views") or 0))
        self.following_btn.setText("关注 %d" % int(stats.get("following_count") or 0))
        self.followers_btn.setText("粉丝 %d" % int(stats.get("follower_count") or 0))

        created = yearmode.fmt_time(data.get("created_at"))
        self.reg_meta.setText("注册于 %s" % created if created else "")

    def _meta_parts(self, user: dict) -> list:
        parts = []
        try:
            gender = int(user.get("gender") or 0)
        except (TypeError, ValueError):
            gender = 0
        if gender in (1, 2):
            parts.append("性别：%s" % _GENDER_LABELS[gender])
        birthday = yearmode.fmt_birthday(user.get("age"))
        if birthday:
            parts.append("生日：%s" % birthday)
        age = yearmode.short_age(user.get("age"))
        if age:
            parts.append("%s 岁" % age)
        return parts

    # ────────────────────── 交互 ──────────────────────
    def _delete_comment(self, comment: dict) -> None:
        comment_id = str(comment.get("id") or "")
        if not comment_id:
            return
        if not self.confirm("删除评论", "确定删除这条评论吗？", ok_text="删除",
                            danger=True):
            return

        def _done(result):
            if not result.ok:
                self.toast(result.message)
                return
            self.toast(result.message or "评论已删除")
            self.comments_pane.reload()

        self.run(lambda: self.api.delete_comment(comment_id), _done, None,
                 label="删除评论")

    def _open_user_list(self, kind: str) -> None:
        uid = self._me_id()
        if not uid:
            return
        title = "我的关注" if kind == "following" else "我的粉丝"
        dialog = UserListDialog(uid, kind, self.window(), title=title)
        dialog.open_user.connect(self.open_user)
        dialog.exec()

    def _open_edit(self) -> None:
        if not self.need_login("请先登录"):
            return
        dialog = EditProfileDialog(self, self.window())
        dialog.exec()
        if dialog.saved:
            self.reload()

    def _open_password(self) -> None:
        if not self.need_login("请先登录"):
            return
        dialog = ChangePasswordDialog(self, self.window())
        dialog.exec()
        if dialog.changed:
            # 后端改密后已清掉登录态，回登录页重新登录
            self.toast("密码修改成功，请重新登录")
            if self.shell is not None:
                self.shell.refresh_user()
            self.go("auth", mode="login")

    def _open_email(self) -> None:
        if not self.need_login("请先登录"):
            return
        dialog = ChangeEmailDialog(self, self.window())
        dialog.exec()
        if dialog.changed:
            self.reload()

    # ────────────────────── 页签 ──────────────────────
    def _on_tab_changed(self, index: int) -> None:
        pane = self.tabs.widget(index)
        if not isinstance(pane, _ListPane) or pane.loaded or not self.me:
            return
        pane.reload()

    def _load_current_tab(self) -> None:
        self._on_tab_changed(self.tabs.currentIndex())


def _has_letter(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def _has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


class _Cooldown:
    """验证码按钮的 60 秒倒计时（随按钮一起销毁）。"""

    def __init__(self, button_widget, seconds: int = _COOLDOWN_SECONDS) -> None:
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


class EditProfileDialog(BaseDialog):
    """编辑资料（对照 Web 端「编辑资料」面板）。

    所有阻塞调用都走页面传入的 :meth:`Page.run`，回调在主线程。
    """

    def __init__(self, page, parent: QWidget | None = None) -> None:
        super().__init__(parent, title="编辑资料", width=480)
        self._page = page
        user = dict(page.me or {})
        self.saved = False
        self._pending_avatar = ""
        self._local_path = ""
        self._birth_dirty = False

        self.name_input = QLineEdit(str(user.get("name") or ""))
        self.name_input.setMaxLength(constants.PROFILE_NAME_MAX)
        self.field("昵称", self.name_input)

        self.gender_box = QComboBox()
        for value in (0, 1, 2):
            self.gender_box.addItem(_GENDER_LABELS[value], value)
        try:
            gender = int(user.get("gender") or 0)
        except (TypeError, ValueError):
            gender = 0
        index = self.gender_box.findData(gender)
        self.gender_box.setCurrentIndex(index if index >= 0 else 0)
        self.field("性别", self.gender_box)

        birth_wrap = QWidget()
        birth_row = hbox(birth_wrap, spacing=10)
        self.birth_input = QDateEdit()
        self.birth_input.setCalendarPopup(True)
        self.birth_input.setDisplayFormat("yyyy-MM-dd")
        self.birth_input.setDateRange(QDate(1900, 1, 1), QDate.currentDate())
        initial = yearmode.to_date_value(user.get("age"))
        start = QDate.fromString(initial, "yyyy-MM-dd") if initial else QDate(2000, 1, 1)
        self.birth_input.setDate(start if start.isValid() else QDate(2000, 1, 1))
        self.birth_input.dateChanged.connect(self._mark_birth_dirty)
        birth_row.addWidget(self.birth_input)
        self.no_birth_box = QCheckBox("不展示出生日期")
        self.no_birth_box.toggled.connect(self._toggle_birth)
        birth_row.addWidget(self.no_birth_box)
        birth_row.addStretch(1)
        self.field("出生日期", birth_wrap)

        self.prefix_input = QLineEdit(str(user.get("prefix") or ""))
        self.prefix_input.setMaxLength(constants.PROFILE_PREFIX_MAX)
        self.prefix_input.setPlaceholderText("如：妖精")
        self.field("称号前缀", self.prefix_input)

        self.intro_input = QPlainTextEdit(str(user.get("intro") or ""))
        self.intro_input.setFixedHeight(80)
        self.intro_input.textChanged.connect(self._on_intro_changed)
        self.field("简介", self.intro_input)
        self.intro_counter = Muted("")
        self.body.addWidget(self.intro_counter)
        self._on_intro_changed()

        avatar_wrap = QWidget()
        avatar_row = hbox(avatar_wrap, spacing=10)
        self.avatar = Avatar(56)
        self.avatar.set_url(str(user.get("avatar") or ""))
        avatar_row.addWidget(self.avatar)
        self.preview = QLabel()
        self.preview.setFixedSize(56, 56)
        self.preview.hide()
        avatar_row.addWidget(self.preview)
        pick_box = vbox(spacing=6)
        self.file_name = Muted("未选择文件")
        pick_box.addWidget(self.file_name)
        pick_row = hbox(spacing=8)
        pick_row.addWidget(button("选择图片", None, self._pick_avatar))
        self.upload_btn = button("上传头像", None, self._upload_avatar)
        pick_row.addWidget(self.upload_btn)
        pick_row.addStretch(1)
        pick_box.addLayout(pick_row)
        avatar_row.addLayout(pick_box, 1)
        self.field("头像", avatar_wrap)

        self.add_action("取消", None, self.reject)
        self.save_btn = self.add_action("保存", "primary", self._save)

    # ── 生日 ──
    def _mark_birth_dirty(self, *_args) -> None:
        self._birth_dirty = True

    def _toggle_birth(self, checked: bool) -> None:
        self.birth_input.setEnabled(not checked)
        self._birth_dirty = True

    # ── 简介字数 ──
    def _on_intro_changed(self) -> None:
        text = self.intro_input.toPlainText()
        if len(text) > _INTRO_MAX:
            cursor = self.intro_input.textCursor()
            position = cursor.position()
            self.intro_input.blockSignals(True)
            self.intro_input.setPlainText(text[:_INTRO_MAX])
            cursor.setPosition(min(position, _INTRO_MAX))
            self.intro_input.setTextCursor(cursor)
            self.intro_input.blockSignals(False)
            text = text[:_INTRO_MAX]
        self.intro_counter.setText("%d/%d" % (len(text), _INTRO_MAX))

    # ── 头像 ──
    def _pick_avatar(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, "选择头像图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
        if not path:
            return
        self.clear_error()
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = 0
        if size > constants.AVATAR_MAX_BYTES:
            self.show_error(_AVATAR_TOO_LARGE)
            return
        self._local_path = str(path)
        self.file_name.setText(Path(path).name)
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self.preview.setPixmap(pixmap.scaled(
                56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            self.preview.show()

    def _upload_avatar(self) -> None:
        path = self._local_path
        if not path:
            self.show_error("请先选择图片文件")
            return
        self.clear_error()
        self.upload_btn.setEnabled(False)
        self._page.run(lambda: self._page.api.upload_avatar(path),
                       self._on_uploaded, self._on_upload_failed, label="上传头像")

    def _on_uploaded(self, result) -> None:
        self.upload_btn.setEnabled(True)
        if not result.ok:
            self.show_error(result.message)
            return
        avatar = str(result.get("avatar") or "")
        if avatar:
            self._pending_avatar = avatar
            self.avatar.set_url(avatar)
            self.preview.hide()
            self._local_path = ""
            self.file_name.setText("未选择文件")
        toast(result.message or "头像已上传")

    def _on_upload_failed(self, message: str) -> None:
        self.upload_btn.setEnabled(True)
        self.show_error(message)

    # ── 保存 ──
    def _save(self) -> None:
        self.clear_error()
        name = self.name_input.text().strip()
        if not name:
            self.show_error("请填写昵称")
            return
        if not (2 <= len(name) <= constants.PROFILE_NAME_MAX):
            self.show_error("昵称长度需为 2-%d 个字符" % constants.PROFILE_NAME_MAX)
            return
        prefix = self.prefix_input.text().strip()
        if len(prefix) > constants.PROFILE_PREFIX_MAX:
            self.show_error("称号前缀最多 %d 个字符" % constants.PROFILE_PREFIX_MAX)
            return
        intro = self.intro_input.toPlainText().strip()
        if len(intro) > _INTRO_MAX:
            self.show_error("简介最多 %d 字" % _INTRO_MAX)
            return

        fields = {
            "name": name,
            "gender": int(self.gender_box.currentData() or 0),
            "prefix": prefix,
            "intro": intro,
        }
        # 生日只在用户实际改动选择器时提交，格式 YYYYMMDD（与 Web / V1 一致）
        if self._birth_dirty:
            if self.no_birth_box.isChecked():
                fields["age"] = ""
            else:
                value = yearmode.from_date_value(
                    self.birth_input.date().toString("yyyy-MM-dd"))
                if not value:
                    self.show_error("出生日期不正确，请重新选择")
                    return
                fields["age"] = str(value)
        if self._pending_avatar:
            fields["avatar"] = self._pending_avatar

        self.save_btn.setEnabled(False)
        self._page.run(lambda: self._page.api.update_profile(**fields),
                       self._on_saved, self._on_save_failed, label="保存资料")

    def _on_saved(self, result) -> None:
        self.save_btn.setEnabled(True)
        if not result.ok:
            self.show_error(result.message)
            return
        self.saved = True
        toast(result.message or "资料已更新")
        self.accept()

    def _on_save_failed(self, message: str) -> None:
        self.save_btn.setEnabled(True)
        self.show_error(message)


class ChangePasswordDialog(BaseDialog):
    """修改密码（需邮箱验证码，无需旧密码）。"""

    def __init__(self, page, parent: QWidget | None = None) -> None:
        super().__init__(parent, title="修改密码", width=440)
        self._page = page
        self.changed = False

        self.body.addWidget(Muted(
            "系统会向你的绑定邮箱发送 6 位验证码，验证后即可设置新密码（无需旧密码）。"))

        code_wrap = QWidget()
        code_row = hbox(code_wrap, spacing=8)
        self.code_input = QLineEdit()
        self.code_input.setMaxLength(_CODE_MAX)
        self.code_input.setPlaceholderText("6 位数字验证码")
        code_row.addWidget(self.code_input, 1)
        self.send_btn = button("获取验证码", None, self._send_code)
        code_row.addWidget(self.send_btn)
        self.field("邮箱验证码", code_wrap)
        self._cool = _Cooldown(self.send_btn)

        self.new_input = QLineEdit()
        self.new_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_input.setMaxLength(constants.PASSWORD_MAX)
        self.new_input.setPlaceholderText("至少 8 位，含字母和数字")
        self.field("新密码", self.new_input)

        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input.setMaxLength(constants.PASSWORD_MAX)
        self.field("确认新密码", self.confirm_input)

        self.add_action("取消", None, self.reject)
        self.submit_btn = self.add_action("修改密码", "primary", self._submit)

    def _send_code(self) -> None:
        if not self._cool.ready():
            return
        self.clear_error()
        self.send_btn.setEnabled(False)
        self._page.run(lambda: self._page.api.send_change_password_code(),
                       self._on_code_sent, self._on_code_failed, label="验证码")

    def _on_code_sent(self, result) -> None:
        if not result.ok:
            self.send_btn.setEnabled(True)
            self.show_error(result.message)
            return
        toast(result.message or "验证码已发送至邮箱")
        self._cool.start()

    def _on_code_failed(self, message: str) -> None:
        self.send_btn.setEnabled(True)
        self.show_error(message)

    def _submit(self) -> None:
        self.clear_error()
        code = self.code_input.text().strip()
        new_password = self.new_input.text()
        if not code:
            self.show_error("请填写邮箱验证码")
            return
        if not new_password:
            self.show_error("请输入新密码")
            return
        if not (constants.PASSWORD_MIN <= len(new_password) <= constants.PASSWORD_MAX):
            self.show_error("密码长度需为 %d-%d 位"
                            % (constants.PASSWORD_MIN, constants.PASSWORD_MAX))
            return
        if not (_has_letter(new_password) and _has_digit(new_password)):
            self.show_error("密码需同时包含字母和数字")
            return
        if new_password != self.confirm_input.text():
            self.show_error("两次新密码不一致")
            return
        self.submit_btn.setEnabled(False)
        self._page.run(
            lambda: self._page.api.change_password(new_password, code=code),
            self._on_submitted, self._on_submit_failed, label="修改密码")

    def _on_submitted(self, result) -> None:
        self.submit_btn.setEnabled(True)
        if not result.ok:
            self.show_error(result.message)
            return
        self.changed = True
        self.accept()

    def _on_submit_failed(self, message: str) -> None:
        self.submit_btn.setEnabled(True)
        self.show_error(message)


class ChangeEmailDialog(BaseDialog):
    """更换绑定邮箱（两步：先验当前邮箱身份，再验新邮箱）。"""

    def __init__(self, page, parent: QWidget | None = None) -> None:
        super().__init__(parent, title="更换绑定邮箱", width=460)
        self._page = page
        self.changed = False
        self._step = 1

        self.step_hint = Muted("")
        self.body.addWidget(self.step_hint)

        # 第 1 步：验证当前绑定邮箱身份
        self.step1 = QWidget()
        step1 = vbox(self.step1, spacing=10)
        old_wrap = QWidget()
        old_row = hbox(old_wrap, spacing=8)
        self.old_code = QLineEdit()
        self.old_code.setMaxLength(_CODE_MAX)
        self.old_code.setPlaceholderText("6 位数字验证码")
        old_row.addWidget(self.old_code, 1)
        self.old_send_btn = button("获取验证码", None, self._send_old_code)
        old_row.addWidget(self.old_send_btn)
        _field(step1, "当前邮箱验证码", old_wrap)
        self.body.addWidget(self.step1)
        self._old_cool = _Cooldown(self.old_send_btn)

        # 第 2 步：填写并验证新邮箱
        self.step2 = QWidget()
        step2 = vbox(self.step2, spacing=10)
        self.new_email = QLineEdit()
        self.new_email.setMaxLength(_EMAIL_MAX)
        self.new_email.setPlaceholderText("新邮箱地址")
        _field(step2, "新邮箱", self.new_email)
        new_wrap = QWidget()
        new_row = hbox(new_wrap, spacing=8)
        self.new_code = QLineEdit()
        self.new_code.setMaxLength(_CODE_MAX)
        self.new_code.setPlaceholderText("6 位数字验证码")
        new_row.addWidget(self.new_code, 1)
        self.new_send_btn = button("获取验证码", None, self._send_new_code)
        new_row.addWidget(self.new_send_btn)
        _field(step2, "新邮箱验证码", new_wrap)
        self.body.addWidget(self.step2)
        self._new_cool = _Cooldown(self.new_send_btn)

        self.add_action("取消", None, self.reject)
        self.prev_btn = self.add_action("上一步", None, self._go_step1)
        self.next_btn = self.add_action("下一步", "primary", self._go_step2)
        self.submit_btn = self.add_action("确认更换", "primary", self._submit)

        self._apply_step()

    # ── 分步 ──
    def _apply_step(self) -> None:
        self.clear_error()
        step = self._step
        self.step_hint.setText("第 1 步 / 共 2 步：验证当前绑定邮箱身份" if step == 1
                               else "第 2 步 / 共 2 步：填写并验证新邮箱")
        self.step1.setVisible(step == 1)
        self.step2.setVisible(step == 2)
        self.prev_btn.setVisible(step == 2)
        self.next_btn.setVisible(step == 1)
        self.submit_btn.setVisible(step == 2)

    def _go_step1(self) -> None:
        self._step = 1
        self._apply_step()

    def _go_step2(self) -> None:
        if not self.old_code.text().strip():
            self.show_error("请填写当前邮箱验证码")
            return
        self._step = 2
        self._apply_step()

    # ── 验证码 ──
    def _send_old_code(self) -> None:
        if not self._old_cool.ready():
            return
        self.clear_error()
        self.old_send_btn.setEnabled(False)
        self._page.run(lambda: self._page.api.send_change_email_old_code(),
                       self._on_old_sent, self._on_old_failed, label="验证码")

    def _on_old_sent(self, result) -> None:
        if not result.ok:
            self.old_send_btn.setEnabled(True)
            self.show_error(result.message)
            return
        toast(result.message or "验证码已发送至当前绑定邮箱")
        self._old_cool.start()

    def _on_old_failed(self, message: str) -> None:
        self.old_send_btn.setEnabled(True)
        self.show_error(message)

    def _send_new_code(self) -> None:
        if not self._new_cool.ready():
            return
        self.clear_error()
        email = self.new_email.text().strip()
        if not email:
            self.show_error("请先填写新邮箱")
            return
        self.new_send_btn.setEnabled(False)
        self._page.run(lambda: self._page.api.send_change_email_code(email),
                       self._on_new_sent, self._on_new_failed, label="验证码")

    def _on_new_sent(self, result) -> None:
        if not result.ok:
            self.new_send_btn.setEnabled(True)
            self.show_error(result.message)
            return
        toast(result.message or "验证码已发送至新邮箱")
        self._new_cool.start()

    def _on_new_failed(self, message: str) -> None:
        self.new_send_btn.setEnabled(True)
        self.show_error(message)

    # ── 提交 ──
    def _submit(self) -> None:
        self.clear_error()
        old_code = self.old_code.text().strip()
        email = self.new_email.text().strip()
        code = self.new_code.text().strip()
        if not old_code:
            self._step = 1
            self._apply_step()
            self.show_error("请填写当前邮箱验证码")
            return
        if not email:
            self.show_error("请先填写新邮箱")
            return
        if not code:
            self.show_error("请填写新邮箱验证码")
            return
        self.submit_btn.setEnabled(False)
        self._page.run(lambda: self._page.api.change_email(old_code, email, code),
                       self._on_submitted, self._on_submit_failed, label="更换邮箱")

    def _on_submitted(self, result) -> None:
        self.submit_btn.setEnabled(True)
        if not result.ok:
            self.show_error(result.message)
            return
        self.changed = True
        toast(result.message or "邮箱已更换")
        self.accept()

    def _on_submit_failed(self, message: str) -> None:
        self.submit_btn.setEnabled(True)
        self.show_error(message)

