# -*- coding: utf-8 -*-
"""更新交互组件：发现新版本 → 询问是否下载 → 进度/速度/预计剩余 → 选择安装时机。

托盘菜单、下载页、设置·关于三处「检查更新」共用本模块，保证交互一致。
* 下载完成后三个选项：立即安装 / 退出时自动安装 / 稍后
* 所有对外函数都不抛异常（失败走 ``on_status`` / 信息弹窗 / toast）
* 网络与安装动作全部落在 :mod:`app.updater` 的异步接口上，不阻塞界面
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QLabel, QProgressBar, QWidget

from .. import logger, updater, util
from .common import Divider, Muted, TitleLabel, vbox
from .dialogs import BaseDialog, info_box
from .toast import toast

_log = logger.get_logger("update_ui")


# ────────────────────────── 文案工具 ──────────────────────────


def eta_text(seconds) -> str:
    """秒数 → 「x 秒 / x 分 y 秒 / x 小时 y 分」。"""
    try:
        value = int(max(0, round(float(seconds))))
    except (TypeError, ValueError):
        return "-"
    if value < 60:
        return "%d 秒" % value
    if value < 3600:
        return "%d 分 %d 秒" % (value // 60, value % 60)
    return "%d 小时 %d 分" % (value // 3600, (value % 3600) // 60)


def progress_text(done: int, total: int, speed: float) -> str:
    """进度文案：百分比 · 已下载/总量 · 速度 · 预计剩余。"""
    parts = []
    if total > 0:
        parts.append("%.1f%%" % (done * 100.0 / total))
        parts.append("%s / %s" % (util.human_size(done), util.human_size(total)))
    else:
        parts.append("已下载 %s" % util.human_size(done))
    if speed > 0:
        parts.append("%s/s" % util.human_size(speed))
        if total > done:
            parts.append("剩余 %s" % eta_text((total - done) / speed))
    return " · ".join(parts)


def _emit(callback, *args) -> None:
    """调用回调（不抛异常）。"""
    if not callable(callback):
        return
    try:
        callback(*args)
    except Exception as exc:  # noqa: BLE001
        _log.warning("更新回调执行失败：%s", exc)


# ────────────────────────── 询问是否下载 ──────────────────────────


class UpdateDialog(BaseDialog):
    """发现新版本：展示版本 / 体积 / 更新说明，询问是否现在下载。"""

    def __init__(self, info, parent: QWidget | None = None) -> None:
        super().__init__(parent, title="发现新版本", width=460)
        version = str(getattr(info, "version", "") or "").strip()
        size = int(getattr(info, "size", 0) or 0)

        head = "检测到新版本"
        if version:
            head += " v%s" % version
        current = updater.current_version()
        if current:
            head += "（当前 v%s）" % current
        head += "，是否现在下载？"
        message = QLabel(head)
        message.setWordWrap(True)
        self.body.addWidget(message)

        if size > 0:
            self.body.addWidget(Muted("安装包大小：%s" % util.human_size(size)))

        notes = [str(note).strip() for note in (getattr(info, "notes", ()) or ())
                 if str(note).strip()]
        if notes:
            self.body.addWidget(Divider())
            self.body.addWidget(Muted("更新说明"))
            for note in notes:
                item = QLabel("· %s" % note)
                item.setWordWrap(True)
                self.body.addWidget(item)

        if bool(getattr(info, "mandatory", False)):
            self.body.addWidget(Muted("这是一次重要更新，建议尽快升级。"))

        self.add_action("稍后", None, self.reject)
        self.add_action("立即下载", "primary", self.accept)


def ask_update(parent: QWidget | None, info) -> bool:
    """弹窗询问是否下载新版本；任何异常都当作「暂不下载」。"""
    try:
        return UpdateDialog(info, parent).exec() == QDialog.DialogCode.Accepted
    except Exception as exc:  # noqa: BLE001
        _log.warning("更新确认弹窗失败：%s", exc)
        return False


# ────────────────────────── 选择安装时机 ──────────────────────────


class InstallChoiceDialog(BaseDialog):
    """下载完成：选择「立即安装 / 退出时自动安装 / 稍后」。"""

    def __init__(self, parent: QWidget | None = None, version: str = "") -> None:
        super().__init__(parent, title="下载完成", width=460)
        self.choice = "later"
        head = "更新包已下载完成"
        if str(version or "").strip():
            head += "（v%s）" % str(version).strip()
        head += "。\n\n「立即安装」会关闭当前程序并自动重新启动；"
        head += "「退出时自动安装」会在你退出程序后再静默安装。"
        message = QLabel(head)
        message.setWordWrap(True)
        self.body.addWidget(message)
        self.add_action("稍后", None, lambda _=False: self._pick("later"))
        self.add_action("退出时自动安装", None, lambda _=False: self._pick("pending"))
        self.add_action("立即安装", "primary", lambda _=False: self._pick("now"))

    def _pick(self, choice: str) -> None:
        self.choice = str(choice or "later")
        if self.choice == "later":
            self.reject()
        else:
            self.accept()


def install_choice(parent: QWidget | None, version: str = "") -> str:
    """询问安装时机；返回 ``now`` / ``pending`` / ``later``（异常时当作稍后）。"""
    try:
        dialog = InstallChoiceDialog(parent, version)
        dialog.exec()
        return str(dialog.choice or "later")
    except Exception as exc:  # noqa: BLE001
        _log.warning("安装时机弹窗失败：%s", exc)
        return "later"


# ────────────────────────── 下载进度窗口 ──────────────────────────


class DownloadDialog(QDialog):
    """下载进度窗口：百分比 / 已下载 / 速度 / 预计剩余时间。"""

    def __init__(self, info, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("下载更新")
        self.setModal(False)
        self.setMinimumWidth(400)

        root = vbox(self, margins=(18, 16, 18, 16), spacing=10)
        version = str(getattr(info, "version", "") or "").strip()
        root.addWidget(TitleLabel("正在下载更新 v%s" % version if version
                                  else "正在下载更新"))

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # 大小未知 → 忙等指示
        self.bar.setTextVisible(False)
        root.addWidget(self.bar)

        self.status = Muted("正在连接…")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self._done = 0
        self._total = int(getattr(info, "size", 0) or 0)
        now = time.time()
        self._sample_t = now
        self._sample_done = 0
        self._speed = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_progress(self, done: int, total: int) -> None:
        """记录最新进度（由工作线程回调转投到主线程）。"""
        self._done = int(done)
        if total:
            self._total = int(total)

    def _tick(self) -> None:
        now = time.time()
        elapsed = now - self._sample_t
        if elapsed >= 0.35:
            self._speed = max(0.0, (self._done - self._sample_done) / elapsed)
            self._sample_t = now
            self._sample_done = self._done
        try:
            if self._total > 0:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(min(100, self._done * 100 // self._total)))
            else:
                self.bar.setRange(0, 0)
            self.status.setText(progress_text(self._done, self._total, self._speed))
        except RuntimeError:
            self._stop()

    def _stop(self) -> None:
        try:
            self._timer.stop()
        except RuntimeError:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        self._stop()
        super().closeEvent(event)


def download_and_install(parent: QWidget | None, info, *, on_status=None) -> None:
    """下载更新包（带进度/速度/ETA），完成后询问是否立即安装。"""
    def _status(text: str) -> None:
        _emit(on_status, text)

    dialog = None
    try:
        dialog = DownloadDialog(info, parent)
        dialog.show()
    except Exception as exc:  # noqa: BLE001
        _log.warning("下载进度窗口创建失败：%s", exc)
        dialog = None

    def _on_progress(done: int, total: int) -> None:
        if dialog is not None:
            try:
                dialog.set_progress(done, total)
            except RuntimeError:
                pass
        if total > 0:
            _status("正在下载更新… %s" % progress_text(int(done), int(total), 0.0))
        else:
            _status("正在下载更新… 已下载 %s" % util.human_size(int(done or 0)))

    def _on_done(path, error) -> None:
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                pass
        if error or not path:
            text = "更新包下载失败：%s" % (error or "未知错误")
            _status(text)
            info_box(parent, "下载更新", text)
            return
        version = str(getattr(info, "version", "") or "")
        _status("更新包下载完成")
        choice = install_choice(parent, version)
        if choice == "pending":
            if updater.set_pending_install(path, version):
                _status("已设定为退出程序时自动安装")
                toast("已设定：退出程序时将自动安装更新")
            else:
                _status("无法登记自动安装，可稍后手动安装")
                toast("安装包已保存，可在「下载」页手动安装")
            return
        if choice != "now":
            toast("安装包已保存，可在「下载」页稍后安装")
            return
        try:
            ok, message = updater.launch_installer(path)
        except Exception as exc:  # noqa: BLE001
            _log.warning("启动安装失败：%s", exc)
            _status("启动安装失败：%s" % exc)
            info_box(parent, "安装更新", "启动安装失败：%s" % exc)
            return
        _status(message)
        if not ok:
            info_box(parent, "安装更新", message)

    try:
        updater.download_update(info, on_progress=_on_progress, on_done=_on_done)
    except Exception as exc:  # noqa: BLE001
        _log.error("启动下载失败：%s", exc, exc_info=True)
        _on_done(None, str(exc))


# ────────────────────────── 统一入口 ──────────────────────────


def check_and_prompt(parent: QWidget | None, *, on_status=None, on_result=None) -> None:
    """「检查更新」统一入口：检查 → 有新版本则询问下载 → 下载 → 询问安装。

    * ``on_status(text)``：状态文本回调（状态栏 / toast 由调用方决定）
    * ``on_result(info)``：检查完成后回调，便于页面刷新标签
    """
    def _status(text: str) -> None:
        _emit(on_status, text)

    _status("正在检查更新…")

    def _done(info) -> None:
        info = info or updater.UpdateInfo(available=False, message="检查更新失败")
        _emit(on_result, info)
        message = info.message or ("发现新版本" if info.available else "当前已是最新版本")
        _status(message)
        if not info.available:
            if message == updater.UNAVAILABLE_TEXT:
                toast(message)
            else:
                info_box(parent, "检查更新", message)
            return
        if not ask_update(parent, info):
            return
        # 下载阶段的进度由进度窗口呈现，不再透传状态回调以免消息刷屏
        download_and_install(parent, info)

    try:
        updater.check_async(_done, label="检查更新")
    except Exception as exc:  # noqa: BLE001
        _log.error("检查更新失败：%s", exc, exc_info=True)
        _status("检查更新失败：%s" % exc)
        info_box(parent, "检查更新", "检查更新失败：%s" % exc)
