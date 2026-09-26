# -*- coding: utf-8 -*-
"""发布帖子页（对照 Web 端 ``PostCreateView.vue``）。

* 标题（≤ 100 字，实时字数）+ 分区下拉（:data:`app.constants.CATEGORY_ORDER`）
* 「编辑 / 预览」两个页签：编辑用 ``QPlainTextEdit``，预览用 :class:`MarkdownView`
* 底部固定「取消 / 发布」，发布成功后直接跳到新帖详情
* 下方「发帖须知」与 Web 端同源（8 条合规清单，原文照搬）

``KEEP_ALIVE = False``：每次进入都是新实例，因此表单天然是空的。未登录时
禁用表单并跳登录页（登录后该页会被重建）。
"""

from __future__ import annotations

from PyQt6.QtWidgets import (QComboBox, QLabel, QLineEdit, QPlainTextEdit,
                             QTabWidget, QWidget)

from .. import constants
from ..widgets import (Card, MarkdownView, Muted, ScrollPage, button, hbox,
                       vbox)
# CardTitle 未在 widgets/__init__ 的显式导出中，直接取子模块
from ..widgets.common import CardTitle
from .base import Page

#: 发帖须知（原文取自 Web 端 ``PostCreateView.vue``）
NOTICE_ITEMS = (
    "遵守中华人民共和国相关法律法规，不得发布违法违规内容",
    "禁止涉及政治敏感、涉黄涉暴、血腥恐怖、毒品赌博等内容",
    "禁止人身攻击、谩骂侮辱、恶意引战、网络暴力等行为",
    "禁止发布广告、spam、外链刷量、引流等垃圾信息",
    "禁止泄露他人或自己的隐私信息（真实姓名、电话、地址等）",
    "禁止侵犯他人知识产权，转载请注明出处或获得授权",
    "内容应与论坛主题（罗小黑战记及二次元文化）相关，鼓励友善交流",
    "违反以上规定的帖子将被删除，情节严重者将封禁账号",
)


