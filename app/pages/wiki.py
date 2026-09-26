# -*- coding: utf-8 -*-
"""WIKI 页（``wiki`` 路由）：《罗小黑战记》资料馆。

子栏目由 ``on_show(kind=...)`` 切换，与 :meth:`app.shell.Shell.handle_internal_url`
里 ``/WIKI/*`` 的映射一一对应：

* ``overview``    总览：官方 / 个人 两张入口卡
* ``official``    官方内容（因为版权问题无法发布）
* ``personal``    个人开发：鼠标指针 / Live2D
* ``mouse``       罗小黑战记鼠标（Linux 版入口）
* ``mouse_linux`` Linux 版：下载 zip + README + 致谢
* ``live2d``      Live2D 动作示例（GIF + 原作者）

实现要点：

* 下载 / 取图 / 取文本都走异步回调，回调里先比对构建令牌，避免快速切换
  子栏目时把内容写进已经销毁的控件
* 下载进度回调发生在工作线程，统一用 :class:`_ProgressBridge` 信号
  （队列连接）转回主线程，不直接碰控件
* 动图用 ``QMovie`` 播放，控件销毁前必须停掉，否则定时器空转
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import QLabel, QProgressBar, QWidget

from .. import constants, logger, paths, theme, util
from ..widgets import (AsyncImage, Card, CardTitle, MarkdownView, Muted,
                       ScrollPage, button, hbox, vbox)
from ..widgets.images import image_cache
from .base import Page

_log = logger.get_logger("wiki_page")

_MAX_IMAGE_WIDTH = 420
_MOVIE_MAX = 260

_KIND_TITLES = {
    "overview": ("WIKI", "罗小黑战记 Wiki · 资料与个人作品"),
    "official": ("罗小黑战记官方", "官方发布的内容信息"),
    "personal": ("罗小黑战记个人开发", "用户分享的个人创作"),
    "mouse": ("罗小黑战记鼠标", "自定义鼠标指针包"),
    "mouse_linux": ("罗小黑战记鼠标 - Linux 版", "罗小黑战记鼠标 Linux版.zip"),
    "live2d": ("罗小黑 Live2D 模型", "原作者：%s" % constants.LIVE2D_AUTHOR),
}


class _LinkCard(Card):
    """整卡可点击的入口卡。

    ``AsyncImage.set_local`` 不会设置 ``_url``，所以它的 ``clicked`` 永远不发信号，
    卡片整体的点击单独用 ``mouseReleaseEvent`` 实现。
    """

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class _Warning(QLabel):
    """红色警示文字（颜色取当前主题的 danger，跟随主题切换）。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.reload_theme()

    def reload_theme(self) -> None:
        try:
            color = str(theme.palette().get("danger") or "")
        except Exception:  # noqa: BLE001 - 主题不可用时保持默认色
            color = ""
        self.setStyleSheet("color: %s;" % color if color else "")


class _ProgressBridge(QObject):
    """把工作线程里的下载进度回调转回主线程（控件不可跨线程访问）。"""

    progress = pyqtSignal(int, int)  # (已完成字节, 总字节；0 表示未知)


