# -*- coding: utf-8 -*-
"""人机验证的客户端侧离线用例。

V1.3.15 新增（自研滑块）：

* ``api.CAPTCHA_PROTECTED_ENDPOINTS`` 与 10 个受保护方法的 ``captcha_token`` 透传；
* ``api._with_captcha`` 的合并语义（空串不写入，保持旧请求体口径）；
* ``captcha_challenge`` / ``captcha_verify`` 两个新接口的路径与请求体；
* ``SliderCaptchaDialog._apply_challenge`` 的渲染状态（与网络解耦）；
* ``SliderStage`` 的“手柄位置 ↔ 拼图块 x”映射与钳位；
* 各调用点已接入 ``ask_captcha``（源码扫描）。

V1.3.16 扩展（Cloudflare Turnstile）：

* ``provider_of`` / ``embed_url`` / ``event_of`` / ``token_from_event`` 四个纯函数；
* 弹窗在滑块舞台与内嵌 WebView 之间切换、以及接收 ``captcha:...`` 标题事件；
* ``main.py`` 必须在 ``QApplication`` 之前导入 WebEngine（源码扫描）。

不依赖 pytest / 不联网：直接由 tests/run_tests.py 调用。
"""

from __future__ import annotations

import base64
import os
import tempfile

from PyQt6.QtWidgets import QApplication

from app import api as api_mod
from app import constants

_app = None


def _app_instance():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _client():
    from app import session_store
    return api_mod.ForumApi(store=session_store.SessionStore(
        os.path.join(tempfile.mkdtemp(), "captcha.bin")))


def _png_data_url(color: str = "#336699", size: int = 12) -> str:
    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QColor, QPixmap

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    raw = bytes(buffer.data())
    buffer.close()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _challenge_payload(token: str = "TOKEN-1") -> dict:
    return {
        "success": True,
        "token": token,
        "bg": _png_data_url("#225577"),
        "piece": _png_data_url("#88ccaa"),
        "y": 42,
        "width": 320,
        "height": 180,
        "piece_size": 50,
        "expires_in": 300,
    }


# ────────────────────── 常量 / 请求体 ──────────────────────


_GATED_CALLS = (
    ("login", lambda c, t: c.login("pw", captcha_token=t), "/api/user/login"),
    ("register", lambda c, t: c.register("n", "a@b.c", "pw12345", "123456",
                                         captcha_token=t),
     "/api/user/register"),
    ("send_register_code", lambda c, t: c.send_register_code("a@b.c", captcha_token=t),
     "/api/email/send-register-code"),
    ("send_reset_code", lambda c, t: c.send_reset_code("a@b.c", captcha_token=t),
     "/api/email/send-code-reset-password"),
    ("reset_password_by_code",
     lambda c, t: c.reset_password_by_code("a@b.c", "123456", "pw12345", captcha_token=t),
     "/api/email/reset-password-by-code"),
    ("send_change_password_code",
     lambda c, t: c.send_change_password_code(captcha_token=t),
     "/api/email/send-change-password-code"),
    ("send_change_email_old_code",
     lambda c, t: c.send_change_email_old_code(captcha_token=t),
     "/api/email/send-change-email-old-code"),
    ("send_change_email_code",
     lambda c, t: c.send_change_email_code("a@b.c", captcha_token=t),
     "/api/email/send-change-email-code"),
    ("send_delete_account_code",
     lambda c, t: c.send_delete_account_code(captcha_token=t),
     "/api/email/send-delete-account-code"),
    ("delete_account",
     lambda c, t: c.delete_account("purge", password="pw", captcha_token=t),
     "/api/user/delete"),
)


def test_captcha_required_code_matches_server():
    assert api_mod.CAPTCHA_REQUIRED_CODE == "CAPTCHA_REQUIRED"


def test_captcha_protected_endpoints_constant():
    endpoints = api_mod.CAPTCHA_PROTECTED_ENDPOINTS
    assert len(endpoints) == 10, endpoints
    assert len(set(endpoints)) == 10, "不应有重复"
    assert all(item.startswith("/api/") for item in endpoints)
    # 服务端 @captcha_required 的 11 个端点中，Windows 客户端不调用 send-verify-email
    assert "/api/email/send-verify-email" not in endpoints
    # 终止步骤（不需验证码）：客户端不弹滑块
    assert "/api/user/password" not in endpoints
    assert "/api/user/email" not in endpoints
    # 与下方受保护方法的路径完全一致
    assert set(endpoints) == {path for _n, _fn, path in _GATED_CALLS}


