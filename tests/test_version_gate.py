# -*- coding: utf-8 -*-
"""V1.3.14 新增：服务端「最低版本闸门」的客户端侧离线用例。

覆盖：

* 每个请求都携带 ``X-Client-Platform`` / ``X-Client-Version``；
* 命中 ``426``（或响应体 ``code == VERSION_TOO_LOW``）时只通知一次；
* 「版本过低」弹窗不可关闭（Esc / 标题栏 / 外部点击均无效），
  只提供「去更新」与「退出应用」。

不依赖 pytest：``tests/run_tests.py`` 以无参形式逐个调用用例函数。
"""

from __future__ import annotations

import os
import tempfile

import requests

from app import api as api_mod
from app import constants, session_store
from app import widgets  # noqa: F401  （确保包已导入）


# ────────────────────── 小工具 ──────────────────────


def _qt():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])


def _client() -> api_mod.ForumApi:
    store = session_store.SessionStore(
        os.path.join(tempfile.mkdtemp(prefix="vg-\u4e34\u65f6"), "account.bin"))
    return api_mod.ForumApi(store=store)


class _FakeResponse:
    def __init__(self, status: int, text: str) -> None:
        self.status_code = status
        self.text = text
        self.headers: dict = {}


class _FakeSession:
    """最小可用的 ``requests.Session`` 替身（只实现 .headers / .cookies / .request）。"""

    def __init__(self, response: _FakeResponse) -> None:
        self.headers: dict = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.verify = True
        self._response = response
        self.calls = 0

    def request(self, *args, **kwargs):  # noqa: D102
        self.calls += 1
        return self._response


def _patch(obj, name, value):
    old = getattr(obj, name, None)
    setattr(obj, name, value)
    return old


# ────────────────────── 请求头 ──────────────────────


def test_client_header_constants():
    assert constants.CLIENT_PLATFORM == "windows"
    assert constants.CLIENT_UA == "CrForum-Windows/%s" % constants.APP_VERSION
    assert constants.CLIENT_HEADERS == {
        "X-Client-Platform": "windows",
        "X-Client-Version": constants.APP_VERSION,
    }


def test_session_carries_client_headers():
    client = _client()
    headers = client.session.headers
    assert headers.get("X-Client-Platform") == "windows"
    assert headers.get("X-Client-Version") == constants.APP_VERSION
    # 原有头不能丢
    assert headers.get("User-Agent") == constants.CLIENT_UA
    assert headers.get("Accept-Language")


def test_fetch_helpers_carry_client_headers():
    seen: list[dict] = []
    original = requests.get

    def _fake_get(url, **kwargs):
        seen.append(dict(kwargs.get("headers") or {}))
        raise requests.RequestException("离线用例")

    requests.get = _fake_get
    try:
        client = _client()
        assert client.fetch_text("https://example.invalid/a") == ""
        assert client.fetch_json("https://example.invalid/b") is None
    finally:
        requests.get = original

    assert len(seen) == 2, seen
    for headers in seen:
        assert headers.get("X-Client-Platform") == "windows", headers
        assert headers.get("X-Client-Version") == constants.APP_VERSION, headers


def test_image_cache_download_carries_client_headers():
    from app.widgets import images as images_mod
    original = requests.get
    seen: list[dict] = []

    def _fake_get(url, **kwargs):
        seen.append(dict(kwargs.get("headers") or {}))
        raise requests.RequestException("离线用例")

    requests.get = _fake_get
    try:
        cache = images_mod.ImageCache()
        try:
            cache._download("https://example.invalid/avatar.png")
        except Exception:  # noqa: BLE001
            pass
    finally:
        requests.get = original

    assert seen, "图片下载未发出请求"
    assert seen[0].get("X-Client-Platform") == "windows"
    assert seen[0].get("X-Client-Version") == constants.APP_VERSION


# ────────────────────── 426 识别与通知 ──────────────────────