class WikiPage(Page):
    """WIKI 页（路由 ``wiki``，``on_show(kind="overview")``）。"""

    ROUTE = "wiki"
    TITLE = "WIKI"
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._kind = ""                 # 空字符串 = 尚未构建
        self._build_token = 0           # 子栏目重建计数（旧回调直接丢弃）
        self._download_token = 0        # 下载任务计数
        self._movies: list[QMovie] = []
        self._dl_target = ""

        root = vbox(self, margins=(12, 12, 12, 12), spacing=10)
        self.scroll = ScrollPage(self, spacing=12)
        self.scroll.set_load_more_enabled(False)
        root.addWidget(self.scroll, 1)

    # ── 生命周期 ──
    def on_show(self, kind: str = "overview", **kwargs) -> None:
        super().on_show(**kwargs)
        kind = str(kind or "overview")
        if kind not in _KIND_TITLES:
            _log.debug("WIKI 未知子栏目 %s，回退到总览", kind)
            kind = "overview"
        if kind == self._kind:
            return
        self._kind = kind
        self._build()

    def on_hide(self) -> None:
        self._stop_movies()
        super().on_hide()

    # ── 构建 ──
    def _build(self) -> None:
        """重建当前子栏目内容。"""
        self._build_token += 1
        self._download_token += 1
        token = self._build_token
        self._stop_movies()
        try:
            self.scroll.clear()
        except Exception as exc:  # noqa: BLE001
            _log.warning("WIKI 清空旧内容失败：%s", exc)

        title, subtitle = _KIND_TITLES.get(self._kind, _KIND_TITLES["overview"])
        header, box = self.make_header(title, subtitle)
        if self._kind != "overview":
            header.actions.addWidget(button(
                "‹ 返回 WIKI", "ghost",
                lambda _=False: self.go("wiki", kind="overview")))
        self.scroll.add(header)

        builder = getattr(self, "_build_" + self._kind, None)
        if not callable(builder):
            self.scroll.add(Muted("该栏目还在建设中…"))
            return
        try:
            builder(token)
        except Exception as exc:  # noqa: BLE001 - 单个子栏目出错不能连带整个页面
            _log.error("WIKI 子栏目 %s 构建失败：%s", self._kind, exc, exc_info=True)
            try:
                self.scroll.add(Muted("内容加载失败：%s" % exc))
            except Exception:  # noqa: BLE001
                pass

    def _stop_movies(self) -> None:
        for movie in self._movies:
            try:
                movie.stop()
            except RuntimeError:
                pass
        self._movies = []

    # ── 总览 ──
    def _build_overview(self, token: int) -> None:
        self.scroll.add(self._entry_card(
            "官方", "官方发布的内容信息",
            str(constants.RES_WIKI_OFFICIAL), "official"))
        self.scroll.add(self._entry_card(
            "个人", "用户分享的个人创作",
            str(constants.RES_WIKI_PERSONAL), "personal"))
        self.scroll.add(self._footer("更多内容持续更新中…"))

    def _entry_card(self, title: str, desc: str, cover: str, kind: str) -> Card:
        card = _LinkCard()
        card.clicked.connect(lambda k=kind: self.go("wiki", kind=k))
        card.body.addWidget(CardTitle(title))
        if desc:
            card.body.addWidget(Muted(desc))
        image = AsyncImage(max_width=_MAX_IMAGE_WIDTH)
        if cover and Path(cover).is_file():
            image.set_local(cover)
        else:
            image.setText("封面缺失")
        card.body.addWidget(image)
        card.body.addWidget(button("查看详情 →", "ghost",
                                   lambda _=False, k=kind: self.go("wiki", kind=k)))
        return card

    def _footer(self, text: str) -> QLabel:
        label = Muted(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    # ── 官方 / 个人 / 鼠标 ──
    def _build_official(self, token: int) -> None:
        card = Card()
        card.body.addWidget(CardTitle("罗小黑战记官方"))
        card.body.addWidget(_Warning("因为版权问题无法发布"))
        card.body.addWidget(Muted("官方资料受版权限制，暂不提供下载与转载。"))
        self.scroll.add(card)
        self.scroll.add(self._footer("更多内容持续更新中…"))

    def _build_personal(self, token: int) -> None:
        self.scroll.add(_Warning("未经授权禁止商用！！"))
        self.scroll.add(self._entry_card(
            "罗小黑战记鼠标", "自定义鼠标指针包",
            str(constants.RES_MOUSE_BANNER), "mouse"))
        self.scroll.add(self._entry_card(
            "罗小黑Live2D模型（不可下载）", "动作示例与原作者信息",
            "", "live2d"))
        self.scroll.add(self._footer("更多内容持续更新中…"))

    def _build_mouse(self, token: int) -> None:
        self.scroll.add(_Warning("未经授权禁止商用！！"))
        self.scroll.add(self._entry_card(
            "Liunx 版", "罗小黑战记鼠标 Linux版",
            str(constants.RES_MOUSE_BANNER), "mouse_linux"))
        self.scroll.add(self._footer("更多内容持续更新中…"))

    # ── Live2D 动作示例 ──
    def _build_live2d(self, token: int) -> None:
        intro = Card()
        intro.body.addWidget(CardTitle("罗小黑Live2D模型"))
        intro.body.addWidget(_Warning("不可下载，仅供展示"))
        intro.body.addWidget(Muted("模型与动作版权归原作者所有，本页仅做预览。"))
        self.scroll.add(intro)

        author = Card()
        author.body.addWidget(Muted("Live2D 模型原作者"))
        row = hbox(spacing=8)
        row.addWidget(QLabel(constants.LIVE2D_AUTHOR))
        row.addStretch(1)
        row.addWidget(button(
            "查看Ta的主页 →", "ghost",
            lambda _=False: self._open_external(constants.LIVE2D_AUTHOR_URL)))
        author.body.addLayout(row)
        author.body.addWidget(Muted("在小红书收获了 199.2K 次赞与收藏"))
        self.scroll.add(author)

        self.scroll.add(CardTitle("动作示例"))
        for name, remote in constants.LIVE2D_GIFS:
            self.scroll.add(self._gif_box(name, remote, token))
        self.scroll.add(self._footer("点击模型可以互动哦~"))

    def _open_external(self, url: str) -> None:
        """外链统一走确认弹窗（与正文链接同一套安全策略）。"""
        try:
            self.open_link(url)
        except Exception as exc:  # noqa: BLE001
            _log.warning("打开外链失败：%s", exc)

    def _gif_box(self, name: str, remote: str, token: int) -> Card:
        card = Card()
        card.body.addWidget(CardTitle(name))
        holder = QLabel("动图加载中…")
        holder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        holder.setMinimumHeight(160)
        card.body.addWidget(holder)

        url = constants.absolute(remote)
        local = image_cache.local(url)
        if local:
            self._start_movie(holder, local, token)
            return card

        def _ok(_url, path, t=token):
            if t != self._build_token:
                return
            self._start_movie(holder, str(path), t)

        def _fail(_message, t=token):
            if t != self._build_token:
                return
            try:
                holder.setText("动图加载失败")
            except RuntimeError:
                pass

        image_cache.fetch(url, on_ready=_ok, on_error=_fail)
        return card

    def _start_movie(self, holder: QLabel, path: str, token: int) -> None:
        if token != self._build_token:
            return
        try:
            movie = QMovie(path)
            if not movie.isValid():
                holder.setText("动图不可用")
                return
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            movie.setScaledSize(self._movie_size(movie))
            holder.setMovie(movie)
            holder.setText("")
            movie.setParent(holder)
            self._movies.append(movie)
            movie.start()
        except Exception as exc:  # noqa: BLE001
            _log.debug("Live2D 动图加载失败：%s", exc)
            try:
                holder.setText("动图不可用")
            except RuntimeError:
                pass

    @staticmethod
    def _movie_size(movie: QMovie) -> QSize:
        """按首帧比例缩放到 _MOVIE_MAX 以内（失败时回退正方形）。"""
        try:
            movie.jumpToFrame(0)
            frame = movie.currentPixmap()
            if not frame.isNull() and frame.width() > 0 and frame.height() > 0:
                size = frame.size()
                size.scale(_MOVIE_MAX, _MOVIE_MAX, Qt.AspectRatioMode.KeepAspectRatio)
                return size
        except Exception:  # noqa: BLE001
            pass
        return QSize(_MOVIE_MAX, _MOVIE_MAX)

    # ── 鼠标 Linux 版 ──
    def _build_mouse_linux(self, token: int) -> None:
        self.scroll.add(_Warning("未经授权禁止商用！！"))

        download = Card()
        download.body.addWidget(CardTitle("下载鼠标包"))
        download.body.addWidget(Muted("罗小黑战记鼠标 Linux版.zip"))
        bar = QProgressBar()
        bar.setVisible(False)
        download.body.addWidget(bar)
        path_label = Muted("")
        download.body.addWidget(path_label)
        btn = button("开始下载", "primary")
        folder_btn = button("打开文件夹", "ghost")
        folder_btn.setVisible(False)
        row = hbox(spacing=8)
        row.addWidget(btn)
        row.addWidget(folder_btn)
        row.addStretch(1)
        download.body.addLayout(row)
        btn.clicked.connect(lambda _=False: self._download_mouse_zip(
            token, btn, bar, path_label, folder_btn))
        folder_btn.clicked.connect(lambda _=False: self._reveal_download())
        self.scroll.add(download)

        readme = Card()
        readme.body.addWidget(CardTitle("使用说明（README）"))
        view = MarkdownView(min_height=180, max_height=460)
        view.link_clicked.connect(self._open_external)
        view.set_markdown("使用说明加载中…")
        readme.body.addWidget(view)
        self.scroll.add(readme)
        self._load_readme(view, token)

        credits = Card()
        credits.body.addWidget(CardTitle("致谢与来源"))
        credits.body.addWidget(Muted("移植者：%s" % constants.MOUSE_LINUX_AUTHOR))
        credits_view = MarkdownView(min_height=120, max_height=320)
        credits_view.link_clicked.connect(self._open_external)
        credits_view.set_markdown(self._local_text(constants.RES_MOUSE_CREDITS)
                                  or "暂无致谢信息。")
        credits.body.addWidget(credits_view)
        source_row = hbox(spacing=8)
        source_row.addWidget(button(
            "查看原帖 →", "ghost",
            lambda _=False: self._open_external(constants.MOUSE_LINUX_SOURCE)))
        source_row.addStretch(1)
        credits.body.addLayout(source_row)
        self.scroll.add(credits)
        self.scroll.add(self._footer("更多内容持续更新中…"))

    # ── 鼠标包下载 ──
    @staticmethod
    def _zip_target() -> Path:
        return paths.data_dir() / "downloads" / "罗小黑战记鼠标Linux版.zip"

    @staticmethod
    def _local_text(path) -> str:
        """读取本地 Markdown（小文件，直接同步读即可）。"""
        try:
            target = Path(path)
            if target.is_file():
                return target.read_text(encoding="utf-8")
        except OSError as exc:
            _log.debug("读取本地文本失败：%s", exc)
        return ""

    def _load_readme(self, view: MarkdownView, token: int) -> None:
        def _ok(text, t=token):
            if t != self._build_token:
                return
            try:
                view.set_markdown(str(text or "").strip()
                                  or "README 加载失败，请稍后重试。")
            except RuntimeError:
                pass

        def _fail(_message, t=token):
            if t != self._build_token:
                return
            try:
                view.set_markdown("README 加载失败，请稍后重试。")
            except RuntimeError:
                pass

        self.run(
            lambda: self.api.fetch_text(
                constants.absolute(constants.REMOTE_MOUSE_README)),
            _ok, _fail, label="鼠标 README")

    def _reveal_download(self) -> None:
        target = self._dl_target or str(self._zip_target())
        try:
            if not util.reveal_in_explorer(target):
                self.toast("未找到下载文件，请先下载")
        except Exception as exc:  # noqa: BLE001
            _log.warning("打开下载目录失败：%s", exc)
            self.toast("打开失败")

    def _download_mouse_zip(self, token: int, btn, bar: QProgressBar,
                            path_label, folder_btn) -> None:
        """流式下载鼠标包；进度由工作线程经信号回到主线程。"""
        if token != self._build_token:
            return
        target = self._zip_target()
        try:
            if not btn.isEnabled():
                self.toast("正在下载中，请稍候")
                return
            btn.setEnabled(False)
            btn.setText("下载中…")
            bar.setMaximum(0)
            bar.setFormat("准备下载…")
            bar.setVisible(True)
            path_label.setText("")
        except RuntimeError:
            return

        self._download_token += 1
        my = self._download_token
        bridge = _ProgressBridge(self)
        bridge.progress.connect(
            lambda done, total, tk=my, widget=bar: self._on_dl_progress(
                tk, done, total, widget))

        def _on_progress(done, total):
            bridge.progress.emit(int(done), int(total))

        def _restore_button() -> None:
            try:
                btn.setEnabled(True)
                btn.setText("重新下载")
            except RuntimeError:
                pass

        def _done(result) -> None:
            if my != self._download_token or token != self._build_token:
                return
            _restore_button()
            if result.ok:
                saved = str(result.get("path") or target)
                self._dl_target = saved
                try:
                    bar.setMaximum(100)
                    bar.setValue(100)
                    bar.setFormat("已完成")
                    path_label.setText("已保存到：%s" % saved)
                    folder_btn.setVisible(True)
                except RuntimeError:
                    pass
                self.toast("下载完成")
            else:
                try:
                    bar.setVisible(False)
                except RuntimeError:
                    pass
                self.toast(result.message or "下载失败")

        def _fail(message: str) -> None:
            if my != self._download_token or token != self._build_token:
                return
            _restore_button()
            try:
                bar.setVisible(False)
            except RuntimeError:
                pass
            self.toast(message)

        self.run(
            lambda: self.api.download(
                constants.absolute(constants.REMOTE_MOUSE_ZIP), target,
                on_progress=_on_progress),
            _done, _fail, label="下载鼠标包")

    def _on_dl_progress(self, token: int, done: int, total: int,
                        bar: QProgressBar) -> None:
        """主线程里刷新进度条（工作线程不得直接碰控件）。"""
        if token != self._download_token:
            return
        try:
            if total > 0:
                bar.setMaximum(100)
                bar.setValue(int(done * 100 // total))
                bar.setFormat("%s / %s" % (util.human_size(done),
                                          util.human_size(total)))
            else:
                bar.setMaximum(0)
                bar.setFormat("已下载 %s" % util.human_size(done))
        except RuntimeError:
            return


