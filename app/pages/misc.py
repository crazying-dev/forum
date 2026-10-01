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

# 隐私政策完整版 v2.0（三端唯一真源：forum/.git/_privacy_policy_v2.md）。
# 仅取 [通用] + [WIN] 段落，丢弃 [WEB] / [ANDROID]；Markdown 表格已改成
# 「· 名称 — 用途」逐行纯文本（PyQt6 QLabel 不渲染表格语法）。
_PRIVACY_TITLE = "妖精论坛 隐私政策"
_PRIVACY_META = ("生效日期：2026 年 10 月 1 日　|　最近更新：2026 年 10 月 1 日"
                 "　|　版本：2.0")

# (kind, text)：kind ∈ {"h2", "h3", "p", "li"}
_PRIVACY_BLOCKS = (
    ("p", _PRIVACY_META),

    ("h2", "引言与适用范围"),
    ("p", "「妖精论坛」（以下简称「本论坛」）是《罗小黑战记》的粉丝非官方二创项目，"
          "由个人开发者以公益、非营利方式运营，不隶属于任何官方机构，也不进行任何商业变现。"),
    ("p", "我们深知个人信息对你的重要性，并将按照《中华人民共和国个人信息保护法》"
          "《中华人民共和国网络安全法》《信息安全技术 个人信息安全规范》等法律法规与"
          "国家标准的要求，采取相应的安全保护措施保护你的个人信息。"),
    ("p", "本政策适用于以下三端产品："),
    ("li", "1. 网页端：crazying-dev.top 及其子域下的全部页面；"),
    ("li", "2. Windows 桌面客户端（CrForum，妖精论坛 Windows 版）；"),
    ("li", "3. Android 客户端（妖精论坛 Android 版）。"),
    ("p", "本政策不适用于通过本论坛跳转的第三方网站或服务（如 GitHub、哔哩哔哩、"
          "小红书等），它们的信息处理行为适用其各自的隐私政策。"),
    ("p", "请你在使用本论坛前仔细阅读并充分理解本政策。当你注册账号、登录或继续使用"
          "本论坛服务时，即表示你已同意本政策。"),

    ("h2", "一、我们收集哪些个人信息"),
    ("p", "我们遵循「最小必要」原则，仅收集实现产品功能所必需的信息："),
    ("li", "· 账号信息 — 用户名、密码（仅保存 PBKDF2 加盐哈希，不保存明文）、"
           "邮箱地址；场景：注册、登录、找回密码；必需。"),
    ("li", "· 邮箱验证码 — 6 位数字验证码；场景：注册验证、修改密码、换绑邮箱、"
           "注销账号；必需。"),
    ("li", "· 个人资料 — 头像图片、性别、出生日期、个性签名、称号；"
           "场景：你主动在「编辑资料」中填写；非必需。"),
    ("li", "· 你发布的内容 — 帖子标题与正文、评论、图片外链、世界频道消息；"
           "场景：你主动发布；非必需。"),
    ("li", "· 互动记录 — 点赞、收藏、关注、举报记录；场景：你主动操作；非必需。"),
    ("li", "· 第三方账号标识 — GitHub OAuth 返回的第三方用户 ID 与昵称；"
           "场景：你选择「使用 GitHub 登录」；非必需。"),
    ("p", "我们不会收集：你的真实姓名、身份证号、手机号、精确地理位置、通讯录、短信、"
          "通话记录、相册全量照片、麦克风/摄像头数据、剪贴板内容、已安装应用列表，"
          "也不会读取你设备上的其他文件。"),

    ("h2", "二、我们如何使用你的个人信息"),
    ("li", "1. 提供账号服务：注册、登录、找回/修改密码、换绑邮箱、注销账号；"),
    ("li", "2. 提供社区功能：发布与展示帖子、评论、世界频道消息，展示互动状态与回复关系；"),
    ("li", "3. 安全与风控：邮箱验证、验证码校验、接口频率限制、举报处理、封禁违规账号；"),
    ("li", "4. 保障服务运行：排查故障、统计帖子浏览量（仅在服务端计数，不含任何用户标识）。"),
    ("p", "我们不会："),
    ("li", "- 将你的个人信息用于广告推送、用户画像或自动化决策；"),
    ("li", "- 将你的个人信息出售、出租或以其他方式提供给任何第三方；"),
    ("li", "- 将你的个人信息用于本政策未载明的其他目的。"),
    ("p", "如确需将信息用于本政策未载明的其他用途，我们会再次征得你的单独同意。"),

    ("h2", "三、Cookie 与本地存储"),
    ("h3", "3.1 Windows 客户端"),
    ("p", "数据根目录：%USERPROFILE%\\.Cr\\forum\\"),
    ("li", "· config.json — 界面偏好（主题、窗口尺寸等）；仅存本机"),
    ("li", "· account.bin — 登录凭证；使用本机指纹派生的密钥加密后存储"),
    ("li", "· cache/avatar/、cache/image/ — 头像与图片缓存；仅存本机，可随时删除"),
    ("li", "· cache/post/ — 帖子正文与元数据缓存；最多 300 条"),
    ("li", "· logs/ — 客户端运行日志；仅保留最近 14 天，不含密码"),
    ("li", "· update/、tmp/ — 更新包与临时文件；仅存本机"),
    ("p", "注册表项（均可在设置中关闭或还原）："),
    ("li", "· HKCU\\...\\Run\\CrForum — 开机自启动（非必需）"),
    ("li", "· HKCU\\Control Panel\\Cursors — 自定义鼠标指针（非必需）"),
    ("li", "· HKCU\\Software\\Classes\\Crforum — 注册 crforum:// 协议（非必需）"),

    ("h2", "四、第三方服务与信息共享"),
    ("p", "为向你提供服务，本论坛在你的设备或请求链路中会触达以下第三方域名/服务："),
    ("li", "· cdn.jsdelivr.net（jsDelivr）— 加载 Font Awesome 图标字体（触达端：网页）"),
    ("li", "· dlystc.unknownmp.top — 第三方「每日一言」接口，首页展示每日一句"
           "（仅文本）（触达端：网页）"),
    ("li", "· img.crazying-dev.top — 本项目自建图床，加载赞赏码图片（触达端：三端）"),
    ("li", "· qm.qq.com（腾讯 QQ）— 「加入 QQ 群」按钮跳转（触达端：网页）"),
    ("li", "· github.com / *.githubusercontent.com / *.githubassets.com — "
           "检查更新、下载新版安装包、查看项目主页（触达端：三端）"),
    ("li", "· ghproxy.net / gh-proxy.com / ghfast.top — 第三方 GitHub 加速镜像，"
           "直连 GitHub 失败时下载更新包（触达端：三端）"),
    ("li", "· dns.alidns.com / doh.pub / cloudflare-dns.com / dns.google — "
           "仅用于解析 github.com 等域名（应对 DNS 污染）（触达端：Windows）"),
    ("li", "· smtp.163.com（网易 163 邮箱）— 发送注册、改密、换绑、注销等验证码邮件"
           "（触达端：服务端）"),
    ("li", "· localhost（本机回环）— GitHub OAuth 授权回调（触达端：Windows）"),
    ("p", "我们不会向上述第三方提供你的账号信息；上述请求仅携带实现该功能所必需的参数"
          "（如文件名、帖子 ID）。"),
    ("p", "法定披露：只有在法律法规要求，或司法机关、行政机关依法定程序提出要求时，"
          "我们才会提供必要的信息。"),

    ("h2", "五、信息的存储与保存期限"),
    ("p", "存储位置：本论坛的服务器位于中华人民共和国境内。除服务器所在云服务商外，"
          "我们不向境外提供你的个人信息。"),
    ("p", "我们遵循最短必要原则，保存期限如下："),
    ("li", "· 账号信息（用户名、邮箱、密码哈希）— 自注销之日起删除；选择「匿名化保留」"
           "则仅保留无法识别到你本人的脱敏记录"),
    ("li", "· 帖子与评论 — 你主动删除或注销账号时删除；「匿名化保留」模式下保留正文"
           "但去除可识别身份"),
    ("li", "· 世界频道消息 — 仅保留最近 1000 条，超出后自动滚动删除"),
    ("li", "· 邮箱验证码 — 5 分钟，超时自动失效"),
    ("li", "· 邮箱验证链接 — 30 分钟，超时自动失效"),
    ("li", "· 登录凭证 — 7 天，到期自动失效"),
    ("li", "· 举报记录 — 用于风控与违规处理，保留至处理完毕后的合理期限"),
    ("li", "· 服务端访问日志 — 仅用于故障排查与安全审计，滚动覆盖"),

    ("h2", "六、我们如何保护你的信息"),
    ("li", "- 密码使用 PBKDF2 加盐哈希存储，任何人（包括管理员）都无法还原出明文；"),
    ("li", "- 传输过程尽可能使用 HTTPS；"),
    ("li", "- 敏感操作（修改密码、换绑邮箱、注销账号）均需邮箱验证码或密码二次验证；"),
    ("li", "- 接口设有频率限制，防止暴力破解与滥用；"),
    ("li", "- 服务端数据库不对外开放。"),
    ("p", "尽管我们已采取上述合理措施，但互联网环境并非绝对安全。请你妥善保管账号密码，"
          "不要与他人共享。"),
    ("p", "请你特别注意：你在帖子、评论、世界频道或个性签名中主动公开的信息，"
          "可能被其他用户或第三方看到、保存、转发，请谨慎发布。"),

    ("h2", "七、未成年人保护"),
    ("p", "本论坛面向一般公众，不专门面向未成年人。如果你是不满 14 周岁的儿童，"
          "请在监护人的陪同下阅读本政策，并在取得监护人同意后使用本论坛。若我们发现"
          "在未事先获得可证实的监护人同意的情况下收集了儿童的个人信息，会设法尽快"
          "删除相关数据。"),

    ("h2", "八、你的权利"),
    ("p", "依据《中华人民共和国个人信息保护法》，你对你的个人信息享有以下权利："),
    ("li", "1. 查阅、复制：登录后进入「个人主页」即可查看你的全部资料与发布内容；"),
    ("li", "2. 更正、补充：在「个人主页 → 编辑资料」中随时修改头像、性别、出生日期、"
           "个性签名；"),
    ("li", "3. 删除：你可以自行删除自己发布的帖子与评论，也可以在"
           "「编辑资料 → 账号安全 → 注销账号」中删除整个账号；"),
    ("li", "4. 注销账号：我们提供真正可用的自助注销入口（「个人主页 → 编辑资料 → "
           "账号安全 → 注销账号」）。注销时你可以选择："),
    ("li", "　　· 彻底删除：删除账号及你发布的全部帖子、评论、点赞、收藏、关注、"
           "举报记录，该操作不可恢复；"),
    ("li", "　　· 匿名化保留：删除邮箱、密码等身份信息，用户名统一显示为"
           "「已注销用户」，历史帖子与评论正文保留但无法再关联到你。"),
    ("li", "　　为保护账号安全，注销前需要通过「账号密码」或「绑定邮箱验证码」"
           "（二选一）验证身份，并输入「注销账号」四字确认。"),
    ("li", "5. 撤回同意：你可以随时停止使用本论坛，并通过上述方式注销账号；"
           "清除浏览器 Cookie 与本地存储可撤回对功能性存储的同意；"),
    ("li", "6. 投诉举报：若你认为你的个人信息权利受到侵害，可通过本政策第十部分的"
           "联系方式与我们联系，我们将在 15 个工作日内答复。"),

    ("h2", "九、本政策的更新"),
    ("p", "我们可能会适时修订本政策。当本政策发生重大变更（例如：收集的个人信息类型"
          "发生变化、使用目的发生变化、对外共享对象发生变化、你行使权利的方式发生变化）"
          "时，我们会在网站首页以显著方式提示，并在你重新登录时再次征得你的同意。"),

    ("h2", "十、联系我们"),
    ("p", "本论坛为个人公益二创项目，未设立专门的个人信息保护负责人，但会以同等谨慎"
          "处理你的请求。"),
    ("li", "· 邮箱：3890320020@qq.com"),
    ("li", "· 项目主页：https://github.com/crazying-dev"),
    ("li", "· 网站：https://crazying-dev.top"),
    ("p", "我们通常会在收到你的请求后 15 个工作日内答复。"),
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
    """隐私政策（路由 ``privacy``，对照三端唯一真源 v2.0 的 [通用] + [WIN] 段）。"""

    ROUTE = "privacy"
    TITLE = "隐私政策"
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        root = vbox(self, margins=(12, 12, 12, 12), spacing=10)
        header, _ = self.make_header("隐私政策", "我们如何对待你的数据")
        root.addWidget(header)

        # QScrollArea：长文不会撑爆窗口；窄窗口下各 QLabel 自动换行
        scroll = ScrollPage(self, spacing=12)
        root.addWidget(scroll, 1)

        card = Card()
        card.body.addWidget(CardTitle(_PRIVACY_TITLE))
        meta = Muted(_PRIVACY_META)
        meta.setWordWrap(True)
        meta.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(meta)
        card.body.addWidget(Divider())

        for kind, text in _PRIVACY_BLOCKS:
            if kind == "h2":
                card.body.addWidget(CardTitle(text))
                continue
            if kind == "h3":
                sub = QLabel(text)
                sub.setStyleSheet("font-weight: 700;")
                sub.setWordWrap(True)
                card.body.addWidget(sub)
                continue
            label = Muted(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            card.body.addWidget(label)
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
