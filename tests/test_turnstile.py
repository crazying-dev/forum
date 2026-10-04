# -*- coding: utf-8 -*-
"""回归：Cloudflare Turnstile 人机验证（服务端 siteverify 校验）。

覆盖：
  * provider 选择与回退（turnstile / slider / off）；密钥不齐自动回退 slider；
  * siteverify 请求体构造、error-codes → 中文文案映射、hostname 收紧；
  * /api/captcha/challenge 按 provider 下发不同负载（turnstile 不返回图片）；
  * /api/captcha/verify 对 turnstile 只透传 token（token 一次性，不能提前消费）；
  * 业务接口用同一个 captcha_token 字段携带 Turnstile token（接口零改动）；
  * GET /captcha-embed 承载页（Windows QWebEngineView / Android WebView）。

注意：不访问真实网络 —— 所有 siteverify 调用都 monkeypatch 掉 _post_siteverify。
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import config  # noqa: E402
import api.captcha as captcha  # noqa: E402
import api.turnstile as turnstile  # noqa: E402

TEMPLATES = os.path.join(PROJECT_ROOT, "templates")

FAKE_SITEKEY = "0x4AAAAAAA_probe_sitekey"
FAKE_SECRET = "0x4AAAAAAA_probe_secret"


class _Ctx:
    """临时覆盖 config 属性，退出时还原（避免污染同进程内的其他用例）。"""

    def __init__(self, **kw):
        self.kw = kw
        self.old = {}

    def __enter__(self):
        for key, value in self.kw.items():
            self.old[key] = getattr(config, key, None)
            setattr(config, key, value)
        return self

    def __exit__(self, *exc):
        for key, value in self.old.items():
            setattr(config, key, value)
        return False


def _client():
    from flask import Flask, jsonify

    app = Flask(__name__, template_folder=TEMPLATES)
    app.register_blueprint(captcha.captcha_bp, url_prefix="/api/captcha")
    app.register_blueprint(captcha.captcha_embed_bp)

    @app.route("/api/probe", methods=["POST"])
    @captcha.captcha_required
    def _probe():
        return jsonify({"success": True, "probe": True})

    return app.test_client()


def _fake_siteverify(result=None, error=None, calls=None):
    """替换 turnstile._post_siteverify，返回指定的 siteverify 响应。"""
    def _inner(data):
        if calls is not None:
            calls.append(data)
        if error is not None:
            raise error
        return result if result is not None else {"success": True}
    return _inner


# ──────────────────────────
# provider 选择
# ──────────────────────────
def test_provider_default_falls_back_to_slider_without_keys():
    """默认 provider=turnstile，但密钥不齐时必须回退 slider（不把线上打死）。"""
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY="", TURNSTILE_SECRET=""):
        assert captcha._provider() == "slider"
    with _Ctx(CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=""):
        assert captcha._provider() == "slider", "只配 sitekey 也要回退"


def test_provider_turnstile_when_configured():
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        assert captcha._provider() == "turnstile"


def test_provider_off_and_slider_values():
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="slider",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        assert captcha._provider() == "slider", "显式 slider 优先于已配置的密钥"
    for value in ("off", "none", "disable", "disabled", "0", "false"):
        with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER=value,
                  TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
            assert captcha._provider() == "off", f"{value} 应关闭"


def test_provider_disabled_env_wins():
    with _Ctx(CAPTCHA_ENABLED=False, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        assert captcha._provider() == "off"


# ──────────────────────────
# turnstile 模块：纯逻辑
# ──────────────────────────
def test_token_field_matches_slider_field():
    """Turnstile 与自研滑块共用 captcha_token 字段 —— 这是接口零改动的关键。"""
    assert turnstile.TOKEN_FIELD == "captcha_token"


def test_official_test_keys_documented():
    assert turnstile.TEST_SITEKEY == "1x00000000000000000000AA"
    assert turnstile.TEST_SECRET == "1x0000000000000000000000000000000AA"


def test_message_for_maps_error_codes():
    assert "过期" in turnstile.message_for(["timeout-or-duplicate"])
    assert "配置" in turnstile.message_for(["invalid-input-secret"])
    assert "不可用" in turnstile.message_for(["internal-error"])
    assert "失败" in turnstile.message_for(["invalid-input-response"])
    assert turnstile.message_for(["unknown-code"]) == turnstile.DEFAULT_ERROR_MESSAGE
    assert turnstile.message_for([]) == turnstile.DEFAULT_ERROR_MESSAGE
    assert turnstile.message_for(None) == turnstile.DEFAULT_ERROR_MESSAGE
    # 传单个字符串也要能处理
    assert "过期" in turnstile.message_for("timeout-or-duplicate")
    # 多码时取第一个能识别的
    assert "失败" in turnstile.message_for(["bad-request", "timeout-or-duplicate"])


def test_request_payload_shape():
    with _Ctx(TURNSTILE_SECRET=FAKE_SECRET):
        data = turnstile.request_payload("tok", "1.2.3.4")
        assert data["secret"] == FAKE_SECRET
        assert data["response"] == "tok"
        assert data["remoteip"] == "1.2.3.4"
        assert "remoteip" not in turnstile.request_payload("tok")


def test_configured_requires_both_keys():
    with _Ctx(TURNSTILE_SITEKEY="", TURNSTILE_SECRET=""):
        assert turnstile.configured() is False
    with _Ctx(TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=""):
        assert turnstile.configured() is False
    with _Ctx(TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        assert turnstile.configured() is True


def test_verify_url_and_timeout_defaults():
    with _Ctx(TURNSTILE_VERIFY_URL=""):
        assert turnstile.verify_url() == turnstile.DEFAULT_VERIFY_URL
        assert turnstile.verify_url().startswith("https://challenges.cloudflare.com/")
    with _Ctx(TURNSTILE_TIMEOUT="0"):
        assert turnstile.timeout() == 10


# ──────────────────────────
# turnstile 模块：verify_token
# ──────────────────────────
def test_verify_token_empty_rejected():
    with _Ctx(TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        ok, msg = turnstile.verify_token("")
        assert ok is False and "请先完成" in msg


def test_verify_token_unconfigured():
    with _Ctx(TURNSTILE_SITEKEY="", TURNSTILE_SECRET=""):
        ok, msg = turnstile.verify_token("tok")
        assert ok is False and "配置" in msg


def test_verify_token_success():
    calls = []
    with _Ctx(TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        original = turnstile._post_siteverify
        turnstile._post_siteverify = _fake_siteverify(
            {"success": True, "hostname": "www.yjlt.top", "action": "login"}, calls=calls)
        try:
            ok, msg = turnstile.verify_token("tok-1", "9.9.9.9")
        finally:
            turnstile._post_siteverify = original
    assert ok is True and msg == ""
    assert calls and calls[0]["response"] == "tok-1" and calls[0]["remoteip"] == "9.9.9.9"


def test_verify_token_failure_maps_message():
    with _Ctx(TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        original = turnstile._post_siteverify
        try:
            turnstile._post_siteverify = _fake_siteverify({"success": False, "error-codes": ["timeout-or-duplicate"]})
            ok, msg = turnstile.verify_token("tok")
            assert ok is False and "过期" in msg
            turnstile._post_siteverify = _fake_siteverify({"success": False, "error-codes": ["invalid-input-response"]})
            ok, msg = turnstile.verify_token("tok")
            assert ok is False and "失败" in msg
        finally:
            turnstile._post_siteverify = original


def test_verify_token_network_error_is_friendly():
    with _Ctx(TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        original = turnstile._post_siteverify
        turnstile._post_siteverify = _fake_siteverify(error=OSError("boom"))
        try:
            ok, msg = turnstile.verify_token("tok")
        finally:
            turnstile._post_siteverify = original
    assert ok is False and "稍后重试" in msg


def test_verify_token_hostname_check():
    with _Ctx(TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET,
              TURNSTILE_EXPECTED_HOSTNAME="www.yjlt.top"):
        original = turnstile._post_siteverify
        try:
            turnstile._post_siteverify = _fake_siteverify({"success": True, "hostname": "evil.example"})
            ok, msg = turnstile.verify_token("tok")
            assert ok is False, "hostname 不匹配必须拒绝"
            turnstile._post_siteverify = _fake_siteverify({"success": True, "hostname": "WWW.YJLT.TOP"})
            ok, _msg = turnstile.verify_token("tok")
            assert ok is True, "hostname 比对应忽略大小写"
        finally:
            turnstile._post_siteverify = original


# ──────────────────────────
# /api/captcha/challenge
# ──────────────────────────
def test_challenge_returns_turnstile_config():
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        body = _client().post("/api/captcha/challenge").get_json()
    assert body["success"] is True
    assert body["enabled"] is True
    assert body["provider"] == "turnstile"
    assert body["sitekey"] == FAKE_SITEKEY
    assert body["embed_url"] == "/captcha-embed"
    assert "bg" not in body and "piece" not in body, "turnstile 不应下发图片"


def test_challenge_returns_slider_payload():
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="slider"):
        body = _client().post("/api/captcha/challenge").get_json()
    assert body["provider"] == "slider"
    assert body["bg"].startswith("data:image/png;base64,")
    assert body["piece"].startswith("data:image/png;base64,")


def test_challenge_disabled_returns_enabled_false():
    with _Ctx(CAPTCHA_ENABLED=False):
        body = _client().post("/api/captcha/challenge").get_json()
    assert body["success"] is True and body["enabled"] is False


# ──────────────────────────
# 业务接口 + /verify
# ──────────────────────────
def test_business_endpoint_requires_turnstile_token():
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        client = _client()
        miss = client.post("/api/probe", json={})
        assert miss.status_code == 400
        body = miss.get_json()
        assert body["code"] == "CAPTCHA_REQUIRED"
        assert "人机验证" in body["message"]

        original = turnstile._post_siteverify
        turnstile._post_siteverify = _fake_siteverify({"success": True, "hostname": "www.yjlt.top"})
        try:
            ok = client.post("/api/probe", json={"captcha_token": "turnstile-token"})
        finally:
            turnstile._post_siteverify = original
        assert ok.status_code == 200
        assert ok.get_json()["probe"] is True


def test_business_endpoint_blocks_when_siteverify_fails():
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        original = turnstile._post_siteverify
        turnstile._post_siteverify = _fake_siteverify({"success": False, "error-codes": ["invalid-input-response"]})
        try:
            resp = _client().post("/api/probe", json={"captcha_token": "bad"})
        finally:
            turnstile._post_siteverify = original
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "CAPTCHA_REQUIRED"


def test_verify_endpoint_passthrough_for_turnstile():
    """turnstile 的 token 一次性：/verify 只能透传，不能提前消费。"""
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        client = _client()
        resp = client.post("/api/captcha/verify", json={"captcha_token": "tok-abc"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["token"] == "tok-abc", "必须原样回传 token 供业务请求使用"
        assert body["provider"] == "turnstile"

        miss = client.post("/api/captcha/verify", json={})
        assert miss.status_code == 400
        assert miss.get_json()["code"] == "CAPTCHA_REQUIRED"


def test_verify_endpoint_slider_path_untouched():
    """provider=slider 时 /verify 仍是原来的两步式行为。"""
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="slider"):
        client = _client()
        ch = client.post("/api/captcha/challenge").get_json()
        answer = captcha._store[ch["token"]]["answer_x"]
        ok = client.post("/api/captcha/verify",
                         json={"captcha_token": ch["token"], "captcha_x": answer})
        assert ok.status_code == 200
        bad = client.post("/api/captcha/verify",
                          json={"captcha_token": ch["token"], "captcha_x": answer + 999})
        assert bad.status_code == 400


# ──────────────────────────
# /captcha-embed 承载页
# ──────────────────────────
def test_embed_page_renders_turnstile_widget():
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        resp = _client().get("/captcha-embed")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert FAKE_SITEKEY in html, "承载页必须注入 sitekey"
    assert "challenges.cloudflare.com/turnstile/v0/api.js" in html
    assert "render=explicit" in html
    assert "document.title" in html, "缺少 document.title 回传兜底"
    assert "AndroidCaptcha" in html, "缺少 Android JS bridge"


def test_embed_page_honours_theme_and_lang():
    with _Ctx(CAPTCHA_ENABLED=True, CAPTCHA_PROVIDER="turnstile",
              TURNSTILE_SITEKEY=FAKE_SITEKEY, TURNSTILE_SECRET=FAKE_SECRET):
        html = _client().get("/captcha-embed?theme=dark&lang=en").get_data(as_text=True)
    assert 'data-theme="dark"' in html
    assert "'en'" in html or '"en"' in html


def test_embed_page_when_provider_off():
    with _Ctx(CAPTCHA_ENABLED=False):
        resp = _client().get("/captcha-embed")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "off" in html, "未配置 provider 时页面应告知已关闭"


# ──────────────────────────
# 配置默认值
# ──────────────────────────
def test_config_captcha_provider_default_is_turnstile():
    """源码默认值是 turnstile；实际生效值由 _provider() 决定（密钥不齐回退）。"""
    import io as _io
    src = _io.open(os.path.join(PROJECT_ROOT, "config.py"), encoding="utf-8").read()
    assert 'os.getenv("CAPTCHA_PROVIDER", "turnstile")' in src
    assert "TURNSTILE_SITEKEY" in src and "TURNSTILE_SECRET" in src
    assert "TURNSTILE_VERIFY_URL" in src and "TURNSTILE_TIMEOUT" in src
    assert "TURNSTILE_EXPECTED_HOSTNAME" in src


def test_slider_tolerance_widened_to_twelve():
    assert config.CAPTCHA_TOLERANCE == 12


def test_embed_blueprint_registered_in_api():
    """api/__init__.py 必须注册承载页蓝图（否则 /captcha-embed 404）。"""
    path = os.path.join(PROJECT_ROOT, "api", "__init__.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "captcha_embed_bp" in src
    assert "app.register_blueprint(captcha_embed_bp)" in src


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS  " + name)
        except Exception as e:  # noqa: BLE001
            print("FAIL  %s: %s: %s" % (name, type(e).__name__, e))
            failed += 1
    print("\n%d/%d passed, %d failed" % (len(tests) - failed, len(tests), failed))
    sys.exit(0 if failed == 0 else 1)
