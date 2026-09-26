# -*- coding: utf-8 -*-
"""系统托盘图标：主窗口显隐、世界频道、Live2D 桌宠、主题 / 年制、更新与退出。

主程序只需 ``tray = TrayIcon(app, shell)`` 与 ``tray.show()``。

* 菜单状态在每次弹出前（``aboutToShow``）按当前配置与窗口状态刷新
* 耗时操作（检查更新 / 下载）全部走 :mod:`app.updater` 的异步接口，不阻塞界面
* 新版本提示与最小化提示用 :meth:`QSystemTrayIcon.showMessage` 气泡
"""

from __future__ import annotations

from PyQt6.QtGui import QAction, QActionGroup, QIcon
from PyQt6.QtWidgets import (QMenu, QMessageBox, QProgressDialog,
                             QSystemTrayIcon)

from . import config, constants, logger, paths, updater, util, yearmode

_log = logger.get_logger("tray")

THEME_ITEMS = (
    (constants.THEME_DAY, "日间"),
    (constants.THEME_NIGHT, "夜间"),
    (constants.THEME_AUTO, "跟随系统"),
)

YEAR_ITEMS = (
    (constants.YEAR_MODE_WUXIAN, "无限年"),
    (constants.YEAR_MODE_CE, "公元年"),
)

ABOUT_TEXT = (
    "<b>%s 客户端</b><br>版本：%s<br><br>"
    "妖精论坛官方桌面客户端（Windows）。<br>"
    "程序内所有内容版权归妖精论坛及各原作者所有，<br>"
    "仅供学习与交流，未经许可请勿用于商业用途。"
) % (constants.APP_NAME, constants.APP_VERSION)


def _tray_icon() -> QIcon:
    """托盘图标：优先 ``icon.ico``，缺失时回退 ``logo.png``。"""
    for path in (constants.RES_ICON, constants.RES_LOGO):
        try:
            if path.is_file():
                icon = QIcon(str(path))
                if not icon.isNull():
                    return icon
        except Exception:  # noqa: BLE001
            continue
    _log.warning("内置图标缺失，托盘将使用空图标")
    return QIcon()


