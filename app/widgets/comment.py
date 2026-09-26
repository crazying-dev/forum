# -*- coding: utf-8 -*-
"""评论：单条评论（支持楼中楼折叠）与评论列表（按 parent_id 组装树）。"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import logger, yearmode
from .common import Muted, UserLink, button, clear_layout, hbox, vbox
from .images import Avatar

_log = logger.get_logger("comments")

CHILD_FOLD_THRESHOLD = 3  # 子回复超过这个数量默认折叠


class CommentItem(QFrame):
    """单条评论（布局对照 Web 端 CommentItem.vue）。"""

    open_post = pyqtSignal(str)
    open_user = pyqtSignal(str)
    reply = pyqtSignal(dict)
    like = pyqtSignal(dict)
    delete = pyqtSignal(dict)
    report = pyqtSignal(dict)

    def __init__(self, comment: dict, *, me_id: str = "", post_link: str = "",
                 depth: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CommentItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._comment = dict(comment or {})
        self._me_id = str(me_id or "")
        self._post_link = post_link or ""
        self._depth = depth
        self._liked = bool(self._comment.get("liked"))

        root = vbox(self, margins=(0, 4, 0, 4), spacing=2)
        row = hbox(spacing=8)

        self.avatar = Avatar(28 if depth == 0 else 24)
        self.avatar.clicked.connect(self._on_avatar)
        row.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)

        body = vbox(spacing=3)
        head = hbox(spacing=6)
        self.user = UserLink()
        self.user.activated.connect(self._on_user_link)
        head.addWidget(self.user)
        if self._comment.get("parent_id"):
            reply_tag = QLabel("回复")
            reply_tag.setProperty("muted", "true")
            head.addWidget(reply_tag)
        self.meta = Muted("")
        head.addWidget(self.meta)
        head.addStretch(1)
        body.addLayout(head)

        self.content = QLabel(str(self._comment.get("content") or ""))
        self.content.setWordWrap(True)
        self.content.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        body.addWidget(self.content)

        actions = hbox(spacing=2)
        self.like_btn = button("", "ghost", self._on_like, tooltip="点赞")
        actions.addWidget(self.like_btn)
        self.reply_btn = button("回复", "ghost", self._on_reply)
        actions.addWidget(self.reply_btn)
        self.report_btn = button("举报", "ghost", self._on_report)
        actions.addWidget(self.report_btn)
        self.delete_btn = button("删除", "ghost", self._on_delete)
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        body.addLayout(actions)
        row.addLayout(body, 1)
        root.addLayout(row)

        self._children_box = vbox(spacing=2)
        self._children_box.setContentsMargins(36 if depth == 0 else 24, 0, 0, 0)
        self._children_box_wrap = QWidget(self)
        self._children_box_wrap.setLayout(self._children_box)
        self._children_box_wrap.hide()
        root.addWidget(self._children_box_wrap)

        self._fold_btn = button("", "ghost", self._toggle_fold)
        self._fold_btn.hide()
        fold_row = hbox()
        fold_row.setContentsMargins(36 if depth == 0 else 24, 0, 0, 0)
        fold_row.addWidget(self._fold_btn)
        fold_row.addStretch(1)
        root.addLayout(fold_row)

        self.set_children([])
        self.refresh()

    # ── 数据 ──
    @property
    def comment_id(self) -> str:
        return str(self._comment.get("id") or "")

    @property
    def data(self) -> dict:
        return dict(self._comment)

    def refresh(self) -> None:
        data = self._comment
        self.avatar.set_url(str(data.get("user_avatar") or ""))
        self.user.set_user(str(data.get("user_id") or ""),
                           str(data.get("user_name") or "匿名用户"))
        self.meta.setText("· " + yearmode.fmt_time(data.get("created_at")))
        content = str(data.get("content") or "")
        self.content.setText(content)
        self.content.setVisible(bool(content))
        likes = int(data.get("likes") or 0)
        self.like_btn.setText(("♥ " if self._liked else "♡ ") + str(likes))
        mine = bool(self._me_id) and self._me_id == str(data.get("user_id") or "")
        self.delete_btn.setVisible(mine)
        self.report_btn.setVisible(not mine)

    def set_liked(self, liked: bool, likes: int | None = None) -> None:
        self._liked = bool(liked)
        if likes is not None:
            self._comment["likes"] = int(likes)
        self.refresh()

    # ── 子回复 ──
    def set_children(self, children: list) -> None:
        while self._children_box.count():
            item = self._children_box.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._children = []
        for child in children:
            item = CommentItem(child, me_id=self._me_id,
                               post_link=self._post_link, depth=self._depth + 1)
            self._wire_child(item)
            self._children_box.addWidget(item)
            self._children.append(item)
        count = len(self._children)
        if count:
            self._children_box_wrap.show()
            self._fold_btn.show()
            if count > CHILD_FOLD_THRESHOLD:
                self._children_box_wrap.hide()
                self._fold_btn.setText("展开回复 (%d)" % count)
            else:
                self._fold_btn.setText("收起回复")
        else:
            self._children_box_wrap.hide()
            self._fold_btn.hide()

    def _wire_child(self, item: "CommentItem") -> None:
        item.open_post.connect(self.open_post)
        item.open_user.connect(self.open_user)
        item.reply.connect(self.reply)
        item.like.connect(self.like)
        item.delete.connect(self.delete)
        item.report.connect(self.report)

    def children(self) -> list:
        return list(getattr(self, "_children", []))

    # ── 交互 ──
    def _toggle_fold(self) -> None:
        visible = self._children_box_wrap.isVisible()
        self._children_box_wrap.setVisible(not visible)
        self._fold_btn.setText("收起回复" if not visible
                               else "展开回复 (%d)" % len(self.children()))

    def _on_avatar(self) -> None:
        uid = str(self._comment.get("user_id") or "")
        if uid:
            self.open_user.emit(uid)

    def _on_user_link(self, user_id: str) -> None:
        if user_id:
            self.open_user.emit(user_id)

    def _on_like(self) -> None:
        self.like.emit(self.data)

    def _on_reply(self) -> None:
        self.reply.emit({"id": self.comment_id,
                         "name": str(self._comment.get("user_name") or "")})

    def _on_delete(self) -> None:
        self.delete.emit(self.data)

    def _on_report(self) -> None:
        self.report.emit(self.data)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._post_link:
            self.open_post.emit(self._post_link)
        event.accept()


class CommentList(QWidget):
    """评论列表：把扁平数组按 ``parent_id`` 组装成楼中楼，支持折叠。"""

    open_post = pyqtSignal(str)
    open_user = pyqtSignal(str)
    reply = pyqtSignal(dict)
    like = pyqtSignal(dict)
    delete = pyqtSignal(dict)
    report = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None, *, fold_roots: int = 5,
                 collapsible: bool = False) -> None:
        super().__init__(parent)
        self._fold_roots = int(fold_roots)
        self._collapsible = bool(collapsible)
        self._expanded = False
        self._roots: list[dict] = []
        self._me_id = ""
        self._post_link = ""
        self._items: list[CommentItem] = []

        self._box = vbox(self, margins=(0, 0, 0, 0), spacing=4)
        self._switch_row = hbox()
        self._switch_btn = button("", "ghost", self._toggle_all)
        self._switch_row.addWidget(self._switch_btn)
        self._switch_row.addStretch(1)
        self._empty = QLabel("还没有评论，来抢沙发吧~")
        self._empty.setObjectName("EmptyHint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # ── 配置 ──
    def set_fold_limit(self, count: int) -> None:
        self._fold_roots = max(0, int(count))
        self._rebuild()

    def set_collapsible(self, enabled: bool) -> None:
        self._collapsible = bool(enabled)
        self._expanded = False
        self._rebuild()

    # ── 数据 ──
    def set_comments(self, comments: list, *, me_id: str = "", post_link: str = "",
                     total: int | None = None) -> None:
        self._me_id = str(me_id or "")
        self._post_link = post_link or ""
        self._roots = _build_tree(comments or [])
        self._total = total if total is not None else len(self._roots)
        self._rebuild()

    def _rebuild(self) -> None:
        clear_layout(self._box)
        self._items = []

        roots = self._roots
        if not roots:
            self._empty.setParent(None)
            self._box.addWidget(self._empty)
            self._empty.show()
            return

        shown = roots
        hidden = 0
        if self._collapsible and not self._expanded and self._fold_roots > 0 \
                and len(roots) > self._fold_roots:
            shown = roots[:self._fold_roots]
            hidden = len(roots) - self._fold_roots

        for node in shown:
            item = CommentItem(node, me_id=self._me_id, post_link=self._post_link)
            self._wire(item)
            self._box.addWidget(item)
            self._items.append(item)

        if hidden:
            btn = button("展开全部评论（共 %d 条，还有 %d 条）" % (len(roots), hidden),
                         "ghost", self._toggle_all)
            self._box.addWidget(btn)
        elif self._collapsible and self._expanded and len(roots) > self._fold_roots:
            btn = button("收起评论", "ghost", self._toggle_all)
            self._box.addWidget(btn)

    def _toggle_all(self) -> None:
        self._expanded = not self._expanded
        self._rebuild()

    def _wire(self, item: CommentItem) -> None:
        item.open_post.connect(self.open_post)
        item.open_user.connect(self.open_user)
        item.reply.connect(self.reply)
        item.like.connect(self.like)
        item.delete.connect(self.delete)
        item.report.connect(self.report)

    # ── 查询 ──
    def items(self) -> list[CommentItem]:
        result = list(self._items)
        for item in self._items:
            result.extend(_walk(item))
        return result

    def item_for(self, comment_id: str) -> CommentItem | None:
        for item in self.items():
            if item.comment_id == comment_id:
                return item
        return None

    @property
    def root_count(self) -> int:
        return len(self._roots)


def _walk(item: CommentItem) -> list[CommentItem]:
    out: list[CommentItem] = []
    for child in item.children():
        out.append(child)
        out.extend(_walk(child))
    return out


def _build_tree(comments: list) -> list[dict]:
    """扁平评论 → 树（保持服务端顺序；子回复按时间升序）。"""
    nodes: dict[str, dict] = {}
    order: list[str] = []
    for raw in comments:
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("id") or "")
        if not cid or cid in nodes:
            continue
        node = dict(raw)
        node["children"] = []
        nodes[cid] = node
        order.append(cid)
    roots: list[dict] = []
    for cid in order:
        node = nodes[cid]
        parent_id = str(node.get("parent_id") or "")
        parent = nodes.get(parent_id)
        if parent is not None and parent is not node:
            parent["children"].append(node)
        else:
            roots.append(node)
    for node in nodes.values():
        if node["children"]:
            node["children"].sort(key=lambda c: (yearmode.parse_time(c.get("created_at"))
                                                 or yearmode.parse_time("1970-01-01")))
    # 环状 parent_id（A→B→A）会让所有结点都不是根，评论会整体消失：
    # 把“从根出发不可达”的结点提升为根。
    reachable: set[int] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if id(node) in reachable:
            continue
        reachable.add(id(node))
        stack.extend(node["children"])
    for cid in order:
        node = nodes[cid]
        if id(node) not in reachable:
            roots.append(node)
            reachable.add(id(node))
    _flatten_orphans(roots, nodes)
    return roots


def _flatten_orphans(roots: list, nodes: dict) -> None:
    """处理环状 parent_id（避免评论丢失）。"""
    seen: set[str] = set()

    def visit(node: dict) -> bool:
        key = id(node)
        if key in seen:
            return False
        seen.add(key)
        kept = []
        for child in node.get("children") or []:
            if visit(child):
                kept.append(child)
        node["children"] = kept
        return True

    for root in list(roots):
        visit(root)