class PostCreatePage(Page):
    """发布帖子：标题 + 分区 + Markdown 正文（编辑 / 预览）。"""

    ROUTE = "post_create"
    TITLE = "发布帖子"
    KEEP_ALIVE = False

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._busy = False

        root = vbox(self, margins=(14, 12, 14, 10), spacing=8)
        header, header_layout = self.make_header("发布帖子", "支持 Markdown 格式内容")
        header.actions.addWidget(button("返回", "ghost", self.go_back))
        self.hint = Muted("")
        header_layout.addWidget(self.hint)
        root.addWidget(header)

        self.scroll = ScrollPage(self, spacing=10)
        self.scroll.add(self._build_form_card())
        self.scroll.add(self._build_editor_card())
        self.scroll.add(self._build_notice_card())
        root.addWidget(self.scroll, 1)
        root.addWidget(self._build_actions())

    # ────────────────────── 构建 ──────────────────────
    def _build_form_card(self) -> Card:
        card = Card(padding=(16, 14, 16, 14), spacing=8)

        title_row = hbox(spacing=6)
        title_row.addWidget(Muted("标题"))
        title_row.addStretch(1)
        self.title_count = Muted("0/%d" % constants.TITLE_MAX)
        title_row.addWidget(self.title_count)
        card.body.addLayout(title_row)

        self.title_input = QLineEdit()
        self.title_input.setMaxLength(constants.TITLE_MAX)
        self.title_input.setPlaceholderText(
            "一句话说明帖子主题（最多 %d 字）" % constants.TITLE_MAX)
        self.title_input.textChanged.connect(self._on_title_changed)
        card.body.addWidget(self.title_input)

        cat_row = hbox(spacing=8)
        cat_row.addWidget(Muted("分区"))
        self.category = QComboBox()
        for key in constants.CATEGORY_ORDER:
            self.category.addItem(constants.category_label(key), key)
        cat_row.addWidget(self.category)
        cat_row.addStretch(1)
        card.body.addLayout(cat_row)
        return card

    def _build_editor_card(self) -> Card:
        card = Card(padding=(10, 10, 10, 10), spacing=6)
        self.tabs = QTabWidget()

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("支持 Markdown 格式内容")
        self.editor.setMinimumHeight(320)
        self.editor.textChanged.connect(self._on_content_changed)
        self.tabs.addTab(self.editor, "编辑")

        self.preview = MarkdownView(min_height=320)
        self.preview.link_clicked.connect(self.open_link)
        self.tabs.addTab(self.preview, "预览")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        card.body.addWidget(self.tabs, 1)

        bottom = hbox(spacing=6)
        self.content_count = Muted("0 字")
        bottom.addWidget(self.content_count)
        bottom.addStretch(1)
        card.body.addLayout(bottom)
        return card

    def _build_notice_card(self) -> Card:
        card = Card(padding=(16, 14, 16, 14), spacing=6)
        card.body.addWidget(CardTitle("发帖须知"))
        for index, text in enumerate(NOTICE_ITEMS, start=1):
            item = QLabel("%d. %s" % (index, text))
            item.setWordWrap(True)
            item.setProperty("muted", "true")
            card.body.addWidget(item)
        return card

    def _build_actions(self) -> QWidget:
        row = QWidget(self)
        layout = hbox(row)
        layout.addStretch(1)
        layout.addWidget(button("取消", None, self.go_back))
        self.publish_btn = button("发布", "primary", self._publish)
        layout.addWidget(self.publish_btn)
        return row

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, **kwargs) -> None:
        super().on_show(**kwargs)
        self._busy = False
        self.refresh_auth()
        if not self.me:
            self.need_login("请先登录后发帖")

    def refresh_auth(self) -> None:
        """登录态变化后启 / 禁用表单（Shell.refresh_user 会回调）。"""
        logged = bool(self.me)
        self.title_input.setEnabled(logged)
        self.category.setEnabled(logged)
        self.editor.setEnabled(logged)
        self.hint.setText("" if logged else "请先登录后再发布帖子")
        self._refresh_publish()

    # ────────────────────── 表单 ──────────────────────
    def _on_title_changed(self) -> None:
        text = self.title_input.text()
        self.title_count.setText("%d/%d" % (len(text), constants.TITLE_MAX))
        self._refresh_publish()

    def _on_content_changed(self) -> None:
        self.content_count.setText("%d 字" % len(self.editor.toPlainText()))
        self._refresh_publish()

    def _refresh_publish(self) -> None:
        ready = (bool(self.me)
                 and bool(self.title_input.text().strip())
                 and bool(self.editor.toPlainText().strip()))
        self.publish_btn.setEnabled(ready and not self._busy)

    def _on_tab_changed(self, index: int) -> None:
        """切到「预览」时同步一次 Markdown 渲染。"""
        if index == 1:
            self.preview.set_markdown(self.editor.toPlainText())

    # ────────────────────── 发布 ──────────────────────
    def _publish(self) -> None:
        if not self.need_login("请先登录后发帖"):
            return
        title = self.title_input.text().strip()
        content = self.editor.toPlainText().strip()
        if not title:
            self.toast("请填写标题")
            return
        if not content:
            self.toast("请填写正文内容")
            return
        category = str(self.category.currentData() or "general")
        self._busy = True
        self.publish_btn.setText("发布中…")
        self._refresh_publish()

        def _done(result):
            self._busy = False
            self.publish_btn.setText("发布")
            self._refresh_publish()
            if not result.ok:
                self.hint.setText(result.message)
                self.toast(result.message)
                return
            self.hint.setText("")
            self.toast("发布成功")
            post_id = str(result.get("id") or "")
            if post_id:
                self.open_post(post_id)
            else:
                self.go_back()

        def _fail(message):
            self._busy = False
            self.publish_btn.setText("发布")
            self._refresh_publish()
            self.hint.setText(message)

        self.run(lambda: self.api.create_post(title, content, category),
                 _done, _fail, label="发布帖子")