def test_426_triggers_listener_once():
    body = ('{"success": false, "code": "VERSION_TOO_LOW", '
            '"message": "\u7248\u672c\u8fc7\u4f4e\uff0c\u8bf7\u66f4\u65b0", '
            '"min_version": "1.3.14", '
            '"download_url": "https://yjlt.top/Download"}')
    client = _client()
    client.session = _FakeSession(_FakeResponse(426, body))
    got: list[dict] = []
    client.add_version_too_low_listener(got.append)

    first = client.get("/api/posts")
    assert first.status == 426
    assert first.ok is False
    assert len(got) == 1, got
    assert got[0].get("code") == api_mod.VERSION_TOO_LOW_CODE
    assert got[0].get("min_version") == "1.3.14"

    # 第二次（及以后）不再重复弹窗
    client.get("/api/posts")
    client.post("/api/user/login", {"password": "x"})
    assert len(got) == 1, got


def test_business_code_without_426_also_triggers():
    body = '{"success": false, "code": "VERSION_TOO_LOW", "message": "\u7248\u672c\u8fc7\u4f4e"}'
    client = _client()
    client.session = _FakeSession(_FakeResponse(400, body))
    got: list[dict] = []
    client.add_version_too_low_listener(got.append)
    client.get("/api/posts")
    assert len(got) == 1, got


def test_normal_response_does_not_trigger():
    client = _client()
    client.session = _FakeSession(_FakeResponse(200, '{"posts": []}'))
    got: list[dict] = []
    client.add_version_too_low_listener(got.append)
    result = client.get("/api/posts")
    assert result.ok is True
    assert got == []


def test_listener_registration_is_idempotent():
    client = _client()
    got: list[dict] = []
    client.add_version_too_low_listener(got.append)
    client.add_version_too_low_listener(got.append)
    assert len(client._version_listeners) == 1


def test_listener_exception_is_swallowed():
    client = _client()
    client.session = _FakeSession(
        _FakeResponse(426, '{"code": "VERSION_TOO_LOW"}'))

    def _boom(_payload):
        raise RuntimeError("listener 崩了也不能影响请求")

    client.add_version_too_low_listener(_boom)
    result = client.get("/api/posts")
    assert result.status == 426


# ────────────────────── 「版本过低」弹窗（强制） ──────────────────────


def test_forced_dialog_has_no_close_button_and_two_actions():
    _qt()
    from PyQt6.QtWidgets import QAbstractButton
    from app.widgets.dialogs import VersionTooLowDialog

    dialog = VersionTooLowDialog("\u7248\u672c\u8fc7\u4f4e\uff0c\u8bf7\u66f4\u65b0",
                                 "https://yjlt.top/Download")
    texts = [b.text() for b in dialog.findChildren(QAbstractButton)]
    assert "\u53bb\u66f4\u65b0" in texts, texts
    assert "\u9000\u51fa\u5e94\u7528" in texts, texts
    assert "\u2715" not in texts, texts
    assert len(texts) == 2, texts
    dialog.deleteLater()


def test_forced_dialog_ignores_reject_and_close():
    _qt()
    from PyQt6.QtGui import QCloseEvent
    from app.widgets.dialogs import VersionTooLowDialog

    dialog = VersionTooLowDialog("\u7248\u672c\u8fc7\u4f4e")
    dialog.show()
    dialog.reject()
    # reject() 被忽略：对话框仍在展示，result 仍为 0（未 Accepted/Rejected）
    assert dialog.result() == 0
    assert dialog.isVisible() is True

    event = QCloseEvent()
    dialog.closeEvent(event)
    assert event.isAccepted() is False
    assert dialog.isVisible() is True
    dialog.hide()
    dialog.deleteLater()


def test_base_dialog_default_is_closable():
    _qt()
    from PyQt6.QtWidgets import QAbstractButton
    from app.widgets.dialogs import BaseDialog

    dialog = BaseDialog(title="\u5bf9\u6bd4")
    texts = [b.text() for b in dialog.findChildren(QAbstractButton)]
    assert "\u2715" in texts, texts
    dialog.deleteLater()
