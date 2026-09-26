# -*- coding: utf-8 -*-
"""发布清单 / 下载页 / 断点续传下载用例。

* :mod:`app.releases`：清单解析、离线兜底、版本比较、更新判定
* :mod:`app.updater`：``download_to`` 的断点续传（本地 HTTP 服务器）
* :class:`app.pages.download.DownloadPage`：路由契约 + 预留位卡片（离线，不联网）
"""

from __future__ import annotations

import contextlib
import http.server
import os
import tempfile
import threading

# 本地回环不应走系统代理（requests 会在请求时读取这些环境变量）
os.environ["NO_PROXY"] = (os.environ.get("NO_PROXY", "") + ",127.0.0.1,localhost").strip(",")
os.environ["no_proxy"] = (os.environ.get("no_proxy", "") + ",127.0.0.1,localhost").strip(",")

from app import constants, releases, updater


# ───────────────────── 工具 ──────────────────────


@contextlib.contextmanager
def _patched_fetch(result):
    """临时替换 :func:`app.releases._fetch`，并在进出时清缓存。"""
    orig = releases._fetch
    releases._fetch = lambda: result
    releases.reset_cache()
    try:
        yield
    finally:
        releases._fetch = orig
        releases.reset_cache()


def _catalog_payload(windows_version: str = "9.9.9", extra=None) -> dict:
    platforms = {
        "windows": {
            "label": "Windows",
            "status": "available",
            "releases": [{
                "version": windows_version,
                "date": "2026-01-01",
                "size": 12345678,
                "url": "/api/app/windows/forum.exe",
                "filename": "forum.exe",
                "notes": "测试版本",
            }],
        }
    }
    if extra:
        platforms.update(extra)
    return {"schema": 1, "platforms": platforms}


# ────────────────────── 纯逻辑 ──────────────────────


def test_compare_versions_basic():
    assert releases.compare_versions("1.0.0", "1.0.0") == 0
    assert releases.compare_versions("1.0.1", "1.0.0") == 1
    assert releases.compare_versions("1.0.0", "1.0.1") == -1
    assert releases.compare_versions("2.0", "1.9.9") == 1
    assert releases.compare_versions("1.0", "1.0.0") == 0
    assert releases.compare_versions("", "1") == -1


def test_norm_status_and_labels():
    assert releases._norm_status("available") == releases.STATUS_AVAILABLE
    assert releases._norm_status("Released") == releases.STATUS_AVAILABLE
    assert releases._norm_status("coming soon") == releases.STATUS_COMING_SOON
    assert releases._norm_status(None) == releases.STATUS_COMING_SOON
    assert releases.platform_label("windows") == "Windows"
    assert releases.platform_label("未知") == "未知"
    assert releases.platform_icon("windows")
    assert releases.platform_icon("unknown")


def test_release_from_dict_parses_fields():
    release = releases.Release.from_dict({
        "version": "1.2.3",
        "date": "2026-01-01",
        "size": 2048,
        "url": "/x",
        "filename": "a.exe",
        "notes": "n",
        "force": True,
        "sha256": "deadbeef",
    })
    assert release.version == "1.2.3"
    assert release.date == "2026-01-01"
    assert release.size == 2048
    assert release.size_text == "2.0 KB"
    assert release.url == "/x"
    assert release.filename == "a.exe"
    assert release.notes == "n"
    assert release.mandatory is True
    assert release.sha256 == "deadbeef"
    assert releases.Release.from_dict("not a dict").version == ""


def test_parse_platform_and_catalog():
    info = releases._parse_platform("windows", {
        "label": "Win",
        "status": "available",
        "releases": [{"version": "1.0", "url": "/a"}],
    })
    assert info.available is True
    assert info.latest.version == "1.0"
    soon = releases._parse_platform("android", {"status": "coming_soon"})
    assert soon.coming_soon is True
    assert soon.latest is None
    catalog = releases._parse_catalog(
        {"platforms": {"windows": {"releases": [{"version": "2.0", "url": "/b"}]}}})
    assert catalog["windows"].latest.version == "2.0"
    # 有 releases 时即便没写 status 也应视为可用
    assert catalog["windows"].available is True


