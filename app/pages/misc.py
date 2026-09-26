# -*- coding: utf-8 -*-
"""杂项页面：隐私政策（``privacy``）、会馆列表（``huiguan``）、彩蛋（``easter_egg``）。

数据来源（均为后端杂项接口）：

* ``GET /api/huiguan`` → ``{success, list: [{会馆名称, 馆长在总群的名称, 馆长QQ号,
  会馆QQ号, 馆长个人站点}]}``
* ``GET /Easter-Egg`` → 随机一条 ``{ID, Name, Text}``
* 每日一言接口（:data:`app.constants.SENTENCE_TEXT_URL`）与彩蛋随机轮换展示

约定：

* 可选数据缺失 / 请求失败只给中文提示，页面本身绝不抛异常
* 阻塞请求一律走 :meth:`Page.run`，回调回到主线程
* 后端域名只从 :mod:`app.constants` 取，绝不写死
"""

from __future__ import annotations

import random

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

from .. import constants, logger
from ..widgets import (Card, CardTitle, Divider, Muted, ScrollPage, button, hbox,
                       vbox)
from .base import ListPage, Page

_log = logger.get_logger("misc_pages")

_PRIVACY_PARAGRAPHS = (
    "本论坛为《罗小黑战记》粉丝同人项目，仅用于学习与交流。",
    "我们收集必要的信息（用户名、邮箱）以提供账号服务，不会向第三方出售您的数据。",
    "如有疑问，请联系 3890320020@qq.com。",
)


def _pick(row, *keys) -> str:
    """从字典里按顺序取第一个非空的字段值。"""
    if not isinstance(row, dict):
        return ""
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


class PrivacyPage(Page):
    """隐私政策（路由 ``privacy``，对照 Web 端 ``PrivacyView.vue``）。"""

    ROUTE = "privacy"
    TITLE = "隐私政策"
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        root = vbox(self, margins=(12, 12, 12, 12), spacing=10)
        header, _ = self.make_header("隐私政策", "我们如何对待你的数据")
        root.addWidget(header)

        scroll = ScrollPage(self, spacing=12)
        root.addWidget(scroll, 1)

        card = Card()
        card.body.addWidget(CardTitle("隐私政策"))
        for paragraph in _PRIVACY_PARAGRAPHS:
            label = Muted(paragraph)
            label.setWordWrap(True)
            card.body.addWidget(label)
        card.body.addWidget(Divider())
        note = Muted("本页说明与网页版一致；如需删除账号或数据，请通过上方邮箱联系我们。")
        note.setWordWrap(True)
        card.body.addWidget(note)
        scroll.add(card)