def test_with_captcha_merges_token():
    payload = {"a": 1}
    assert api_mod._with_captcha(payload, "") == {"a": 1}
    assert api_mod._with_captcha(payload, "  ") == {"a": 1}
    merged = api_mod._with_captcha(payload, " TK ")
    assert merged == {"a": 1, "captcha_token": "TK"}
    assert payload == {"a": 1}, "原请求体不应被修改"
    assert api_mod._with_captcha(None, "TK") is None


def test_gated_methods_send_captcha_token():
    client = _client()
    calls: list[tuple] = []

    def _fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("json_body")))
        return api_mod.Result(200, {"success": True,
                                    "user": {"id": "RL1", "name": "小黑"}})

    client.request = _fake_request  # type: ignore[assignment]
    for name, invoke, path in _GATED_CALLS:
        calls.clear()
        client._user = {"id": "RL1", "name": "小黑"}
        invoke(client, "TK")
        method, got_path, body = calls[-1]
        assert method == "POST", name
        assert got_path == path, (name, got_path)
        assert isinstance(body, dict), name
        assert body.get("captcha_token") == "TK", name
        # 不传 token 时不写入该字段（服务端关闭人机验证时的旧口径）
        calls.clear()
        client._user = {"id": "RL1", "name": "小黑"}
        invoke(client, "")
        _m, _p, body2 = calls[-1]
        assert "captcha_token" not in (body2 or {}), name


def test_captcha_endpoints_paths_and_bodies():
    client = _client()
    calls: list[tuple] = []

    def _fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs.get("json_body")))
        return api_mod.Result(200, {"success": True})

    client.request = _fake_request  # type: ignore[assignment]
    client.captcha_challenge()
    assert calls[-1][0] == "POST"
    assert calls[-1][1] == "/api/captcha/challenge"
    # 回退通道：强制 provider=slider（大小写 / 空白归一化）
    client.captcha_challenge("slider")
    assert calls[-1][1] == "/api/captcha/challenge?provider=slider"
    client.captcha_challenge("  SLIDER ")
    assert calls[-1][1] == "/api/captcha/challenge?provider=slider"
    client.captcha_verify("TK", 123.5)
    method, path, body = calls[-1]
    assert method == "POST" and path == "/api/captcha/verify"
    assert body == {"captcha_token": "TK", "captcha_x": 123.5}


# ────────────────────── 图像解码 ──────────────────────


def test_decode_data_url():
    _app_instance()
    from app.widgets.captcha import decode_data_url

    assert decode_data_url("") == b""
    assert decode_data_url("data:image/png;base64," +
                          base64.b64encode(b"abc").decode("ascii")) == b"abc"
    assert decode_data_url("###not-base64###") == b""


# ────────────────────── 舞台映射 ──────────────────────


def test_slider_stage_mapping_and_clamp():
    _app_instance()
    from PyQt6.QtGui import QPixmap
    from app.widgets.captcha import SliderStage

    stage = SliderStage()
    try:
        stage.set_challenge(QPixmap(), QPixmap(), width=320, height=180,
                            piece_size=50, piece_y=30)
        assert stage.stage_w == 320 and stage.stage_h == 180
        assert stage.piece_y == 30
        assert stage.max_piece_x() == 270.0
        lo, hi = stage.handle_limits()
        stage.set_drag(0.0)
        assert abs(stage.handle_x() - lo) < 0.001
        stage.set_drag(stage.max_piece_x())
        assert abs(stage.handle_x() - hi) < 0.001
        stage.set_drag(9999)          # 越界钳位
        assert stage.drag_x == stage.max_piece_x()
        stage.set_drag(-5)
        assert stage.drag_x == 0.0
        # 手柄越往右、拼图块越靠右（单调）
        stage.set_drag(100)
        first = stage.handle_x()
        stage.set_drag(200)
        assert stage.handle_x() > first
    finally:
        stage.deleteLater()


