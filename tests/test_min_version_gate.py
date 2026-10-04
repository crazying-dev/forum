# -*- coding: utf-8 -*-
"""回归：客户端最低版本闸门（版本过低 → 426「版本过低，请更新」）。

规则：
  * 清单顶层 `min_versions` 给出各平台最低版本；`web` 键被忽略；
  * 客户端每个请求携带 `X-Client-Platform` / `X-Client-Version`（旧版从
    `User-Agent: CrForum-Windows/1.3.13` 兼底解析）；
  * 版本号逐段比较（先 a，再 b，再 c，数值比较）；
  * 豁免：非 /api/ 路径、/api/app/*、OPTIONS、无法判断平台（fail-open）。
"""
from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

MANIFEST_PATH = os.path.join(PROJECT_ROOT, "app_releases.json")
AFTERBODY = os.path.join(PROJECT_ROOT, "static", "js", "AfterBody.js")


def _load_manifest():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_manifest_has_min_versions():
    """app_releases.json 顶层必须有 min_versions，且含 windows/android/web。"""
    data = _load_manifest()
    mins = data.get("min_versions")
    assert isinstance(mins, dict), "清单缺少 min_versions 字典"
    for key in ("windows", "android", "web"):
        assert key in mins, f"min_versions 缺少 {key}"
    assert mins["windows"] == "1.3.13", "windows 最低版本应为 1.3.13"
    assert mins["android"] == "1.0.10", "android 最低版本应为 1.0.10"


def test_default_manifest_min_versions_matches_file():
    """内置回退清单的 min_versions 必须与 app_releases.json 一致。"""
    import api.release as rel

    assert rel.DEFAULT_MANIFEST.get("min_versions") == _load_manifest().get("min_versions"), \
        "DEFAULT_MANIFEST 与清单文件的 min_versions 不一致"


def test_min_version_for_skips_web_and_unknown():
    """web / 空 / 未配置平台不校验（返回 None）；windows/android 返回最低版本。"""
    import api.release as rel

    assert rel.min_version_for("windows") == "1.3.13"
    assert rel.min_version_for("ANDROID") == "1.0.10", "平台名应大小写不敏感"
    assert rel.min_version_for("web") is None, "web 必须被忽略"
    assert rel.min_version_for("") is None
    assert rel.min_version_for(None) is None
    assert rel.min_version_for("linux") is None, "未配置的平台不校验"


def test_semver_compares_a_then_b_then_c():
    """逐段数值比较：先 a，再 b，再 c（不是字典序）。"""
    import api.release as rel

    # (版本, 是否应被拦截)，基准 windows 最低 1.3.13
    cases = [
        ("1.3.13", False),   # 等于最低
        ("1.3.14", False),   # 补丁号更大
        ("1.4.0", False),    # b 更大
        ("2.0.0", False),    # a 更大
        ("1.3.100", False),  # 数值比较：100 > 13
        ("1.3.12", True),    # c 更小
        ("1.3.9", True),     # 数值比较：9 < 13（非字典序）
        ("1.2.99", True),    # b 更小（c 再大也没用）
        ("0.9.9", True),     # a 更小
        ("V1.3.12", True),   # 前缀 V 不影响解析
        ("v1.3.12", True),   # 小写 v 同理
        ("", True),          # 平台已知但版本缺失 → 视为 0
    ]
    for version, expect_block in cases:
        got = rel.version_gate_violation("windows", version)
        blocked = got is not None
        assert blocked == expect_block, \
            f"版本 {version!r} 应被拦截={expect_block}，实际={blocked}"


def test_violation_payload_shape():
    """426 响应体必须含 code / message / min_version / download_url。"""
    import api.release as rel

    body = rel.version_gate_violation("windows", "1.3.12")
    assert body is not None
    assert body["success"] is False
    assert body["code"] == "VERSION_TOO_LOW"
    assert body["message"] == "版本过低，请更新"
    assert body["min_version"] == "1.3.13"
    assert body["current"] == "1.3.12"
    assert isinstance(body.get("download_url"), str) and body["download_url"], \
        "应给出最新安装包直链"
    assert body.get("download_page"), "应给出下载页地址"