class HuiguanPage(ListPage):
    """会馆列表（路由 ``huiguan``，数据源 ``GET /api/huiguan``）。"""

    ROUTE = "huiguan"
    TITLE = "会馆"
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell=shell, parent=parent,
                         empty_text="暂无会馆信息", spacing=10)
        self._busy = False
        self._loaded = False

        head, _ = self.make_header("会馆", "妖灵会馆名单与联系方式")
        head.actions.addWidget(button("刷新", "ghost",
                                      lambda _=False: self.reload()))
        self.header_layout.addWidget(head)

        self.more_btn.hide()
        self.scroll.set_load_more_enabled(False)

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, **kwargs) -> None:
        super().on_show(**kwargs)
        if not self._loaded or not self.item_count():
            self.reload()

    # ────────────────────── 加载 ──────────────────────
    def reload(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.clear_items()
        self.set_has_more(False)
        self.set_loading(True, "正在加载会馆列表…")
        self.run(lambda: self.api.huiguan(),
                 self._on_loaded, self._on_failed, label="会馆列表")

    def _on_loaded(self, result) -> None:
        self._busy = False
        self.set_loading(False)
        rows = self._rows(result)
        if rows:
            for row in rows:
                self.add_item(self._card(row))
            self._loaded = True
            self.set_empty(visible=False)
            return
        self._loaded = False
        text = "暂无会馆信息" if result.ok else (result.message
                                              or "会馆列表加载失败")
        self.set_empty(text, visible=True)

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self._loaded = False
        self.set_loading(False)
        self.set_empty(message or "会馆列表加载失败，请稍后重试。", visible=True)

    # ────────────────────── 渲染 ──────────────────────
    @staticmethod
    def _rows(result) -> list:
        rows = result.rows("list")
        if rows:
            return rows
        inner = result.get("data")
        if isinstance(inner, dict):
            nested = inner.get("list")
            if isinstance(nested, list):
                return nested
        if isinstance(inner, list):
            return inner
        return []

    def _card(self, row) -> Card:
        card = Card()
        name = _pick(row, "会馆名称", "名称", "name") or "未命名会馆"
        card.body.addWidget(CardTitle(name))

        keeper = _pick(row, "馆长在总群的名称", "馆长名称", "owner_name")
        if keeper:
            card.body.addWidget(self._line("馆长", keeper))
        owner_qq = _pick(row, "馆长QQ号", "馆长QQ", "owner_qq")
        if owner_qq:
            card.body.addWidget(self._line("馆长 QQ", owner_qq))
        group_qq = _pick(row, "会馆QQ号", "会馆QQ", "qq")
        if group_qq:
            card.body.addWidget(self._line("会馆 QQ", group_qq))

        site = _pick(row, "馆长个人站点", "个人站点", "site", "url")
        if site:
            line = hbox(spacing=8)
            line.addWidget(Muted("个人站点"))
            line.addWidget(button(site, "ghost",
                                  lambda _=False, u=site: self._open_site(u)))
            line.addStretch(1)
            card.body.addLayout(line)
        return card

    @staticmethod
    def _line(label_text: str, value: str) -> QWidget:
        box = QWidget()
        row = hbox(box, spacing=8)
        row.addWidget(Muted(label_text))
        value_label = QLabel(value)
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(value_label)
        row.addStretch(1)
        return box

    def _open_site(self, url: str) -> None:
        target = str(url or "").strip()
        if not target:
            return
        if not target.lower().startswith(("http://", "https://")):
            target = "https://" + target
        self.open_link(target)


class EasterEggPage(Page):
    """彩蛋（路由 ``easter_egg``，数据源 ``GET /Easter-Egg``）。

    进入方式：左侧导航 / 深链 ``Crforum://easter_egg`` / 站内 ``/INFO*``
    都会带 ``play=True``；页面上的「再来一个彩蛋」随时可以再抽一条。
    """

    ROUTE = "easter_egg"
    TITLE = "彩蛋"
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._busy = False

        root = vbox(self, margins=(12, 12, 12, 12), spacing=10)
        header, _ = self.make_header("彩蛋", "点一下，看看会掉出什么")
        root.addWidget(header)

        scroll = ScrollPage(self, spacing=12)
        root.addWidget(scroll, 1)

        card = Card()
        card.body.addWidget(CardTitle("今日彩蛋"))
        self._result = QLabel("点下面的按钮抽一条彩蛋。")
        self._result.setWordWrap(True)
        self._result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._result.setAlignment(Qt.AlignmentFlag.AlignLeft
                                  | Qt.AlignmentFlag.AlignTop)
        self._result.setMinimumHeight(90)
        card.body.addWidget(self._result)

        self._play_btn = button("🎁 再来一个彩蛋", "primary",
                                lambda _=False: self._play_once())
        self._play_btn.setMinimumHeight(44)
        card.body.addWidget(self._play_btn)

        card.body.addWidget(Divider())
        card.body.addWidget(Muted("每次点击会随机奉上一条彩蛋或每日一言。"))
        scroll.add(card)

        links = Card()
        links.body.addWidget(CardTitle("顺路看看"))
        row = hbox(spacing=8)
        row.addWidget(button("会馆列表", "ghost",
                             lambda _=False: self.go("huiguan")))
        row.addWidget(button("隐私政策", "ghost",
                             lambda _=False: self.go("privacy")))
        row.addWidget(button("打开 WIKI", "ghost",
                             lambda _=False: self.go("wiki")))
        row.addWidget(button("反馈 Bug", "ghost",
                             lambda _=False: self.bug_report()))
        row.addStretch(1)
        links.body.addLayout(row)
        scroll.add(links)

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, play: bool = False, **kwargs) -> None:
        super().on_show(**kwargs)
        if play:
            self._play_once()

    # ────────────────────── 抽取 ──────────────────────
    def _play_once(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_busy(True)
        self._set_result("正在抽取…")
        self.run(self._fetch, self._finish, self._fail, label="彩蛋")

    def _set_busy(self, busy: bool) -> None:
        try:
            self._play_btn.setEnabled(not busy)
        except RuntimeError:
            pass

    def _set_result(self, text: str) -> None:
        try:
            self._result.setText(text)
        except RuntimeError:
            pass

    def _finish(self, text) -> None:
        self._busy = False
        self._set_busy(False)
        message = str(text or "").strip()
        if not message:
            self._set_result("这次什么也没抽到，稍后再试试吧。")
            self.toast("彩蛋获取失败，请稍后再试")
            return
        self._set_result(message)
        self.toast("🎁 彩蛋已奉上")

    def _fail(self, message: str) -> None:
        self._busy = False
        self._set_busy(False)
        self._set_result("彩蛋获取失败：%s" % (message or "请稍后再试"))

    # ────────────────────── 后台取数（工作线程）──────────────────────
    def _fetch(self) -> str:
        """随机从「彩蛋」或「每日一言」取一条；任一来源失败就换另一个。"""
        if random.random() < 0.5:
            return self._fetch_egg() or self._fetch_sentence()
        return self._fetch_sentence() or self._fetch_egg()

    def _fetch_egg(self) -> str:
        """向 ``/Easter-Egg`` 要一条彩蛋，拿不到返回空串。"""
        result = None
        try:
            result = self.api.easter_egg()
        except Exception as exc:  # noqa: BLE001
            _log.warning("彩蛋请求失败：%s", exc)
        if result is not None and result.ok:
            return self._format_egg(self._egg_item(result.data))
        return ""

    def _fetch_sentence(self) -> str:
        try:
            text = str(self.api.fetch_text(
                constants.SENTENCE_TEXT_URL) or "").strip()
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            return "📝 %s" % text
        try:
            data = self.api.fetch_json(constants.SENTENCE_JSON_URL)
        except Exception:  # noqa: BLE001
            data = None
        return self._format_sentence(data)

    @staticmethod
    def _format_sentence(data) -> str:
        if not isinstance(data, dict):
            return ""
        text = str(data.get("text") or data.get("hitokoto") or "").strip()
        if not text:
            return ""
        author = str(data.get("from_who") or data.get("author") or "").strip()
        source = str(data.get("from") or data.get("source") or "").strip()
        suffix = ""
        if author:
            suffix += " —— %s" % author
        if source:
            suffix += " 《%s》" % source
        return "📝 %s%s" % (text, suffix)

    @staticmethod
    def _format_egg(item) -> str:
        if not isinstance(item, dict):
            return ""
        name = str(item.get("Name") or item.get("name") or "").strip()
        text = str(item.get("Text") or item.get("text") or "").strip()
        for br in ("<br />", "<br/>", "<BR>", "<br>"):
            text = text.replace(br, "\n")
        if name and text:
            return "🎁 %s\n\n%s" % (name, text)
        if text:
            return "🎁 %s" % text
        if name:
            return "🎁 %s" % name
        return ""

    @staticmethod
    def _egg_item(data):
        """把包装层（``{success}`` / ``{data}``）剥掉，拿到那一条彩蛋。"""
        if isinstance(data, dict):
            for key in ("Text", "text", "Name", "name", "ID"):
                if key in data:
                    return data
            for key in ("data", "item", "egg", "list", "result"):
                value = data.get(key)
                if isinstance(value, dict):
                    return value
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return None