# ────────────────────── 弹窗渲染状态 ──────────────────────


def test_slider_captcha_dialog_applies_challenge():
    _app_instance()
    from app.widgets.captcha import SliderCaptchaDialog

    dialog = SliderCaptchaDialog(None, autostart=False)
    try:
        assert dialog.result_token == ""
        assert dialog.enabled is True
        assert dialog.stage.is_enabled() is False, "未拿到挑战前不可拖动"
        dialog._apply_challenge(_challenge_payload("TOKEN-ABC"))
        assert dialog._challenge_token == "TOKEN-ABC"
        assert dialog.stage.is_enabled() is True
        assert dialog.stage.piece_y == 42
        assert dialog.stage.stage_w == 320 and dialog.stage.stage_h == 180
        assert dialog.stage.piece_size == 50
        assert dialog.stage.drag_x == 0.0
        # 素材不可用时不应启用拖动
        dialog._apply_challenge({"token": "X", "bg": "", "piece": ""})
        assert dialog._challenge_token == ""
        assert dialog.stage.is_enabled() is False
    finally:
        dialog.deleteLater()


def test_ask_captcha_is_callable():
    _app_instance()
    from app.widgets import captcha as captcha_mod
    from app.pages.base import Page

    assert callable(captcha_mod.ask_captcha)
    assert callable(getattr(Page, "ask_captcha", None)), \
        "Page.ask_captcha 必须在（各页面统一入口）"


# ────────────────────── 调用点接入（源码扫描） ──────────────────────


def _read(relative: str) -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(constants.__file__)))
    with open(os.path.join(root, relative), "r", encoding="utf-8") as handle:
        return handle.read()


def test_call_sites_wire_captcha():
    auth = _read(os.path.join("app", "pages", "auth.py"))
    profile = _read(os.path.join("app", "pages", "profile.py"))
    dialogs = _read(os.path.join("app", "widgets", "dialogs.py"))
    api_src = _read(os.path.join("app", "api.py"))

    assert auth.count("ask_captcha()") >= 4, "登录/注册/发码x2/重置 至少 5 处"
    assert auth.count("captcha_token=token") >= 4
    assert "ask_captcha" in profile and profile.count("captcha_token=token") >= 3
    assert "ask_captcha" in dialogs and "captcha_token=token" in dialogs
    # api 层：请求体合并 + 两个新接口
    assert "/api/captcha/challenge" in api_src
    assert "/api/captcha/verify" in api_src
    assert "def _with_captcha" in api_src
    for _name, _invoke, path in _GATED_CALLS:
        assert '"%s"' % path in api_src, path


# ────────────────────── provider / 内嵌验证页（V1.3.16） ──────────────────────


def test_provider_constants_match_server():
    from app.widgets import captcha as c

    assert c.PROVIDER_SLIDER == "slider"
    assert c.PROVIDER_TURNSTILE == "turnstile"
    assert c.PROVIDER_OFF == "off"
    assert c.EMBED_PATH == "/captcha-embed"
    assert c.EVENT_PREFIX == "captcha:"
    assert c.EMBED_SIZE == "flexible"


def test_provider_of_normalises_and_falls_back_to_slider():
    from app.widgets import captcha as c

    assert c.provider_of("turnstile") == c.PROVIDER_TURNSTILE
    assert c.provider_of("  TURNSTILE  ") == c.PROVIDER_TURNSTILE
    assert c.provider_of("slider") == c.PROVIDER_SLIDER
    for raw in ("off", "none", "disable", "disabled", "0", "false", "OFF"):
        assert c.provider_of(raw) == c.PROVIDER_OFF, raw
    for raw in ("", None, "???", "cloudflare"):
        assert c.provider_of(raw) == c.PROVIDER_SLIDER, raw


def test_embed_url_builds_absolute_url_with_query():
    from app.widgets import captcha as c

    url = c.embed_url("https://www.yjlt.top", "/captcha-embed", "dark", "normal")
    assert url == "https://www.yjlt.top/captcha-embed?theme=dark&size=normal"