def test_resolve_client_prefers_headers_over_user_agent():
    """有 X-Client-* 请求头时优先使用，忽略 User-Agent。"""
    import api.release as rel

    platform, version = rel.resolve_client(
        {"X-Client-Platform": "Android", "X-Client-Version": "1.0.10"},
        "CrForum-Windows/1.3.12",
    )
    assert platform == "android", "平台名应归一为小写"
    assert version == "1.0.10"


def test_resolve_client_falls_back_to_user_agent():
    """无请求头时从 User-Agent「CrForum-<平台>/<版本>」兼底解析。"""
    import api.release as rel

    assert rel.resolve_client({}, "CrForum-Windows/1.3.12") == ("windows", "1.3.12")
    assert rel.resolve_client({}, "CrForum-Android/1.0.9") == ("android", "1.0.9")
    # 浏览器 UA → 无法判断 → 放行
    assert rel.resolve_client({}, "Mozilla/5.0 (Windows NT 10.0)") == ("", "")


def test_should_block_request_exemptions():
    """豁免：非 /api/ 路径、/api/app/*、OPTIONS、未知客户端、web 平台。"""
    import api.release as rel

    old = {"X-Client-Platform": "windows", "X-Client-Version": "1.0.0"}
    # 应拦截
    assert rel.should_block_request("GET", "/api/posts", old, "") is not None
    # 非 /api/ 路径不拦
    assert rel.should_block_request("GET", "/Download", old, "") is None
    assert rel.should_block_request("GET", "/static/js/AfterBody.js", old, "") is None
    # /api/app/* 豁免（保证客户端能自助更新）
    assert rel.should_block_request("GET", "/api/app/releases", old, "") is None
    assert rel.should_block_request("GET", "/api/app/check", old, "") is None
    assert rel.should_block_request("GET", "/api/app/mirror/windows/forum_setup.exe", old, "") is None
    # /api/status-log 豁免（运维观测接口，不应被最低版本闸门挡住）
    assert rel.should_block_request("GET", "/api/status-log", old, "") is None
    # OPTIONS 预检不拦
    assert rel.should_block_request("OPTIONS", "/api/posts", old, "") is None
    # 未知客户端放行（fail-open）
    assert rel.should_block_request("GET", "/api/posts", {}, "curl/8.0") is None
    # web 平台忽略
    assert rel.should_block_request("GET", "/api/posts",
                                   {"X-Client-Platform": "web", "X-Client-Version": "0"}, "") is None


def _gated_client():
    """最小 Flask app：接入与 app.py 相同的闸门钩子（不触发 DB / 鉴权）。"""
    from flask import Flask, jsonify, request

    from api.release import should_block_request

    app = Flask(__name__)

    @app.before_request
    def _gate():
        violation = should_block_request(
            request.method, request.path, request.headers,
            request.headers.get("User-Agent", ""),
        )
        if violation:
            resp = jsonify(violation)
            resp.status_code = 426
            return resp
        return None

    @app.route("/api/posts")
    def _posts():
        return jsonify({"success": True})

    @app.route("/api/app/releases")
    def _releases():
        return jsonify({"success": True})

    @app.route("/Download")
    def _download():
        return "ok"

    return app.test_client()


