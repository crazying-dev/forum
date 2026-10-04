# -*- coding: utf-8 -*-
"""回归：滑块拼图人机验证（captcha）。

规则：
  * POST /api/captcha/challenge 发挑战（token + 背景图 + 拼图块，base64 data URL）；
  * 一步式：业务请求直接带 {captcha_token, captcha_x}；
  * 两步式：先 POST /api/captcha/verify 校验，再用同一 token 提交业务请求；
  * 服务端内存字典：IP 绑定 + 一次性（校验时 pop）+ 默认 5 分钟过期；
  * 容差默认 ±6px；CAPTCHA_ENABLED=0 时整体放行。
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def _client(extra_routes=True):
    """最小 Flask app：只挂 captcha 蓝图 + 一个受保护探针接口。"""
    from flask import Flask, jsonify

    import api.captcha as captcha

    app = Flask(__name__)
    app.register_blueprint(captcha.captcha_bp, url_prefix="/api/captcha")

    @app.route("/api/probe", methods=["POST"])
    @captcha.captcha_required
    def _probe():
        return jsonify({"success": True, "probe": True})

    return app.test_client()


def _challenge(client, xff=None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    resp = client.post("/api/captcha/challenge", headers=headers)
    assert resp.status_code == 200, f"challenge 应 200，实际 {resp.status_code}"
    return resp.get_json()


def _answer(token):
    import api.captcha as captcha

    return captcha._store[token]["answer_x"]


def test_challenge_payload_shape():
    """challenge 返回结构化字段 + 两张 base64 图 + 合理尺寸。"""
    import config

    client = _client()
    body = _challenge(client)
    assert body["success"] is True
    assert isinstance(body["token"], str) and len(body["token"]) >= 16
    assert body["bg"].startswith("data:image/png;base64,"), "背景图应内联为 data URL"
    assert body["piece"].startswith("data:image/png;base64,"), "拼图块应内联为 data URL"
    assert body["width"] == config.CAPTCHA_WIDTH
    assert body["height"] == config.CAPTCHA_HEIGHT
    assert 0 < body["y"] < body["height"], "拼图块纵向位置应在图内"
    assert body["expires_in"] == config.CAPTCHA_TTL_SECONDS


def test_direct_one_shot_passes_then_token_burned():
    """一步式：正确 x 直接通过；同一 token 重放失败（一次性）。"""
    client = _client()
    body = _challenge(client)
    token, x = body["token"], _answer(body["token"])

    ok = client.post("/api/probe", json={"captcha_token": token, "captcha_x": x})
    assert ok.status_code == 200, f"正确滑块应通过，实际 {ok.status_code}"
    assert ok.get_json()["probe"] is True

    replay = client.post("/api/probe", json={"captcha_token": token, "captcha_x": x})
    assert replay.status_code == 400, "token 应已被消费，重放必须失败"
    assert replay.get_json()["code"] == "CAPTCHA_REQUIRED"


def test_wrong_x_rejected_and_token_burned():
    """错误 x → 400 + CAPTCHA_REQUIRED，且该 token 立即失效。"""
    client = _client()
    body = _challenge(client)
    token, x = body["token"], _answer(body["token"])

    bad = client.post("/api/probe", json={"captcha_token": token, "captcha_x": x + 40})
    assert bad.status_code == 400
    assert bad.get_json()["code"] == "CAPTCHA_REQUIRED"
    # 失败后即便正确答案也不能再用（防爆破）
    again = client.post("/api/probe", json={"captcha_token": token, "captcha_x": x})
    assert again.status_code == 400


def test_two_step_verify_then_business():
    """两步式：/verify 通过后，同一 token 可用于一次业务请求，之后失效。"""
    client = _client()
    body = _challenge(client)
    token, x = body["token"], _answer(body["token"])

    v = client.post("/api/captcha/verify", json={"captcha_token": token, "captcha_x": x})
    assert v.status_code == 200, f"verify 应 200，实际 {v.status_code}"
    assert v.get_json()["token"] == token

    ok = client.post("/api/probe", json={"captcha_token": token})
    assert ok.status_code == 200, "已解答 token 应能完成业务请求"
    assert client.post("/api/probe", json={"captcha_token": token}).status_code == 400


def test_verify_wrong_x_fails():
    """/verify 收到错误 x 应返回 400。"""
    client = _client()
    body = _challenge(client)
    token, x = body["token"], _answer(body["token"])
    resp = client.post("/api/captcha/verify", json={"captcha_token": token, "captcha_x": x + 99})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "CAPTCHA_REQUIRED"


def test_missing_token_rejected():
    """业务请求不带 captcha 字段 → 400（一律必填）。"""
    client = _client()
    resp = client.post("/api/probe", json={})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "CAPTCHA_REQUIRED"
    assert "人机验证" in body["message"]


def test_expired_token_rejected():
    """TTL 过期后即便 x 正确也拒绝。"""
    import api.captcha as captcha

    client = _client()
    body = _challenge(client)
    token, x = body["token"], _answer(body["token"])
    captcha._store[token]["expires"] = 1.0  # 追溯到过去
    resp = client.post("/api/probe", json={"captcha_token": token, "captcha_x": x})
    assert resp.status_code == 400


def test_ip_binding():
    """挑战绑定 IP：换 IP 提交必须失败；同 IP 成功（各自使用独立挑战，因 token 一次性）。"""
    client = _client()
    a = _challenge(client, xff="1.2.3.4")
    xa = _answer(a["token"])
    bad = client.post("/api/probe", headers={"X-Forwarded-For": "5.6.7.8"},
                      json={"captcha_token": a["token"], "captcha_x": xa})
    assert bad.status_code == 400, "IP 不一致应拒绝"

    b = _challenge(client, xff="1.2.3.4")
    xb = _answer(b["token"])
    ok = client.post("/api/probe", headers={"X-Forwarded-For": "1.2.3.4"},
                     json={"captcha_token": b["token"], "captcha_x": xb})
    assert ok.status_code == 200, "同 IP 应通过"


def test_tolerance_within_range():
    """容差内的偏差应可通过（±tolerance）。"""
    import config

    client = _client()
    body = _challenge(client)
    x = _answer(body["token"])
    resp = client.post("/api/probe", json={"captcha_token": body["token"],
                                            "captcha_x": x + config.CAPTCHA_TOLERANCE})
    assert resp.status_code == 200, "容差内偏差应通过"


def test_disabled_bypasses():
    """CAPTCHA_ENABLED=0 时：挑战返回 enabled=False，业务请求直接放行。"""
    import config
    import api.captcha as captcha

    old = config.CAPTCHA_ENABLED
    config.CAPTCHA_ENABLED = False
    try:
        client = _client()
        ch = client.post("/api/captcha/challenge").get_json()
        assert ch["success"] is True and ch.get("enabled") is False
        assert client.post("/api/probe", json={}).status_code == 200
    finally:
        config.CAPTCHA_ENABLED = old


def test_config_defaults():
    """默认参数：TTL 300s、容差 6px、尺寸 320x180、拼图块 50px。"""
    import config

    assert config.CAPTCHA_TTL_SECONDS == 300
    assert config.CAPTCHA_TOLERANCE == 6
    assert (config.CAPTCHA_WIDTH, config.CAPTCHA_HEIGHT) == (320, 180)
    assert config.CAPTCHA_PIECE == 50


def test_store_pruned_after_expiry():
    """过期记录会在下次创建挑战时被清理。"""
    import api.captcha as captcha

    client = _client()
    body = _challenge(client)
    captcha._store[body["token"]]["expires"] = 1.0
    _challenge(client)  # 触发 _prune_locked
    assert body["token"] not in captcha._store, "过期 token 应被清理"


# ──────────────────────────────────────────────
# 接入范围：11 个目标接口都必须挂上 @captcha_required
# ──────────────────────────────────────────────
USER_FILE = os.path.join(PROJECT_ROOT, "api", "user", "__init__.py")
EMAIL_FILE = os.path.join(PROJECT_ROOT, "api", "email", "__init__.py")

TARGET_ROUTES = [
    (USER_FILE, '@user_bp.route("/login", methods=["POST"])'),
    (USER_FILE, '@user_bp.route("/register", methods=["POST"])'),
    (USER_FILE, '@user_bp.route("/delete", methods=["POST"])'),
    (EMAIL_FILE, '@email_bp.route("/email/send-verify-email", methods=["POST"])'),
    (EMAIL_FILE, '@email_bp.route("/email/send-register-code", methods=["POST"])'),
    (EMAIL_FILE, '@email_bp.route("/email/send-code-reset-password", methods=["POST"])'),
    (EMAIL_FILE, '@email_bp.route("/email/reset-password-by-code", methods=["POST"])'),
    (EMAIL_FILE, '@email_bp.route("/email/send-change-password-code", methods=["POST"])'),
    (EMAIL_FILE, '@email_bp.route("/email/send-change-email-code", methods=["POST"])'),
    (EMAIL_FILE, '@email_bp.route("/email/send-change-email-old-code", methods=["POST"])'),
    (EMAIL_FILE, '@email_bp.route("/email/send-delete-account-code", methods=["POST"])'),
]


def test_target_route_count_is_eleven():
    assert len(TARGET_ROUTES) == 11, "目标接口清单应为 11 个"


def test_all_target_routes_are_decorated():
    """每个目标路由的装饰器块内必须紧随 @captcha_required。"""
    cache = {}
    for path, marker in TARGET_ROUTES:
        if path not in cache:
            with open(path, "r", encoding="utf-8") as f:
                cache[path] = f.read()
        src = cache[path]
        idx = src.find(marker)
        assert idx != -1, f"未找到路由：{marker}（{os.path.basename(path)}）"
        tail = src[idx:idx + 300]
        assert "@captcha_required" in tail, f"{marker} 未挂 @captcha_required"


# ──────────────────────────
# Web 前端接入（源码 + 构建产物）
# ──────────────────────────
WEB_SRC = os.path.join(PROJECT_ROOT, "frontend", "src")
AUTH_VIEW = os.path.join(WEB_SRC, "views", "AuthView.vue")
USER_VIEW = os.path.join(WEB_SRC, "views", "UserView.vue")
SLIDER = os.path.join(WEB_SRC, "components", "SliderCaptcha.vue")
BUILD_AUTH = os.path.join(PROJECT_ROOT, "static", "vue", "auth.js")
BUILD_USERS = os.path.join(PROJECT_ROOT, "static", "vue", "users.js")


def _text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_web_slider_component_calls_captcha_api():
    """滑块组件存在，且调 /challenge 与 /verify，并对外暴露 capture()。"""
    src = _text(SLIDER)
    assert "/api/captcha/challenge" in src, "组件未请求 /api/captcha/challenge"
    assert "/api/captcha/verify" in src, "组件未请求 /api/captcha/verify"
    assert "defineExpose" in src and "capture" in src, "组件未对外暴露 capture()"


def test_web_auth_view_wires_captcha():
    """登录/注册/找回密码授权：引入组件 + 提交带 captcha_token。"""
    src = _text(AUTH_VIEW)
    assert "SliderCaptcha" in src, "AuthView 未引入滑块组件"
    assert "captchaRef.value.capture()" in src, "AuthView 未调用 capture()"
    # 登录 / 注册 / 验证码重置三个受保护分支都要带 captcha_token
    body_src = src[src.find("async function submit()"):]
    assert body_src.count("captcha_token") >= 3, "登录/注册/重置未全部携带 captcha_token"
    # 发码接口（注册 / 找回密码）也要带
    code_src = src[src.find("async function sendCode()"):src.find("async function submit()")]
    assert "captcha_token" in code_src, "发码接口未携带 captcha_token"


def test_web_user_view_wires_captcha():
    """个人资料：发码与注销均带 captcha_token。"""
    src = _text(USER_VIEW)
    assert "SliderCaptcha" in src, "UserView 未引入滑块组件"
    assert "captchaRef.value.capture()" in src, "UserView 未调用 capture()"
    for endpoint in ("/api/email/send-change-password-code",
                     "/api/email/send-change-email-old-code",
                     "/api/email/send-change-email-code",
                     "/api/email/send-delete-account-code"):
        idx = src.find(endpoint)
        assert idx != -1, f"缺少调用：{endpoint}"
        assert "captcha_token" in src[idx:idx + 160], f"{endpoint} 未携带 captcha_token"
    didx = src.find("/api/user/delete")
    assert "captcha_token" in src[:didx], "注销提交未携带 captcha_token"


def test_web_bundle_contains_captcha_calls():
    """构建产物（static/vue）必须已含 captcha 调用（前端已重建）。"""
    root = os.path.join(PROJECT_ROOT, "static", "vue")
    found = False
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".js") and "/api/captcha/challenge" in _text(os.path.join(dirpath, name)):
                found = True
                break
        if found:
            break
    assert found, "构建产物未包含人机验证调用（需重建 Vue 产物）"
    # auth.js / users.js 必须已打包并引用滑块组件
    for path in (BUILD_AUTH, BUILD_USERS):
        assert os.path.isfile(path), f"构建产物缺失：{path}"
        assert "SliderCaptcha" in _text(path), f"{os.path.basename(path)} 未引用滑块组件"


def test_static_version_covers_captcha_build():
    """前端资源已变更，STATIC_VERSION 必须 >= 41。"""
    import config

    assert int(str(config.STATIC_VERSION)) >= 41, \
        "STATIC_VERSION 应 >= 41（Vue 产物已变更）"


if __name__ == "__main__":
    tests = [
        ("test_challenge_payload_shape", test_challenge_payload_shape),
        ("test_direct_one_shot_passes_then_token_burned", test_direct_one_shot_passes_then_token_burned),
        ("test_wrong_x_rejected_and_token_burned", test_wrong_x_rejected_and_token_burned),
        ("test_two_step_verify_then_business", test_two_step_verify_then_business),
        ("test_verify_wrong_x_fails", test_verify_wrong_x_fails),
        ("test_missing_token_rejected", test_missing_token_rejected),
        ("test_expired_token_rejected", test_expired_token_rejected),
        ("test_ip_binding", test_ip_binding),
        ("test_tolerance_within_range", test_tolerance_within_range),
        ("test_disabled_bypasses", test_disabled_bypasses),
        ("test_config_defaults", test_config_defaults),
        ("test_store_pruned_after_expiry", test_store_pruned_after_expiry),
        ("test_target_route_count_is_eleven", test_target_route_count_is_eleven),
        ("test_web_slider_component_calls_captcha_api", test_web_slider_component_calls_captcha_api),
        ("test_web_auth_view_wires_captcha", test_web_auth_view_wires_captcha),
        ("test_web_user_view_wires_captcha", test_web_user_view_wires_captcha),
        ("test_web_bundle_contains_captcha_calls", test_web_bundle_contains_captcha_calls),
        ("test_static_version_covers_captcha_build", test_static_version_covers_captcha_build),
        ("test_all_target_routes_are_decorated", test_all_target_routes_are_decorated),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS  " + name)
        except Exception as e:  # noqa: BLE001
            print("FAIL  %s: %s: %s" % (name, type(e).__name__, e))
            failed += 1
    print("\n%s failed" % failed)
    sys.exit(0 if failed == 0 else 1)