def test_embed_url_defaults_are_light_and_flexible():
    from app.widgets import captcha as c

    # 末尾斜杠会被归一化；theme/size 非法一律回退 light + flexible
    assert c.embed_url("https://www.yjlt.top/", None, None, None) == \
        "https://www.yjlt.top/captcha-embed?theme=light&size=flexible"
    assert c.embed_url("https://www.yjlt.top", "", "LIGHT", "huge").endswith(
        "?theme=light&size=flexible")
    assert c.embed_url("https://www.yjlt.top", None, "National", "").endswith(
        "?theme=light&size=flexible")


def test_embed_url_accepts_absolute_and_protocol_relative_paths():
    from app.widgets import captcha as c

    # 已带 query 时用 & 拼接
    absolute = c.embed_url("https://www.yjlt.top",
                           "https://cdn.example.com/embed?x=1", None, "compact")
    assert absolute == "https://cdn.example.com/embed?x=1&theme=light&size=compact"
    # 协议相对地址补 https:
    assert c.embed_url("https://www.yjlt.top", "//cdn.example.com/e", "dark", "normal") == \
        "https://cdn.example.com/e?theme=dark&size=normal"
    # 相对路径自动补 / 与 base
    assert c.embed_url("https://www.yjlt.top", "captcha-embed", None, None) == \
        "https://www.yjlt.top/captcha-embed?theme=light&size=flexible"


def test_event_of_parses_kind_and_payload():
    from app.widgets import captcha as c

    assert c.event_of("captcha:token:ABC") == ("token", "ABC")
    assert c.event_of("captcha:error:disabled") == ("error", "disabled")
    # 只在首个冒号处切分：token 里的冒号原样保留
    assert c.event_of("captcha:token:a:b:c") == ("token", "a:b:c")
    assert c.event_of("captcha:token:") == ("token", "")
    assert c.event_of("captcha:TOKEN:X") == ("token", "X")
    assert c.event_of("captcha::X") is None
    assert c.event_of("captcha:") is None
    assert c.event_of("安全验证") is None
    assert c.event_of("about:blank") is None
    assert c.event_of("") is None
    assert c.event_of(None) is None


def test_token_from_event_only_accepts_token_kind():
    from app.widgets import captcha as c

    long_token = "T" * 2048          # Turnstile token 上限 2048，且不能被截断
    assert c.token_from_event("captcha:token:" + long_token) == long_token
    assert c.token_from_event("captcha:token:  TK  ") == "TK"
    assert c.token_from_event("captcha:token:") is None
    assert c.token_from_event("captcha:error:x") is None
    assert c.token_from_event("captcha:") is None
    assert c.token_from_event("nope") is None
    assert c.token_from_event(None) is None


# ────────────────────── 弹窗：滑块 ↔ 内嵌页切换 ──────────────────────


def test_dialog_switches_between_stage_and_embed():
    _app_instance()
    from app.widgets.captcha import SliderCaptchaDialog

    dialog = SliderCaptchaDialog(None, autostart=False)
    try:
        assert dialog.provider == "slider"
        assert dialog.stage.isHidden() is False
        assert dialog.refresh_btn.text() == "换一张"
        dialog._show_embed()
        assert dialog.stage.isHidden() is True
        dialog._show_stage()
        assert dialog.stage.isHidden() is False
    finally:
        dialog.deleteLater()


def test_dialog_turnstile_without_sitekey_falls_back_to_slider():
    _app_instance()
    from app.widgets import captcha as c
    from app.widgets.captcha import SliderCaptchaDialog

    dialog = SliderCaptchaDialog(None, autostart=False)
    orig = c.api_mod.run_async
    c.api_mod.run_async = lambda fn, *a, **k: None   # 拦截网络
    try:
        # 服务端给了 provider 但没给 sitekey（理论上不会发生）→ 不能白屏，改走滑块
        dialog._apply_turnstile({"provider": "turnstile"})
        assert dialog.provider == "slider"
        assert dialog.stage.isHidden() is False
        assert dialog.refresh_btn.text() == "换一张"
    finally:
        c.api_mod.run_async = orig
        dialog.deleteLater()


