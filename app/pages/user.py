# -*- coding: utf-8 -*-
"""用户主页（对照 Web 端 ``UserView.vue``）。

* 资料卡：头像 / 昵称 / 头衔 / 性别 / 生日 / 年龄 / 简介 / 注册时间
* 统计行：帖子、获赞、浏览 + 可点击的「关注」「粉丝」（弹 :class:`UserListDialog`）
* 右上按钮：自己 → 「编辑资料」（跳到 ``me``）；他人 → 「关注 / 已关注」
* 三个页签：发布的帖子 / 收藏（仅本人可见）/ 评论，均支持「加载更多」

``KEEP_ALIVE = False``：每次进入都按 ``user_id`` 全量重载，避免旧数据的
异步回调写到别的用户身上。
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTabWidget, QWidget

from .. import constants, yearmode
from ..widgets import (Card, Chip, EmptyHint, Muted, PostCard, ScrollPage,
                       UserLink, UserListDialog, button, hbox, set_variant, vbox,
                       with_author)
from ..widgets.images import Avatar
from .base import Page

_GENDER_LABELS = {0: "保密", 1: "男", 2: "女"}


class _ListPane(QWidget):
    """滚动列表 + 空态 / 加载态 / 「加载更多」（帖子与评论共用）。"""

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
        """不发请求，直接显示一句提示（如「无权查看他人收藏」）。"""
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


class UserPage(Page):
    """用户主页：资料卡 + 关注 / 粉丝列表 + 帖子 / 收藏 / 评论。"""

    ROUTE = "user"
    TITLE = "用户主页"
    KEEP_ALIVE = False

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._user_id = ""
        self._user: dict = {}
        self._following = False

        root = vbox(self, margins=(14, 12, 14, 10), spacing=10)
        header, header_layout = self.make_header("用户主页", "")
        self.action_btn = button("关注", "primary", self._on_action)
        self.action_btn.hide()
        header.actions.addWidget(self.action_btn)
        header.actions.addWidget(button("刷新", "ghost", self.reload))
        self.hint = Muted("")
        header_layout.addWidget(self.hint)
        root.addWidget(header)

        root.addWidget(self._build_profile_card())
        self.tabs = self._build_tabs()
        root.addWidget(self.tabs, 1)

    # ────────────────────── 构建 ──────────────────────
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

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        self.posts_pane = _ListPane(self, self._fetch_posts, rows_key="posts",
                                    build_item=self._build_own_post_widget,
                                    empty_text="暂无帖子")
        tabs.addTab(self.posts_pane, "发布的帖子")
        self.favorites_pane = _ListPane(self, self._fetch_favorites,
                                        rows_key="posts",
                                        build_item=self._build_post_widget,
                                        empty_text="暂无收藏")
        tabs.addTab(self.favorites_pane, "收藏")
        self.comments_pane = _ListPane(self, self._fetch_comments,
                                       rows_key="comments",
                                       build_item=self._build_comment_widget,
                                       empty_text="暂无评论")
        tabs.addTab(self.comments_pane, "评论")
        tabs.currentChanged.connect(self._on_tab_changed)
        return tabs

    def _author_defaults(self) -> dict:
        """主页主人资料：接口未返回作者字段时用来补齐帖子卡片。"""
        user = self._user or {}
        return {
            "user_id": str(user.get("id") or self._user_id),
            "name": str(user.get("name") or ""),
            "avatar": str(user.get("avatar") or ""),
        }

    def _build_own_post_widget(self, post: dict) -> QWidget:
        """「发布的帖子」：作者字段缺失时用主页主人资料补齐（历史接口兼容）。"""
        return self._build_post_widget(with_author(post, **self._author_defaults()))

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

        post_id = str(comment.get("_id") or "")
        title = str(comment.get("post_title") or "") or ("帖子 %s" % post_id)
        meta = hbox(spacing=6)
        meta.addWidget(Muted("评论于《%s》" % title))
        meta.addWidget(Muted(yearmode.fmt_time(comment.get("created_at"))))
        meta.addStretch(1)
        meta.addWidget(button("查看原帖", "ghost",
                              lambda: self.open_post(post_id)))
        card.body.addLayout(meta)
        return card

    # ────────────────────── 数据 ──
    def _fetch_posts(self, page_no: int):
        return self.api.user_posts(self._user_id, page_no, constants.PAGE_SIZE)

    def _fetch_favorites(self, page_no: int):
        return self.api.user_favorites(self._user_id, page_no, constants.PAGE_SIZE)

    def _fetch_comments(self, page_no: int):
        return self.api.user_comments(self._user_id, page_no, constants.PAGE_SIZE)

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, user_id: str = "", **kwargs) -> None:
        super().on_show(**kwargs)
        self._user_id = str(user_id or "").strip()
        self._user = {}
        self._following = False
        self._reset_view()
        self.reload()

    def reload(self) -> None:
        if not self._user_id:
            self.hint.setText("缺少用户 ID，无法加载")
            self.action_btn.hide()
            return
        self.hint.setText("加载中…")
        uid = self._user_id
        self.run(lambda: self.api.get_user(uid), self._on_loaded, self._on_failed,
                 label="用户主页")

    def refresh_auth(self) -> None:
        """登录态变化后刷新右上按钮（Shell.refresh_user 会回调）。"""
        self._refresh_actions()

    def title_text(self) -> str:
        name = str((self._user or {}).get("name") or "")
        return "%s · %s" % (self.TITLE, name) if name else self.TITLE

    def _on_failed(self, message: str) -> None:
        self.hint.setText(message or "加载失败")
        self.toast(message)

    def _on_loaded(self, result) -> None:
        if not result.ok:
            self.hint.setText(result.message or "用户加载失败")
            self.toast(result.message)
            return
        user = result.get("user") or {}
        if not user:
            self.hint.setText("用户不存在或已被封禁")
            return
        self.hint.setText("")
        self._user = user
        self._following = bool(user.get("is_following"))
        self._render_profile()
        for pane in (self.posts_pane, self.favorites_pane, self.comments_pane):
            pane.reset()
        self._load_current_tab()

    # ────────────────────── 渲染 ──────────────────────
    def _reset_view(self) -> None:
        """回到「未加载」状态（切换用户 / 刷新前清场）。"""
        self.avatar.clear()
        self.name_link.set_user("", "")
        self.title_chip.hide()
        self.meta.setText("")
        self.stat_posts.setText("帖子 0")
        self.stat_likes.setText("获赞 0")
        self.stat_views.setText("浏览 0")
        self.following_btn.setText("关注 0")
        self.followers_btn.setText("粉丝 0")
        self.intro.setText("")
        self.intro.hide()
        self.reg_meta.setText("")
        for pane in (self.posts_pane, self.favorites_pane, self.comments_pane):
            pane.reset()
        self.tabs.setCurrentIndex(0)
        self._refresh_actions()

    def _render_profile(self) -> None:
        user = self._user or {}
        uid = str(user.get("id") or self._user_id)
        self.avatar.set_url(str(user.get("avatar") or ""))
        self.name_link.set_user(uid, str(user.get("name") or "匿名用户"))

        title = str(user.get("title") or "").strip()
        self.title_chip.setText(title)
        self.title_chip.setVisible(bool(title))

        meta_parts = []
        try:
            gender = int(user.get("gender") or 0)
        except (TypeError, ValueError):
            gender = 0
        if gender in (1, 2):
            meta_parts.append("性别：%s" % _GENDER_LABELS[gender])
        birthday = yearmode.fmt_birthday(user.get("age"))
        if birthday:
            meta_parts.append("生日：%s" % birthday)
        age = yearmode.short_age(user.get("age"))
        if age:
            meta_parts.append("%s 岁" % age)
        self.meta.setText("   ".join(meta_parts))

        intro = str(user.get("intro") or "").strip()
        self.intro.setText(intro)
        self.intro.setVisible(bool(intro))

        stats = user.get("stats") or {}
        self.stat_posts.setText("帖子 %d" % int(stats.get("post_count") or 0))
        self.stat_likes.setText("获赞 %d" % int(stats.get("total_likes") or 0))
        self.stat_views.setText("浏览 %d" % int(stats.get("total_views") or 0))
        self.following_btn.setText("关注 %d" % int(stats.get("following_count") or 0))
        self.followers_btn.setText("粉丝 %d" % int(stats.get("follower_count") or 0))

        created = yearmode.fmt_time(user.get("created_at"))
        self.reg_meta.setText("注册于 %s" % created if created else "")
        self._refresh_actions()

    def _is_self(self) -> bool:
        user = self._user or {}
        if user.get("is_self"):
            return True
        me_id = str((self.me or {}).get("id") or "")
        return bool(me_id) and me_id == str(user.get("id") or self._user_id)

    def _refresh_actions(self) -> None:
        if not self._user:
            self.action_btn.hide()
            return
        self.action_btn.show()
        if self._is_self():
            self.action_btn.setText("编辑资料")
            set_variant(self.action_btn, None)
            return
        self.action_btn.setText("已关注" if self._following else "关注")
        set_variant(self.action_btn, None if self._following else "primary")

    # ────────────────────── 交互 ──────────────────────
    def _on_action(self) -> None:
        if self._is_self():
            self.go("me")
        else:
            self._toggle_follow()

    def _toggle_follow(self) -> None:
        if not self.need_login("请先登录后关注"):
            return
        uid = str((self._user or {}).get("id") or self._user_id)
        if not uid:
            return
        self.action_btn.setEnabled(False)

        def _done(result):
            self.action_btn.setEnabled(True)
            if not result.ok:
                self.toast(result.message)
                return
            self._following = bool(result.get("following"))
            self._refresh_actions()
            self.toast("已关注" if self._following else "已取消关注")

        def _fail(message):
            self.action_btn.setEnabled(True)
            self.toast(message)

        self.run(lambda: self.api.follow(uid), _done, _fail, label="关注")

    def _open_user_list(self, kind: str) -> None:
        if not self._user_id:
            return
        name = str((self._user or {}).get("name") or "该用户")
        title = ("%s 的关注" % name) if kind == "following" else ("%s 的粉丝" % name)
        dialog = UserListDialog(self._user_id, kind, self.window(), title=title)
        dialog.open_user.connect(self.open_user)
        dialog.exec()

    # ────────────────────── 页签 ──────────────────────
    def _on_tab_changed(self, index: int) -> None:
        pane = self.tabs.widget(index)
        if not isinstance(pane, _ListPane) or pane.loaded or not self._user:
            return
        if pane is self.favorites_pane and not self._is_self():
            pane.show_message("无权查看他人收藏")
            return
        pane.reload()

    def _load_current_tab(self) -> None:
        self._on_tab_changed(self.tabs.currentIndex())

