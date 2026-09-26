# -*- coding: utf-8 -*-
"""更新交互组件（``app/widgets/update.py``）与三处入口接入的离线用例。

不依赖 pytest 夹具：``tests/run_tests.py`` 以无参形式逐个调用用例函数。
"""

from __future__ import annotations

import inspect

from app import updater
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