def test_parse_server_shaped_manifest():
    """服务端 app_releases.json 的真实形状：platforms 为列表、notes 为列表。"""
    payload = {
        "schema": 1,
        "updated_at": "2026-09-26T12:00:00+08:00",
        "platforms": [
            {"key": "windows", "name": "Windows", "icon": "fa-windows",
             "status": "available", "requirement": "Windows 10 / 11（64 位）",
             "releases": [{"version": "1.0.0", "channel": "stable",
                           "date": "2026-09-26", "size": 48468327,
                           "url": "https://www.yjlt.top/api/app/windows/forum.exe",
                           "sha256": "", "notes": ["甲", "乙"], "mandatory": False}]},
            {"key": "android", "name": "Android", "status": "coming_soon", "releases": []},
            {"key": "linux", "name": "Linux", "status": "coming_soon", "releases": []},
            {"key": "macos", "name": "macOS", "status": "coming_soon", "releases": []},
        ],
    }
    with _patched_fetch((payload, True)):
        catalog = releases.platforms()
    assert catalog.known is True
    win = catalog.latest_for("windows")
    assert win.version == "1.0.0"
    assert win.notes == "甲\n乙"
    assert win.size_text == "46.2 MB"
    assert catalog.platform("android").coming_soon is True
    assert [p.key for p in catalog.order()] == ["windows", "android", "linux", "macos"]


def test_fallback_has_windows_and_reserved_slots():
    plats = releases._fallback_platforms()
    assert list(plats.keys()) == ["windows", "android", "linux", "macos"]
    assert plats["windows"].available is True
    assert plats["windows"].latest.version == constants.APP_VERSION
    for key in ("android", "linux", "macos"):
        assert plats[key].coming_soon is True


# ────────────────────── 清单获取（打桩） ──────────────────────


def test_platforms_falls_back_offline():
    with _patched_fetch(({}, False)):
        catalog = releases.platforms()
    assert catalog.known is False
    assert catalog.source == "fallback"
    assert len(catalog.platforms) == 4
    assert catalog.order()[0].key == "windows"


def test_platforms_merges_server_catalog():
    payload = _catalog_payload(windows_version="2.5.0", extra={
        "linux": {"label": "Linux", "status": "coming_soon", "releases": []},
    })
    with _patched_fetch((payload, True)):
        catalog = releases.platforms()
    assert catalog.known is True
    assert catalog.source == "server"
    assert catalog.latest_for("windows").version == "2.5.0"
    assert catalog.platform("linux").coming_soon is True
    # 服务器未提到的平台仍保留兜底预留位
    assert catalog.platform("macos") is not None


def test_platforms_cache_is_reused():
    with _patched_fetch((_catalog_payload(windows_version="3.0.0"), True)):
        first = releases.platforms()
        second = releases.platforms()
    assert first is second


def test_check_reports_new_version():
    with _patched_fetch((_catalog_payload(windows_version="9.9.9"), True)):
        found = releases.check("1.0.0")
    assert found.known is True
    assert found.available is True
    assert found.version == "9.9.9"
    assert found.release is not None
    assert "9.9.9" in found.message


def test_check_current_is_latest():
    with _patched_fetch((_catalog_payload(windows_version=constants.APP_VERSION), True)):
        found = releases.check(constants.APP_VERSION)
    assert found.known is True
    assert found.available is False
    assert found.message == "当前已是最新版本"


def test_check_unknown_when_offline():
    with _patched_fetch(({}, False)):
        found = releases.check("1.0.0")
    assert found.known is False
    assert found.available is False


def test_updater_prefers_release_catalog():
    """有可用的发布清单时，更新检查不应再走远端指纹探测。"""
    with _patched_fetch((_catalog_payload(windows_version="9.9.9"), True)):
        info = updater.check_for_update(manifest_url="https://example.invalid/x.exe")
    assert info.available is True
    assert info.version == "9.9.9"


# ────────────────────── download_to（本地 HTTP 服务器） ──────────────────────


class _Handler(http.server.BaseHTTPRequestHandler):
    """最小 GET 服务器：支持 ``Range: bytes=N-``。"""

    payload = b""
    ranges: list = []

    def log_message(self, *args):  # 静音
        pass

    def do_GET(self):
        cls = type(self)
        if self.path != "/file":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = cls.payload
        range_header = self.headers.get("Range")
        cls.ranges.append(range_header)
        start = 0
        if range_header and range_header.startswith("bytes="):
            token = range_header[len("bytes="):].split("-", 1)[0]
            if token.isdigit():
                start = int(token)
        if start > 0 and start < len(data):
            chunk = data[start:]
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d"
                             % (start, len(data) - 1, len(data)))
        else:
            chunk = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


