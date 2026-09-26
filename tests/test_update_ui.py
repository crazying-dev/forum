# -*- coding: utf-8 -*-
"""更新交互组件（``app/widgets/update.py``）与三处入口接入的离线用例。

不依赖 pytest 夹具：``tests/run_tests.py`` 以无参形式逐个调用用例函数。
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app import paths, updater
from app.widgets import update as upd


# ────────────────────── 手工打桩（保存/恢复） ──────────────────────

_PATCHES: list = []


def _patch(obj, name, value) -> None:
    had = hasattr(obj, name)
    old = getattr(obj, name, None)
    _PATCHES.append((obj, name, had, old))
    setattr(obj, name, value)


def _restore_all() -> None:
    while _PATCHES:
        obj, name, had, old = _PATCHES.pop()
        if had:
            setattr(obj, name, old)
        else:
            try:
                delattr(obj, name)
            except AttributeError:
                pass


def _qt():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _info(**kwargs):
    return updater.UpdateInfo(**kwargs)


# ────────────────────── 文案工具 ──────────────────────


def test_eta_text_formats():
    assert upd.eta_text(0) == "0 秒"
    assert upd.eta_text(59) == "59 秒"
    assert upd.eta_text(60) == "1 分 0 秒"
    assert upd.eta_text(90) == "1 分 30 秒"
    assert upd.eta_text(3700) == "1 小时 1 分"
    assert upd.eta_text(None) == "-"
    assert upd.eta_text(-5) == "0 秒"


def test_progress_text_formats():
    text = upd.progress_text(50, 100, 10.0)
    assert "%" in text and "/" in text and "/s" in text and "剩余" in text
    unknown = upd.progress_text(2048, 0, 0.0)
    assert "已下载" in unknown


# ────────────────────── 弹窗 ──────────────────────


def test_update_dialog_constructs():
    _qt()
    info = _info(available=True, version="9.9.9", size=1024 * 1024,
                 notes=("修复若干问题", "优化下载体验"))
    dlg = upd.UpdateDialog(info, None)
    try:
        assert dlg.windowTitle() == "发现新版本"
    finally:
        dlg.deleteLater()


def test_download_dialog_progress():
    _qt()
    info = _info(available=True, version="9.9.9", size=100)
    dlg = upd.DownloadDialog(info, None)
    try:
        dlg.set_progress(50, 100)
        dlg._tick()
        assert dlg.bar.value() == 50
    finally:
        dlg._stop()
        dlg.deleteLater()


# ────────────────────── 统一入口分期 ──────────────────────


def test_check_and_prompt_reports_latest():
    _qt()
    seen: list = []
    boxes: list = []
    _patch(upd, "info_box", lambda parent, title, text, **k: boxes.append(text))
    _patch(upd, "toast", lambda *a, **k: None)
    _patch(upd.updater, "check_async",
           lambda on_done, **k: on_done(_info(available=False,
                                              message="当前已是最新版本")))
    try:
        upd.check_and_prompt(None, on_status=seen.append)
    finally:
        _restore_all()
    assert "当前已是最新版本" in seen
    assert boxes and "最新" in boxes[-1]


def test_check_and_prompt_unavailable_uses_toast():
    _qt()
    toasts: list = []
    _patch(upd, "info_box", lambda *a, **k: None)
    _patch(upd, "toast", lambda text, **k: toasts.append(text))
    _patch(upd.updater, "check_async",
           lambda on_done, **k: on_done(_info(available=False,
                                              message=updater.UNAVAILABLE_TEXT)))
    try:
        upd.check_and_prompt(None, on_status=lambda t: None)
    finally:
        _restore_all()
    assert updater.UNAVAILABLE_TEXT in toasts


def test_check_and_prompt_declined_skips_download():
    _qt()
    asked = {"ask": 0, "download": 0}
    _patch(upd, "info_box", lambda *a, **k: None)
    _patch(upd, "toast", lambda *a, **k: None)
    _patch(upd.updater, "check_async",
           lambda on_done, **k: on_done(_info(available=True, version="9.9.9", size=10)))
    _patch(upd, "ask_update",
           lambda parent, info: asked.__setitem__("ask", asked["ask"] + 1) or False)
    _patch(upd, "download_and_install",
           lambda *a, **k: asked.__setitem__("download", asked["download"] + 1))
    try:
        upd.check_and_prompt(None, on_status=lambda t: None)
    finally:
        _restore_all()
    assert asked["ask"] == 1
    assert asked["download"] == 0


def test_check_and_prompt_accepted_starts_download():
    _qt()
    got: dict = {}
    _patch(upd, "info_box", lambda *a, **k: None)
    _patch(upd, "toast", lambda *a, **k: None)
    _patch(upd.updater, "check_async",
           lambda on_done, **k: on_done(_info(available=True, version="9.9.9", size=10)))
    _patch(upd, "ask_update", lambda parent, info: True)
    _patch(upd, "download_and_install",
           lambda parent, info, **k: got.__setitem__("info", info))
    try:
        upd.check_and_prompt(None, on_status=lambda t: None)
    finally:
        _restore_all()
    assert got.get("info") is not None
    assert got["info"].version == "9.9.9"


# ────────────────────── 三处入口接入 ──────────────────────


def test_download_page_delegates_to_shared_module():
    _qt()
    calls: list = []
    _patch(upd, "check_and_prompt", lambda parent, **k: calls.append(parent))
    from app.pages.download import DownloadPage
    page = DownloadPage()
    try:
        page._check_update()
    finally:
        page.deleteLater()
        _restore_all()
    assert len(calls) == 1


def test_settings_page_delegates_to_shared_module():
    _qt()
    calls: list = []
    _patch(upd, "check_and_prompt", lambda parent, **k: calls.append(parent))
    from app.pages.settings import SettingsPage
    page = SettingsPage(shell=None)
    try:
        page._check_update()
    finally:
        page.deleteLater()
        _restore_all()
    assert len(calls) == 1


def test_tray_delegates_to_shared_module():
    from app.tray import TrayIcon
    source = inspect.getsource(TrayIcon._check_update)
    assert "check_and_prompt" in source
    assert "from .widgets import update" in source


# ────────────────────── 按版本隔离的下载目录 / 文件名 ──────────────────────


class _FakeDownloadDialog:
    """替身：只记录调用，不建真窗口。"""

    def __init__(self, info, parent=None) -> None:
        self.closed = False

    def show(self) -> None:
        pass

    def set_progress(self, done, total) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_asset_name_prefers_filename_then_url():
    gh = ("https://github.com/crazying-dev/forum/releases/download/"
          "Windows-V1.3.2/forum_setup.exe")
    assert updater.asset_name(gh) == "forum_setup.exe"
    assert updater.asset_name(gh, "forum_setup.exe") == "forum_setup.exe"
    # 旧版裸 exe 兜底源：仍按 URL 末段命名，走热替换分支
    assert updater.asset_name("https://www.yjlt.top/api/app/windows/forum.exe") == "forum.exe"
    # 拿不到 .exe 名时回落到安装包默认名
    assert updater.asset_name("https://example.com/x") == updater.INSTALLER_NAME


def test_download_dir_is_per_version():
    assert updater.download_dir(_info(available=True, version="1.3.2")).name == "1.3.2"
    assert updater.download_dir(_info(available=True, version="")).name == "update"
    # 远端版本号不可控：必须做路径穿越清洗
    assert updater.download_dir(_info(available=True, version="../../x")).name == "x"
    assert updater.download_dir(_info(available=True, version="1.3.2")) == \
        paths.update_dir("1.3.2")


def test_is_installer_detects_setup_name():
    assert updater.is_installer("forum_setup.exe") is True
    assert updater.is_installer(str(Path("C:/u/1.3.2/Forum_Setup_v1.3.2.exe"))) is True
    assert updater.is_installer("forum.exe") is False
    assert updater.is_installer("") is False


def test_installer_script_silent_and_restarts():
    script = updater._installer_script_text(Path(r"C:\u\1.3.2\forum_setup.exe"),
                                            Path(r"C:\app\forum.exe"))
    assert "/SILENT" in script
    assert "/NORESTART" in script
    assert "forum_setup.exe" in script
    assert 'start "" /wait' in script
    assert 'start "" "%APP%"' in script
    assert "tasklist" in script


# ────────────────────── 退出时自动安装 ──────────────────────


def test_pending_install_roundtrip():
    target = paths.update_dir("9.9.9") / "forum_setup.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    try:
        updater.clear_pending_install()
        assert updater.pending_install() is None
        assert updater.set_pending_install(target, "9.9.9") is True
        info = updater.pending_install()
        assert info is not None
        assert info["path"] == str(target)
        assert info["version"] == "9.9.9"
        updater.clear_pending_install()
        assert updater.pending_install() is None
        # 安装包不存在时不登记
        assert updater.set_pending_install(target.parent / "missing.exe", "9.9.9") is False
    finally:
        updater.clear_pending_install()
        try:
            target.unlink()
        except OSError:
            pass


def test_pending_install_dropped_when_file_gone():
    target = paths.update_dir("9.9.8") / "forum_setup.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    try:
        assert updater.set_pending_install(target, "9.9.8") is True
        target.unlink()
        assert updater.pending_install() is None
    finally:
        updater.clear_pending_install()
        try:
            target.unlink()
        except OSError:
            pass


def test_run_pending_install_without_registration():
    updater.clear_pending_install()
    assert updater.run_pending_install() is False


# ────────────────────── 安装时机选择 ──────────────────────


def test_install_choice_dialog_defaults_to_later():
    _qt()
    dlg = upd.InstallChoiceDialog(None, "9.9.9")
    try:
        assert dlg.choice == "later"
        assert dlg.windowTitle() == "下载完成"
    finally:
        dlg.deleteLater()


def test_download_and_install_pending_registers():
    _qt()
    registered: dict = {}
    _patch(upd, "DownloadDialog", _FakeDownloadDialog)
    _patch(upd, "install_choice", lambda parent, version="": "pending")
    _patch(upd, "toast", lambda *a, **k: None)
    _patch(upd.updater, "set_pending_install",
           lambda path, version="": (registered.update(path=path, version=version)
                                     or True))
    _patch(upd.updater, "download_update",
           lambda info, on_progress=None, on_done=None:
               on_done("C:/u/1.3.2/forum_setup.exe", ""))
    try:
        upd.download_and_install(None, _info(available=True, version="1.3.2", size=10))
    finally:
        _restore_all()
    assert registered.get("path") == "C:/u/1.3.2/forum_setup.exe"
    assert registered.get("version") == "1.3.2"


def test_download_and_install_now_launches():
    _qt()
    got: dict = {}
    _patch(upd, "DownloadDialog", _FakeDownloadDialog)
    _patch(upd, "install_choice", lambda parent, version="": "now")
    _patch(upd, "toast", lambda *a, **k: None)
    _patch(upd, "info_box", lambda *a, **k: None)
    _patch(upd.updater, "launch_installer",
           lambda path: (got.__setitem__("path", path) or (True, "ok")))
    _patch(upd.updater, "download_update",
           lambda info, on_progress=None, on_done=None:
               on_done("C:/u/forum_setup.exe", ""))
    try:
        upd.download_and_install(None, _info(available=True, version="1.3.2", size=10))
    finally:
        _restore_all()
    assert got.get("path") == "C:/u/forum_setup.exe"


def test_download_and_install_later_keeps_file():
    _qt()
    flags = {"pending": 0, "launch": 0}
    _patch(upd, "DownloadDialog", _FakeDownloadDialog)
    _patch(upd, "install_choice", lambda parent, version="": "later")
    _patch(upd, "toast", lambda *a, **k: None)
    _patch(upd.updater, "set_pending_install",
           lambda path, version="": flags.__setitem__("pending", flags["pending"] + 1))
    _patch(upd.updater, "launch_installer",
           lambda path: (flags.__setitem__("launch", flags["launch"] + 1) or (True, "ok")))
    _patch(upd.updater, "download_update",
           lambda info, on_progress=None, on_done=None:
               on_done("C:/u/forum_setup.exe", ""))
    try:
        upd.download_and_install(None, _info(available=True, version="1.3.2", size=10))
    finally:
        _restore_all()
    assert flags["pending"] == 0
    assert flags["launch"] == 0
