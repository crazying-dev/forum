# -*- coding: utf-8 -*-
"""帖子详情页（对照 Web 端 ``PostDetailView.vue``）。

结构：

* 顶部：标题 + 刷新 + 状态提示
* 滚动区：帖子卡（作者 / 标题 / Markdown 正文 / 操作栏）+ 评论卡（楼中楼）
* 底部：固定评论输入框（未登录时置灰）
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QWidget

from .. import constants, yearmode
from ..widgets import (Card, Chip, CommentList, MarkdownView, Muted, ScrollPage,
                       UserLink, button, divider, hbox, set_variant, vbox)
# CardTitle 未在 widgets/__init__ 的显式导出中，直接取子模块
from ..widgets.common import CardTitle
from ..widgets.images import Avatar
from .base import Page


class PostDetailPage(Page):
    """帖子详情：正文 + 点赞 / 收藏 / 举报 / 删除 / 分享 + 评论。"""

    ROUTE = "post"
    TITLE = "帖子详情"
    KEEP_ALIVE = False

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._post_id = ""
        self._post: dict = {}
        self._liked = False
        self._favorited = False
        self._likes = 0
        self._views = 0
        self._reply_id = ""
        self._reply_name = ""

        root = vbox(self, margins=(14, 12, 14, 10), spacing=8)
        header, header_layout = self.make_header("帖子详情", "")
        self.refresh_btn = button("刷新", "ghost", self.reload)
        header.actions.addWidget(self.refresh_btn)
        self.hint = Muted("")
        header_layout.addWidget(self.hint)
        root.addWidget(header)

        self.scroll = ScrollPage(self, spacing=10)
        self.scroll.add(self._build_post_card())
        self.scroll.add(self._build_comment_card())
        root.addWidget(self.scroll, 1)
        root.addWidget(self._build_input_card())

    # ────────────────────── 构建 ──────────────────────
    def _build_post_card(self) -> Card:
        card = Card(padding=(16, 14, 16, 14), spacing=10)

        head = hbox(spacing=10)
        self.avatar = Avatar(42)
        self.avatar.clicked.connect(self._open_author)
        head.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)

        info = vbox(spacing=5)
        name_row = hbox(spacing=6)
        self.user = UserLink()
        self.user.activated.connect(self.open_user)
        name_row.addWidget(self.user)
        self.title_chip = Chip("", "title")
        name_row.addWidget(self.title_chip)
        self.cat_chip = Chip("", "category")
        name_row.addWidget(self.cat_chip)
        self.meta = Muted("")
        name_row.addWidget(self.meta)
        name_row.addStretch(1)
        info.addLayout(name_row)

        self.title = QLabel("")
        self.title.setObjectName("PostTitle")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        info.addWidget(self.title)
        head.addLayout(info, 1)
        card.body.addLayout(head)
        card.body.addWidget(divider())

        self.content = MarkdownView(min_height=180)
        self.content.link_clicked.connect(self.open_link)
        card.body.addWidget(self.content, 1)

        actions = hbox(spacing=4)
        self.like_btn = button("♡ 0", None, self._on_like, tooltip="点赞")
        actions.addWidget(self.like_btn)
        self.fav_btn = button("☆ 收藏", None, self._on_favorite, tooltip="收藏")
        actions.addWidget(self.fav_btn)
        self.share_btn = button("分享", "ghost", self._on_share)
        actions.addWidget(self.share_btn)
        self.report_btn = button("举报", "ghost", self._on_report)
        actions.addWidget(self.report_btn)
        self.delete_btn = button("删除", "ghost", self._on_delete)
        self.delete_btn.hide()
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        card.body.addLayout(actions)
        return card

    def _build_comment_card(self) -> Card:
        card = Card(padding=(16, 14, 16, 14), spacing=8)
        head = hbox(spacing=6)
        head.addWidget(CardTitle("评论"))
        self.comment_count = Muted("")
        head.addWidget(self.comment_count)
        head.addStretch(1)
        card.body.addLayout(head)

        self.comment_list = CommentList(collapsible=False)
        self.comment_list.open_user.connect(self.open_user)
        self.comment_list.open_post.connect(self.open_post)
        self.comment_list.like.connect(self._on_comment_like)
        self.comment_list.delete.connect(self._on_comment_delete)
        self.comment_list.reply.connect(self._on_comment_reply)
        self.comment_list.report.connect(self._on_comment_report)
        card.body.addWidget(self.comment_list)
        return card

    def _build_input_card(self) -> Card:
        card = Card(padding=(16, 12, 16, 12), spacing=6)
        self.reply_bar = QWidget(card)
        reply_row = hbox(self.reply_bar, spacing=6)
        self.reply_label = Muted("")
        reply_row.addWidget(self.reply_label)
        reply_row.addStretch(1)
        reply_row.addWidget(button("✕", "ghost", self._cancel_reply, tooltip="取消回复"))
        self.reply_bar.hide()
        card.body.addWidget(self.reply_bar)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("写下你的评论…")
        self.input.setFixedHeight(80)
        self.input.textChanged.connect(self._on_input_changed)
        card.body.addWidget(self.input)

        bottom = hbox(spacing=8)
        self.input_count = Muted("")
        bottom.addWidget(self.input_count)
        bottom.addStretch(1)
        self.send_btn = button("发表评论", "primary", self._submit_comment)
        bottom.addWidget(self.send_btn)
        card.body.addLayout(bottom)
        return card

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, post_id: str = "", **kwargs) -> None:
        super().on_show(**kwargs)
        pid = str(post_id or "")
        if pid and pid != self._post_id:
            self._post_id = pid
            self._post = {}
            self._liked = False
            self._favorited = False
            self._likes = 0
            self._views = 0
            self.title.setText("")
            self.content.set_markdown("")
            self.comment_list.set_comments([])
            self.comment_count.setText("")
            self._cancel_reply()
        self.refresh_auth()
        self.reload()

    def refresh_auth(self) -> None:
        """登录态变化后刷新输入框（Shell.refresh_user 会回调）。"""
        logged = bool(self.me)
        self.input.setEnabled(logged)
        self.input.setPlaceholderText("写下你的评论…（最多 500 字）" if logged
                                      else "请先登录后发表评论")
        self._on_input_changed()

    def reload(self) -> None:
        if not self._post_id:
            self.hint.setText("缺少帖子 ID，无法加载")
            return
        self.hint.setText("加载中…")
        pid = self._post_id
        self.run(lambda: self.api.post(pid), self._on_loaded, label="帖子详情")

    # ────────────────────── 渲染 ──────────────────────
    def _on_loaded(self, result) -> None:
        if not result.ok:
            self.hint.setText(result.message or "帖子加载失败")
            return
        self.hint.setText("")
        self._post = result.get("post") or {}
        self._liked = bool(result.get("liked"))
        self._favorited = bool(result.get("favorited"))
        self._render_post()
        self._render_comments(result.rows("comments"))

    def _render_post(self) -> None:
        post = self._post or {}
        uid = str(post.get("user_id") or "")
        self.avatar.set_url(str(post.get("user_avatar") or ""))
        self.user.set_user(uid, str(post.get("user_name") or "匿名用户"))
        title_chip = str(post.get("user_title") or post.get("title") or "").strip()
        self.title_chip.setText(title_chip)
        self.title_chip.setVisible(bool(title_chip))
        self.cat_chip.setText(constants.category_label(post.get("category")))
        self.title.setText(str(post.get("title") or "（无标题）"))
        self._likes = int(post.get("likes") or 0)
        self._views = int(post.get("views") or 0)
        self.content.set_markdown(str(post.get("content") or ""))
        me_id = str((self.me or {}).get("id") or "")
        self.delete_btn.setVisible(bool(uid) and uid == me_id)
        self._refresh_meta()
        self._refresh_actions()

    def _refresh_meta(self) -> None:
        post = self._post or {}
        self.meta.setText("%s   👁 %d   ♥ %d" % (
            yearmode.fmt_time(post.get("created_at")), self._views, self._likes))

    def _refresh_actions(self) -> None:
        self.like_btn.setText("♥ %d" % self._likes if self._liked
                              else "♡ %d" % self._likes)
        set_variant(self.like_btn, "primary" if self._liked else None)
        self.fav_btn.setText("★ 已收藏" if self._favorited else "☆ 收藏")
        set_variant(self.fav_btn, "primary" if self._favorited else None)

    def _render_comments(self, comments: list) -> None:
        rows = [c for c in (comments or []) if isinstance(c, dict)]
        me_id = str((self.me or {}).get("id") or "")
        self.comment_list.set_comments(rows, me_id=me_id, post_link=self._post_id,
                                       total=len(rows))
        self.comment_count.setText("(%d)" % len(rows))

    def _reload_comments(self) -> None:
        if not self._post_id:
            return
        pid = self._post_id

        def _done(result):
            if not result.ok:
                self.toast(result.message)
                return
            self._render_comments(result.rows("comments"))

        self.run(lambda: self.api.comments(pid, 1, 50), _done, label="评论")

    # ────────────────────── 帖子操作 ──────────────────────
    def _open_author(self) -> None:
        self.open_user(str((self._post or {}).get("user_id") or ""))

    def _on_like(self) -> None:
        if not self.need_login("请先登录后点赞"):
            return
        if not self._post_id:
            return
        pid = self._post_id
        self.like_btn.setEnabled(False)

        def _done(result):
            self.like_btn.setEnabled(True)
            if not result.ok:
                self.toast(result.message)
                return
            self._liked = bool(result.get("liked"))
            self._likes = self._likes + 1 if self._liked else max(self._likes - 1, 0)
            likes = result.get("likes")
            if isinstance(likes, int):
                self._likes = likes
            self._refresh_meta()
            self._refresh_actions()

        self.run(lambda: self.api.like_post(pid), _done, label="点赞")

    def _on_favorite(self) -> None:
        if not self.need_login("请先登录后收藏"):
            return
        if not self._post_id:
            return
        pid = self._post_id

        def _done(result):
            if not result.ok:
                self.toast(result.message)
                return
            favorited = result.get("favorited")
            self._favorited = (bool(favorited) if favorited is not None
                               else not self._favorited)
            self._refresh_actions()
            self.toast("已收藏" if self._favorited else "已取消收藏")

        self.run(lambda: self.api.favorite_post(pid), _done, label="收藏")

    def _on_share(self) -> None:
        if not self._post_id:
            return
        url = "%s/post/%s" % (constants.BASE_URL, self._post_id)
        QGuiApplication.clipboard().setText(url)
        self.toast("链接已复制")

    def _on_report(self) -> None:
        if self._post_id:
            self.report_dialog("post", self._post_id)

    def _on_delete(self) -> None:
        if not self._post_id:
            return
        if not self.confirm("删除帖子", "确定删除该帖子？删除后无法恢复。",
                            ok_text="删除", danger=True):
            return
        pid = self._post_id

        def _done(result):
            if not result.ok:
                self.toast(result.message)
                return
            self.toast("帖子已删除")
            self.go_back()

        self.run(lambda: self.api.delete_post(pid), _done, label="删除帖子")

    # ────────────────────── 评论操作 ──────────────────────
    def _on_comment_like(self, data: dict) -> None:
        cid = str((data or {}).get("id") or "")
        if not cid:
            return
        if not self.need_login("请先登录后点赞"):
            return

        def _done(result):
            if not result.ok:
                self.toast(result.message)
                return
            item = self.comment_list.item_for(cid)
            if item is not None:
                item.set_liked(bool(result.get("liked")), result.get("likes"))

        self.run(lambda: self.api.like_comment(cid), _done, label="评论点赞")

    def _on_comment_delete(self, data: dict) -> None:
        cid = str((data or {}).get("id") or "")
        if not cid:
            return
        if not self.confirm("删除评论", "确定删除这条评论？", ok_text="删除", danger=True):
            return

        def _done(result):
            if not result.ok:
                self.toast(result.message)
                return
            self.toast("评论已删除")
            self._reload_comments()

        self.run(lambda: self.api.delete_comment(cid), _done, label="删除评论")

    def _on_comment_report(self, data: dict) -> None:
        cid = str((data or {}).get("id") or "")
        if cid:
            self.report_dialog("comment", cid)

    def _on_comment_reply(self, data: dict) -> None:
        self._start_reply(str((data or {}).get("id") or ""),
                          str((data or {}).get("name") or ""))

    def _start_reply(self, comment_id: str, name: str) -> None:
        if not comment_id:
            return
        self._reply_id = comment_id
        self._reply_name = name
        self.reply_label.setText("回复 @%s" % (name or "匿名用户"))
        self.reply_bar.show()
        self.input.setFocus()

    def _cancel_reply(self) -> None:
        self._reply_id = ""
        self._reply_name = ""
        self.reply_label.setText("")
        self.reply_bar.hide()

    # ────────────────────── 评论输入 ──────────────────────
    def _on_input_changed(self) -> None:
        text = self.input.toPlainText()
        if len(text) > constants.COMMENT_MAX:
            text = text[:constants.COMMENT_MAX]
            cursor = self.input.textCursor()
            self.input.blockSignals(True)
            self.input.setPlainText(text)
            self.input.blockSignals(False)
            cursor.setPosition(len(text))
            self.input.setTextCursor(cursor)
        self.input_count.setText("%d/%d" % (len(text), constants.COMMENT_MAX))
        self.send_btn.setEnabled(bool(self.me) and bool(text.strip()))

    def _submit_comment(self) -> None:
        if not self.need_login("请先登录后发表评论"):
            return
        if not self._post_id:
            return
        content = self.input.toPlainText().strip()[:constants.COMMENT_MAX]
        if not content:
            self.toast("请输入评论内容")
            return
        pid = self._post_id
        parent = self._reply_id or None
        self.send_btn.setEnabled(False)

        def _done(result):
            self.send_btn.setEnabled(True)
            if not result.ok:
                self.toast(result.message)
                return
            self.toast("评论已发表")
            self.input.blockSignals(True)
            self.input.clear()
            self.input.blockSignals(False)
            self._on_input_changed()
            self._cancel_reply()
            self._reload_comments()

        self.run(lambda: self.api.create_comment(pid, content, parent), _done,
                 label="发表评论")
