# -*- coding: utf-8 -*-
"""下载页（``download`` 路由）：按平台展示客户端安装包 + 断点续传下载。

* 清单来源：服务端 ``GET /api/app/releases``（见 :mod:`app.releases`）
* 已发布平台给出「下载 / 另存为 / 立即安装 / 打开文件夹」，并实时显示进度 / 速度 / 剩余时间
* 未发布平台（预留位）显示灰化的「即将推出」卡片
* 下载支持断点续传（Range），完成后 Windows 端可「立即安装」
  （走 :func:`app.updater.launch_installer`，开发态会给出中文提示）
* 页面本身绝不抛异常：网络失败只给中文提示，界面永不崩
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFileDialog, QLabel, QProgressBar, QWidget

from .. import constants, logger, paths, releases, updater, util
from ..widgets import (Card, CardTitle, Divider, Muted, ScrollPage, button, chip,
                       clear_layout, hbox, set_active, vbox)
from .base import Page

_log = logger.get_logger("download_page")

# 平台筛选（「全部」+ 四个平台；顺序与 :data:`app.releases.PLATFORM_ORDER` 一致）
_PLATFORM_FILTERS = (("all", "全部"),) + tuple(
    (key, releases.platform_label(key)) for key in releases.PLATFORM_ORDER)


class DownloadPage(Page):
    """下载页（路由 ``download``，数据源 ``GET /api/app/releases``）。"""

    ROUTE = "download"
    TITLE = "下载"
    SHOW_WORLD_PANEL = False
    KEEP_ALIVE = True

    def __init__(self, shell=None, parent: QWidget | None = None) -> None:
        super().__init__(shell, parent)
        self._busy = False
        self._loaded = False
        self._catalog = None
        self._filter = "all"
        self._chip_buttons: dict = {}
        self._cards: list = []            # [(平台 key, 卡片控件)]，用于筛选显隐
        self._progress_ui: dict = {}      # 平台 key → (容器, 进度条, 文案, 安装按钮)
        self._last_download: Path | None = None
        self._dl = {"active": False}

        root = vbox(self, margins=(12, 12, 12, 12), spacing=10)
        header, _ = self.make_header("下载", "客户端安装包与版本发布")
        root.addWidget(header)
        self.scroll = ScrollPage(self, spacing=12)
        root.addWidget(self.scroll, 1)

        self._build_version_card()
        self._build_filter_card()
        self._cards_box = vbox(spacing=12)
        self.scroll.add_layout(self._cards_box)

        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._tick)

    # ────────────────────── 生命周期 ──────────────────────
    def on_show(self, **kwargs) -> None:
        super().on_show(**kwargs)
        if not self._loaded or self._catalog is None:
            self.load(force=False)

    def on_hide(self) -> None:
        super().on_hide()
        try:
            self._timer.stop()
        except RuntimeError:
            pass

    # ────────────────────── 顶部：本机版本 ──────────────────────
    def _build_version_card(self) -> None:
        card = Card()
        card.body.addWidget(CardTitle("本机版本"))
        self._version_label = Muted("当前版本 v%s" % constants.APP_VERSION)
        card.body.addWidget(self._version_label)
        self._state_label = Muted("正在获取发布信息…")
        self._state_label.setWordWrap(True)
        card.body.addWidget(self._state_label)

        row = hbox(spacing=8)
        row.addWidget(button("检查更新", "ghost",
                             lambda _=False: self._check_update()))
        row.addWidget(button("打开发布页", "ghost",
                             lambda _=False: self._open_release_page()))
        row.addWidget(button("刷新", "ghost",
                             lambda _=False: self.load(force=True)))
        row.addStretch(1)
        card.body.addLayout(row)

        card.body.addWidget(Divider())
        note = Muted("安装包按平台分组展示；除 Windows 外的分支为预留位，"
                     "后续上线后会自动出现在这里。")
        note.setWordWrap(True)
        card.body.addWidget(note)
        self.scroll.add(card)

    # ────────────────────── 平台筛选 ──────────────────────
    def _build_filter_card(self) -> None:
        card = Card()
        card.body.addWidget(CardTitle("平台"))
        row = hbox(spacing=6)
        for key, label in _PLATFORM_FILTERS:
            btn = button(label, "chip", lambda _=False, k=key: self._set_filter(k))
            self._chip_buttons[key] = btn
            row.addWidget(btn)
        row.addStretch(1)
        card.body.addLayout(row)
        self.scroll.add(card)
        self._mark_filter()

    def _set_filter(self, key: str) -> None:
        self._filter = key or "all"
        self._mark_filter()
        self._apply_filter()

    def _mark_filter(self) -> None:
        for key, btn in self._chip_buttons.items():
            try:
                set_active(btn, key == self._filter)
            except RuntimeError:
                continue

    def _apply_filter(self) -> None:
        for key, widget in self._cards:
            try:
                widget.setVisible(self._filter in ("all", key))
            except RuntimeError:
                continue

    # ────────────────────── 加载清单 ──────────────────────
    def load(self, *, force: bool = False) -> None:
        if self._busy:
            return
        self._busy = True
        self._state_label.setText("正在获取发布信息…")
        self.run(lambda: releases.platforms(refresh=force),
                 self._on_loaded, self._on_failed, label="发布清单")

    def _on_loaded(self, catalog) -> None:
        self._busy = False
        self._loaded = True
        if catalog is None:
            catalog = releases.platforms()
        self._catalog = catalog
        if getattr(catalog, "known", False):
            self._state_label.setText("发布信息已同步（数据来自服务器）。")
        else:
            self._state_label.setText("暂时无法连接服务器，下方显示内置信息。")
        self._rebuild_cards()

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self._state_label.setText("获取发布信息失败：%s" % (message or "请稍后重试"))
        if not self._cards:
            self._rebuild_cards()

    # ────────────────────── 卡片重建 ──────────────────────
    def _rebuild_cards(self) -> None:
        clear_layout(self._cards_box)
        self._cards = []
        self._progress_ui = {}
        catalog = self._catalog or releases.platforms()
        try:
            infos = catalog.order()
        except Exception as exc:  # noqa: BLE001
            _log.warning("发布清单排序失败：%s", exc)
            infos = list(getattr(catalog, "platforms", {}).values())
        for info in infos:
            try:
                card = self._build_platform_card(info)
            except Exception as exc:  # noqa: BLE001
                _log.warning("构建 %s 平台卡片失败：%s", getattr(info, "key", "?"), exc)
                continue
            self._cards_box.addWidget(card)
            self._cards.append((getattr(info, "key", ""), card))
        if not self._cards:
            hint = Muted("暂无可用的发布信息。")
            hint.setWordWrap(True)
            self._cards_box.addWidget(hint)
        self._apply_filter()

    def _build_platform_card(self, info) -> Card:
        card = Card()
        label = getattr(info, "label", "") or releases.platform_label(info.key)
        card.body.addWidget(CardTitle("%s %s" % (releases.platform_icon(info.key), label)))
        if getattr(info, "available", False):
            self._build_available(card, info)
        else:
            self._build_coming_soon(card, info)
        return card

    def _build_available(self, card: Card, info) -> None:
        release = info.latest
        meta = self._meta_text(release)
        if meta:
            card.body.addWidget(Muted(meta))
        notes = str(getattr(release, "notes", "") or "").strip()
        if notes:
            note = Muted(notes)
            note.setWordWrap(True)
            card.body.addWidget(note)

        row = hbox(spacing=8)
        row.addWidget(button("下载", "primary",
                             lambda _=False, i=info, r=release: self._start_download(i, r)))
        row.addWidget(button("另存为…", "ghost",
                             lambda _=False, i=info, r=release: self._start_download(i, r, save_as=True)))
        row.addWidget(button("打开文件夹", "ghost", lambda _=False: self._open_folder()))
        row.addStretch(1)
        card.body.addLayout(row)

        container = QWidget()
        box = vbox(container, margins=(0, 0, 0, 0), spacing=4)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        box.addWidget(bar)
        status = Muted("")
        status.setWordWrap(True)
        box.addWidget(status)
        install_btn = button("立即安装", "primary", lambda _=False: self._install())
        install_btn.hide()
        box.addWidget(install_btn)
        container.hide()
        card.body.addWidget(container)
        self._progress_ui[info.key] = (container, bar, status, install_btn)

    def _build_coming_soon(self, card: Card, info) -> None:
        note = Muted(str(getattr(info, "note", "") or "").strip()
                     or "该平台客户端正在开发中，敬请期待。")
        note.setWordWrap(True)
        card.body.addWidget(note)
        row = hbox(spacing=8)
        row.addWidget(chip("即将推出", "category"))
        row.addStretch(1)
        card.body.addLayout(row)
        try:
            card.setEnabled(False)
        except RuntimeError:
            pass

    @staticmethod
    def _meta_text(release) -> str:
        if release is None:
            return ""
        parts = []
        version = str(getattr(release, "version", "") or "").strip()
        if version:
            parts.append("版本 %s" % version)
        date = str(getattr(release, "date", "") or "").strip()
        if date:
            parts.append(date)
        size_text = str(getattr(release, "size_text", "") or "").strip()
        if size_text:
            parts.append(size_text)
        return " · ".join(parts)

    # ────────────────────── 下载 ──────────────────────
    def _start_download(self, info, release, *, save_as: bool = False) -> None:
        if self._dl.get("active"):
            self.toast("已有下载任务进行中，请稍候")
            return
        url = str(getattr(release, "url", "") or "").strip()
        if not url:
            self.toast("该版本暂无可用下载地址")
            return
        full = url if url.startswith(("http://", "https://")) else constants.absolute(url)
        filename = self._default_filename(info.key, release)
        if save_as:
            chosen, _ = QFileDialog.getSaveFileName(self, "另存为",
                                                    str(Path.home() / filename))
            if not chosen:
                return
            dest = Path(chosen)
        else:
            try:
                dest = paths.update_dir() / util.safe_filename(filename)
                dest.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.toast("无法创建下载目录：%s" % exc)
                return
        expected = int(getattr(release, "size", 0) or 0)

        self._prepare_progress(info)
        now = time.time()
        self._dl = {"active": True, "done": 0, "total": expected,
                    "t0": now, "sample_t": now, "sample_done": 0, "speed": 0.0}
        self._timer.start()

        def _on_progress(done: int, total: int) -> None:
            self._dl["done"] = int(done)
            if total:
                self._dl["total"] = int(total)

        def _work():
            return updater.download_to(full, dest, expected=expected, resume=True,
                                       on_progress=_on_progress)

        self.run(_work,
                 lambda result: self._finish_download(info, dest, result),
                 lambda message: self._finish_download(info, dest, (False, message)),
                 label="下载安装包")

    def _prepare_progress(self, info) -> None:
        ui = self._progress_ui.get(getattr(info, "key", ""))
        if not ui:
            return
        container, bar, status, install_btn = ui
        try:
            bar.setValue(0)
            status.setText("正在连接…")
            install_btn.hide()
            container.show()
        except RuntimeError:
            return

    def _finish_download(self, info, dest, result) -> None:
        try:
            self._timer.stop()
        except RuntimeError:
            pass
        self._dl = {"active": False}
        ok = False
        error = ""
        if isinstance(result, tuple) and len(result) == 2:
            ok, error = bool(result[0]), str(result[1] or "")
        name = Path(dest).name
        ui = self._progress_ui.get(getattr(info, "key", ""))
        if not ok:
            if ui:
                try:
                    ui[0].hide()
                except RuntimeError:
                    ui = None
            self.toast(error or "下载失败")
            return
        self._last_download = Path(dest)
        if ui:
            container, bar, status, install_btn = ui
            try:
                bar.setValue(100)
                status.setText("下载完成：%s" % name)
                if getattr(info, "key", "") == "windows":
                    install_btn.show()
            except RuntimeError:
                pass
        self.toast("下载完成：%s" % name)

    def _tick(self) -> None:
        state = self._dl
        if not state.get("active"):
            try:
                self._timer.stop()
            except RuntimeError:
                pass
            return
        now = time.time()
        done = int(state.get("done", 0))
        total = int(state.get("total", 0))
        elapsed = now - float(state.get("sample_t", now) or now)
        if elapsed >= 0.35:
            prev = int(state.get("sample_done", 0))
            state["speed"] = max(0.0, (done - prev) / elapsed)
            state["sample_t"] = now
            state["sample_done"] = done
        self._paint_progress(done, total, float(state.get("speed", 0.0)))

    def _paint_progress(self, done: int, total: int, speed: float) -> None:
        ui = None
        for _key, value in self._progress_ui.items():
            if value[0].isVisible():
                ui = value
                break
        if ui is None:
            return
        container, bar, status, _install_btn = ui
        try:
            if total > 0:
                bar.setRange(0, 100)
                bar.setValue(int(min(100, done * 100 // total)))
            else:
                bar.setRange(0, 0)
        except RuntimeError:
            return
        try:
            status.setText(self._progress_text(done, total, speed, time.time()))
        except RuntimeError:
            return

    @staticmethod
    def _progress_text(done: int, total: int, speed: float, now: float) -> str:
        parts = []
        if total > 0:
            parts.append("%.1f%%" % (done * 100.0 / total))
            parts.append("%s / %s" % (util.human_size(done), util.human_size(total)))
        else:
            parts.append("已下载 %s" % util.human_size(done))
        if speed > 0:
            parts.append("%s/s" % util.human_size(speed))
            if total > done:
                eta = (total - done) / speed
                parts.append("剩余 %s" % DownloadPage._eta_text(eta))
        return " · ".join(parts)

    @staticmethod
    def _eta_text(seconds: float) -> str:
        try:
            value = int(max(0, round(seconds)))
        except (TypeError, ValueError):
            return "-"
        if value < 60:
            return "%d 秒" % value
        if value < 3600:
            return "%d 分 %d 秒" % (value // 60, value % 60)
        return "%d 小时 %d 分" % (value // 3600, (value % 3600) // 60)

    @staticmethod
    def _default_filename(platform: str, release) -> str:
        name = str(getattr(release, "filename", "") or "").strip()
        if name:
            return util.safe_filename(name, "forum-%s" % platform)
        url = str(getattr(release, "url", "") or "")
        base = ""
        if url:
            try:
                base = urlparse(url).path.rsplit("/", 1)[-1]
            except Exception:  # noqa: BLE001
                base = ""
        return util.safe_filename(base, "forum-%s" % platform)

    def _install(self) -> None:
        if not self._last_download:
            self.toast("请先下载安装包")
            return
        try:
            ok, message = updater.launch_installer(self._last_download)
        except Exception as exc:  # noqa: BLE001
            _log.warning("启动安装失败：%s", exc)
            self.toast("启动安装失败：%s" % exc)
            return
        self.toast(message)

    def _open_folder(self) -> None:
        target = self._last_download
        if target is None:
            base = paths.update_dir()
            try:
                base.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            target = base
        if not util.reveal_in_explorer(str(target)):
            self.toast("打开文件夹失败")

    # ────────────────────── 更新检查 / 发布页 ──────────────────────
    def _check_update(self) -> None:
        self._state_label.setText("正在检查更新…")

        def _done(info) -> None:
            info = info or updater.UpdateInfo(available=False, message="检查更新失败")
            message = info.message or ("发现新版本" if info.available else "当前已是最新版本")
            self._state_label.setText(message)
            if info.available:
                self.toast(message)

        try:
            updater.check_async(_done)
        except Exception as exc:  # noqa: BLE001
            _log.warning("检查更新失败：%s", exc)
            self._state_label.setText("检查更新失败")
            self.toast("检查更新失败")

    def _open_release_page(self) -> None:
        url = constants.absolute(constants.APP_DOWNLOAD_PAGE)
        if not util.open_in_system(url):
            self.toast("无法打开浏览器")

    # ────────────────────── 主题 ──────────────────────
    def reload_theme(self) -> None:
        super().reload_theme()
        try:
            self._mark_filter()
        except RuntimeError:
            pass