class TrayIcon(QSystemTrayIcon):
    """托盘图标与右键菜单。"""

    def __init__(self, app, shell, parent=None) -> None:
        super().__init__(parent)
        self._app = app
        self._shell = shell
        self._update_info = None
        self._progress = None

        self.setIcon(_tray_icon())
        self.setToolTip("%s 客户端" % constants.APP_NAME)

        self._menu = QMenu()
        self._build_menu()
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        self._sync()

    # ────────────────────── 菜单 ──────────────────────

    def _build_menu(self) -> None:
        self._window_action = QAction("隐藏主窗口", self._menu)
        self._window_action.triggered.connect(self.toggle_window)
        self._menu.addAction(self._window_action)

        self._world_action = QAction("隐藏世界频道", self._menu)
        self._world_action.setCheckable(True)
        self._world_action.triggered.connect(self._toggle_world)
        self._menu.addAction(self._world_action)

        self._pet_action = QAction("Live2D 桌宠", self._menu)
        self._pet_action.setCheckable(True)
        self._pet_action.triggered.connect(self._toggle_pet)
        self._menu.addAction(self._pet_action)

        self._menu.addSeparator()

        self._theme_actions = self._add_radio_menu("主题", THEME_ITEMS, self._set_theme)
        self._year_actions = self._add_radio_menu("年制", YEAR_ITEMS, self._set_year)

        self._menu.addSeparator()

        self._add_item("打开数据目录", self._open_data_dir)
        self._add_item("检查更新", self._check_update)
        self._add_item("反馈 Bug", self._bug_report)

        self._menu.addSeparator()

        self._add_item("关于", self._about)
        self._add_item("退出", self._quit)

        self._menu.aboutToShow.connect(self._sync)

    def _add_item(self, text: str, slot) -> QAction:
        action = QAction(text, self._menu)
        action.triggered.connect(lambda _checked=False: slot())
        self._menu.addAction(action)
        return action

    def _add_radio_menu(self, title: str, items, handler) -> dict:
        """单选子菜单（主题 / 年制）；返回 ``{值: QAction}``。"""
        menu = self._menu.addMenu(title)
        group = QActionGroup(menu)
        group.setExclusive(True)
        actions: dict = {}
        for value, label in items:
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setData(value)
            action.triggered.connect(lambda _checked=False, v=value: handler(v))
            group.addAction(action)
            menu.addAction(action)
            actions[value] = action
        return actions

    def _sync(self) -> None:
        """每次弹出菜单前重新读状态，刷新文案与勾选。"""
        try:
            visible = bool(self._shell.isVisible())
        except Exception:  # noqa: BLE001
            visible = False
        self._window_action.setText("隐藏主窗口" if visible else "显示主窗口")

        panel = getattr(self._shell, "world_panel", None)
        if panel is None:
            self._world_action.setEnabled(False)
            self._world_action.setChecked(False)
            self._world_action.setText("世界频道显示 / 隐藏（不可用）")
        else:
            try:
                collapsed = bool(panel.is_collapsed())
            except Exception:  # noqa: BLE001
                collapsed = False
            self._world_action.setEnabled(True)
            self._world_action.setChecked(not collapsed)
            self._world_action.setText("显示世界频道" if collapsed else "隐藏世界频道")

        pet = getattr(self._shell, "pet_controller", None)
        self._pet_action.setEnabled(pet is not None)
        if pet is None:
            self._pet_action.setText("Live2D 桌宠（当前不可用）")
        else:
            self._pet_action.setText("Live2D 桌宠")
        self._pet_action.setChecked(self._pet_running())

        cfg = config.current()
        theme = str(cfg.get("theme", constants.THEME_AUTO))
        for value, action in getattr(self, "_theme_actions", {}).items():
            action.setChecked(value == theme)
        mode = yearmode.get_mode()
        for value, action in getattr(self, "_year_actions", {}).items():
            action.setChecked(value == mode)

    # ────────────────────── 窗口 / 托盘交互 ──────────────────────

    def _on_activated(self, reason) -> None:
        try:
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
                self.toggle_window()
        except Exception as exc:  # noqa: BLE001
            _log.debug("托盘激活处理失败：%s", exc)

    def toggle_window(self) -> None:
        """显示 / 隐藏主窗口（双击托盘图标也走这里）。"""
        try:
            visible = bool(self._shell.isVisible())
        except Exception:  # noqa: BLE001
            visible = False
        if visible:
            self.hide_window()
        else:
            try:
                self._shell.show_window()
            except Exception as exc:  # noqa: BLE001
                _log.warning("显示主窗口失败：%s", exc)

    def hide_window(self) -> None:
        try:
            self._shell.hide()
        except Exception as exc:  # noqa: BLE001
            _log.warning("隐藏主窗口失败：%s", exc)
            return
        self.notify("已最小化到系统托盘，双击托盘图标可恢复")

    def notify(self, message: str, *, title: str = "", msecs: int = 6000) -> None:
        """托盘气泡（新版本提示 / 最小化提示）。"""
        try:
            self.showMessage(title or constants.APP_NAME, str(message),
                             QSystemTrayIcon.MessageIcon.Information, int(msecs))
        except Exception as exc:  # noqa: BLE001
            _log.debug("托盘气泡失败：%s", exc)

    # ────────────────────── 世界频道 ──────────────────────

    def _toggle_world(self) -> None:
        panel = getattr(self._shell, "world_panel", None)
        if panel is None:
            return
        try:
            panel.set_collapsed(not bool(panel.is_collapsed()))
        except Exception as exc:  # noqa: BLE001
            _log.warning("切换世界频道失败：%s", exc)

    # ────────────────────── 桌宠 ──────────────────────

    def _pet_running(self) -> bool:
        pet = getattr(self._shell, "pet_controller", None)
        if pet is None:
            return False
        for name in ("is_running", "running", "is_active"):
            value = getattr(pet, name, None)
            try:
                if callable(value):
                    value = value()
            except Exception:  # noqa: BLE001
                value = None
            if isinstance(value, bool):
                return value
        return False

    def _toggle_pet(self) -> None:
        pet = getattr(self._shell, "pet_controller", None)
        if pet is None:
            return
        running = self._pet_running()
        try:
            if running:
                pet.stop()
            else:
                pet.start()
        except Exception as exc:  # noqa: BLE001
            _log.warning("切换桌宠失败：%s", exc)
            self._set_status("桌宠切换失败：%s" % exc)
            return
        now_running = bool(getattr(pet, "running", not running))
        try:
            config.current().set("pet.enabled", now_running)
        except Exception as exc:  # noqa: BLE001
            _log.debug("保存桌宠开关失败：%s", exc)
        self._set_status("已开启 Live2D 桌宠" if now_running else "已关闭 Live2D 桌宠")

    # ────────────────────── 主题 / 年制 ──────────────────────

    def _set_theme(self, value: str) -> None:
        try:
            config.current().set("theme", value)
        except Exception as exc:  # noqa: BLE001
            _log.warning("切换主题失败：%s", exc)

    def _set_year(self, mode: str) -> None:
        try:
            yearmode.set_mode(mode)
        except Exception as exc:  # noqa: BLE001
            _log.warning("切换年制失败：%s", exc)

    # ────────────────────── 其他入口 ──────────────────────

    def _open_data_dir(self) -> None:
        try:
            ok = util.reveal_in_explorer(str(paths.data_dir()))
        except Exception as exc:  # noqa: BLE001
            _log.warning("打开数据目录失败：%s", exc)
            ok = False
        if not ok:
            self._set_status("无法打开数据目录")

    def _bug_report(self) -> None:
        try:
            from .widgets.dialogs import BugReportDialog
        except Exception as exc:  # noqa: BLE001
            _log.warning("反馈模块不可用：%s", exc)
            QMessageBox.warning(self._shell, "反馈 Bug", "反馈模块不可用：%s" % exc)
            return
        try:
            BugReportDialog(self._shell, page_url=constants.BASE_URL).exec()
        except Exception as exc:  # noqa: BLE001
            _log.error("打开反馈窗口失败：%s", exc, exc_info=True)

    def _about(self) -> None:
        try:
            QMessageBox.about(self._shell, "关于 %s" % constants.APP_NAME, ABOUT_TEXT)
        except Exception as exc:  # noqa: BLE001
            _log.warning("关于窗口失败：%s", exc)

    def _quit(self) -> None:
        try:
            self._shell.request_quit()
        except Exception as exc:  # noqa: BLE001
            _log.warning("退出失败：%s", exc)

    def _set_status(self, text: str) -> None:
        setter = getattr(self._shell, "set_status", None)
        if callable(setter):
            try:
                setter(str(text))
            except Exception:  # noqa: BLE001
                pass

    # ────────────────────── 检查更新 / 下载 ──────────────────────

    def _check_update(self) -> None:
        """检查更新（异步，不阻塞界面）。"""
        self._set_status("正在检查更新…")
        try:
            updater.check_async(self._on_update_checked, label="检查更新")
        except Exception as exc:  # noqa: BLE001
            _log.error("检查更新失败：%s", exc, exc_info=True)
            self._set_status("检查更新失败：%s" % exc)

    def _on_update_checked(self, info) -> None:
        info = info or updater.UpdateInfo(available=False, message="检查更新失败")
        message = info.message or ("发现新版本" if info.available else "当前已是最新版本")
        self._set_status(message)
        if not info.available:
            if info.message == updater.UNAVAILABLE_TEXT:
                # 更新服务不可达：只给气泡与状态栏，不弹错误弹窗
                self.notify(message)
            else:
                QMessageBox.information(self._shell, "检查更新", message)
            return

        self._update_info = info
        self.notify(message, msecs=8000)
        text = "%s\n\n是否现在下载并安装？" % message
        try:
            from .widgets.dialogs import confirm
            accepted = confirm(self._shell, "检查更新", text, ok_text="下载", cancel_text="稍后")
        except Exception as exc:  # noqa: BLE001
            _log.warning("更新确认弹窗失败：%s", exc)
            accepted = False
        if not accepted:
            return
        self._start_download(info)

    def _start_download(self, info) -> None:
        dialog = None
        try:
            dialog = QProgressDialog("正在下载更新…", "取消", 0, 100, self._shell)
            dialog.setWindowTitle("下载更新")
            dialog.setCancelButton(None)
            dialog.setMinimumDuration(0)
            dialog.setAutoClose(False)
            dialog.setValue(0)
            dialog.show()
        except Exception as exc:  # noqa: BLE001
            _log.warning("进度窗口创建失败：%s", exc)
            dialog = None
        self._progress = dialog

        def _on_progress(done: int, total: int) -> None:
            if self._progress is not None:
                try:
                    if total > 0:
                        self._progress.setRange(0, 100)
                        self._progress.setValue(int(min(100, done * 100 // total)))
                    else:
                        self._progress.setRange(0, 0)  # 大小未知→忙等指示
                except Exception:  # noqa: BLE001
                    pass
            if total > 0:
                self._set_status("正在下载更新… %s / %s" % (
                    util.human_size(done), util.human_size(total)))
            else:
                self._set_status("正在下载更新… %s" % util.human_size(done))

        def _on_done(path, error) -> None:
            if self._progress is not None:
                try:
                    self._progress.close()
                except Exception:  # noqa: BLE001
                    pass
                self._progress = None
            if error or not path:
                text = "更新包下载失败：%s" % (error or "未知错误")
                self._set_status(text)
                QMessageBox.warning(self._shell, "检查更新", text)
                return
            ok, message = updater.launch_installer(path)
            self._set_status(message)
            if not ok:
                QMessageBox.warning(self._shell, "检查更新", message)

        try:
            updater.download_update(info, on_progress=_on_progress, on_done=_on_done)
        except Exception as exc:  # noqa: BLE001
            _log.error("启动下载失败：%s", exc, exc_info=True)
            _on_done(None, str(exc))