def _start_server(payload: bytes):
    handler = type("_Handler", (_Handler,), {"payload": payload, "ranges": []})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1], handler


def test_download_to_fresh():
    payload = bytes(range(256)) * 40  # 10240 B
    httpd, port, _handler = _start_server(payload)
    try:
        dest = os.path.join(tempfile.mkdtemp(), "forum.exe")
        ok, err = updater.download_to("http://127.0.0.1:%d/file" % port, dest,
                                     expected=len(payload), resume=True)
        assert ok is True, err
        assert err == ""
        with open(dest, "rb") as fh:
            assert fh.read() == payload
        assert not os.path.exists(dest + ".part")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_download_to_resumes_from_part():
    payload = bytes(range(256)) * 40
    half = len(payload) // 2
    httpd, port, handler = _start_server(payload)
    try:
        folder = tempfile.mkdtemp()
        dest = os.path.join(folder, "forum.exe")
        with open(dest + ".part", "wb") as fh:
            fh.write(payload[:half])
        ok, err = updater.download_to("http://127.0.0.1:%d/file" % port, dest,
                                     expected=len(payload), resume=True)
        assert ok is True, err
        with open(dest, "rb") as fh:
            assert fh.read() == payload
        assert ("bytes=%d-" % half) in handler.ranges
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_download_to_reports_incomplete():
    payload = b"A" * 4096
    httpd, port, _handler = _start_server(payload)
    try:
        dest = os.path.join(tempfile.mkdtemp(), "forum.exe")
        ok, err = updater.download_to("http://127.0.0.1:%d/file" % port, dest,
                                     expected=len(payload) + 500, resume=True)
        assert ok is False
        assert "不完整" in err
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_download_to_missing_resource():
    httpd, port, _handler = _start_server(b"data")
    try:
        dest = os.path.join(tempfile.mkdtemp(), "forum.exe")
        ok, err = updater.download_to("http://127.0.0.1:%d/nope" % port, dest)
        assert ok is False
        assert "404" in err
    finally:
        httpd.shutdown()
        httpd.server_close()


# ────────────────────── 下载页 / 路由契约 ──────────────────────


def test_download_page_contract():
    from app.pages.download import DownloadPage
    assert DownloadPage.ROUTE == "download"
    assert DownloadPage.TITLE == "下载"
    assert DownloadPage.SHOW_WORLD_PANEL is False
    assert constants.APP_DOWNLOAD_PAGE == "/Download"


def test_shell_registers_download_route():
    from app import pages, shell
    # 「下载」已从 APP 导航栏移除（客户端本身就是下载产物），
    # 但路由/页面必须保留：/Download 深链与托盘「打开下载页」仍然依赖它。
    nav_routes = [item[0] for item in shell.NAV_ITEMS]
    assert "download" not in nav_routes
    assert shell.PAGE_MODULES["download"] == ("app.pages.download", "DownloadPage")
    assert "download" in pages.__all__


def test_download_page_helpers():
    from app.pages.download import DownloadPage
    assert DownloadPage._eta_text(30) == "30 秒"
    assert DownloadPage._eta_text(90) == "1 分 30 秒"
    assert DownloadPage._eta_text(3700) == "1 小时 1 分"
    assert DownloadPage._eta_text(None) == "-"
    text = DownloadPage._progress_text(50, 100, 10.0, 0.0)
    assert "%" in text and "/" in text
    named = releases.Release.from_dict(
        {"version": "1.0", "url": "/api/app/windows/forum.exe", "filename": "forum.exe"})
    assert DownloadPage._default_filename("windows", named) == "forum.exe"
    derived = releases.Release.from_dict(
        {"version": "1.0", "url": "/api/app/windows/forum.exe"})
    assert DownloadPage._default_filename("windows", derived) == "forum.exe"


def test_download_page_builds_reserved_slots_offline():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.pages import download as dl_mod
    page = dl_mod.DownloadPage()
    try:
        page._catalog = releases.ReleaseCatalog(
            platforms=releases._fallback_platforms(), known=True)
        page._rebuild_cards()
        keys = [key for key, _card in page._cards]
        assert keys == ["windows", "android", "linux", "macos"]
        assert len(page._cards) == 4
        page._set_filter("windows")
        assert page._filter == "windows"
        page._set_filter("all")
        assert page._filter == "all"
    finally:
        page.deleteLater()