def test_gate_end_to_end_426():
    """端到端：旧版客户端请求 /api/* → 426 + VERSION_TOO_LOW；新版/web/豁免路径放行。"""
    client = _gated_client()

    resp = client.get("/api/posts", headers={"X-Client-Platform": "windows",
                                             "X-Client-Version": "1.3.12"})
    assert resp.status_code == 426, f"旧版 Windows 应被拦，实际 {resp.status_code}"
    body = resp.get_json()
    assert body["code"] == "VERSION_TOO_LOW"
    assert body["message"] == "版本过低，请更新"

    # 当前最低版本 → 放行
    ok = client.get("/api/posts", headers={"X-Client-Platform": "windows",
                                           "X-Client-Version": "1.3.13"})
    assert ok.status_code == 200, f"1.3.13 应放行，实际 {ok.status_code}"

    # Android 低于 1.0.10 → 拦；等于 → 放行
    low_a = client.get("/api/posts", headers={"X-Client-Platform": "android",
                                              "X-Client-Version": "1.0.9"})
    assert low_a.status_code == 426, "Android 1.0.9 应被拦"
    ok_a = client.get("/api/posts", headers={"X-Client-Platform": "android",
                                             "X-Client-Version": "1.0.10"})
    assert ok_a.status_code == 200, "Android 1.0.10 应放行"

    # User-Agent 兼底：旧版 Windows 无请求头也会被拦
    ua = client.get("/api/posts", headers={"User-Agent": "CrForum-Windows/1.3.11"})
    assert ua.status_code == 426, "应能从 User-Agent 识别旧版"

    # 豁免路径：/api/app/* 与页面
    assert client.get("/api/app/releases", headers={"X-Client-Platform": "windows",
                                                    "X-Client-Version": "1.0.0"}).status_code == 200
    assert client.get("/Download", headers={"X-Client-Platform": "windows",
                                            "X-Client-Version": "1.0.0"}).status_code == 200

    # web 平台忽略
    assert client.get("/api/posts", headers={"X-Client-Platform": "web",
                                             "X-Client-Version": "0"}).status_code == 200

    # 未知客户端（无头无 UA）放行
    assert client.get("/api/posts").status_code == 200


def test_release_api_payloads_expose_min_versions():
    """清单接口回传 min_versions；/check 回传 min_version 与 too_low。"""
    from flask import Flask

    import api.release as rel

    app = Flask(__name__)
    app.register_blueprint(rel.release_bp, url_prefix="/api/app")
    client = app.test_client()

    body = client.get("/api/app/releases").get_json()
    assert body["min_versions"]["windows"] == "1.3.13"

    check = client.get("/api/app/check?platform=windows&version=1.3.12").get_json()
    assert check["min_version"] == "1.3.13"
    assert check["too_low"] is True, "1.3.12 低于最低版本，too_low 应为真"

    check2 = client.get("/api/app/check?platform=windows&version=1.3.13").get_json()
    assert check2["too_low"] is False


def test_web_frontend_sends_client_headers():
    """网页端全局请求封装必须携带 X-Client-Platform=web 与版本号。"""
    with open(AFTERBODY, "r", encoding="utf-8") as f:
        js = f.read()
    assert "window.__clientHeaders" in js, "AfterBody.js 缺少 __clientHeaders 封装"
    assert "'X-Client-Platform': 'web'" in js, "网页端未携带 X-Client-Platform"
    assert "'X-Client-Version'" in js, "网页端未携带 X-Client-Version"
    # 全局 apiFetch 必须应用该头
    assert "window.__clientHeaders(), o.headers" in js, "apiFetch 未应用客户端请求头"


def test_static_version_bumped_for_web_headers():
    """AfterBody.js 内容已变，STATIC_VERSION 必须递增以让浏览器重新拉取。"""
    import config

    assert int(str(config.STATIC_VERSION)) >= 40, \
        "STATIC_VERSION 应 >= 40（AfterBody.js 已变更）"


if __name__ == "__main__":
    tests = [
        ("test_manifest_has_min_versions", test_manifest_has_min_versions),
        ("test_default_manifest_min_versions_matches_file",
         test_default_manifest_min_versions_matches_file),
        ("test_min_version_for_skips_web_and_unknown",
         test_min_version_for_skips_web_and_unknown),
        ("test_semver_compares_a_then_b_then_c", test_semver_compares_a_then_b_then_c),
        ("test_violation_payload_shape", test_violation_payload_shape),
        ("test_resolve_client_prefers_headers_over_user_agent",
         test_resolve_client_prefers_headers_over_user_agent),
        ("test_resolve_client_falls_back_to_user_agent",
         test_resolve_client_falls_back_to_user_agent),
        ("test_should_block_request_exemptions", test_should_block_request_exemptions),
        ("test_gate_end_to_end_426", test_gate_end_to_end_426),
        ("test_release_api_payloads_expose_min_versions",
         test_release_api_payloads_expose_min_versions),
        ("test_web_frontend_sends_client_headers", test_web_frontend_sends_client_headers),
        ("test_static_version_bumped_for_web_headers",
         test_static_version_bumped_for_web_headers),
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