def test_dialog_consumes_embed_token_events():
    _app_instance()
    from PyQt6.QtWidgets import QDialog
    from app.widgets.captcha import SliderCaptchaDialog

    dialog = SliderCaptchaDialog(None, autostart=False)
    try:
        dialog.provider = "turnstile"
        dialog._on_embed_title("安全验证")          # 页面标题，不属于协议 → 忽略
        assert dialog.result_token == ""
        dialog._on_embed_title("captcha:token:" + "K" * 2048)
        assert dialog.result_token == "K" * 2048
        assert dialog.result() == QDialog.DialogCode.Accepted
    finally:
        dialog.deleteLater()


def test_dialog_falls_back_to_slider_on_turnstile_error():
    """Turnstile 报错 / 加载失败 → 自动回退自研滑块（只回退一次）。"""
    _app_instance()
    from app.widgets import captcha as c
    from app.widgets.captcha import SliderCaptchaDialog

    dialog = SliderCaptchaDialog(None, autostart=False)
    orig = c.api_mod.run_async
    c.api_mod.run_async = lambda fn, *a, **k: None   # 拦截网络
    try:
        dialog.provider = c.PROVIDER_TURNSTILE
        dialog._on_embed_error("组件炸了")
        assert dialog.provider == c.PROVIDER_SLIDER, "Turnstile 报错应回退自研滑块"
        assert dialog.refresh_btn.text() == "换一张"
        assert dialog.stage.isHidden() is False

        # 回退已用过：再报错只展示文案，不再回退
        dialog.provider = c.PROVIDER_TURNSTILE
        dialog._on_embed_error("disabled")
        assert "已关闭" in dialog.status.text()
        dialog._on_embed_error("unconfigured")
        assert "未配置" in dialog.status.text()
        dialog._on_embed_error("组件炸了")          # 未知短码原样展示
        assert dialog.status.text() == "组件炸了"

        # 承载页加载失败同样触发回退（新弹窗）
        other = SliderCaptchaDialog(None, autostart=False)
        other.provider = c.PROVIDER_TURNSTILE
        other._on_embed_load_finished(False)
        assert other.provider == c.PROVIDER_SLIDER
        other.deleteLater()
    finally:
        c.api_mod.run_async = orig
        dialog.deleteLater()


def test_dialog_ignores_events_when_provider_is_slider():
    _app_instance()
    from app.widgets.captcha import SliderCaptchaDialog

    dialog = SliderCaptchaDialog(None, autostart=False)
    try:
        assert dialog.provider == "slider"
        dialog._on_embed_title("captcha:token:SHOULD-NOT-WIN")
        assert dialog.result_token == "", "非 turnstile provider 不得采信标题事件"
    finally:
        dialog.deleteLater()


# ────────────────────── 装配检查（源码扫描） ──────────────────────


def test_captcha_module_wires_turnstile_embed():
    src = _read(os.path.join("app", "widgets", "captcha.py"))
    assert "PyQt6.QtWebEngineWidgets" in src
    assert "titleChanged" in src
    assert "PROVIDER_TURNSTILE" in src
    assert "embed_url(" in src and "embed_path_of(" in src
    assert "event_of(" in src and "token_from_event(" in src
    assert "captcha_area" in src
    # 回退通道（Turnstile 解不出来 → 自研滑块）
    assert "loadFinished" in src, "承载页加载失败必须能感知"
    assert "_fallback_to_slider(" in src, "缺少 Turnstile → 滑块回退入口"


def test_main_imports_webengine_before_qapplication():
    src = _read("main.py")
    assert "PyQt6.QtWebEngineWidgets" in src
    assert "AA_ShareOpenGLContexts" in src
    idx_import = src.find("import PyQt6.QtWebEngineWidgets")
    idx_app = src.find("QApplication(argv)")
    assert idx_import != -1 and idx_app != -1
    assert idx_import < idx_app, "WebEngine 必须在 QApplication 之前导入"


def test_requirements_declare_webengine():
    req = _read(os.path.join("requirements.txt"))
    assert "PyQt6-WebEngine" in req, "内嵌 Turnstile 依赖必须写入 requirements.txt"


def test_packaging_collects_webengine():
    spec = _read(os.path.join("packaging", "forum.spec"))
    assert "PyQt6.QtWebEngineWidgets" in spec, "打包配置必须显式收集 WebEngine"
